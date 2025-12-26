from __future__ import annotations

import json
import logging
import os
import socket
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt
from langchain_community.utilities import SQLDatabase
from langchain_core.tools import StructuredTool

from config import (
    DEFAULT_USER_ID,
    MQTT_BROKER,
    MQTT_PORT,
    REMINDER_DB_PATH,
    REMINDER_TOPIC,
)
from system_memory import SystemMemoryManager

logger = logging.getLogger("ReminderModule")
logger.setLevel(logging.INFO)


@dataclass
class Reminder:
    id: int
    user_id: str
    content: str
    severity: str
    due_time: Optional[str]
    repeat_rule: Optional[str]
    status: str
    tags: Optional[str]
    created_at: str

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["type"] = "reminder"
        return payload

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Reminder":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            severity=row["severity"],
            due_time=row["due_time"],
            repeat_rule=row["repeat_rule"],
            status=row["status"],
            tags=row["tags"],
            created_at=row["created_at"],
        )


class ReminderMQTTPublisher:
    """负责将提醒信息通过 MQTT 推送给终端。"""

    def __init__(
        self,
        broker: str = MQTT_BROKER,
        port: int = MQTT_PORT,
        topic: str = REMINDER_TOPIC,
    ):
        self.topic = topic
        self.source = os.getenv("REMINDER_SOURCE_ID", socket.gethostname())
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.available = True
        try:
            self.client.connect(broker, port, 60)
            self.client.loop_start()
        except Exception as exc:
            self.available = False
            logger.warning("MQTT 连接失败，改为本地模式: %s", exc)

    def publish(self, reminder: Reminder, event: str) -> None:
        if not self.available:
            return
        payload = {
            "event": event,
            "reminder": reminder.to_payload(),
            "published_at": datetime.utcnow().isoformat(),
            "source": self.source,
        }
        try:
            self.client.publish(self.topic, json.dumps(payload), retain=False)
            logger.info("📣 MQTT 推送提醒: %s", payload)
        except Exception as exc:
            logger.error("MQTT 推送失败: %s", exc)


class ReminderManager:
    """对提醒任务进行 CRUD，并与系统记忆、MQTT 推送打通。"""

    def __init__(
        self,
        db_path: str = REMINDER_DB_PATH,
        enable_mqtt: bool = True,
        memory_manager: Optional[SystemMemoryManager] = None,
    ):
        self.db_path = db_path
        self.memory = memory_manager or SystemMemoryManager()
        self._init_schema()
        self.sql_db = SQLDatabase.from_uri(f"sqlite:///{self.db_path}")
        self.publisher = ReminderMQTTPublisher() if enable_mqtt else None

    # ------------------------------------------------------------------
    # DB 基础
    # ------------------------------------------------------------------
    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    severity TEXT DEFAULT 'medium',
                    due_time TEXT,
                    repeat_rule TEXT,
                    status TEXT DEFAULT 'pending',
                    tags TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reminders_due
                ON reminders (status, due_time)
                """
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_reminder(
        self,
        content: str,
        *,
        user_id: str = DEFAULT_USER_ID,
        severity: str = "medium",
        due_time: Optional[datetime] = None,
        repeat_rule: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Reminder:
        due_str = due_time.isoformat() if isinstance(due_time, datetime) else due_time
        tag_str = ",".join(tags) if tags else None

        with self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO reminders (user_id, content, severity, due_time, repeat_rule, tags)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, content, severity, due_str, repeat_rule, tag_str),
            )
            reminder_id = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()

        reminder = Reminder.from_row(row)
        self.memory.log_reminder_event(user_id, reminder.id, "created", content)
        if self.publisher:
            self.publisher.publish(reminder, event="created")
        return reminder

    def list_reminders(
        self, *, status: Optional[str] = None, user_id: Optional[str] = None
    ) -> List[Reminder]:
        query = "SELECT * FROM reminders WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY COALESCE(due_time, created_at)"

        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [Reminder.from_row(row) for row in rows]

    def update_status(
        self,
        reminder_id: int,
        status: str,
        *,
        note: Optional[str] = None,
        user_id: str = DEFAULT_USER_ID,
        propagate_mqtt: bool = True,
    ) -> Reminder:
        with self._connection() as conn:
            conn.execute(
                "UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id)
            )
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()

        reminder = Reminder.from_row(row)
        self.memory.log_reminder_event(user_id, reminder_id, status, note)
        if self.publisher and propagate_mqtt:
            self.publisher.publish(reminder, event=status)
        return reminder

    def trigger_due_reminders(self, now: Optional[datetime] = None) -> List[Reminder]:
        now = now or datetime.utcnow()
        iso_now = now.isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE status = 'pending' AND due_time IS NOT NULL AND due_time <= ?
                """,
                (iso_now,),
            ).fetchall()
        reminders = [Reminder.from_row(row) for row in rows]
        for reminder in reminders:
            self.update_status(reminder.id, "triggered", user_id=reminder.user_id)
        return reminders

    def get_reminders_by_ids(self, ids: List[int]) -> List[Reminder]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        query = f"SELECT * FROM reminders WHERE id IN ({placeholders})"
        with self._connection() as conn:
            rows = conn.execute(query, ids).fetchall()
        return [Reminder.from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # LangChain Tool 暴露
    # ------------------------------------------------------------------
    def to_tools(self) -> List[StructuredTool]:
        def _create(content: str, due_time: Optional[str] = None) -> str:
            dt = datetime.fromisoformat(due_time) if due_time else None
            reminder = self.create_reminder(content=content, due_time=dt)
            return json.dumps(reminder.to_payload(), ensure_ascii=False)

        def _list(status: Optional[str] = None) -> str:
            reminders = self.list_reminders(status=status)
            return json.dumps([r.to_payload() for r in reminders], ensure_ascii=False)

        def _complete(reminder_id: int) -> str:
            reminder = self.update_status(reminder_id, "completed")
            return json.dumps(reminder.to_payload(), ensure_ascii=False)

        return [
            StructuredTool.from_function(
                _create,
                name="create_health_reminder",
                description="为用户创建提醒，例如补水、测血压等。参数: content(str), due_time(optional ISO8601)",
            ),
            StructuredTool.from_function(
                _list,
                name="list_health_reminders",
                description="查看用户的提醒列表，可根据 status 过滤 (pending/triggered/completed/ignored)",
            ),
            StructuredTool.from_function(
                _complete,
                name="complete_health_reminder",
                description="将提醒设置为 completed 状态，参数 reminder_id(int)",
            ),
        ]

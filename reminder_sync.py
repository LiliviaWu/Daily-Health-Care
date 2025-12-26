from __future__ import annotations

import json
import logging
import os
import socket
from typing import Optional

import paho.mqtt.client as mqtt

from config import DEFAULT_USER_ID, MQTT_BROKER, MQTT_PORT, REMINDER_TOPIC
from reminder_module import ReminderManager

logger = logging.getLogger("ReminderSync")
logger.setLevel(logging.INFO)


class ReminderSync:
    """
    订阅提醒 MQTT 事件，接收远端的状态更新（如 completed），同步到本地 DB。
    """

    def __init__(
        self,
        manager: ReminderManager,
        *,
        broker: str = MQTT_BROKER,
        port: int = MQTT_PORT,
        topic: str = REMINDER_TOPIC,
        source_id: Optional[str] = None,
    ):
        self.manager = manager
        self.broker = broker
        self.port = port
        self.topic = topic
        self.source_id = source_id or os.getenv("REMINDER_SOURCE_ID", socket.gethostname())
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def start(self) -> None:
        """连接并开始监听（非阻塞，内部 loop_start）。"""
        try:
            self.client.connect(self.broker, self.port, 60)
            self.client.loop_start()
            logger.info("ReminderSync 已连接 MQTT，订阅 %s", self.topic)
        except Exception as exc:
            logger.error("ReminderSync 连接失败: %s", exc)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(self.topic)
        else:
            logger.error("ReminderSync 连接失败 code=%s", rc)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            logger.warning("ReminderSync 收到非 JSON 消息，忽略")
            return

        if payload.get("source") == self.source_id:
            return

        event = payload.get("event")
        reminder = payload.get("reminder") or {}
        reminder_id = reminder.get("id")
        status = reminder.get("status") or event
        user_id = reminder.get("user_id") or DEFAULT_USER_ID

        if event in {"completed", "ignored", "pending", "triggered"} and reminder_id:
            try:
                self.manager.update_status(
                    reminder_id,
                    status,
                    user_id=user_id,
                    propagate_mqtt=False,  # 避免回环
                )
                logger.info("📥 同步远端提醒状态 id=%s status=%s", reminder_id, status)
            except Exception as exc:
                logger.error("同步提醒失败 id=%s status=%s: %s", reminder_id, status, exc)
        else:
            logger.debug("忽略事件 %s", event)


def start_reminder_sync(manager: Optional[ReminderManager] = None) -> ReminderSync:
    """
    便捷启动函数：传入已有 manager 或让函数创建一个。
    """
    mgr = manager or ReminderManager()
    sync = ReminderSync(mgr)
    sync.start()
    return sync

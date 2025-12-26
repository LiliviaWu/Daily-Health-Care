from __future__ import annotations

import json
from typing import Any, Dict, Optional

from reminder_module import ReminderManager


def _extract_message_text(raw_message: Any) -> Any:
    """
    尝试从 RAG 返回的 JSON 文本中提取 message 字段。
    非字符串或解析失败时原样返回。
    """
    if not isinstance(raw_message, str):
        return raw_message

    text = raw_message.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # 移除 ```json / ``` 包裹
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "message" in data:
            return data.get("message")
    except Exception:
        pass
    return raw_message


def build_mqtt_payload(
    route_result: Dict[str, Any],
    state: Dict[str, Any],
    reminder_manager: Optional[ReminderManager] = None,
) -> Dict[str, Any]:
    """
    清洗路由结果，去掉 evidence，将 reminder_ids 替换为提醒内容，并补充天气字段。
    """
    payload: Dict[str, Any] = {k: v for k, v in route_result.items() if k != "evidence"}
    payload["message"] = _extract_message_text(route_result.get("message"))

    weather = state.get("weather", {})
    payload["weather"] = {
        "temperature": weather.get("temperature"),
        "humidity": weather.get("humidity"),
        "warnings": weather.get("warnings", []),
    }

    reminder_entries = []
    reminder_ids = route_result.get("reminder_ids") or []
    if reminder_ids:
        manager = reminder_manager or ReminderManager(enable_mqtt=False)
        reminders = manager.get_reminders_by_ids(reminder_ids)
        reminder_entries = [
            {
                "id": r.id,
                "content": r.content,
                "severity": r.severity,
                "due_time": r.due_time,
                "status": r.status,
                "tags": r.tags.split(",") if r.tags else [],
            }
            for r in reminders
        ]

    payload.pop("reminder_ids", None)
    payload["reminders"] = reminder_entries

    return payload

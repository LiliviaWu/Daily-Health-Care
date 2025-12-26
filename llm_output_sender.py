"""
将构建好的 payload 通过 MQTT 发送到 ierg6200/health/llmoutput。

用法:
    python llm_output_sender.py '{"route": "template", "message": "..."}'
    # 或从文件:
    python llm_output_sender.py @payload.json
"""

import json
import random
import sys
from typing import Any, Dict

import paho.mqtt.client as mqtt

from config import LLM_OUTPUT_TOPIC, MQTT_BROKER, MQTT_PORT


def _load_payload(arg: str) -> Dict[str, Any]:
    if arg.startswith("@"):
        path = arg[1:]
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(arg)


def send_llm_output(payload: Dict[str, Any], *, client_id: str | None = None) -> None:
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id or f"llm-output-{random.randint(0, 9999)}",
    )
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    client.publish(LLM_OUTPUT_TOPIC, json.dumps(payload, ensure_ascii=False), retain=False)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python llm_output_sender.py '<json>' 或 python llm_output_sender.py @file.json")
        sys.exit(1)
    payload = _load_payload(sys.argv[1])
    send_llm_output(payload)
    print(f"已发送到 {LLM_OUTPUT_TOPIC}: {payload}")

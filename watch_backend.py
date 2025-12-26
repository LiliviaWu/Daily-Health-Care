# watch_backend.py
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from hko_weather_info import get_hko_weather
from routing_engine import RiskRouter
from user_sensors import get_user_sensors
from mqtt_payload import build_mqtt_payload
from llm_output_sender import send_llm_output
from reminder_sync import start_reminder_sync


# ======== 实时状态：从传感器 + 天气 API 取数 ========
def build_state():
    # 等待传感器线程拉取到最新数据（你原来的逻辑）
    time.sleep(2)
    heart_rate, steps, sleep = get_user_sensors()
    temperature, humidity, warnings = get_hko_weather()

    return {
        "user_id": "user_001",
        "timestamp": datetime.utcnow().isoformat(),
        "weather": {
            "temperature": temperature,
            "humidity": humidity,
            "warnings": warnings,
        },
        "vitals": {"heart_rate": heart_rate, "steps": steps, "sleep": sleep},
        "notes": "自动测试样例（实时数据）",
    }


# ======== Demo 状态： high / medium / low 三个场景 ========
def build_demo_state(scenario: str):
    """
    用你在 main 里写过的 state_high / state_medium / state_low，
    方便前端演示不同风险等级。
    """
    if scenario == "high":
        # 高风险示例
        return {
            "user_id": "user_001",
            "timestamp": datetime.utcnow().isoformat(),
            "weather": {"temperature": 35, "humidity": None, "warnings": ["WHOT"]},
            "vitals": {"heart_rate": 115, "steps": 1800, "sleep": 5.5},
            "notes": "Demo：高温 + 心率高 + 睡眠不足",
        }

    if scenario == "medium":
        # 你之前写的 state_medium 示例
        return {
            "user_id": "user_001",
            "timestamp": datetime.utcnow().isoformat(),
            "weather": {
                "temperature": 32,   # 4 分
                "humidity": 88,
                "warnings": []       # 没有高危警告
            },
            "vitals": {
                "heart_rate": 95,
                "steps": 2000,       # 随便补一个步数
                "sleep": 5.5         # 2 分，总代码 6 => medium
            },
            "notes": "Demo：室外偏热，用户诉说乏力,但今天不需要出门",
        }

    if scenario == "low":
        # 你之前写的 state_low 示例
        return {
            "user_id": "user_001",
            "timestamp": datetime.utcnow().isoformat(),
            "weather": {"temperature": 24, "humidity": None, "warnings": []},
            "vitals": {"heart_rate": 78, "steps": 2500, "sleep": 7.2},
            "notes": "Demo：状态平稳，睡眠充足",
        }

    # 兜底：如果传了奇怪的 scenario，就退回实时数据
    return build_state()


# ======== 初始化你的 router ========
router = RiskRouter()

# ======== FastAPI 实例 ========
app = FastAPI()

# 开发阶段放开 CORS，方便前端本地调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 生产环境记得改成具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ======== 启动时顺便启动 reminder 同步（如果你需要一直收提醒） ========
@app.on_event("startup")
def on_startup():
    # 如果 start_reminder_sync 内部自己起线程/协程，这里调用一次就好
    try:
        start_reminder_sync()
        print("[watch_backend] reminder_sync started.")
    except Exception as e:
        print("[watch_backend] start_reminder_sync failed:", e)


# ======== 核心接口：前端就是调这个 ========
@app.get("/api/watch_state")
def get_watch_state(
    user_id: str = "user_001",
    scenario: str = "live",   # 新增参数：live / high / medium / low
):
    """
    调用方式示例：
      实时数据： http://localhost:8000/api/watch_state?user_id=user_001
      high demo: http://localhost:8000/api/watch_state?user_id=user_001&scenario=high
      low  demo: http://localhost:8000/api/watch_state?user_id=user_001&scenario=low
    """

    # 1. 选择 state 来源：实时 or demo
    if scenario == "live":
        state = build_state()
    else:
        state = build_demo_state(scenario)

    # 2. 调用你的风险路由器
    raw_result = router.route(state)

    # 3. 用你原来的函数构造 payload（就是之前 print 出来的那种）
    output_payload = build_mqtt_payload(raw_result, state)

    # 4. 保持原行为：照常发给 MQTT / 其它下游
    try:
        send_llm_output(output_payload)
    except Exception as e:
        print("[watch_backend] send_llm_output failed:", e)

    # 5. 前端专用结构：一层包起来
    engine_payload = {
        "user_name": "王淑珍",   # TODO：以后可以从用户配置表里查
        "state": state,
        "output": output_payload,
    }

    return engine_payload


if __name__ == "__main__":
    # 启动后端服务 http://localhost:8000
    uvicorn.run(
        "watch_backend:app",   # 文件名.变量名
        host="0.0.0.0",
        port=8000,
        reload=True,           # 开发模式自动重载
    )

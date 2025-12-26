import os

# ============================================================
# 全局配置集中管理，避免在多个模块里重复硬编码常量
# ============================================================

# ---- LLM / Embedding 服务配置 ----
OPENAI_API_KEY = os.getenv(
    "DMX_OPENAI_API_KEY",
    "sk-IjZDUwpFwke4Kque8O2pF7O1PiV0dfP9xdE0Unt4zdFnRsHq",
)
OPENAI_BASE_URL = os.getenv("DMX_OPENAI_BASE_URL", "https://www.dmxapi.cn/v1")
EMBEDDING_MODEL = os.getenv("DMX_EMBED_MODEL", "text-embedding-ada-002")
CHAT_MODEL = os.getenv("DMX_CHAT_MODEL", "gpt-4o-mini")

# ---- 数据与存储路径 ----
PERSON_KB_PATH = os.getenv("PERSON_KB_PATH", "person_basic_info_db")
SYSTEM_MEMORY_PATH = os.getenv("SYSTEM_MEMORY_PATH", "system_memory_db")
REMINDER_DB_PATH = os.getenv("REMINDER_DB_PATH", "reminders.db")
USER_PROFILE_PATH = os.getenv("USER_PROFILE_PATH", "person_basic_info/info.txt")

# ---- MQTT 相关 ----
MQTT_BROKER = os.getenv("HEALTH_MQTT_BROKER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("HEALTH_MQTT_PORT", "1883"))
SENSOR_TOPIC = os.getenv("HEALTH_SENSOR_TOPIC", "ierg6200/health/monitor1")
REMINDER_TOPIC = os.getenv("REMINDER_TOPIC", "ierg6200/health/reminders")
LLM_OUTPUT_TOPIC = os.getenv("LLM_OUTPUT_TOPIC", "ierg6200/health/llmoutput")

# ---- 其它 ----
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "user_001")

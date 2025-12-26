# Daily Health Care Backend (watch_backend.py 启动指引)


## 环境与依赖
- Python 3.10+ 建议
- 主要依赖：`fastapi`、`uvicorn[standard]`、`requests`、`paho-mqtt`。
  安装示例：
  ```bash
  python -m venv .venv
  .\.venv\Scripts\activate
  pip install fastapi "uvicorn[standard]" requests paho-mqtt
  ```
- 可选环境变量（见 `config.py`）：
  - OpenAI 相关：`DMX_OPENAI_API_KEY`、`DMX_OPENAI_BASE_URL`、`DMX_EMBED_MODEL`、`DMX_CHAT_MODEL`
  - MQTT 相关：`HEALTH_MQTT_BROKER`、`HEALTH_MQTT_PORT`、`HEALTH_SENSOR_TOPIC`、`REMINDER_TOPIC`、`LLM_OUTPUT_TOPIC`
  - 其他：`PERSON_KB_PATH`、`SYSTEM_MEMORY_PATH`、`REMINDER_DB_PATH`、`USER_PROFILE_PATH`、`DEFAULT_USER_ID`
  - 如果不设置，将使用 `config.py` 中的默认值（含一个示例 API Key 与公开 MQTT broker）。

## 启动后端
在仓库根目录运行（确保虚拟环境已激活）：
```bash
python watch_backend.py
```
默认监听 `0.0.0.0:8000`，开启 `reload=True` 便于开发。启动时会：
- 初始化 `FastAPI` 应用与 `RiskRouter`
- 自动启动提醒同步（`start_reminder_sync`）
- 开放 CORS 便于本地前端联调

如偏好命令行启动，也可：
```bash
uvicorn watch_backend:app --host 0.0.0.0 --port 8000 --reload
```

## 启动前端（watch_frontend.html）
前置：请先按上文启动后端，保持运行在 `http://localhost:8000`。

1. 在仓库根目录启动一个静态服务器（推荐，避免浏览器对本地文件的限制）：
   ```bash
   python -m http.server 5500
   ```
2. 浏览器打开 `http://localhost:5500/watch_frontend.html`，界面每 10 秒轮询后端 `/api/watch_state`。
3. 如需直接双击打开 `watch_frontend.html` 也可，若浏览器拦截跨域，请改用第 1 步的本地服务器方式。
4. 如果后端地址或端口有变，更改 `watch_frontend.html` 中的 `http://localhost:8000` 为实际后端地址。

## 核心接口
- `GET /api/watch_state`
  - 参数：
    - `user_id`（默认 `user_001`）
    - `scenario`：`live`（实时，从传感器和天气 API 取数）或 `high` / `medium` / `low`（内置 Demo 场景）
  - 示例：
    - 实时：`http://localhost:8000/api/watch_state?user_id=user_001`
    - 高风险 Demo：`http://localhost:8000/api/watch_state?user_id=user_001&scenario=high`
    - 低风险 Demo：`http://localhost:8000/api/watch_state?user_id=user_001&scenario=low`
  - 返回：包含用户状态（传感器 + 天气）与路由决策输出的统一 payload，并会尝试通过 MQTT 发送（`send_llm_output`）。

## 相关模块
- 传感器模拟：`user_sensors.py`
- 天气获取：`hko_weather_info.py`（调用香港天文台 API）
- 路由逻辑：`routing_engine.py`
- MQTT 发送：`llm_output_sender.py`
- 提醒同步：`reminder_sync.py`
- 配置：`config.py`

## 快速自检
- 启动后访问 `http://localhost:8000/docs` 查看自动生成的 Swagger UI。
- 如需仅走 Demo 数据，可将 `scenario` 设为 `high`/`medium`/`low`，无需真实传感器与天气 API。
- 若 MQTT 不可用或未配置，接口仍会返回数据，控制台会打印发送失败信息。

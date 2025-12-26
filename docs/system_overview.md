# 系统总览（基于最新代码）

本文按“输入 → 处理 → 输出”梳理数据流，并标注主要 Topic/模块，便于接入 MQTT 与前端。

# 信息输入

## 传感器信息
- 来源：MQTT Topic `ierg6200/health/monitor1`。
- 载荷示例：
  ```json
  {
    "device_id": "watch_alpha_01",
    "timestamp": 1730198400,
    "metrics": { "heart_rate": 110, "steps": 3200, "sleep": 5.5 }
  }
  ```
- 处理：`user_sensors.HealthMonitor` 后台订阅，缓存最新 `heart_rate/steps/sleep`，对外 `get_user_sensors()` 提供最新值。

## 代办任务的完成
- 来源：MQTT Topic `ierg6200/health/reminders`。
- 载荷示例（远端确认完成）：
  ```json
  {
    "event": "completed",
    "reminder": { "id": 41, "user_id": "user_001", "status": "completed" },
    "source": "mobile_app_1",
    "published_at": 1730198500.123
  }
  ```
- 处理：`reminder_sync.ReminderSync` 订阅该 Topic，调用 `ReminderManager.update_status(..., propagate_mqtt=False)` 同步本地 SQLite，避免回环。

## 天气信息
- 来源：HKO API（`hko_weather_info.get_hko_weather()`），返回 `(temperature, humidity, warnings)`。
- 典型字段：温度（float）、湿度（int）、警告代码数组（如 `["WHOT"]`）。

## 知识库构建
- 脚本：`long_memory_storage.py`（切分 `person_basic_info/` 下资料并存 FAISS）。
- 组成：外部健康知识、用户档案（`person_basic_info/info.txt`）、系统短期记忆（`system_memory_db/`，由 `SystemMemoryManager` 维护）。

# 信息处理

## RiskRouter
- 文件：`routing_engine.py`。
- 评分：`evaluate()` 根据温度/湿度/警告/心率/睡眠打分，level ∈ {low, medium, high}。
- 分流：
  - `route=macro`（high）：`CareMacroEngine` 触发关怀宏，调用 `ReminderManager.create_reminder()` 生成多条提醒（补水、联系家属、睡眠记录等），MQTT 广播。
  - `route=rag`（medium）：`MultiLayerMemory.retrieve()` 取知识/档案/短期记忆，RAG 生成关怀文案；异常则回退规则。
  - `route=template` (low)：模板提示+简单建议，不调用 LLM。
- 记忆：每次路由写入 `SystemMemoryManager` 两条事件：`routing_request`、`routing_result`。

## Reminder 数据库的维护
- 文件：`reminder_module.py`。
- 存储：SQLite（`reminders` 表），字段包含 `id/user_id/content/severity/due_time/status/tags`。
- 操作：
  - `create_reminder()`：写库、写系统记忆、MQTT 推送 `event=created`。
  - `update_status()`：更新状态（pending/triggered/completed/ignored），可选择是否再推 MQTT（`propagate_mqtt`）。
  - `get_reminders_by_ids()`：按 ID 批量取回，供输出 payload 展开文本。
  - `trigger_due_reminders()`：把到期的 pending 标记为 triggered 并推送。
- 同步：`reminder_sync.ReminderSync` 监听远端状态更新，保持本地与远端一致（通过 `source` 字段避免自反弹）。

# 信息输出

## 输出内容解析
- 路由原始结果（示例，高风险）：
  ```json
  {
    "route": "macro",
    "risk_level": "high",
    "message": "🌡️ ...\n😴 ...",
    "reminder_ids": [41, 42]
  }
  ```
- 清洗后发送的 payload（`mqtt_payload.build_mqtt_payload`）：
  ```json
  {
    "route": "macro",
    "risk_level": "high",
    "message": "🌡️ ...\n😴 ...",
    "weather": { "temperature": 35, "humidity": 88, "warnings": ["WHOT"] },
    "reminders": [
      { "id": 41, "content": "...补水...", "severity": "high", "due_time": "...", "status": "pending", "tags": ["heat","hydration"] },
      { "id": 42, "content": "...联系家属...", "severity": "high", "due_time": "...", "status": "pending", "tags": ["family","safety"] }
    ]
  }
  ```
- 发送通道：
  - LLM 输出 / 关怀提示：MQTT Topic `ierg6200/health/llmoutput`（`llm_output_sender.py`）。
  - 提醒生命周期：`ierg6200/health/reminders`，事件 `created/triggered/completed/ignored`。

前端或移动端只需监听 `llmoutput` 获取关怀文案与提醒列表，并在完成任务时向 `reminders` 发送状态更新，即可闭环。 

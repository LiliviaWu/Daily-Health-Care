# 前端联调说明（仅通过 MQTT）

前端无需阅读后台代码或调用 HTTP 接口，所有交互均通过 MQTT 完成。请确保使用 TLS/鉴权策略时与后台保持一致（默认示例使用公共 Broker）。

---

## 1. MQTT 基础配置

| 项目 | 默认值 |
| --- | --- |
| Broker | `broker.emqx.io` |
| Port   | `1883`（无需 TLS） |
| ClientID | 任意唯一字符串（示例：`health-frontend-001`） |
| QoS   | 建议使用 `1`（确保消息至少一次送达） |

可根据需要在前端或中间服务器配置 KeepAlive（默认 60 秒）与自动重连逻辑。

---

## 2. 发送用户传感器数据

**Topic（发布）**：`ierg6200/health/monitor1`

后台订阅该 Topic 并缓存最新心率、步数、睡眠数据。前端或可穿戴设备需要周期性发送如下 JSON（UTF-8 文本）：

```json
{
  "device_id": "watch_alpha_01",
  "timestamp": 1732000000,
  "metrics": {
    "heart_rate": 105,
    "steps": 4200,
    "sleep": 5.3
  }
}
```

- `device_id`：可用硬件 ID 或用户 ID。
- `timestamp`：Unix 时间戳（秒）。
- `metrics` 支持扩展字段，例如 `blood_pressure`、`temperature` 等，后台会忽略未知字段。
- 发送频率可根据设备能力调节（推荐 1~5 分钟一次）。若长时间无数据，后台会沿用旧值。

---

## 3. 接收提醒 & 风险提示

**Topic（订阅）**：`ierg6200/health/reminders`

后台在生成提醒或更新状态时，向该 Topic 发布 JSON，前端只需监听即可。消息字段如下：

```json
{
  "event": "created",            // created / triggered / completed / ignored
  "reminder": {
    "id": 42,
    "user_id": "user_001",
    "content": "晚上 22:00 前完成放松活动",
    "severity": "medium",        // low / medium / high
    "due_time": "2025-11-19T14:00:00+00:00",
    "repeat_rule": null,         // 未来可扩展 cron/ISO8601 重复规则
    "status": "pending",
    "tags": "sleep,routine",
    "created_at": "2025-11-19T06:12:30"
  },
  "published_at": "2025-11-19T06:12:30"
}
```

前端可根据 `event` 和 `reminder.status` 来更新 UI：

| event        | 描述 |
| ------------ | ---- |
| `created`    | 新提醒任务；需要在 UI 中新增一条 |
| `triggered`  | 到期已触发，提示用户立即执行 |
| `completed`  | 用户按时完成，前端可打勾或收起提醒 |
| `ignored`    | 用户忽略或后台标记为未完成，前端可弹出二次提醒 |

如需让用户手动回传 “完成/忽略” 状态，可再定义上行 Topic（例如 `ierg6200/health/reminders/ack`），目前后台默认由服务端逻辑更新。

---

## 4. 调试 & 常见问题

1. **如何模拟设备？**  
   使用 `user_sensor_sending_simulation.py` 或任意 MQTT 客户端，向 `ierg6200/health/monitor1` 发布上文示例 JSON，即可触发后台评估并产生提醒。

2. **如何验证提醒通道？**  
   订阅 `ierg6200/health/reminders`，后台每创建/更新一条提醒都会推送。可通过 CLI（`mosquitto_sub -h broker.emqx.io -t ierg6200/health/reminders -v`）查看。

3. **离线调试**  
   若无法访问外网，可搭建本地 Broker（如 emqx/mosquitto）并通知后台修改 Broker 地址。消息格式保持不变。

4. **消息签名/安全**  
   若需要加密或鉴权，可在 MQTT 层增加用户名/密码或 TLS，或对 payload 加签。当前示例为演示环境，未启用认证。

---

## 5. 快速接入步骤

1. 前端在初始化时连接 MQTT Broker，并订阅 `ierg6200/health/reminders`。
2. 将来自设备或模拟器的测量数据发布到 `ierg6200/health/monitor1`。
3. 在提醒 Topic 上监听 `event`，更新 UI 并引导用户执行任务。
4. 如需额外的用户反馈（例如“用户已完成提醒”），可与后台协商新增上行 Topic；目前只需消费提醒即可。

完成以上步骤，即可实现前端与后台完全通过 MQTT 解耦的交互，不需要触碰任何 Python 代码或 REST 接口。欢迎在需要更多事件类型时继续扩展 Topic 约定。***

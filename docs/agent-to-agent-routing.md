# Agent 与 Agent 经天枢收发（E10-S1 契约）

## 目的

已注册 Agent 可经天枢向另一已注册 Agent 发消息或状态，带唯一 ID、收发方、时间戳；Sub-agent 与主 Agent、对等 Agent 间均走同一套路由与审计契约。

## 能力

- **路由**：天枢根据 `receiver_agent_id` 解析目标 Agent 的收件 Matrix Room（无则自动创建并登记），将消息发往该 Room。
- **审计**：每条消息带 `message_id`、`sender`（agent_id 或 `tianshu`）、`receiver`（agent_id）、`timestamp`。

## 程序化调用

```python
from src.core.agent_routing import send_agent_message

# matrix_client：天枢侧 Matrix 客户端（已 connect）
# sender_agent_id：发送方 Agent ID，None 表示系统/天枢
# receiver_agent_id：接收方 Agent ID，必须已注册
# content：{"body": "文本", "msgtype": "m.text"} 或含 state 等
event_id = await send_agent_message(
    matrix_client,
    sender_agent_id="tianshu-agent-xxx",
    receiver_agent_id="tianshu-agent-yyy",
    content={"body": "hello", "msgtype": "m.text"},
)
```

## HTTP 挂载（可选）

部署时可暴露 `POST /api/v1/agent/send`，请求体示例：

```json
{
  "sender_agent_id": "tianshu-agent-xxx",
  "receiver_agent_id": "tianshu-agent-yyy",
  "content": { "body": "hello", "msgtype": "m.text" }
}
```

服务端从应用上下文取得 `matrix_client` 后调用 `send_agent_message`。

## 接收方 Agent 收消息

- 每个已注册 Agent 对应一个 Matrix Room（见 `src/core/agent_rooms`）。
- 接收方 Agent 需加入该 Room 才能收到事件（天枢创建 Room 后，可邀请 Agent 的 `matrix_id` 或由 Agent 凭 room_id 加入；room_id 可通过后续「协作关系/收件 Room 查询」API 或发现端点获取）。

## 与主从链

主 Agent 与 Sub-agent 间收发使用同一接口；身份与关系中的主从链（E3-S3）仅做审计与归属，路由不区分主从，均按 `receiver_agent_id` 解析 Room。

# E10-S1：Agent 与 Agent 经天枢收发消息与状态
# 已注册 Agent 可解析目标 Agent 身份并路由到对应 Matrix Room；消息带唯一 ID、收发方、时间戳

from typing import Any, Dict, Optional

from src.identity import get_agent
from src.core.agent_rooms import ensure_room_for_agent
from src.core.audit import inject_audit_fields


async def send_agent_message(
    matrix_client,
    sender_agent_id: Optional[str],
    receiver_agent_id: str,
    content: Dict[str, Any],
) -> Optional[str]:
    """
    Agent A 发往 Agent B 的消息/状态经天枢路由到 B 的收件 Room。
    - sender_agent_id: 发送方 Agent ID，可为 None（表示系统/天枢）
    - receiver_agent_id: 接收方 Agent ID，必须已注册
    - content: 消息体，至少含 body；可含 msgtype（默认 m.text 或 tianshu.agent_message）
    返回 Matrix event_id，失败返回 None。
    """
    if not matrix_client:
        return None
    agent_b = get_agent(receiver_agent_id)
    if not agent_b:
        return None
    room_id = await ensure_room_for_agent(receiver_agent_id, matrix_client)
    if not room_id:
        return None
    payload = dict(content)
    if "msgtype" not in payload:
        payload["msgtype"] = "m.text"
    if "body" not in payload:
        payload["body"] = ""
    # 审计字段：sender / receiver 用 agent_id，便于谛听与排障
    payload = inject_audit_fields(
        payload,
        sender=sender_agent_id or "tianshu",
        receiver=receiver_agent_id,
    )
    return await matrix_client._send_custom(room_id, payload)

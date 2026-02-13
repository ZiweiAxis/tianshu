# E5-S1：审批请求投递至渠道
# 审批请求以语义化 payload（approval_request）经 Matrix 投递事件进入天枢；Bridge 消费后调渠道适配层发飞书卡片

from typing import Any, Dict, Optional

from src.config import DELIVERY_ROOM_ID


async def submit_approval_request(
    matrix_client: Any,
    target: Dict[str, Any],
    payload: Dict[str, Any],
    delivery_room_id: Optional[str] = None,
) -> Optional[str]:
    """
    将审批请求投递到飞书指定用户/群。
    target: {"channel": "feishu", "receive_id": "oc_xxx", "receive_id_type": "chat_id"}
    payload: approval_request 语义字段（title, description, source_agent_id, request_id, callback_url 等）
    返回 Matrix event_id，失败返回 None。
    """
    room_id = delivery_room_id or DELIVERY_ROOM_ID
    if not room_id:
        return None
    return await matrix_client.send_delivery(
        room_id=room_id,
        semantic_type="approval_request",
        target=target,
        payload=payload,
        body_summary=payload.get("title") or "审批请求",
    )

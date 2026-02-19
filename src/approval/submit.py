# E5-S1：审批请求投递至渠道
# 审批请求以 Matrix MSC1767 原生卡片消息发送，支持交互按钮

from typing import Any, Dict, Optional

from src.config import DELIVERY_ROOM_ID


async def submit_approval_request(
    matrix_client: Any,
    payload: Dict[str, Any],
    card_id: Optional[str] = None,
    delivery_room_id: Optional[str] = None,
) -> Optional[str]:
    """
    将审批请求作为 Matrix 原生卡片消息发送到房间。
    
    Args:
        matrix_client: Matrix 客户端实例
        payload: approval_request 语义字段（title, description, source_agent_id, request_id, callback_url 等）
        card_id: 卡片唯一标识（用于回调关联），默认使用 request_id
        delivery_room_id: 投递房间 ID，默认使用 DELIVERY_ROOM_ID
    
    Returns:
        Matrix event_id，失败返回 None
    """
    room_id = delivery_room_id or DELIVERY_ROOM_ID
    if not room_id:
        return None
    
    # 使用 card_id 或 payload 中的 request_id
    final_card_id = card_id or payload.get("request_id")
    
    return await matrix_client.send_card(
        room_id=room_id,
        semantic_type="approval_request",
        payload=payload,
        card_id=final_card_id,
    )

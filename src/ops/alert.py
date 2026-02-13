# E8-S3：Owner 收告警/通知
# 约定场景（Agent 离线、触达失败等）产出 alert_notification 语义，经 Matrix 投递推送到 Owner 所在渠道（飞书）

from typing import Any, Dict, Optional

from src.identity.owners import get_owner_channel
from src.config import DELIVERY_ROOM_ID


async def notify_owner_alert(
    matrix_client: Any,
    owner_id: str,
    level: str,
    title: str,
    body: str,
    related_entity_id: Optional[str] = None,
    action_url: Optional[str] = None,
    delivery_room_id: Optional[str] = None,
) -> Optional[str]:
    """
    向指定 Owner 推送告警/通知（语义 alert_notification），经 Matrix 投递到飞书。
    需已通过 set_owner_channel(owner_id, receive_id, receive_id_type) 登记该 Owner 的飞书接收目标。
    返回 Matrix event_id，失败或未登记则返回 None。
    """
    channel = get_owner_channel(owner_id)
    if not channel:
        return None
    room_id = delivery_room_id or DELIVERY_ROOM_ID
    if not room_id:
        return None
    target = {
        "channel": "feishu",
        "receive_id": channel["receive_id"],
        "receive_id_type": channel.get("receive_id_type", "chat_id"),
    }
    payload = {
        "level": level,
        "title": title,
        "body": body,
        "related_entity_id": related_entity_id or "",
        "action_url": action_url or "",
    }
    return await matrix_client.send_delivery(
        room_id=room_id,
        semantic_type="alert_notification",
        target=target,
        payload=payload,
        body_summary=title,
    )

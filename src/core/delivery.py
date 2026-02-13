# E2-S3：出站投递事件格式与解析
# 业务层向 Matrix 发送投递类事件（含语义 payload、目标、渠道），由 Bridge/投递消费者消费

from typing import Any, Dict, Optional, Tuple

# Matrix 中投递事件的 msgtype（自定义）
DELIVERY_MSGTYPE = "tianshu.delivery"

# 语义类型（与架构 6.1 对齐）
SEMANTIC_TYPES = (
    "approval_request",
    "approval_result",
    "dashboard_summary",
    "agent_list",
    "alert_notification",
    "registration_confirm",
    "agent_status",  # E1-S2：Agent 状态（处理中/完成/异常）
    "text",  # 纯文本投递
)


def build_delivery_content(
    semantic_type: str,
    target: Dict[str, Any],
    payload: Dict[str, Any],
    body_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构造可发往 Matrix 的投递事件 content。
    target: { "channel": "feishu", "receive_id": "oc_xxx", "receive_id_type": "chat_id" }
    payload: 语义化字段，由渠道适配层解析。
    """
    content = {
        "msgtype": DELIVERY_MSGTYPE,
        "body": body_summary or "",
        "semantic_type": semantic_type,
        "target": target,
        "payload": payload,
    }
    return content


def is_delivery_event(msgtype: str, content: Dict[str, Any]) -> bool:
    """判断是否为投递类事件。"""
    if msgtype == DELIVERY_MSGTYPE:
        return True
    return (content or {}).get("msgtype") == DELIVERY_MSGTYPE


def parse_delivery_event(content: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """
    解析投递事件 content，返回 (semantic_type, target, payload)；解析失败返回 None。
    """
    if not content or content.get("msgtype") != DELIVERY_MSGTYPE:
        return None
    semantic_type = content.get("semantic_type") or "text"
    target = content.get("target") or {}
    payload = content.get("payload") or {}
    if not target.get("channel") or not target.get("receive_id"):
        return None
    return (semantic_type, target, payload)

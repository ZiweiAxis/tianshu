# E2-S3：出站投递事件格式与解析
# 业务层向 Matrix 发送投递类事件（含语义 payload、目标、渠道），由 Bridge/投递消费者消费
# 支持两种格式：
# 1. tianshu.delivery - 自定义投递格式（用于飞书等平台适配）
# 2. m.card - Matrix MSC1767 原生卡片格式（用于 Matrix 交互卡片）

from typing import Any, Dict, Optional, Tuple

# Matrix 中投递事件的 msgtype（自定义）
DELIVERY_MSGTYPE = "tianshu.delivery"

# Matrix 原生卡片 msgtype
MATRIX_CARD_MSGTYPE = "m.card"
MATRIX_CARD_FORMAT = "org.matrix.msc1767.card"

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


# ========== Matrix 原生卡片支持 ==========

def build_matrix_card_content(
    semantic_type: str,
    payload: Dict[str, Any],
    card_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构建 Matrix MSC1767 原生卡片消息 content。
    
    用于审批请求等需要交互的卡片场景。
    
    Args:
        semantic_type: 语义类型（如 approval_request, approval_result）
        payload: 业务数据
        card_id: 卡片唯一标识（用于回调关联）
    
    Returns:
        Matrix 卡片消息 content，可直接用于 room_send
    """
    from src.matrix.card_builder import (
        build_approval_card,
        build_approval_result_card,
        build_matrix_card,
    )
    
    if semantic_type == "approval_request":
        # 审批请求卡片
        title = payload.get("title", "审批请求")
        description = payload.get("content", payload.get("description", ""))
        cheq_id = payload.get("metadata", {}).get("cheq_id", card_id or "")
        agent_did = payload.get("metadata", {}).get("agent_did")
        operation = payload.get("metadata", {}).get("operation")
        risk_level = payload.get("metadata", {}).get("risk_level")
        expires_at = payload.get("expires_at")
        
        return build_approval_card(
            title=title,
            description=description,
            cheq_id=cheq_id,
            agent_did=agent_did,
            operation=operation,
            risk_level=risk_level,
            expires_at=expires_at,
        )
    
    elif semantic_type == "approval_result":
        # 审批结果卡片
        title = payload.get("title", "审批结果")
        content = payload.get("content", "")
        cheq_id = payload.get("metadata", {}).get("cheq_id", card_id or "")
        status = payload.get("status", "PENDING")
        approved_by = payload.get("approved_by")
        reason = payload.get("reason")
        
        return build_approval_result_card(
            title=title,
            content=content,
            cheq_id=cheq_id,
            status=status,
            approved_by=approved_by,
            reason=reason,
        )
    
    else:
        # 通用卡片
        title = payload.get("title", semantic_type)
        content = payload.get("content", payload.get("description", str(payload)))
        actions = payload.get("actions")
        
        # 转换 actions 格式
        if actions:
            converted_actions = []
            for a in actions:
                if isinstance(a, dict):
                    converted_actions.append({
                        "id": a.get("id", a.get("action_key", "")),
                        "label": a.get("label", "Button"),
                        "style": a.get("style", "secondary"),
                    })
            actions = converted_actions
        
        metadata = payload.get("metadata", {})
        
        return build_matrix_card(
            title=title,
            content=content,
            actions=actions,
            card_id=card_id,
            metadata=metadata,
        )


def is_matrix_card_event(msgtype: str, content: Dict[str, Any]) -> bool:
    """判断是否为 Matrix 原生卡片事件。"""
    if msgtype == MATRIX_CARD_MSGTYPE:
        return True
    return (content or {}).get("msgtype") == MATRIX_CARD_MSGTYPE

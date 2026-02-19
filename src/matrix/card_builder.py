# Matrix 原生卡片构建器 (MSC1767)
# 用于将审批请求等转换为 Matrix 原生卡片消息格式

from typing import Any, Dict, List, Optional


def build_matrix_card(
    title: str,
    content: str,
    actions: Optional[List[Dict[str, Any]]] = None,
    card_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    构建 Matrix MSC1767 原生卡片消息。
    
    Args:
        title: 卡片标题
        content: 卡片内容描述
        actions: 按钮列表 [{"id": "approve", "label": "批准", "style": "primary"}, ...]
        card_id: 卡片唯一标识（用于回调关联）
        metadata: 业务元信息（包含 cheq_id 等）
    
    Returns:
        Matrix 卡片消息 content
    """
    # 构建 HTML 格式的卡片内容
    html_content = _build_card_html(title, content, actions, metadata)
    
    # 构建 body 摘要（纯文本）
    body = _build_card_body(title, content, actions)
    
    card_content = {
        "msgtype": "m.card",
        "body": body,
        "format": "org.matrix.msc1767.card",
        "formatted_body": html_content,
    }
    
    # 如果有 card_id 或 metadata，添加到卡片中
    if card_id:
        card_content["card_id"] = card_id
    if metadata:
        card_content["metadata"] = metadata
    
    return card_content


def _build_card_html(
    title: str,
    content: str,
    actions: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """构建卡片 HTML 内容"""
    # 转义 HTML 特殊字符
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    
    html_parts = [
        "<strong>{}</strong><br/>".format(esc(title)),
        "<p>{}</p>".format(esc(content)),
    ]
    
    # 添加元信息（如果有）
    if metadata:
        cheq_id = metadata.get("cheq_id")
        if cheq_id:
            html_parts.append('<p style="color: gray; font-size: 12px;">ID: {}</p>'.format(esc(str(cheq_id)[:8])))
    
    # 添加按钮
    if actions:
        html_parts.append("<br/>")
        for action in actions:
            action_id = action.get("id", "")
            label = action.get("label", "Button")
            style = action.get("style", "secondary")
            
            # Matrix 按钮使用 data-action 属性来标识点击动作
            # 由于原生卡片不直接支持按钮，我们使用 URL 方案
            # 格式: button://action_id?card_id=xxx
            button_data = "action={}".format(action_id)
            if metadata:
                cheq_id = metadata.get("cheq_id")
                if cheq_id:
                    button_data += "&cheq_id={}".format(cheq_id)
            
            # 根据样式设置按钮颜色
            button_style = _get_button_style(style)
            
            html_parts.append(
                '<a href="button://{}" style="{}">{}</a> '.format(
                    button_data, button_style, esc(label)
                )
            )
    
    return "".join(html_parts)


def _build_card_body(
    title: str,
    content: str,
    actions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """构建纯文本摘要"""
    body_parts = [title, "\n", content]
    
    if actions:
        body_parts.append("\n\n按钮: ")
        labels = [a.get("label", "Button") for a in actions]
        body_parts.append(" | ".join(labels))
    
    return "".join(body_parts)


def _get_button_style(style: str) -> str:
    """获取按钮样式"""
    styles = {
        "primary": "display: inline-block; padding: 8px 16px; background-color: #0078d4; color: white; text-decoration: none; border-radius: 4px; margin-right: 8px;",
        "success": "display: inline-block; padding: 8px 16px; background-color: #107c10; color: white; text-decoration: none; border-radius: 4px; margin-right: 8px;",
        "danger": "display: inline-block; padding: 8px 16px; background-color: #d13438; color: white; text-decoration: none; border-radius: 4px; margin-right: 8px;",
        "secondary": "display: inline-block; padding: 8px 16px; background-color: #edebe9; color: #333; text-decoration: none; border-radius: 4px; margin-right: 8px;",
    }
    return styles.get(style, styles["secondary"])


def build_approval_card(
    title: str,
    description: str,
    cheq_id: str,
    agent_did: Optional[str] = None,
    operation: Optional[str] = None,
    risk_level: Optional[str] = None,
    expires_at: Optional[int] = None,
) -> Dict[str, Any]:
    """
    构建审批请求卡片。
    
    Args:
        title: 卡片标题
        description: 审批描述
        cheq_id: 审批请求 ID
        agent_did: Agent DID
        operation: 操作类型
        risk_level: 风险等级
        expires_at: 过期时间戳（毫秒）
    
    Returns:
        Matrix 卡片消息 content
    """
    # 构建内容
    content_parts = [description]
    
    if agent_did:
        content_parts.append("\n\nAgent: {}".format(agent_did))
    if operation:
        content_parts.append("\n操作: {}".format(operation))
    if risk_level:
        content_parts.append("\n风险等级: {}".format(risk_level))
    if expires_at:
        from datetime import datetime
        exp_time = datetime.fromtimestamp(expires_at / 1000)
        content_parts.append("\n过期时间: {}".format(exp_time.strftime("%Y-%m-%d %H:%M:%S")))
    
    content = "".join(content_parts)
    
    # 构建元信息
    metadata = {
        "cheq_id": cheq_id,
    }
    if agent_did:
        metadata["agent_did"] = agent_did
    if operation:
        metadata["operation"] = operation
    if risk_level:
        metadata["risk_level"] = risk_level
    
    # 构建按钮
    actions = [
        {"id": "approve", "label": "批准", "style": "success"},
        {"id": "reject", "label": "拒绝", "style": "danger"},
    ]
    
    return build_matrix_card(
        title=title,
        content=content,
        actions=actions,
        card_id=cheq_id,
        metadata=metadata,
    )


def build_approval_result_card(
    title: str,
    content: str,
    cheq_id: str,
    status: str,
    approved_by: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构建审批结果卡片。
    
    Args:
        title: 卡片标题
        content: 结果描述
        cheq_id: 审批请求 ID
        status: 状态 (APPROVED/REJECTED/EXPIRED)
        approved_by: 审批人
        reason: 审批理由
    
    Returns:
        Matrix 卡片消息 content
    """
    # 添加状态信息到内容
    content_parts = [content]
    
    status_emoji = {
        "APPROVED": "✅",
        "REJECTED": "❌",
        "EXPIRED": "⏰",
        "CANCELLED": "🚫",
    }
    
    emoji = status_emoji.get(status, "")
    content_parts.insert(0, "{} **{}**".format(emoji, status))
    
    if approved_by:
        content_parts.append("\n审批人: {}".format(approved_by))
    if reason:
        content_parts.append("\n理由: {}".format(reason))
    
    full_content = "".join(content_parts)
    
    metadata = {
        "cheq_id": cheq_id,
        "status": status,
    }
    
    # 审批结果卡片不显示按钮
    return build_matrix_card(
        title=title,
        content=full_content,
        actions=None,
        card_id=cheq_id,
        metadata=metadata,
    )

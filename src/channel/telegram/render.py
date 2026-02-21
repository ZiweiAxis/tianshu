# E2-S4 渠道适配层：语义 → Telegram 消息/按钮
# 将语义化 payload 转换为 Telegram 消息格式

from typing import Any, Callable, Dict, List, Tuple

# 语义类型 → 默认展示文案键（文本回退）
SEMANTIC_DISPLAY_KEYS = {
    "approval_request": ["title", "description"],
    "approval_result": ["request_id", "approved", "comment"],
    "dashboard_summary": ["participant_count", "agent_count", "deliver_rate"],
    "agent_list": ["items", "total"],
    "alert_notification": ["level", "title", "body"],
    "registration_confirm": ["pairing_code", "agent_display_name", "expire_at"],
    "agent_status": ["status", "agent_id", "message"],
    "text": ["text"],
}

# 可扩展：语义类型 -> 渲染函数 (payload -> {"text", "buttons"})
_card_renderers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


def register_telegram_renderer(semantic_type: str, renderer: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """注册某语义类型的 Telegram 消息渲染器。"""
    _card_renderers[semantic_type] = renderer


def _build_buttons_from_actions(actions: List[Dict[str, Any]]) -> List[List[Dict[str, str]]]:
    """将 actions 转换为 Telegram 内联按钮格式。"""
    if not actions:
        return []
    buttons = []
    for action in actions:
        if isinstance(action, dict):
            buttons.append([{
                "text": action.get("label", action.get("label", "Button")),
                "callback_data": action.get("id", action.get("action_key", "action")),
            }])
    return buttons


def _approval_request_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """approval_request → Telegram 消息（带按钮）。"""
    title = payload.get("title") or "审批请求"
    desc = payload.get("description") or ""
    cheq_id = payload.get("metadata", {}).get("cheq_id", "")
    risk_level = payload.get("metadata", {}).get("risk_level", "")
    
    text = f"*{title}*\n\n{desc}"
    if risk_level:
        text += f"\n\n⚠️ *风险等级*: {risk_level}"
    if cheq_id:
        text += f"\n\n`ID: {cheq_id}`"
    
    # 构建按钮
    actions = payload.get("actions", [])
    if not actions and payload.get("callback_url"):
        actions = [
            {"id": "approve", "label": "✅ 批准"},
            {"id": "reject", "label": "❌ 拒绝"},
        ]
    
    buttons = _build_buttons_from_actions(actions)
    
    return {"text": text, "buttons": buttons}


def _approval_result_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """approval_result → Telegram 消息。"""
    title = payload.get("title", "审批结果")
    status = payload.get("status", "PENDING")
    content = payload.get("content", "")
    approved_by = payload.get("approved_by", "")
    reason = payload.get("reason", "")
    cheq_id = payload.get("metadata", {}).get("cheq_id", "")
    
    status_emoji = {
        "APPROVED": "✅",
        "REJECTED": "❌",
        "PENDING": "⏳",
    }.get(status.upper(), "❓")
    
    text = f"*{status_emoji} {title}*\n\n{content}"
    if approved_by:
        text += f"\n\n*审批人*: {approved_by}"
    if reason:
        text += f"\n\n*原因*: {reason}"
    if cheq_id:
        text += f"\n\n`ID: {cheq_id}`"
    
    return {"text": text, "buttons": []}


def _dashboard_summary_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """dashboard_summary → Telegram 消息。"""
    pc = payload.get("participant_count")
    ac = payload.get("agent_count")
    dr = payload.get("deliver_rate")
    
    lines = ["📊 *运维大盘摘要*", ""]
    if pc is not None:
        lines.append(f"• 👥 参与者数: {pc}")
    if ac is not None:
        lines.append(f"• 🤖 Agent 数: {ac}")
    if dr is not None:
        lines.append(f"• 📈 触达率: {dr}")
    
    text = "\n".join(lines) if len(lines) > 2 else "暂无数据"
    return {"text": text, "buttons": []}


def _agent_list_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """agent_list → Telegram 消息。"""
    items = payload.get("items") or []
    total = payload.get("total", len(items))
    
    lines = [f"📋 *名下 Agent 列表* (共 {total} 个)", ""]
    for i, it in enumerate(items[:15], 1):
        name = it.get("name") or it.get("display_id") or it.get("agent_id", "")
        status = "🟢 在线" if it.get("online") else "🔴 离线"
        lines.append(f"{i}. {name} — {status}")
    
    if total > 15:
        lines.append(f"\n… 其余 {total - 15} 个")
    
    text = "\n".join(lines)
    return {"text": text, "buttons": []}


def _alert_notification_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """alert_notification → Telegram 消息。"""
    level = payload.get("level", "info")
    title = payload.get("title", "通知")
    body = payload.get("body", "")
    related = payload.get("related_entity_id", "")
    action_url = payload.get("action_url", "")
    
    emoji = {
        "error": "🔴",
        "critical": "🚨",
        "warning": "⚠️",
        "info": "ℹ️",
    }.get(level, "📢")
    
    text = f"{emoji} *{title}*\n\n{body}"
    if related:
        text += f"\n\n*关联*: `{related}`"
    if action_url:
        text += f"\n\n[查看详情]({action_url})"
    
    return {"text": text, "buttons": []}


def _registration_confirm_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """registration_confirm → Telegram 消息。"""
    code = payload.get("pairing_code", "")
    name = payload.get("agent_display_name", "Agent")
    expire = payload.get("expire_at")
    
    text = f"🔗 *Agent 注册确认*\n\n"
    text += f"*Agent*: {name}\n"
    text += f"*配对码*: `{code}`"
    if expire:
        text += f"\n*过期时间*: <t:{expire}>"
    
    return {"text": text, "buttons": []}


def _agent_status_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """agent_status → Telegram 消息。"""
    status = payload.get("status", "processing")
    msg = payload.get("message", "")
    aid = payload.get("agent_id", "")
    
    emoji = {
        "processing": "⏳",
        "completed": "✅",
        "error": "❌",
        "online": "🟢",
        "offline": "🔴",
    }.get(status, "❓")
    
    text = f"{emoji} *Agent 状态*\n\n*状态*: {status}"
    if aid:
        text += f"\n*Agent ID*: `{aid}`"
    if msg:
        text += f"\n*消息*: {msg}"
    
    return {"text": text, "buttons": []}


# 注册内置渲染器
register_telegram_renderer("approval_request", _approval_request_message)
register_telegram_renderer("approval_result", _approval_result_message)
register_telegram_renderer("dashboard_summary", _dashboard_summary_message)
register_telegram_renderer("agent_list", _agent_list_message)
register_telegram_renderer("alert_notification", _alert_notification_message)
register_telegram_renderer("registration_confirm", _registration_confirm_message)
register_telegram_renderer("agent_status", _agent_status_message)


def semantic_to_telegram_message(semantic_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    将语义化 payload 转为 Telegram 消息格式。
    优先使用已注册的渲染器；否则回退为文本消息。
    返回 {"text": "...", "buttons": [[{...}, ...], ...]}；buttons 可为空列表。
    """
    if semantic_type in _card_renderers:
        return _card_renderers[semantic_type](payload)
    
    # 回退为纯文本
    keys = SEMANTIC_DISPLAY_KEYS.get(semantic_type, ["text", "title", "body"])
    parts = []
    for k in keys:
        v = payload.get(k)
        if v is None:
            continue
        if isinstance(v, (list, dict)):
            parts.append(f"{k}: (见详情)")
        else:
            parts.append(f"{k}: {v}")
    text = "\n".join(parts) if parts else str(payload)[:500]
    return {"text": text, "buttons": []}

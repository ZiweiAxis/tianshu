# E2-S4 渠道适配层：语义 → 飞书消息/卡片
# 至少一种语义类型转为飞书卡片；其余为文本；渲染逻辑可扩展（注册新 renderer）

from typing import Any, Callable, Dict

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

# 可扩展：语义类型 -> 渲染函数 (payload -> {"msg_type", "content"})
_card_renderers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


def register_card_renderer(semantic_type: str, renderer: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """注册某语义类型的卡片渲染器，由前端 Owner 扩展。"""
    _card_renderers[semantic_type] = renderer


def _dashboard_summary_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    """dashboard_summary → 飞书 interactive 卡片。"""
    pc = payload.get("participant_count")
    ac = payload.get("agent_count")
    dr = payload.get("deliver_rate")
    lines = []
    if pc is not None:
        lines.append(f"**参与者数**: {pc}")
    if ac is not None:
        lines.append(f"**Agent 数**: {ac}")
    if dr is not None:
        lines.append(f"**触达率**: {dr}")
    body = "\n".join(lines) if lines else "暂无数据"
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "运维大盘摘要"},
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": body}},
        ],
    }
    return {"msg_type": "interactive", "content": card}


def _approval_request_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    """approval_request → 飞书 interactive 卡片（标题+描述+占位按钮）。"""
    title = payload.get("title") or "审批请求"
    desc = payload.get("description") or ""
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": "orange", "title": {"tag": "plain_text", "content": title}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": desc or "—"}},
        ],
    }
    return {"msg_type": "interactive", "content": card}


def _registration_confirm_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    """E4-S3：配对码确认 → 飞书卡片。"""
    code = payload.get("pairing_code") or ""
    name = payload.get("agent_display_name") or "Agent"
    expire = payload.get("expire_at")
    body = f"**配对码**: `{code}`\n**Agent**: {name}"
    if expire:
        body += f"\n**过期时间**: <t:{expire}>"
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": "green", "title": {"tag": "plain_text", "content": "Agent 注册确认"}},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}}],
    }
    return {"msg_type": "interactive", "content": card}


def _agent_status_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    """E1-S2：Agent 状态（处理中/完成/异常）→ 飞书卡片。"""
    status = payload.get("status") or "processing"
    msg = payload.get("message") or ""
    aid = payload.get("agent_id") or ""
    body = f"**状态**: {status}\n" + (f"**Agent**: {aid}\n" if aid else "") + (msg if msg else "")
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": "blue", "title": {"tag": "plain_text", "content": "Agent 状态"}},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}}],
    }
    return {"msg_type": "interactive", "content": card}


def _agent_list_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    """E8-S1：Agent 列表（Owner 名下）→ 飞书卡片。"""
    items = payload.get("items") or []
    total = payload.get("total", len(items))
    lines = [f"**共 {total} 个 Agent**"]
    for i, it in enumerate(items[:20], 1):
        name = it.get("name") or it.get("display_id") or it.get("agent_id", "")
        status = it.get("status") or ("在线" if it.get("online") else "离线")
        lines.append(f"{i}. {name} — {status}")
    if total > 20:
        lines.append(f"… 其余 {total - 20} 个")
    body = "\n".join(lines)
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": "green", "title": {"tag": "plain_text", "content": "名下 Agent 列表"}},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body}}],
    }
    return {"msg_type": "interactive", "content": card}


def _alert_notification_card(payload: Dict[str, Any]) -> Dict[str, Any]:
    """E8-S3：告警/通知 → 飞书卡片。"""
    level = payload.get("level") or "info"
    title = payload.get("title") or "通知"
    body = payload.get("body") or ""
    related = payload.get("related_entity_id", "")
    action_url = payload.get("action_url", "")
    template = "red" if level in ("error", "critical") else "orange" if level == "warning" else "blue"
    lines = [body]
    if related:
        lines.append(f"**关联**: {related}")
    if action_url:
        lines.append(f"**操作**: <a href=\"{action_url}\">查看</a>")
    card = {
        "config": {"wide_screen_mode": True},
        "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}],
    }
    return {"msg_type": "interactive", "content": card}


# 内置卡片渲染
register_card_renderer("dashboard_summary", _dashboard_summary_card)
register_card_renderer("approval_request", _approval_request_card)
register_card_renderer("registration_confirm", _registration_confirm_card)
register_card_renderer("agent_status", _agent_status_card)
register_card_renderer("agent_list", _agent_list_card)
register_card_renderer("alert_notification", _alert_notification_card)


def semantic_to_feishu_message(semantic_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    将语义化 payload 转为飞书发消息 API 所需格式。
    优先使用已注册的卡片渲染器；否则回退为文本消息。
    返回 {"msg_type": "text"|"interactive", "content": {...}}；interactive 时 content 为卡片 dict。
    """
    if semantic_type in _card_renderers:
        return _card_renderers[semantic_type](payload)
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
    return {"msg_type": "text", "content": {"text": text}}

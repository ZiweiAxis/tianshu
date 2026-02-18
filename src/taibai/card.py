"""太白消息协议 - 太白卡片格式"""
import time
import random
import string
from dataclasses import dataclass, field
from typing import Any

from .event import ClickEvent, parse_click_event


@dataclass
class Card:
    """太白卡片模型"""
    card_id: str         # card-{timestamp}-{random}
    card_type: str       # approval, info, alert, success
    title: str
    content: str
    actions: list = field(default_factory=list)  # [{"id": "approve", "label": "批准"}]
    metadata: dict = field(default_factory=dict)  # trace_id, request_id, agent_id, owner_id


def _generate_card_id() -> str:
    """生成卡片ID"""
    timestamp = int(time.time() * 1000)
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"card-{timestamp}-{random_str}"


def build_approval_card(
    title: str,
    content: str,
    requester: str = "",
    trace_id: str = "",
    request_id: str = "",
    agent_id: str = "",
    owner_id: str = "",
    extra_actions: list = None
) -> Card:
    """构建审批卡片"""
    card_id = _generate_card_id()

    actions = [
        {"id": "approve", "label": "批准"},
        {"id": "reject", "label": "拒绝"}
    ]
    if extra_actions:
        actions.extend(extra_actions)

    metadata = {
        "trace_id": trace_id,
        "request_id": request_id,
        "agent_id": agent_id,
        "owner_id": owner_id,
        "requester": requester
    }

    return Card(
        card_id=card_id,
        card_type="approval",
        title=title,
        content=content,
        actions=actions,
        metadata=metadata
    )


def build_info_card(
    title: str,
    content: str,
    trace_id: str = "",
    **kwargs
) -> Card:
    """构建信息卡片"""
    return Card(
        card_id=_generate_card_id(),
        card_type="info",
        title=title,
        content=content,
        metadata={"trace_id": trace_id, **kwargs}
    )


def build_alert_card(
    title: str,
    content: str,
    trace_id: str = "",
    **kwargs
) -> Card:
    """构建警告卡片"""
    return Card(
        card_id=_generate_card_id(),
        card_type="alert",
        title=title,
        content=content,
        metadata={"trace_id": trace_id, **kwargs}
    )


def build_success_card(
    title: str,
    content: str,
    trace_id: str = "",
    **kwargs
) -> Card:
    """构建成功卡片"""
    return Card(
        card_id=_generate_card_id(),
        card_type="success",
        title=title,
        content=content,
        metadata={"trace_id": trace_id, **kwargs}
    )


def parse_click_event_from_card(card: Card, raw_event: dict) -> ClickEvent:
    """从卡片和原始事件解析点击事件"""
    click_event = parse_click_event(raw_event)
    # 补充卡片信息
    if not click_event.card_id:
        click_event.card_id = card.card_id
    return click_event

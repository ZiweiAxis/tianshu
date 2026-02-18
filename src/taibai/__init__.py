"""太白消息协议 (TaiBai Message Protocol)

T1: 统一点击事件模型
T2: 统一响应接口
T3: 太白卡片格式
"""

from .event import ClickEvent, parse_click_event
from .context import ResponseContext, DefaultResponseContext
from .card import (
    Card,
    build_approval_card,
    build_info_card,
    build_alert_card,
    build_success_card,
    parse_click_event_from_card
)

__all__ = [
    # Event
    "ClickEvent",
    "parse_click_event",
    # Context
    "ResponseContext",
    "DefaultResponseContext",
    # Card
    "Card",
    "build_approval_card",
    "build_info_card",
    "build_alert_card",
    "build_success_card",
    "parse_click_event_from_card"
]

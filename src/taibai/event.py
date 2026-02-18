"""太白消息协议 - 统一点击事件模型"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClickEvent:
    """点击事件模型"""
    action_key: str           # 按钮 ID
    action_value: dict        # 按钮数据
    card_id: str              # 卡片 ID
    user_id: str              # 用户 DID
    timestamp: int            # 时间戳
    metadata: dict = field(default_factory=dict)  # 原始业务信息


def parse_click_event(raw_event: dict) -> ClickEvent:
    """解析原始事件为 ClickEvent"""
    return ClickEvent(
        action_key=raw_event.get("action_key", ""),
        action_value=raw_event.get("action_value", {}),
        card_id=raw_event.get("card_id", ""),
        user_id=raw_event.get("user_id", ""),
        timestamp=raw_event.get("timestamp", 0),
        metadata=raw_event.get("metadata", {})
    )

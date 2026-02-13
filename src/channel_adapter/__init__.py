# 渠道适配层：语义 → 飞书/钉钉卡片（E2-S4）

from src.channel_adapter.feishu_render import (
    register_card_renderer,
    semantic_to_feishu_message,
)

__all__ = ["semantic_to_feishu_message", "register_card_renderer"]

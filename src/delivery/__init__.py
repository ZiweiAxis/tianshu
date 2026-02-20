"""
消息投递模块
"""

from src.delivery.telegram import (
    send_approval_message,
    send_wukong_message,
    handle_callback,
    get_approval_provider,
    get_wukong_provider,
)

__all__ = [
    "send_approval_message",
    "send_wukong_message",
    "handle_callback",
    "get_approval_provider",
    "get_wukong_provider",
]

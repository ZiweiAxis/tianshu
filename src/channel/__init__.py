# Channel 模块 - 统一出口
# 支持多渠道（Telegram, Matrix, Feishu 等）

from channel.base import CallbackProvider, Channel
from channel.registry import ChannelRegistry, get_channel, register_channel
from channel import telegram

__all__ = [
    # Base
    "Channel",
    "CallbackProvider",
    # Registry
    "ChannelRegistry",
    "get_channel",
    "register_channel",
    # Submodules
    "telegram",
]

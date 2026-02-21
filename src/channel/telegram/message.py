"""
Telegram 消息投递模块 - 便捷函数
"""

import logging
from typing import Any, Dict, List, Optional

from channel.telegram.provider import TelegramProvider

logger = logging.getLogger(__name__)

# 审批 Bot Provider
_approval_provider: Optional[TelegramProvider] = None
# 悟空 Bot Provider
_wukong_provider: Optional[TelegramProvider] = None


def get_approval_provider(token: str) -> TelegramProvider:
    """获取审批 Bot Provider"""
    global _approval_provider
    if _approval_provider is None:
        _approval_provider = TelegramProvider(token)
    return _approval_provider


def get_wukong_provider(token: str) -> TelegramProvider:
    """获取悟空 Bot Provider"""
    global _wukong_provider
    if _wukong_provider is None:
        _wukong_provider = TelegramProvider(token)
    return _wukong_provider


async def send_approval_message(
    provider: TelegramProvider,
    chat_id: str,
    title: str,
    description: str,
    request_id: str,
    callback_url: str,
) -> Optional[int]:
    """
    发送审批请求消息
    
    Args:
        provider: Telegram Provider
        chat_id: 用户 Telegram ID
        title: 审批标题
        description: 审批描述
        request_id: 请求 ID
        callback_url: 回调地址
    
    Returns:
        消息 ID
    """
    # 构建按钮
    buttons = [
        [
            {"text": "✅ 批准", "callback_data": f"approve:{request_id}"},
            {"text": "❌ 拒绝", "callback_data": f"reject:{request_id}"},
        ]
    ]
    
    message = f"📋 *审批请求*\n\n*{title}*\n\n{description}"
    
    return await provider.deliver(
        chat_id=chat_id,
        message=message,
        semantic_type="approval_request",
        buttons=buttons,
    )


async def send_wukong_message(
    provider: TelegramProvider,
    chat_id: str,
    text: str,
    buttons: Optional[List[List[Dict[str, str]]]] = None,
) -> Optional[int]:
    """
    发送悟空 Bot 消息
    
    Args:
        provider: Telegram Provider
        chat_id: 用户 Telegram ID
        text: 消息文本
        buttons: 可选按钮
    
    Returns:
        消息 ID
    """
    return await provider.deliver(
        chat_id=chat_id,
        message=text,
        buttons=buttons,
    )


async def handle_callback(
    provider: TelegramProvider,
    callback_query_id: str,
    callback_data: str,
) -> bool:
    """
    处理按钮回调
    
    Args:
        provider: Telegram Provider
        callback_query_id: 回调查询 ID
        callback_data: 回调数据 (approve:xxx 或 reject:xxx)
    
    Returns:
        是否成功
    """
    return await provider.answer_callback(
        callback_query_id=callback_query_id,
        text="处理中...",
        show_alert=False,
    )

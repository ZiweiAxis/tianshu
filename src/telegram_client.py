"""
Telegram 客户端模块
支持 Webhook 和 Long Polling 两种模式
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

import aiohttp

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org"


@dataclass
class TelegramMessage:
    """Telegram 消息结构"""
    message_id: int
    chat_id: int
    user_id: Optional[int] = None
    text: Optional[str] = None
    date: Optional[datetime] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TelegramCallbackQuery:
    """Telegram 回调查询结构"""
    id: str
    chat_id: Optional[int] = None
    message_id: Optional[int] = None
    user_id: Optional[int] = None
    data: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class TelegramUpdate:
    """Telegram Update 对象封装"""
    update_id: int
    message: Optional[TelegramMessage] = None
    callback_query: Optional[TelegramCallbackQuery] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    
    def to_internal_message(self) -> Dict[str, Any]:
        """转换为天枢内部消息格式"""
        msg = self.message
        if msg:
            return {
                "platform": "telegram",
                "chat_id": str(msg.chat_id),
                "user_id": str(msg.user_id) if msg.user_id else None,
                "message_id": msg.message_id,
                "text": msg.text,
                "timestamp": msg.date.isoformat() if msg.date else None,
                "sender": {
                    "first_name": msg.first_name,
                    "last_name": msg.last_name,
                    "username": msg.username,
                },
                "raw": msg.raw,
            }
        return {}


class TelegramClient:
    """
    Telegram Bot API 客户端
    
    支持两种模式：
    1. Long Polling - 通过 getUpdates 获取消息
    2. Webhook - 通过回调接收消息
    
    使用示例：
    ```python
    client = TelegramClient(token=os.getenv("TELEGRAM_BOT_TOKEN"))
    
    # Long Polling 模式
    await client.start_polling()
    
    # 或 Webhook 模式
    await client.set_webhook("https://your-domain.com/webhook")
    
    # 发送消息
    await client.send_message(chat_id=123456789, text="Hello!")
    
    # 处理消息
    @client.on_message
    async def handle_message(update: TelegramUpdate):
        print(f"收到消息: {update.message.text}")
    ```
    """
    
    def __init__(
        self,
        token: Optional[str] = None,
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        """
        初始化 Telegram 客户端
        
        Args:
            token: Bot Token，默认从环境变量 TELEGRAM_BOT_TOKEN 读取
            webhook_url: Webhook URL（可选，用于 Webhook 模式）
            webhook_secret: Webhook 密钥（可选）
        """
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("Token is required. Set TELEGRAM_BOT_TOKEN env or pass token.")
        
        self.api_url = f"{TELEGRAM_API_URL}/bot{self.token}"
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret
        
        # 消息处理器
        self._message_handlers: List[Callable[[TelegramUpdate], Awaitable[Any]]] = []
        self._callback_handlers: List[Callable[[TelegramUpdate], Awaitable[Any]]] = []
        
        # Long Polling 状态
        self._polling = False
        self._polling_task: Optional[asyncio.Task] = None
        self._offset = 0
        
        # 默认请求超时
        self._timeout = aiohttp.ClientTimeout(total=30)

    def on_message(self, func: Callable[[TelegramUpdate], Awaitable[Any]]) -> Callable:
        """装饰器：注册消息处理器"""
        self._message_handlers.append(func)
        return func
    
    def on_callback(self, func: Callable[[TelegramUpdate], Awaitable[Any]]) -> Callable:
        """装饰器：注册回调处理器"""
        self._callback_handlers.append(func)
        return func

    async def _request(
        self, 
        method: str, 
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
    ) -> Dict[str, Any]:
        """发送 API 请求"""
        url = f"{self.api_url}/{method}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, 
                    json=data or {}, 
                    timeout=timeout or self._timeout
                ) as resp:
                    result = await resp.json()
                    if not result.get("ok"):
                        logger.error("Telegram API 错误: %s", result)
                        return {"ok": False, "error": result.get("description", "Unknown error")}
                    return result
        except asyncio.TimeoutError:
            logger.error("Telegram 请求超时: %s", method)
            return {"ok": False, "error": "Request timeout"}
        except Exception as e:
            logger.exception("Telegram 请求异常: %s", e)
            return {"ok": False, "error": str(e)}

    def _parse_message(self, data: Dict[str, Any]) -> Optional[TelegramMessage]:
        """解析消息对象"""
        if not data:
            return None
        
        message = data.get("message", {})
        if not message:
            return None
        
        chat = message.get("chat", {})
        user = message.get("from", {})
        
        date_ts = message.get("date")
        date = None
        if date_ts:
            try:
                date = datetime.fromtimestamp(date_ts)
            except (ValueError, OSError):
                pass
        
        return TelegramMessage(
            message_id=message.get("message_id", 0),
            chat_id=chat.get("id", 0),
            user_id=user.get("id"),
            text=message.get("text") or message.get("caption"),
            date=date,
            first_name=user.get("first_name"),
            last_name=user.get("last_name"),
            username=user.get("username"),
            raw=message,
        )

    def _parse_callback_query(self, data: Dict[str, Any]) -> Optional[TelegramCallbackQuery]:
        """解析回调查询"""
        if not data:
            return None
        
        callback = data.get("callback_query")
        if not callback:
            return None
        
        chat = callback.get("message", {}).get("chat", {})
        user = callback.get("from", {})
        
        return TelegramCallbackQuery(
            id=callback.get("id", ""),
            chat_id=chat.get("id"),
            message_id=callback.get("message", {}).get("message_id"),
            user_id=user.get("id"),
            data=callback.get("data"),
            raw=callback,
        )

    def _parse_update(self, data: Dict[str, Any]) -> TelegramUpdate:
        """解析 Update 对象"""
        return TelegramUpdate(
            update_id=data.get("update_id", 0),
            message=self._parse_message(data),
            callback_query=self._parse_callback_query(data),
            raw=data,
        )

    async def _handle_update(self, update: TelegramUpdate):
        """处理 Update 事件"""
        if update.message:
            for handler in self._message_handlers:
                try:
                    await handler(update)
                except Exception as e:
                    logger.exception("消息处理器异常: %s", e)
        
        if update.callback_query:
            for handler in self._callback_handlers:
                try:
                    await handler(update)
                except Exception as e:
                    logger.exception("回调处理器异常: %s", e)

    # ==================== Long Polling ====================
    
    async def get_updates(
        self, 
        timeout: int = 60,
        allowed_updates: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取更新（Long Polling）
        
        Args:
            timeout: 超时时间（秒）
            allowed_updates: 要接收的更新类型
            
        Returns:
            更新列表
        """
        data = {
            "offset": self._offset,
            "timeout": timeout,
            "allowed_updates": allowed_updates or ["message", "callback_query"],
        }
        
        result = await self._request("getUpdates", data, aiohttp.ClientTimeout(total=timeout + 10))
        
        if result.get("ok"):
            updates = result.get("result", [])
            if updates:
                self._offset = updates[-1].get("update_id", 0) + 1
            return updates
        
        return []

    async def _polling_loop(self):
        """Long Polling 循环"""
        logger.info("开始 Long Polling...")
        
        while self._polling:
            try:
                updates = await self.get_updates()
                
                for update_data in updates:
                    update = self._parse_update(update_data)
                    await self._handle_update(update)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Polling 异常: %s", e)
                await asyncio.sleep(5)  # 等待后重试
        
        logger.info("Long Polling 已停止")

    async def start_polling(self, allowed_updates: Optional[List[str]] = None):
        """
        启动 Long Polling
        
        Args:
            allowed_updates: 要接收的更新类型
        """
        if self._polling:
            logger.warning("Polling 已在运行中")
            return
        
        self._polling = True
        self._polling_task = asyncio.create_task(self._polling_loop())
        logger.info("Long Polling 已启动")

    async def stop_polling(self):
        """停止 Long Polling"""
        if not self._polling:
            return
        
        self._polling = False
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        logger.info("Long Polling 已停止")

    # ==================== Webhook ====================

    async def set_webhook(
        self,
        url: Optional[str] = None,
        secret_token: Optional[str] = None,
        allowed_updates: Optional[List[str]] = None,
    ) -> bool:
        """
        设置 Webhook
        
        Args:
            url: Webhook URL
            secret_token: 密钥（用于验证请求）
            allowed_updates: 要接收的更新类型
            
        Returns:
            是否成功
        """
        url = url or self.webhook_url
        if not url:
            raise ValueError("Webhook URL is required")
        
        data: Dict[str, Any] = {
            "url": url,
            "allowed_updates": allowed_updates or ["message", "callback_query"],
        }
        
        if secret_token:
            data["secret_token"] = secret_token
        elif self.webhook_secret:
            data["secret_token"] = self.webhook_secret
        
        result = await self._request("setWebhook", data)
        
        if result.get("ok"):
            logger.info("Webhook 已设置: %s", url)
        else:
            logger.error("设置 Webhook 失败: %s", result.get("description"))
        
        return result.get("ok", False)

    async def delete_webhook(self, drop_pending_updates: bool = False) -> bool:
        """
        删除 Webhook
        
        Args:
            drop_pending_updates: 是否丢弃待处理的更新
            
        Returns:
            是否成功
        """
        result = await self._request("deleteWebhook", {"drop_pending_updates": drop_pending_updates})
        return result.get("ok", False)

    async def get_webhook_info(self) -> Optional[Dict[str, Any]]:
        """获取 Webhook 信息"""
        result = await self._request("getWebhookInfo")
        if result.get("ok"):
            return result.get("result")
        return None

    async def handle_webhook(self, data: Dict[str, Any]) -> bool:
        """
        处理 Webhook 请求（供外部调用）
        
        Args:
            data: Webhook 请求体（JSON 解析后的字典）
            
        Returns:
            是否成功处理
        """
        try:
            update = self._parse_update(data)
            await self._handle_update(update)
            return True
        except Exception as e:
            logger.exception("处理 Webhook 异常: %s", e)
            return False

    # ==================== 消息发送 ====================

    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        发送文本消息
        
        Args:
            chat_id: 聊天 ID
            text: 消息文本
            parse_mode: 解析模式（Markdown, HTML）
            reply_markup: 回复键盘（内联按钮等）
            reply_to_message_id: 回复的消息 ID
            
        Returns:
            发送成功的消息 ID，失败返回 None
        """
        data: Dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id

        result = await self._request("sendMessage", data)
        
        if result.get("ok"):
            return result["result"]["message_id"]
        return None

    async def send_message_with_buttons(
        self,
        chat_id: Union[int, str],
        text: str,
        buttons: List[List[Dict[str, str]]],
        parse_mode: str = "Markdown",
    ) -> Optional[int]:
        """
        发送带内联按钮的消息
        
        Args:
            chat_id: 聊天 ID
            text: 消息文本
            buttons: 按钮布局 [[{text, callback_data}, ...], ...]
            parse_mode: 解析模式
            
        Returns:
            发送成功的消息 ID
        """
        reply_markup = {"inline_keyboard": buttons}
        return await self.send_message(chat_id, text, parse_mode, reply_markup)

    async def send_photo(
        self,
        chat_id: Union[int, str],
        photo: str,
        caption: Optional[str] = None,
        parse_mode: str = "Markdown",
    ) -> Optional[int]:
        """
        发送图片
        
        Args:
            chat_id: 聊天 ID
            photo: 图片 URL 或 file_id
            caption: 图片说明
            parse_mode: 解析模式
            
        Returns:
            发送成功的消息 ID
        """
        data: Dict[str, Any] = {
            "chat_id": str(chat_id),
            "photo": photo,
        }
        if caption:
            data["caption"] = caption
            data["parse_mode"] = parse_mode

        result = await self._request("sendPhoto", data)
        
        if result.get("ok"):
            return result["result"]["message_id"]
        return None

    # ==================== 消息操作 ====================

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """
        回答回调查询
        
        Args:
            callback_query_id: 回调查询 ID
            text: 显示的文本
            show_alert: 是否显示为 Alert
            
        Returns:
            是否成功
        """
        data: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
        }
        if text:
            data["text"] = text
        if show_alert:
            data["show_alert"] = show_alert

        result = await self._request("answerCallbackQuery", data)
        return result.get("ok", False)

    async def edit_message_text(
        self,
        chat_id: Union[int, str],
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        编辑消息文本
        
        Args:
            chat_id: 聊天 ID
            message_id: 消息 ID
            text: 新文本
            parse_mode: 解析模式
            reply_markup: 新的键盘
            
        Returns:
            是否成功
        """
        data: Dict[str, Any] = {
            "chat_id": str(chat_id),
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = reply_markup

        result = await self._request("editMessageText", data)
        return result.get("ok", False)

    async def delete_message(
        self,
        chat_id: Union[int, str],
        message_id: int,
    ) -> bool:
        """
        删除消息
        
        Args:
            chat_id: 聊天 ID
            message_id: 消息 ID
            
        Returns:
            是否成功
        """
        data = {
            "chat_id": str(chat_id),
            "message_id": message_id,
        }
        result = await self._request("deleteMessage", data)
        return result.get("ok", False)

    # ==================== 用户和聊天 ====================

    async def get_me(self) -> Optional[Dict[str, Any]]:
        """获取 Bot 信息"""
        result = await self._request("getMe")
        if result.get("ok"):
            return result["result"]
        return None

    async def get_chat(self, chat_id: Union[int, str]) -> Optional[Dict[str, Any]]:
        """获取聊天信息"""
        result = await self._request("getChat", {"chat_id": str(chat_id)})
        if result.get("ok"):
            return result["result"]
        return None

    async def get_chat_administrators(
        self, 
        chat_id: Union[int, str]
    ) -> List[Dict[str, Any]]:
        """获取群管理员列表"""
        result = await self._request("getChatAdministrators", {"chat_id": str(chat_id)})
        if result.get("ok"):
            return result.get("result", [])
        return []

    # ==================== 工具方法 ====================

    async def close(self):
        """关闭客户端，清理资源"""
        await self.stop_polling()
        logger.info("Telegram 客户端已关闭")

    def __repr__(self) -> str:
        return f"TelegramClient(token=***{self.token[-4:] if self.token else None})"


# 便捷函数

def create_client(
    token: Optional[str] = None,
    webhook_url: Optional[str] = None,
) -> TelegramClient:
    """
    创建 Telegram 客户端的便捷函数
    
    Args:
        token: Bot Token
        webhook_url: Webhook URL
        
    Returns:
        TelegramClient 实例
    """
    return TelegramClient(token=token, webhook_url=webhook_url)

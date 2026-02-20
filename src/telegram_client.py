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

# 獬豸审批 API 地址
XIEZHI_API_BASE = os.getenv("XIEZHI_API_BASE", os.getenv("DITING_CHAIN_URL", "http://localhost:8081/chain").replace("/chain", ""))


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
    # 群组/频道扩展字段
    chat_type: Optional[str] = None  # "private", "group", "supergroup", "channel"
    is_group: bool = False
    is_channel: bool = False
    is_command: bool = False
    command: Optional[str] = None
    command_args: Optional[List[str]] = None
    reply_to_message: Optional[Dict[str, Any]] = None
    mentions: List[int] = field(default_factory=list)  # 被 @ 的用户 ID
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
    channel_post: Optional[TelegramMessage] = None  # 频道消息
    edited_message: Optional[TelegramMessage] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_group_message(self) -> bool:
        """是否群组消息"""
        msg = self.message
        return msg is not None and msg.is_group
    
    @property
    def is_channel_message(self) -> bool:
        """是否频道消息"""
        msg = self.channel_post or self.message
        return msg is not None and msg.is_channel
    
    @property
    def is_command(self) -> bool:
        """是否命令消息"""
        msg = self.message
        return msg is not None and msg.is_command
    
    def to_internal_message(self) -> Dict[str, Any]:
        """转换为天枢内部消息格式"""
        msg = self.message or self.channel_post
        if msg:
            return {
                "platform": "telegram",
                "chat_id": str(msg.chat_id),
                "user_id": str(msg.user_id) if msg.user_id else None,
                "message_id": msg.message_id,
                "text": msg.text,
                "timestamp": msg.date.isoformat() if msg.date else None,
                "chat_type": msg.chat_type,
                "is_group": msg.is_group,
                "is_channel": msg.is_channel,
                "is_command": msg.is_command,
                "command": msg.command,
                "command_args": msg.command_args,
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
        
        # 审批回调
        self._approval_callback: Optional[Callable[[str, str, bool], Awaitable[Any]]] = None
        
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

    def set_approval_callback(
        self,
        callback: Callable[[str, str, bool], Awaitable[Any]]
    ):
        """
        设置审批回调函数
        
        Args:
            callback: 回调函数，签名: async def callback(query_id: str, request_id: str, approved: bool)
        """
        self._approval_callback = callback

    async def _call_xiezhi_approval_api(
        self,
        request_id: str,
        approved: bool,
    ) -> bool:
        """
        调用獬豸审批 API
        
        Args:
            request_id: 审批请求 ID (cheq_id)
            approved: 是否批准
            
        Returns:
            是否成功
        """
        url = f"{XIEZHI_API_BASE}/cheq/approve?id={request_id}&approved={'true' if approved else 'false'}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        logger.info("獬豸审批 API 调用成功: request_id=%s, approved=%s", request_id, approved)
                        return True
                    else:
                        logger.error("獬豸审批 API 调用失败: status=%s", resp.status)
                        return False
        except Exception as e:
            logger.exception("调用獬豸审批 API 异常: %s", e)
            return False

    async def _handle_approval_callback(
        self,
        query_id: str,
        callback_data: str,
    ) -> str:
        """
        处理审批回调（批准/拒绝按钮）
        
        Args:
            query_id: 回调查询 ID
            callback_data: 回调数据，格式: "approve:request_id" 或 "reject:request_id"
            
        Returns:
            显示给用户的反馈文本
        """
        try:
            parts = callback_data.split(":", 1)
            if len(parts) != 2:
                return "无效的回调数据"
            
            action, request_id = parts[0], parts[1]
            
            if action not in ("approve", "reject"):
                return "未知的操作类型"
            
            approved = (action == "approve")
            
            # 调用獬豸审批 API
            api_success = await self._call_xiezhi_approval_api(request_id, approved)
            
            # 如果有自定义回调，也调用它
            if self._approval_callback:
                try:
                    await self._approval_callback(query_id, request_id, approved)
                except Exception as e:
                    logger.exception("审批回调函数执行异常: %s", e)
            
            if api_success:
                return "✅ 已批准" if approved else "❌ 已拒绝"
            else:
                return "⚠️ 审批处理失败，请稍后重试"
                
        except Exception as e:
            logger.exception("处理审批回调异常: %s", e)
            return "⚠️ 处理异常"

    async def _process_approval_async(self, query_id: str, callback_data: str) -> None:
        """
        异步处理审批回调
        
        Args:
            query_id: 回调查询 ID
            callback_data: 回调数据，格式: "approve:request_id" 或 "reject:request_id"
        """
        try:
            # 调用处理逻辑获取结果
            feedback = await self._handle_approval_callback(query_id, callback_data)
            
            # 可选：通过发送消息更新用户最终结果
            # 注意：answer_callback_query 已经有响应，这里可以记录日志
            logger.info("审批处理完成: query_id=%s, result=%s", query_id, feedback)
            
        except Exception as e:
            logger.exception("异步审批处理异常: %s", e)

    async def _request(
        self, 
        method: str, 
        data: Optional[Dict[str, Any]] = None,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        retry: int = 3,
    ) -> Dict[str, Any]:
        """发送 API 请求，带重试机制"""
        url = f"{self.api_url}/{method}"
        
        for attempt in range(retry):
            try:
                async with aiohttp.ClientSession(trust_env=True) as session:
                    async with session.post(
                        url, 
                        json=data or {}, 
                        timeout=timeout or self._timeout
                    ) as resp:
                        result = await resp.json()
                        if not result.get("ok"):
                            # 限流错误，等待后重试
                            if result.get("error_code") == 429:
                                wait_time = int(result.get("parameters", {}).get("retry_after", 5))
                                logger.warning(f"Telegram 限流，等待 {wait_time} 秒后重试...")
                                await asyncio.sleep(wait_time)
                                continue
                            logger.error("Telegram API 错误: %s", result)
                            return {"ok": False, "error": result.get("description", "Unknown error")}
                        return result
            except asyncio.TimeoutError:
                logger.warning(f"Telegram 请求超时 (尝试 {attempt + 1}/{retry}): {method}")
                if attempt < retry - 1:
                    await asyncio.sleep(1)  # 等待后重试
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"Telegram 连接错误 (尝试 {attempt + 1}/{retry}): {e}")
                if attempt < retry - 1:
                    await asyncio.sleep(2)  # 等待后重试
            except Exception as e:
                logger.exception("Telegram 请求异常: %s", e)
                return {"ok": False, "error": str(e)}
        
        return {"ok": False, "error": f"请求失败，已重试 {retry} 次"}

    def _parse_message(self, data: Dict[str, Any], is_channel: bool = False) -> Optional[TelegramMessage]:
        """解析消息对象"""
        if not data:
            return None
        
        message = data.get("message", {}) or data
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
        
        # 识别聊天类型
        chat_type = chat.get("type", "private")
        is_group = chat_type in ("group", "supergroup")
        is_channel = is_channel or chat_type == "channel"
        
        # 解析命令和 @mention
        command = None
        command_args = []
        is_command = False
        mentions = []
        
        text = message.get("text", "")
        entities = message.get("entities", [])
        
        for ent in entities:
            ent_type = ent.get("type")
            if ent_type == "bot_command":
                is_command = True
                # 解析命令和参数
                offset = ent.get("offset", 0)
                length = ent.get("length", 0)
                if text and offset < len(text):
                    cmd_text = text[offset:offset + length]
                    if "/" in cmd_text:
                        parts = cmd_text[1:].split("@", 1)  # /start@botname
                        command = parts[0]
                        if len(parts) > 1:
                            command_args = [parts[1]]
            elif ent_type == "mention":
                # @mention - 获取用户名
                offset = ent.get("offset", 0)
                length = ent.get("length", 0)
                # 这里只能获取到名字，user_id 需要额外查询
            elif ent_type == "text_mention":
                # 带有用户 ID 的 mention
                mentioned_user = ent.get("user", {})
                if mentioned_user.get("id"):
                    mentions.append(mentioned_user["id"])
        
        # 检查消息文本是否以命令开头（fallback）
        if text and text.startswith("/") and not is_command:
            parts = text[1:].split(" ", 1)
            cmd = parts[0].split("@")[0]
            if cmd.isalpha() or cmd.isalnum():
                is_command = True
                command = cmd
                if len(parts) > 1:
                    command_args = parts[1].split()
        
        # 解析回复消息
        reply_to_message = message.get("reply_to_message")
        
        return TelegramMessage(
            message_id=message.get("message_id", 0),
            chat_id=chat.get("id", 0),
            user_id=user.get("id"),
            text=message.get("text") or message.get("caption"),
            date=date,
            first_name=user.get("first_name"),
            last_name=user.get("last_name"),
            username=user.get("username"),
            chat_type=chat_type,
            is_group=is_group,
            is_channel=is_channel,
            is_command=is_command,
            command=command,
            command_args=command_args,
            mentions=mentions,
            reply_to_message=reply_to_message,
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
        # 频道消息 (channel_post)
        channel_post = None
        if "channel_post" in data:
            channel_post = self._parse_message(data, is_channel=True)
        
        # 编辑的消息 (edited_message)
        edited_message = None
        if "edited_message" in data:
            edited_message = self._parse_message(data.get("edited_message", {}))
        
        # 新成员加入 (new_chat_members)
        # 成员离开 (left_chat_member)
        # 群组标题更改 (new_chat_title)
        # 群组图片更改 (new_chat_photo)
        # 群组删除 (group_chat_created, supergroup_chat_created, migrate_to_chat_id, migrate_from_chat_id)
        
        return TelegramUpdate(
            update_id=data.get("update_id", 0),
            message=self._parse_message(data),
            callback_query=self._parse_callback_query(data),
            channel_post=channel_post,
            edited_message=edited_message,
            raw=data,
        )

    async def _handle_update(self, update: TelegramUpdate):
        """处理 Update 事件"""
        # 处理普通消息
        if update.message:
            for handler in self._message_handlers:
                try:
                    await handler(update)
                except Exception as e:
                    logger.exception("消息处理器异常: %s", e)
        
        # 处理频道消息
        if update.channel_post:
            for handler in self._message_handlers:
                try:
                    await handler(update)
                except Exception as e:
                    logger.exception("频道消息处理器异常: %s", e)
        
        # 处理编辑消息
        if update.edited_message:
            # 创建编辑消息的 Update 副本
            edited_update = TelegramUpdate(
                update_id=update.update_id,
                message=update.edited_message,
                raw=update.raw,
            )
            for handler in self._message_handlers:
                try:
                    await handler(edited_update)
                except Exception as e:
                    logger.exception("编辑消息处理器异常: %s", e)
        
        # 处理回调查询
        if update.callback_query:
            callback = update.callback_query
            callback_data = callback.data
            
            # 自动处理审批回调（approve:xxx 或 reject:xxx）
            if callback_data and (callback_data.startswith("approve:") or callback_data.startswith("reject:")):
                # 1. 立即响应用户，不等待后续处理
                await self.answer_callback_query(callback.id, "⏳ 处理中...", show_alert=False)
                
                # 2. 异步处理审批，不阻塞轮询循环
                asyncio.create_task(self._process_approval_async(callback.id, callback_data))
            else:
                # 处理其他回调
                for handler in self._callback_handlers:
                    try:
                        await handler(update)
                    except Exception as e:
                        logger.exception("回调处理器异常: %s", e)

    async def check_proxy_health(self) -> bool:
        """
        检查代理/Telegram 连接是否可用
        
        Returns:
            连接是否可用
        """
        try:
            me = await self.get_me()
            return me is not None
        except Exception as e:
            logger.warning("代理健康检查失败: %s", e)
            return False

    async def _ensure_proxy_connection(self):
        """
        确保代理连接有效，如果不可用则尝试重新连接
        
        通过重置 offset 来触发新的连接尝试
        """
        logger.warning("代理不可用，尝试重新连接...")
        
        # 重置 offset 以确保获取最新的更新
        self._offset = 0
        
        # 等待一小段时间后重试
        await asyncio.sleep(2)
        
        # 再次检查
        if await self.check_proxy_health():
            logger.info("代理连接已恢复")
        else:
            logger.error("代理重连失败")

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
        if allowed_updates is None:
            # 默认接收所有常见更新类型
            allowed_updates = [
                "message", 
                "callback_query", 
                "channel_post",
                "edited_message",
                "new_chat_members",
                "left_chat_member",
                "new_chat_title",
                "new_chat_photo",
                "group_chat_created",
                "supergroup_chat_created",
                "migrate_to_chat_id",
                "migrate_from_chat_id",
            ]
        
        data = {
            "offset": self._offset,
            "timeout": timeout,
            "allowed_updates": allowed_updates,
        }
        
        result = await self._request("getUpdates", data, aiohttp.ClientTimeout(total=timeout + 10))
        
        if result.get("ok"):
            updates = result.get("result", [])
            if updates:
                self._offset = updates[-1].get("update_id", 0) + 1
            return updates
        
        return []

    async def _polling_loop(self):
        """Long Polling 循环，带错误处理和退避，以及代理健康检查"""
        logger.info("开始 Long Polling...")
        
        backoff = 1  # 初始等待秒数
        max_backoff = 30  # 最大等待秒数
        health_check_interval = 60  # 每60秒检查一次代理健康状态
        last_health_check = 0
        
        while self._polling:
            try:
                # 定期检查代理健康状态
                current_time = asyncio.get_event_loop().time()
                if current_time - last_health_check > health_check_interval:
                    last_health_check = current_time
                    if not await self.check_proxy_health():
                        logger.warning("轮询中发现代理不可用，尝试重连...")
                        await self._ensure_proxy_connection()
                
                updates = await self.get_updates()
                
                # 成功获取更新，重置退避
                if updates:
                    backoff = 1
                
                for update_data in updates:
                    update = self._parse_update(update_data)
                    await self._handle_update(update)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Polling 异常: {e}, {backoff}秒后重试...")
                await asyncio.sleep(backoff)
                # 指数退避
                backoff = min(backoff * 2, max_backoff)
        
        logger.info("Long Polling 已停止")

    async def start_polling(
        self,
        callback: Optional[Callable[[str, str, bool], Awaitable[Any]]] = None,
        allowed_updates: Optional[List[str]] = None,
    ):
        """
        启动 Long Polling
        
        Args:
            callback: 审批回调函数，签名: async def callback(query_id, request_id, approved)
                     当用户点击批准/拒绝按钮时调用
            allowed_updates: 要接收的更新类型
        """
        if self._polling:
            logger.warning("Polling 已在运行中")
            return
        
        # 设置审批回调
        if callback:
            self.set_approval_callback(callback)
        
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

    async def get_chat_member_count(
        self, 
        chat_id: Union[int, str]
    ) -> Optional[int]:
        """获取群组成员数量"""
        result = await self._request("getChatMemberCount", {"chat_id": str(chat_id)})
        if result.get("ok"):
            return result.get("result")
        return None

    async def get_chat_member(
        self, 
        chat_id: Union[int, str],
        user_id: int,
    ) -> Optional[Dict[str, Any]]:
        """获取群组成员信息"""
        result = await self._request("getChatMember", {
            "chat_id": str(chat_id),
            "user_id": user_id,
        })
        if result.get("ok"):
            return result.get("result")
        return None

    async def is_bot_admin(
        self, 
        chat_id: Union[int, str]
    ) -> bool:
        """检查 Bot 是否为群管理员"""
        me = await self.get_me()
        if not me:
            return False
        
        bot_user_id = me.get("id")
        administrators = await self.get_chat_administrators(chat_id)
        
        for admin in administrators:
            if admin.get("user", {}).get("id") == bot_user_id:
                return True
        return False

    async def can_bot_send_messages(
        self, 
        chat_id: Union[int, str]
    ) -> bool:
        """检查 Bot 是否有发送消息的权限"""
        me = await self.get_me()
        if not me:
            return False
        
        bot_user_id = me.get("id")
        member = await self.get_chat_member(chat_id, bot_user_id)
        
        if not member:
            return False
        
        # 检查成员状态
        status = member.get("status")
        if status in ("administrator", "creator"):
            return True
        
        # 检查具体权限
        if status == "member":
            # 检查 can_send_messages 权限
            return member.get("can_send_messages", True)
        
        return False

    # ==================== 频道消息 ====================

    async def send_channel_message(
        self,
        channel_id: Union[int, str],
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """
        发送频道消息
        
        Args:
            channel_id: 频道 ID (格式: @channel_username 或 -1001234567890)
            text: 消息文本
            parse_mode: 解析模式
            reply_markup: 回复键盘
            
        Returns:
            发送成功的消息 ID
        """
        return await self.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )

    async def forward_message(
        self,
        chat_id: Union[int, str],
        from_chat_id: Union[int, str],
        message_id: int,
    ) -> Optional[int]:
        """
        转发消息
        
        Args:
            chat_id: 目标聊天 ID
            from_chat_id: 源聊天 ID
            message_id: 源消息 ID
            
        Returns:
            新消息 ID
        """
        data = {
            "chat_id": str(chat_id),
            "from_chat_id": str(from_chat_id),
            "message_id": message_id,
        }
        result = await self._request("forwardMessage", data)
        if result.get("ok"):
            return result["result"]["message_id"]
        return None

    # ==================== 群组事件 ====================

    def parse_chat_event(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        解析群组事件（成员加入/离开等）
        
        Args:
            data: Telegram Update 原始数据
            
        Returns:
            事件信息 dict，包含:
            - event_type: "member_joined", "member_left", "title_changed", etc.
            - chat_id: 群组 ID
            - user_id: 触发事件的用户 ID
            - user_name: 用户名称
            - raw: 原始数据
        """
        event = None
        
        # 新成员加入
        if "message" in data:
            msg = data["message"]
            chat = msg.get("chat", {})
            
            if "new_chat_members" in msg:
                members = msg["new_chat_members"]
                for user in members:
                    event = {
                        "event_type": "member_joined",
                        "chat_id": chat.get("id"),
                        "chat_type": chat.get("type"),
                        "user_id": user.get("id"),
                        "user_name": self._format_user_name(user),
                        "user": user,
                        "raw": msg,
                    }
            
            # 成员离开
            elif "left_chat_member" in msg:
                user = msg["left_chat_member"]
                event = {
                    "event_type": "member_left",
                    "chat_id": chat.get("id"),
                    "chat_type": chat.get("type"),
                    "user_id": user.get("id"),
                    "user_name": self._format_user_name(user),
                    "user": user,
                    "raw": msg,
                }
            
            # 群组标题更改
            elif "new_chat_title" in msg:
                event = {
                    "event_type": "title_changed",
                    "chat_id": chat.get("id"),
                    "chat_type": chat.get("type"),
                    "old_title": None,  # 需要对比
                    "new_title": msg.get("new_chat_title"),
                    "raw": msg,
                }
            
            # 群组图片更改
            elif "new_chat_photo" in msg:
                event = {
                    "event_type": "photo_changed",
                    "chat_id": chat.get("id"),
                    "chat_type": chat.get("type"),
                    "raw": msg,
                }
            
            # 群组创建
            elif "group_chat_created" in msg:
                event = {
                    "event_type": "group_created",
                    "chat_id": chat.get("id"),
                    "chat_type": chat.get("type"),
                    "raw": msg,
                }
            
            elif "supergroup_chat_created" in msg:
                event = {
                    "event_type": "supergroup_created",
                    "chat_id": chat.get("id"),
                    "chat_type": chat.get("type"),
                    "raw": msg,
                }
            
            # 迁移
            elif "migrate_to_chat_id" in msg:
                event = {
                    "event_type": "migrated_to_supergroup",
                    "chat_id": chat.get("id"),
                    "new_chat_id": msg.get("migrate_to_chat_id"),
                    "raw": msg,
                }
            
            elif "migrate_from_chat_id" in msg:
                event = {
                    "event_type": "migrated_from_group",
                    "chat_id": msg.get("migrate_from_chat_id"),
                    "new_chat_id": chat.get("id"),
                    "raw": msg,
                }
        
        return event

    def _format_user_name(self, user: Dict[str, Any]) -> str:
        """格式化用户名"""
        if not user:
            return "Unknown"
        if user.get("username"):
            return f"@{user['username']}"
        name = ""
        if user.get("first_name"):
            name = user["first_name"]
        if user.get("last_name"):
            name += " " + user["last_name"]
        return name or "Unknown"

    # ==================== 命令处理 ====================

    async def handle_command(
        self,
        update: TelegramUpdate,
        commands: Dict[str, Callable],
    ) -> Optional[Any]:
        """
        处理命令消息
        
        Args:
            update: Telegram Update
            commands: 命令字典 {"start": handler, "help": handler, ...}
            
        Returns:
            处理结果
        """
        msg = update.message
        if not msg or not msg.is_command:
            return None
        
        command = msg.command
        if command in commands:
            handler = commands[command]
            try:
                return await handler(update, msg.command_args or [])
            except Exception as e:
                logger.exception(f"命令处理器异常 /{command}: {e}")
        
        return None

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

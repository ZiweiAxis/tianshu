# Telegram 消息格式转换模块
# 实现天枢内部消息格式与 Telegram 消息格式之间的转换

from typing import Any, Dict, List, Optional, Union


class TelegramConverter:
    """Telegram 与天枢内部消息格式转换器。"""

    def __init__(self, parse_mode: str = "Markdown"):
        """
        初始化转换器。
        
        Args:
            parse_mode: 默认解析模式，可选 "Markdown" 或 "HTML"
        """
        self.parse_mode = parse_mode

    # ==================== Telegram → 天枢 ====================

    def to_internal(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Telegram Update 转换为天枢内部消息格式。
        
        Args:
            update: Telegram Bot API Update 对象
            
        Returns:
            天枢内部消息格式 dict，包含:
            - msgtype: 消息类型 (text, photo, callback)
            - body: 原始文本内容
            - formatted_body: 格式化文本 (如果有)
            - sender: 发送者信息 {"id": "...", "name": "..."}
            - chat: 聊天信息 {"id": "...", "type": "..."}
            - message_id: Telegram 消息 ID
            - raw: 原始 Telegram 消息数据
        """
        # 处理回调查询 (按钮点击)
        if "callback_query" in update:
            return self._parse_callback_query(update["callback_query"])
        
        # 处理普通消息
        if "message" in update:
            return self._parse_message(update["message"])
        
        # 处理编辑消息
        if "edited_message" in update:
            return self._parse_message(update["edited_message"], edited=True)
        
        # 处理其他更新类型
        return {"msgtype": "unknown", "body": "", "raw": update}

    def _parse_message(self, msg: Dict[str, Any], edited: bool = False, is_channel: bool = False) -> Dict[str, Any]:
        """解析普通 Telegram 消息。"""
        chat = msg.get("chat", {})
        user = msg.get("from", {})
        
        # 识别聊天类型
        chat_type = chat.get("type", "private")
        is_group = chat_type in ("group", "supergroup")
        is_channel = is_channel or chat_type == "channel"
        
        # 基础消息结构
        internal = {
            "msgtype": "text",
            "body": "",
            "sender": {
                "id": str(user.get("id", "")) if user else "",
                "name": self._get_user_name(user),
            },
            "chat": {
                "id": str(chat.get("id", "")),
                "type": chat_type,
            },
            "message_id": msg.get("message_id"),
            "date": msg.get("date"),
            "edited": edited,
            "is_group": is_group,
            "is_channel": is_channel,
            "raw": msg,
        }
        
        # 处理文本消息
        if "text" in msg:
            internal["body"] = msg["text"]
            internal["formatted_body"] = msg.get("text", "")
        
        # 处理照片/图片
        if "photo" in msg:
            photos = msg["photo"]
            if photos:
                # 取最大尺寸的照片
                photo = photos[-1]
                internal["msgtype"] = "photo"
                internal["body"] = msg.get("caption", "") or photo.get("file_id", "")
                internal["photo"] = {
                    "file_id": photo.get("file_id"),
                    "width": photo.get("width"),
                    "height": photo.get("height"),
                    "file_size": photo.get("file_size"),
                }
                if msg.get("caption"):
                    internal["caption"] = msg["caption"]
        
        # 处理文件/文档
        if "document" in msg:
            doc = msg["document"]
            internal["msgtype"] = "document"
            internal["body"] = msg.get("caption", "") or doc.get("file_name", "")
            internal["document"] = {
                "file_id": doc.get("file_id"),
                "file_name": doc.get("file_name"),
                "mime_type": doc.get("mime_type"),
                "file_size": doc.get("file_size"),
            }
        
        # 处理音频
        if "audio" in msg:
            audio = msg["audio"]
            internal["msgtype"] = "audio"
            internal["body"] = ""
            internal["audio"] = {
                "file_id": audio.get("file_id"),
                "duration": audio.get("duration"),
                "mime_type": audio.get("mime_type"),
            }
        
        # 处理语音
        if "voice" in msg:
            voice = msg["voice"]
            internal["msgtype"] = "voice"
            internal["body"] = ""
            internal["voice"] = {
                "file_id": voice.get("file_id"),
                "duration": voice.get("duration"),
                "mime_type": voice.get("mime_type"),
            }
        
        # 处理位置
        if "location" in msg:
            loc = msg["location"]
            internal["msgtype"] = "location"
            internal["body"] = ""
            internal["location"] = {
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
            }
        
        # 处理命令
        command = None
        command_args = []
        mentions = []
        
        if "entities" in msg:
            entities = msg["entities"]
            text = msg.get("text", "")
            for ent in entities:
                ent_type = ent.get("type")
                if ent_type == "bot_command":
                    internal["msgtype"] = "command"
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
                    # @mention - 用户名
                    offset = ent.get("offset", 0)
                    length = ent.get("length", 0)
                    if text and offset < len(text):
                        mention_name = text[offset:offset + length]
                        mentions.append({"type": "username", "name": mention_name})
                elif ent_type == "text_mention":
                    # 带有用户 ID 的 mention
                    mentioned_user = ent.get("user", {})
                    if mentioned_user.get("id"):
                        mentions.append({
                            "type": "user_id",
                            "id": str(mentioned_user.get("id")),
                            "name": self._get_user_name(mentioned_user),
                        })
        
        # 如果检测到命令，添加命令信息
        if command:
            internal["command"] = command
            internal["command_args"] = command_args
        
        # 添加 @mention 信息
        if mentions:
            internal["mentions"] = mentions
        
        return internal

    def _parse_callback_query(self, callback: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Telegram 回调查询（按钮点击）。"""
        user = callback.get("from", {})
        message = callback.get("message", {})
        chat = message.get("chat", {}) if message else {}
        
        return {
            "msgtype": "callback",
            "body": callback.get("data", ""),
            "callback_id": callback.get("id"),
            "data": callback.get("data", ""),
            "sender": {
                "id": str(user.get("id", "")) if user else "",
                "name": self._get_user_name(user),
            },
            "chat": {
                "id": str(chat.get("id", "")),
                "type": chat.get("type", "private"),
            },
            "message_id": message.get("message_id") if message else None,
            "inline_message_id": callback.get("inline_message_id"),
            "raw": callback,
        }

    def _get_user_name(self, user: Optional[Dict[str, Any]]) -> str:
        """获取用户显示名称。"""
        if not user:
            return ""
        # 优先使用 username，其次 first_name + last_name
        if user.get("username"):
            return f"@{user['username']}"
        name = ""
        if user.get("first_name"):
            name = user["first_name"]
        if user.get("last_name"):
            name += " " + user["last_name"]
        return name or ""

    # ==================== 天枢 → Telegram ====================

    def to_telegram(
        self,
        internal_msg: Dict[str, Any],
        parse_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将天枢内部消息格式转换为 Telegram API 格式。
        
        Args:
            internal_msg: 天枢内部消息格式 dict
            parse_mode: 可选的解析模式覆盖
            
        Returns:
            Telegram API 参数字典，可直接用于 sendMessage:
            - chat_id: 目标聊天 ID
            - text: 消息文本
            - parse_mode: 解析模式
            - reply_markup: Inline keyboard (可选)
        """
        parse_mode = parse_mode or self.parse_mode
        
        # 从内部消息中提取信息
        chat_id = self._extract_chat_id(internal_msg)
        text = internal_msg.get("body") or internal_msg.get("text", "")
        
        # 处理格式化文本
        formatted_body = internal_msg.get("formatted_body")
        if formatted_body and formatted_body != text:
            text = formatted_body
        
        # 构建基础响应
        result = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        
        # 处理按钮 (Inline Keyboard)
        buttons = internal_msg.get("buttons")
        if buttons:
            result["reply_markup"] = self._build_reply_markup(buttons)
        
        # 处理回复消息
        reply_to_message_id = internal_msg.get("reply_to_message_id")
        if reply_to_message_id:
            result["reply_to_message_id"] = reply_to_message_id
        
        return result

    def to_telegram_with_buttons(
        self,
        text: str,
        buttons: List[List[Dict[str, str]]],
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        快捷方法：创建带按钮的 Telegram 消息。
        
        Args:
            text: 消息文本
            buttons: 按钮列表 [[{"text": "...", "callback_data": "..."}, ...], ...]
            chat_id: 可选的聊天 ID
            parse_mode: 可选的解析模式
            
        Returns:
            Telegram API 参数字典
        """
        parse_mode = parse_mode or self.parse_mode
        
        result = {
            "text": text,
            "parse_mode": parse_mode,
        }
        
        if chat_id:
            result["chat_id"] = chat_id
        
        if buttons:
            result["reply_markup"] = self._build_reply_markup(buttons)
        
        return result

    def _extract_chat_id(self, internal_msg: Dict[str, Any]) -> str:
        """从内部消息中提取聊天 ID。"""
        chat = internal_msg.get("chat", {})
        if chat:
            return str(chat.get("id", ""))
        
        # 尝试从 target 中获取
        target = internal_msg.get("target", {})
        if target:
            return str(target.get("receive_id", ""))
        
        return ""

    def _build_reply_markup(
        self,
        buttons: Union[List[List[Dict[str, str]]], List[Dict[str, str]]],
    ) -> Dict[str, Any]:
        """
        构建 Telegram reply_markup。
        
        Args:
            buttons: 按钮列表
            
        Returns:
            Telegram inline_keyboard 格式
        """
        keyboard = []
        
        # 支持两种格式：
        # 1. List[List[Dict]] - 已经是键盘格式
        # 2. List[Dict] - 单行按钮
        
        if not buttons:
            return {"inline_keyboard": []}
        
        # 检测是否为单层列表
        if buttons and isinstance(buttons[0], dict):
            # 单层列表，转为单行键盘
            keyboard = [buttons]
        else:
            keyboard = buttons
        
        return {"inline_keyboard": keyboard}

    # ==================== 辅助方法 ====================

    def build_callback_answer(
        self,
        callback_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> Dict[str, Any]:
        """
        构建回答回调查询的参数。
        
        Args:
            callback_query_id: 回调查询 ID
            text: 可选的提示文本
            show_alert: 是否显示为 alert
            
        Returns:
            Telegram answerCallbackQuery 参数
        """
        result = {
            "callback_query_id": callback_id,
        }
        if text:
            result["text"] = text
        if show_alert:
            result["show_alert"] = True
        return result

    def build_edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        buttons: Optional[List[List[Dict[str, str]]]] = None,
        parse_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        构建编辑消息的参数。
        
        Args:
            chat_id: 聊天 ID
            message_id: 消息 ID
            text: 新文本
            buttons: 可选的按钮
            parse_mode: 解析模式
            
        Returns:
            Telegram editMessageText 参数
        """
        parse_mode = parse_mode or self.parse_mode
        
        result = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        
        if buttons:
            result["reply_markup"] = self._build_reply_markup(buttons)
        
        return result


# ==================== 便捷函数 ====================

def create_converter(parse_mode: str = "Markdown") -> TelegramConverter:
    """创建 Telegram 转换器实例的便捷函数。"""
    return TelegramConverter(parse_mode=parse_mode)


# ==================== 示例用法 ====================

if __name__ == "__main__":
    # 示例 1: Telegram → 天枢
    converter = TelegramConverter()
    
    # 模拟 Telegram Update (消息)
    telegram_update = {
        "update_id": 123456789,
        "message": {
            "message_id": 123,
            "from": {
                "id": 987654321,
                "is_bot": False,
                "first_name": "John",
                "last_name": "Doe",
                "username": "johndoe",
            },
            "chat": {
                "id": 987654321,
                "type": "private",
            },
            "date": 1704067200,
            "text": "Hello, Bot!",
        },
    }
    
    internal_msg = converter.to_internal(telegram_update)
    print("=== Telegram → 天枢 ===")
    print(f"msgtype: {internal_msg.get('msgtype')}")
    print(f"body: {internal_msg.get('body')}")
    print(f"sender: {internal_msg.get('sender')}")
    print()
    
    # 模拟 Telegram Update (回调)
    callback_update = {
        "update_id": 123456790,
        "callback_query": {
            "id": "1234567890",
            "from": {
                "id": 987654321,
                "first_name": "John",
                "username": "johndoe",
            },
            "chat": {
                "id": 987654321,
                "type": "private",
            },
            "message": {
                "message_id": 124,
                "chat": {
                    "id": 987654321,
                    "type": "private",
                },
            },
            "data": "approve",
        },
    }
    
    callback_msg = converter.to_internal(callback_update)
    print("=== Telegram 回调 → 天枢 ===")
    print(f"msgtype: {callback_msg.get('msgtype')}")
    print(f"data: {callback_msg.get('data')}")
    print()
    
    # 示例 2: 天枢 → Telegram
    internal_for_telegram = {
        "chat": {"id": "987654321"},
        "body": "*Hello* from 天枢!",
        "formatted_body": "<b>Hello</b> from 天枢!",
        "buttons": [
            [{"text": "✅ 批准", "callback_data": "approve"}, {"text": "❌ 拒绝", "callback_data": "reject"}],
        ],
    }
    
    telegram_payload = converter.to_telegram(internal_for_telegram, parse_mode="HTML")
    print("=== 天枢 → Telegram ===")
    print(f"chat_id: {telegram_payload.get('chat_id')}")
    print(f"text: {telegram_payload.get('text')}")
    print(f"parse_mode: {telegram_payload.get('parse_mode')}")
    print(f"reply_markup: {telegram_payload.get('reply_markup')}")
    print()
    
    # 示例 3: 使用便捷方法
    quick_payload = converter.to_telegram_with_buttons(
        text="请选择操作:",
        buttons=[
            [{"text": "操作 A", "callback_data": "action_a"}],
            [{"text": "操作 B", "callback_data": "action_b"}],
        ],
        chat_id="123456789",
    )
    print("=== 便捷方法 ===")
    print(quick_payload)

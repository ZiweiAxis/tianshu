# Channel 模块抽象基类
# 定义渠道抽象接口

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Channel(ABC):
    """渠道抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """渠道名称。"""
        pass

    @property
    def is_configured(self) -> bool:
        """渠道是否已配置。"""
        return True

    @abstractmethod
    async def send_message(
        self,
        target: str,
        content: str,
        **kwargs: Any,
    ) -> Optional[str]:
        """
        发送消息。

        Args:
            target: 目标标识（如 chat_id, room_id）
            content: 消息内容
            **kwargs: 额外参数（如 buttons, reply_to）

        Returns:
            消息 ID，失败返回 None
        """
        pass

    async def send_card(
        self,
        target: str,
        card: Dict[str, Any],
        **kwargs: Any,
    ) -> Optional[str]:
        """
        发送卡片消息。默认调用 send_message。
        """
        return await self.send_message(target, str(card), **kwargs)

    async def handle_callback(
        self,
        callback_data: Dict[str, Any],
    ) -> bool:
        """
        处理回调查询。
        """
        return False


class CallbackProvider(ABC):
    """回调处理接口。"""

    @abstractmethod
    async def answer_callback(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """
        回答回调查询。
        """
        pass

    @abstractmethod
    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        buttons: Optional[List[List[Dict[str, str]]]] = None,
    ) -> bool:
        """
        编辑消息。
        """
        pass

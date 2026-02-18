"""太白消息协议 - 统一响应接口"""
from typing import Optional


class ResponseContext:
    """统一响应上下文接口"""

    def update_card(self, card_id: str, card_data: dict) -> None:
        """更新卡片"""
        raise NotImplementedError

    def redirect_url(self, url: str) -> None:
        """跳转链接"""
        raise NotImplementedError


class DefaultResponseContext(ResponseContext):
    """默认响应上下文实现（用于开发/测试）"""

    def __init__(self):
        self._updates = []
        self._redirects = []

    def update_card(self, card_id: str, card_data: dict) -> None:
        self._updates.append({"card_id": card_id, "card_data": card_data})

    def redirect_url(self, url: str) -> None:
        self._redirects.append(url)

    def get_updates(self):
        return self._updates

    def get_redirects(self):
        return self._redirects

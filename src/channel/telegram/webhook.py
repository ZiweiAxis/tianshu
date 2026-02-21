# Telegram Webhook 处理器
# 用于处理从 Telegram 接收的 Webhook 请求

import hashlib
import hmac
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# Update 处理器类型
UpdateHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class TelegramWebhook:
    """Telegram Webhook 接收器。"""

    def __init__(
        self,
        token: str,
        secret: Optional[str] = None,
        handler: Optional[UpdateHandler] = None,
    ):
        self.token = token
        self.secret = secret
        self.handler = handler

    def verify_secret(self, secret: str) -> bool:
        """验证 Webhook 秘钥。"""
        if not self.secret:
            return True  # 未配置则跳过验证
        return secret == self.secret

    async def handle_update(self, request: web.Request) -> web.Response:
        """处理 Telegram Update。"""
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            logger.warning("无效的 JSON payload")
            return web.Response(status=400, text="Invalid JSON")

        # 验证 secret token
        secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret_token and not self.verify_secret(secret_token):
            logger.warning("Webhook 秘钥验证失败")
            return web.Response(status=403, text="Forbidden")

        # 处理 Update
        if self.handler:
            try:
                await self.handler(payload)
            except Exception as e:
                logger.exception("处理 Update 失败: %s", e)
                return web.Response(status=500, text="Internal Error")

        return web.Response(text="OK")

    def create_app(self) -> web.Application:
        """创建 aiohttp 应用。"""
        app = web.Application()
        app.router.add_post(f"/bot{self.token}/", self.handle_update)
        return app


# 便捷函数：创建 webhook 应用
def create_webhook_app(
    token: str,
    secret: Optional[str] = None,
    handler: Optional[UpdateHandler] = None,
) -> web.Application:
    """创建 Telegram Webhook 应用。"""
    webhook = TelegramWebhook(token, secret, handler)
    return webhook.create_app()

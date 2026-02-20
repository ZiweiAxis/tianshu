"""
Telegram Webhook 接收器

支持公网部署的 Webhook 模式，替代 Long Polling。
可作为独立服务运行，也可集成到天枢主进程中。

环境变量：
    TELEGRAM_BOT_TOKEN          - Bot Token（必需）
    TELEGRAM_WEBHOOK_URL        - 公网 Webhook 地址，如 https://your-domain.com/webhook/telegram
    TELEGRAM_WEBHOOK_SECRET     - Webhook 验证密钥（推荐设置）
    TELEGRAM_WEBHOOK_PORT       - 监听端口（默认 8443）
    TELEGRAM_WEBHOOK_HOST       - 监听地址（默认 0.0.0.0）
    TELEGRAM_WEBHOOK_CERT_PATH  - SSL 证书路径（自签名时需要）
    TELEGRAM_WEBHOOK_KEY_PATH   - SSL 私钥路径
    TELEGRAM_WEBHOOK_MAX_CONN   - 最大并发连接数（默认 40）

独立运行：
    python -m src.telegram_webhook

Docker 部署：
    docker run -d \\
        --name tianshu-webhook \\
        -p 8443:8443 \\
        -e TELEGRAM_BOT_TOKEN=xxx \\
        -e TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook/telegram \\
        -e TELEGRAM_WEBHOOK_SECRET=my-secret \\
        tianshu:latest python -m src.telegram_webhook
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import ssl
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

WEBHOOK_HOST = os.getenv("TELEGRAM_WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8443"))
WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
WEBHOOK_CERT_PATH = os.getenv("TELEGRAM_WEBHOOK_CERT_PATH", "")
WEBHOOK_KEY_PATH = os.getenv("TELEGRAM_WEBHOOK_KEY_PATH", "")
WEBHOOK_MAX_CONNECTIONS = int(os.getenv("TELEGRAM_WEBHOOK_MAX_CONN", "40"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# IP 白名单：Telegram Bot API 服务器 IP 段
# https://core.telegram.org/bots/webhooks#the-short-version
TELEGRAM_IP_RANGES = [
    "149.154.160.0/20",
    "91.108.4.0/22",
]


# ---------------------------------------------------------------------------
# Update 处理器类型
# ---------------------------------------------------------------------------

UpdateHandler = Callable[[Dict[str, Any]], Awaitable[None]]


# ---------------------------------------------------------------------------
# TelegramWebhook 核心类
# ---------------------------------------------------------------------------


class TelegramWebhook:
    """
    Telegram Webhook 接收器。

    职责：
    1. 启动 HTTP(S) 服务，接收 Telegram 推送的 Update
    2. 验证请求来源（secret token + 可选 IP 白名单）
    3. 将 Update 分发给注册的处理器
    4. 通过 Telegram Bot API 注册/注销 Webhook

    用法示例（集成到现有 aiohttp app）::

        webhook = TelegramWebhook(token=BOT_TOKEN, secret=SECRET)
        webhook.add_handler(my_handler)
        webhook.register_routes(existing_app)

    用法示例（独立运行）::

        webhook = TelegramWebhook(token=BOT_TOKEN, secret=SECRET)
        webhook.add_handler(my_handler)
        await webhook.start()  # 阻塞运行
    """

    def __init__(
        self,
        token: Optional[str] = None,
        secret: Optional[str] = None,
        webhook_url: Optional[str] = None,
        host: str = WEBHOOK_HOST,
        port: int = WEBHOOK_PORT,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        max_connections: int = WEBHOOK_MAX_CONNECTIONS,
        ip_whitelist: bool = False,
    ):
        self.token = token or BOT_TOKEN
        self.secret = secret or WEBHOOK_SECRET
        self.webhook_url = webhook_url or WEBHOOK_URL
        self.host = host
        self.port = port
        self.cert_path = cert_path or WEBHOOK_CERT_PATH or None
        self.key_path = key_path or WEBHOOK_KEY_PATH or None
        self.max_connections = max_connections
        self.ip_whitelist = ip_whitelist

        if not self.token:
            raise ValueError(
                "Bot token is required. "
                "Set TELEGRAM_BOT_TOKEN env or pass token= parameter."
            )

        self._api_url = f"https://api.telegram.org/bot{self.token}"
        self._handlers: List[UpdateHandler] = []
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

        # 统计
        self._stats = {
            "received": 0,
            "processed": 0,
            "errors": 0,
            "started_at": None,
        }

    # ------------------------------------------------------------------
    # 处理器管理
    # ------------------------------------------------------------------

    def add_handler(self, handler: UpdateHandler) -> None:
        """注册 Update 处理器。"""
        self._handlers.append(handler)

    def remove_handler(self, handler: UpdateHandler) -> None:
        """移除 Update 处理器。"""
        self._handlers.remove(handler)

    # ------------------------------------------------------------------
    # HTTP 端点
    # ------------------------------------------------------------------

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """
        POST /webhook/telegram — Telegram Update 接收端点。

        流程：
        1. 验证 X-Telegram-Bot-Api-Secret-Token
        2. 解析 JSON body
        3. 分发给所有已注册的处理器
        4. 返回 200 OK（Telegram 要求快速响应）
        """
        self._stats["received"] += 1

        # 1. 验证 secret token
        if self.secret:
            header_secret = request.headers.get(
                "X-Telegram-Bot-Api-Secret-Token", ""
            )
            if not hmac.compare_digest(header_secret, self.secret):
                logger.warning(
                    "Webhook secret 验证失败，来源 IP: %s",
                    request.remote,
                )
                return web.Response(status=403, text="Forbidden")

        # 2. 可选 IP 白名单验证
        if self.ip_whitelist and not self._check_ip(request.remote):
            logger.warning("IP 不在白名单: %s", request.remote)
            return web.Response(status=403, text="Forbidden")

        # 3. 解析 body
        try:
            data = await request.json()
        except Exception:
            logger.warning("无效的 JSON body")
            return web.Response(status=400, text="Bad Request")

        update_id = data.get("update_id", "?")
        logger.debug("收到 Update #%s", update_id)

        # 4. 异步分发（不阻塞响应）
        asyncio.create_task(self._dispatch(data))

        return web.Response(text="OK")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """GET /webhook/health — 健康检查。"""
        uptime = None
        if self._stats["started_at"]:
            uptime = int(time.time() - self._stats["started_at"])
        return web.json_response(
            {
                "status": "ok",
                "uptime_seconds": uptime,
                "stats": {
                    "received": self._stats["received"],
                    "processed": self._stats["processed"],
                    "errors": self._stats["errors"],
                },
            }
        )

    async def _handle_set_webhook(self, request: web.Request) -> web.Response:
        """POST /webhook/setup — 手动触发 setWebhook。"""
        try:
            body = await request.json()
        except Exception:
            body = {}
        url = body.get("url") or self.webhook_url
        if not url:
            return web.json_response(
                {"ok": False, "error": "未提供 webhook_url"},
                status=400,
            )
        ok = await self.set_webhook(url)
        return web.json_response({"ok": ok, "url": url})

    # ------------------------------------------------------------------
    # 路由注册（可嵌入到外部 app）
    # ------------------------------------------------------------------

    def register_routes(
        self,
        app: web.Application,
        prefix: str = "/webhook",
    ) -> None:
        """
        将 Webhook 路由注册到已有的 aiohttp Application 上。

        注册的路由：
            POST {prefix}/telegram   — 接收 Telegram Update
            GET  {prefix}/health     — 健康检查
            POST {prefix}/setup      — 手动设置 Webhook
        """
        app.router.add_post(f"{prefix}/telegram", self._handle_webhook)
        app.router.add_get(f"{prefix}/health", self._handle_health)
        app.router.add_post(f"{prefix}/setup", self._handle_set_webhook)
        logger.info("Webhook 路由已注册: %s/telegram", prefix)

    # ------------------------------------------------------------------
    # 独立运行
    # ------------------------------------------------------------------

    def create_app(self) -> web.Application:
        """创建独立的 aiohttp Application。"""
        app = web.Application()
        self.register_routes(app)
        self._app = app
        return app

    async def start(self, auto_set_webhook: bool = True) -> None:
        """
        启动独立的 Webhook HTTP 服务。

        Args:
            auto_set_webhook: 启动后自动调用 setWebhook
        """
        app = self.create_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()

        # SSL 配置（用于自签名证书直连模式）
        ssl_ctx = None
        if self.cert_path and self.key_path:
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(self.cert_path, self.key_path)
            logger.info("已加载 SSL 证书: %s", self.cert_path)

        site = web.TCPSite(
            self._runner,
            self.host,
            self.port,
            ssl_context=ssl_ctx,
        )
        await site.start()

        self._stats["started_at"] = time.time()
        proto = "https" if ssl_ctx else "http"
        logger.info(
            "Webhook 服务已启动: %s://%s:%s/webhook/telegram",
            proto,
            self.host,
            self.port,
        )

        # 自动注册 Webhook
        if auto_set_webhook and self.webhook_url:
            ok = await self.set_webhook(self.webhook_url)
            if ok:
                logger.info("Webhook 已自动注册: %s", self.webhook_url)
            else:
                logger.error("Webhook 自动注册失败！")

    async def stop(self) -> None:
        """停止 Webhook 服务并注销 Webhook。"""
        logger.info("正在停止 Webhook 服务...")
        await self.delete_webhook()
        if self._runner:
            await self._runner.cleanup()
        logger.info("Webhook 服务已停止")

    # ------------------------------------------------------------------
    # Telegram Bot API 调用
    # ------------------------------------------------------------------

    async def set_webhook(
        self,
        url: Optional[str] = None,
        allowed_updates: Optional[List[str]] = None,
    ) -> bool:
        """
        调用 Telegram setWebhook API。

        Args:
            url: Webhook URL（如 https://your-domain.com/webhook/telegram）
            allowed_updates: 接收的 Update 类型

        Returns:
            是否成功
        """
        import aiohttp as _aiohttp

        target_url = url or self.webhook_url
        if not target_url:
            logger.error("未提供 Webhook URL")
            return False

        payload: Dict[str, Any] = {
            "url": target_url,
            "max_connections": self.max_connections,
            "allowed_updates": allowed_updates
            or [
                "message",
                "callback_query",
                "channel_post",
                "edited_message",
            ],
        }
        if self.secret:
            payload["secret_token"] = self.secret

        api_url = f"{self._api_url}/setWebhook"

        try:
            async with _aiohttp.ClientSession(trust_env=True) as session:
                # 自签名证书需要上传 certificate
                data = None
                if self.cert_path and os.path.isfile(self.cert_path):
                    data = _aiohttp.FormData()
                    for k, v in payload.items():
                        if isinstance(v, list):
                            data.add_field(k, json.dumps(v))
                        else:
                            data.add_field(k, str(v))
                    data.add_field(
                        "certificate",
                        open(self.cert_path, "rb"),
                        filename="cert.pem",
                        content_type="application/x-pem-file",
                    )
                    async with session.post(api_url, data=data) as resp:
                        result = await resp.json()
                else:
                    async with session.post(api_url, json=payload) as resp:
                        result = await resp.json()

                if result.get("ok"):
                    logger.info("setWebhook 成功: %s", target_url)
                    return True
                else:
                    logger.error(
                        "setWebhook 失败: %s", result.get("description")
                    )
                    return False
        except Exception as e:
            logger.exception("setWebhook 异常: %s", e)
            return False

    async def delete_webhook(
        self, drop_pending_updates: bool = False
    ) -> bool:
        """调用 Telegram deleteWebhook API。"""
        import aiohttp as _aiohttp

        try:
            async with _aiohttp.ClientSession(trust_env=True) as session:
                async with session.post(
                    f"{self._api_url}/deleteWebhook",
                    json={"drop_pending_updates": drop_pending_updates},
                ) as resp:
                    result = await resp.json()
                    return result.get("ok", False)
        except Exception as e:
            logger.exception("deleteWebhook 异常: %s", e)
            return False

    async def get_webhook_info(self) -> Optional[Dict[str, Any]]:
        """调用 Telegram getWebhookInfo API。"""
        import aiohttp as _aiohttp

        try:
            async with _aiohttp.ClientSession(trust_env=True) as session:
                async with session.post(
                    f"{self._api_url}/getWebhookInfo"
                ) as resp:
                    result = await resp.json()
                    if result.get("ok"):
                        return result["result"]
                    return None
        except Exception as e:
            logger.exception("getWebhookInfo 异常: %s", e)
            return None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _dispatch(self, data: Dict[str, Any]) -> None:
        """将 Update 分发给所有处理器。"""
        for handler in self._handlers:
            try:
                await handler(data)
                self._stats["processed"] += 1
            except Exception:
                self._stats["errors"] += 1
                logger.exception(
                    "处理器 %s 处理 Update 异常", handler.__name__
                )

    @staticmethod
    def _check_ip(ip: Optional[str]) -> bool:
        """检查 IP 是否在 Telegram 服务器范围内。"""
        if not ip:
            return False
        try:
            import ipaddress

            addr = ipaddress.ip_address(ip)
            for cidr in TELEGRAM_IP_RANGES:
                if addr in ipaddress.ip_network(cidr):
                    return True
        except (ValueError, ImportError):
            pass
        return False


# ---------------------------------------------------------------------------
# 与天枢集成的便捷函数
# ---------------------------------------------------------------------------


def setup_webhook_in_app(
    app: web.Application,
    token: Optional[str] = None,
    secret: Optional[str] = None,
    handlers: Optional[List[UpdateHandler]] = None,
) -> TelegramWebhook:
    """
    在现有 aiohttp Application 中集成 Webhook。

    用法（在 main.py 的 run_health_server 中调用）::

        from src.telegram_webhook import setup_webhook_in_app
        webhook = setup_webhook_in_app(app, handlers=[handle_telegram_event_wrapper])
    """
    webhook = TelegramWebhook(token=token, secret=secret)
    for h in handlers or []:
        webhook.add_handler(h)
    webhook.register_routes(app)
    return webhook


async def create_bridge_handler() -> UpdateHandler:
    """
    创建一个桥接处理器，将 Webhook 收到的 Update 转发给天枢 Bridge 层。

    返回的 handler 可以直接注册到 TelegramWebhook::

        handler = await create_bridge_handler()
        webhook.add_handler(handler)
    """

    async def handler(data: Dict[str, Any]) -> None:
        from src.bridge.telegram import handle_telegram_event
        from src.core import room_manager
        from src.matrix.client import MatrixClient

        matrix = MatrixClient()
        if await matrix.connect():
            try:
                await handle_telegram_event(data, matrix, room_manager)
            finally:
                await matrix.disconnect()

    return handler


async def create_client_handler() -> UpdateHandler:
    """
    创建一个使用 TelegramClient 处理 Update 的处理器。

    使用 telegram_client.py 中的 TelegramClient.handle_webhook() 处理逻辑。
    """
    from src.telegram_client import TelegramClient

    client = TelegramClient(token=BOT_TOKEN)

    async def handler(data: Dict[str, Any]) -> None:
        await client.handle_webhook(data)

    return handler


# ---------------------------------------------------------------------------
# 独立运行入口
# ---------------------------------------------------------------------------


async def _main():
    """独立运行 Webhook 服务。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    webhook = TelegramWebhook()

    # 注册桥接处理器（将消息转到 Matrix）
    try:
        bridge_handler = await create_bridge_handler()
        webhook.add_handler(bridge_handler)
        logger.info("已注册桥接处理器 (Telegram -> Matrix)")
    except ImportError:
        logger.warning("桥接模块不可用，仅运行基础 Webhook")

    # 信号处理
    loop = asyncio.get_running_loop()

    def _signal():
        asyncio.create_task(webhook.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal)
        except NotImplementedError:
            pass

    await webhook.start(auto_set_webhook=True)

    # 阻塞等待
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await webhook.stop()


if __name__ == "__main__":
    asyncio.run(_main())

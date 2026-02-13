# Matrix 连接与 Room/Event 收发（E2-S1）
# 与配置的 MHS 建立连接，可创建/加入 Room、发送与接收 Event；连接断开可重连或告警

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from nio import (
    AsyncClient,
    AsyncClientConfig,
    SyncResponse,
    RoomCreateError,
    JoinError,
)

from src.config import (
    MATRIX_HOMESERVER,
    MATRIX_GATEWAY_USER,
    MATRIX_GATEWAY_TOKEN,
)

logger = logging.getLogger(__name__)


class MatrixClient:
    """天枢侧 Matrix 客户端：连接 MHS，收发 Room/Event，支持重连与告警。"""

    def __init__(
        self,
        homeserver: Optional[str] = None,
        user_id: Optional[str] = None,
        access_token: Optional[str] = None,
        on_disconnect: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self._homeserver = homeserver or (MATRIX_HOMESERVER or "").rstrip("/")
        self._user_id = user_id or MATRIX_GATEWAY_USER or ""
        self._access_token = access_token or MATRIX_GATEWAY_TOKEN
        self._on_disconnect = on_disconnect
        self._client: Optional[AsyncClient] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> bool:
        """与 Matrix Home Server 建立连接（使用 token）。"""
        if not self._homeserver or not self._user_id:
            logger.error("Matrix 配置缺失: MATRIX_HOMESERVER 或 MATRIX_GATEWAY_USER 未设置")
            return False
        if not self._access_token:
            logger.error("Matrix 配置缺失: MATRIX_GATEWAY_TOKEN 未设置")
            return False

        try:
            config = AsyncClientConfig(store_sync_tokens=True)
            self._client = AsyncClient(
                self._homeserver,
                self._user_id,
                config=config,
            )
            # 使用 token 恢复登录（兼容：部分版本为 restore_login，部分为直接赋值）
            if hasattr(self._client, "restore_login"):
                self._client.restore_login(
                    user_id=self._user_id,
                    device_id="tianshu-gateway",
                    access_token=self._access_token,
                )
            else:
                self._client.access_token = self._access_token
                self._client.user_id = self._user_id
                self._client.device_id = self._client.device_id or "tianshu-gateway"
            # 验证连接：执行一次 sync
            await self._client.sync(timeout=5000, full_state=False)
            logger.info("Matrix 连接成功: %s @ %s", self._user_id, self._homeserver)
            return True
        except Exception as e:
            logger.exception("Matrix 连接失败: %s", e)
            self._client = None
            return False

    async def disconnect(self) -> None:
        """关闭连接并停止 sync 循环。"""
        self._running = False
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.close()
            self._client = None
        logger.info("Matrix 连接已关闭")

    async def _sync_loop(self, on_event: Callable[[str, str, dict], Awaitable[None]]) -> None:
        """后台 sync 循环：拉取新事件并回调。连接异常时重试或告警。"""
        timeout_ms = 30_000
        backoff = 2.0
        max_backoff = 60.0
        while self._running and self._client:
            try:
                response = await self._client.sync(timeout=timeout_ms, full_state=False)
                if not isinstance(response, SyncResponse):
                    continue
                backoff = 2.0  # 成功后重置
                for room_id, room_info in (response.rooms.join or {}).items():
                    for event in room_info.timeline.events:
                        if hasattr(event, "body") and hasattr(event, "msgtype"):
                            body = getattr(event, "body", "") or ""
                            msgtype = getattr(event, "msgtype", "m.text") or "m.text"
                            await on_event(room_id, msgtype, {"body": body, "event_id": getattr(event, "event_id", "")})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Matrix sync 异常 (将重试): %s", e)
                if self._on_disconnect:
                    try:
                        await self._on_disconnect()
                    except Exception:
                        pass
                await asyncio.sleep(min(backoff, max_backoff))
                backoff = min(backoff * 2, max_backoff)

    def start_sync_loop(self, on_event: Callable[[str, str, dict], Awaitable[None]]) -> None:
        """启动后台 sync 循环以接收 Event。需在 connect() 之后调用。"""
        if not self._client:
            raise RuntimeError("请先调用 connect()")
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop(on_event))
        logger.info("Matrix sync 循环已启动")

    async def create_room(
        self,
        alias: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Optional[str]:
        """创建 Room，返回 room_id；失败返回 None。"""
        if not self._client:
            return None
        try:
            resp = await self._client.room_create(name=name, topic=None, room_alias_name=alias)
            if hasattr(resp, "room_id"):
                return resp.room_id
            if isinstance(resp, RoomCreateError):
                logger.error("创建 Room 失败: %s", resp.message)
            return None
        except Exception as e:
            logger.exception("创建 Room 异常: %s", e)
            return None

    async def join_room(self, room_id_or_alias: str) -> bool:
        """加入指定 Room（room_id 或 alias）。"""
        if not self._client:
            return False
        try:
            resp = await self._client.join(room_id_or_alias)
            if isinstance(resp, JoinError):
                logger.error("加入 Room 失败: %s", resp.message)
                return False
            return True
        except Exception as e:
            logger.exception("加入 Room 异常: %s", e)
            return False

    async def leave_room(self, room_id: str) -> bool:
        """离开 Room。"""
        if not self._client:
            return False
        try:
            await self._client.room_leave(room_id)
            return True
        except Exception as e:
            logger.exception("离开 Room 异常: %s", e)
            return False

    async def send_text(self, room_id: str, body: str) -> Optional[str]:
        """在 Room 内发送文本消息，返回 event_id；失败返回 None。"""
        if not self._client:
            return None
        try:
            resp = await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": body},
            )
            if hasattr(resp, "event_id"):
                return resp.event_id
            return None
        except Exception as e:
            logger.exception("发送消息异常: %s", e)
            return None

    async def send_delivery(
        self,
        room_id: str,
        semantic_type: str,
        target: dict,
        payload: dict,
        body_summary: Optional[str] = None,
    ) -> Optional[str]:
        """
        E2-S3：向 Matrix 发送投递类事件（语义 payload + 目标 + 渠道）。
        target: {"channel": "feishu", "receive_id": "oc_xxx", "receive_id_type": "chat_id"}
        返回 event_id，失败返回 None。
        """
        from src.core.delivery import build_delivery_content

        content = build_delivery_content(semantic_type, target, payload, body_summary)
        return await self._send_custom(room_id, content)

    async def _send_custom(self, room_id: str, content: dict) -> Optional[str]:
        """发送自定义 content 的 m.room.message。"""
        if not self._client:
            return None
        try:
            resp = await self._client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
            )
            if hasattr(resp, "event_id"):
                return resp.event_id
            return None
        except Exception as e:
            logger.exception("发送投递事件异常: %s", e)
            return None

    def get_rooms(self) -> dict:
        """返回当前已加入的 Room 列表（room_id -> 简单信息）。需在 sync 至少一次后有效。"""
        if not self._client or not self._client.rooms:
            return {}
        return {
            rid: {"room_id": rid, "name": getattr(r, "name", None)}
            for rid, r in self._client.rooms.items()
        }

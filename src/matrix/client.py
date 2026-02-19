# Matrix 连接与 Room/Event 收发（E2-S1）
# 与配置的 MHS 建立连接，可创建/加入 Room、发送与接收 Event；连接断开可重连或告警

import asyncio
import logging
import os
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
        # 支持启动时自举写入的 token（config 在 import 时已读，此处再读一次 env）
        self._access_token = access_token or MATRIX_GATEWAY_TOKEN or os.getenv("MATRIX_GATEWAY_TOKEN")
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

    async def send_card(
        self,
        room_id: str,
        semantic_type: str,
        payload: dict,
        card_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        发送 Matrix MSC1767 原生卡片消息。
        
        用于审批请求等需要交互按钮的场景。
        
        Args:
            room_id: 目标房间 ID
            semantic_type: 语义类型（如 approval_request, approval_result）
            payload: 业务数据
            card_id: 卡片唯一标识（用于回调关联）
        
        Returns:
            event_id，失败返回 None
        """
        from src.core.delivery import build_matrix_card_content

        content = build_matrix_card_content(semantic_type, payload, card_id)
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

    # ========== DM 复用功能 ==========
    # 使用指定 token 创建/查找 DM，支持复用已有 DM room

    async def create_dm_with_token(
        self,
        user_id: str,
        access_token: str,
    ) -> Optional[str]:
        """使用指定 token 创建 DM，返回 room_id；失败返回 None。"""
        import aiohttp
        try:
            # 使用 HTTP API 直接创建 DM，确保创建者就是使用 access_token 的用户
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {access_token}"}
                url = f"{self._homeserver}/_matrix/client/r0/createRoom"
                content = {
                    "invite": [user_id],
                    "is_direct": True,
                    "name": f"DM with {user_id}",
                }
                async with session.post(url, headers=headers, json=content) as resp:
                    if resp.status < 300:
                        data = await resp.json()
                        room_id = data.get("room_id")
                        if room_id:
                            logger.info("使用 token 创建 DM 成功: %s -> %s", user_id[:20], room_id)
                        return room_id
                    else:
                        text = await resp.text()
                        logger.error("创建 DM 失败: %s %s", resp.status, text[:200])
                        return None
        except Exception as e:
            logger.exception("创建 DM 异常: %s", e)
            return None

    async def find_dm_room_with_token(
        self,
        user_id: str,
        access_token: str,
    ) -> Optional[str]:
        """
        使用指定 token 查找与用户的已有 DM room。
        通过遍历已加入的房间，检查是否有且仅有两个成员且包含目标用户。
        """
        import aiohttp
        if not self._client:
            return None
        try:
            # 先尝试通过客户端的 rooms 缓存查找
            for room_id, room in (self._client.rooms or {}).items():
                # 检查成员数量为 2（自己 + 目标用户）
                if hasattr(room, 'members') and room.members:
                    members = list(room.members.keys())
                    if len(members) == 2 and user_id in members:
                        # 这是目标用户的 DM
                        return room_id
            
            # 如果缓存中没有，通过 HTTP API 查询
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {access_token}"}
                # 获取已加入的房间列表
                url = f"{self._homeserver}/_matrix/client/r0/joined_rooms"
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    joined_rooms = data.get("joined_rooms", [])
                    
                    for room_id in joined_rooms:
                        # 获取房间成员
                        import urllib.parse
                        encoded_room_id = urllib.parse.quote(room_id, safe='')
                        members_url = f"{self._homeserver}/_matrix/client/r0/rooms/{encoded_room_id}/members"
                        async with session.get(members_url, headers=headers) as members_resp:
                            if members_resp.status != 200:
                                continue
                            members_data = await members_resp.json()
                            members_list = members_data.get("chunk", [])
                            members = [m.get("state_key") for m in members_list]
                            if len(members) == 2 and user_id in members:
                                return room_id
            return None
        except Exception as e:
            logger.exception("查找 DM 异常: %s", e)
            return None

    async def send_delivery_with_token(
        self,
        user_id: str,
        semantic_type: str,
        target: dict,
        payload: dict,
        access_token: str,
        body_summary: Optional[str] = None,
    ) -> Optional[str]:
        """
        使用指定 token 发送投递消息（用于审批请求等）。
        支持 DM 复用：如果已存在 DM room，直接使用；否则创建新的。
        返回 event_id，失败返回 None。
        """
        import json
        from src.config import DM_MAPPING_FILE
        from src.core.delivery import build_delivery_content

        # 先尝试从映射文件查找已有 DM
        room_id = None
        mapping = {}
        
        # 读取映射文件
        try:
            if os.path.exists(DM_MAPPING_FILE):
                with open(DM_MAPPING_FILE, "r") as f:
                    mapping = json.load(f)
        except Exception as e:
            logger.warning("读取 DM 映射文件失败: %s", e)
        
        # 查找已有的 DM room
        room_id = mapping.get(user_id)
        if room_id:
            logger.info("找到已有 DM room: %s -> %s", user_id[:20], room_id)
        
        # 如果没有找到，尝试创建或查找 DM
        if not room_id:
            # 先尝试查找已有 DM
            room_id = await self.find_dm_room_with_token(user_id, access_token)
            if room_id:
                logger.info("找到已有 DM: %s -> %s", user_id[:20], room_id)
        
        if not room_id:
            # 创建新的 DM
            room_id = await self.create_dm_with_token(user_id, access_token)
            if room_id:
                logger.info("创建新 DM: %s -> %s", user_id[:20], room_id)
        
        if not room_id:
            logger.error("无法创建或找到 DM: %s", user_id[:20])
            return None
        
        # 保存映射关系
        mapping[user_id] = room_id
        try:
            os.makedirs(os.path.dirname(DM_MAPPING_FILE), exist_ok=True)
            with open(DM_MAPPING_FILE, "w") as f:
                json.dump(mapping, f)
            logger.info("已保存 DM 映射: %s -> %s", user_id[:20], room_id)
        except Exception as e:
            logger.warning("保存 DM 映射失败: %s", e)
        
        # 发送投递消息（需要使用正确的 client 或通过 HTTP API）
        # 这里通过 nio 客户端发送（需要切换到对应 token 的客户端）
        # 由于 nio 客户端只能用一个 token，我们使用 HTTP API 直接发送
        return await self._send_delivery_via_http(room_id, semantic_type, target, payload, access_token, body_summary)

    async def _send_delivery_via_http(
        self,
        room_id: str,
        semantic_type: str,
        target: dict,
        payload: dict,
        access_token: str,
        body_summary: Optional[str] = None,
    ) -> Optional[str]:
        """通过 HTTP API 发送投递消息（支持不同 token）。"""
        import aiohttp
        from src.core.delivery import build_delivery_content
        
        content = build_delivery_content(semantic_type, target, payload, body_summary)
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {access_token}"}
                txn_id = f"tianshu_{int(asyncio.get_event_loop().time() * 1000)}"
                # URL-encode the room_id (contains ! which is special in URLs)
                import urllib.parse
                encoded_room_id = urllib.parse.quote(room_id, safe='')
                url = f"{self._homeserver}/_matrix/client/r0/rooms/{encoded_room_id}/send/m.room.message/{txn_id}"
                async with session.put(url, headers=headers, json=content) as resp:
                    if resp.status < 300:
                        data = await resp.json()
                        event_id = data.get("event_id")
                        logger.info("发送投递消息成功: room=%s event=%s", room_id, event_id[:16] if event_id else "N/A")
                        return event_id
                    else:
                        text = await resp.text()
                        logger.error("发送投递消息失败: %s %s", resp.status, text[:200])
                        return None
        except Exception as e:
            logger.exception("发送投递消息异常: %s", e)
            return None

    async def send_card_with_token(
        self,
        user_id: str,
        semantic_type: str,
        payload: dict,
        access_token: str,
        card_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        使用指定 token 发送 Matrix MSC1767 原生卡片消息（用于审批请求等）。
        
        支持 DM 复用：如果已存在 DM room，直接使用；否则创建新的。
        
        Args:
            user_id: 接收方用户 ID
            semantic_type: 语义类型（如 approval_request, approval_result）
            payload: 业务数据
            access_token: Matrix 访问令牌
            card_id: 卡片唯一标识（用于回调关联）
        
        Returns:
            event_id，失败返回 None
        """
        import json
        import aiohttp
        import urllib.parse
        from src.config import DM_MAPPING_FILE
        from src.core.delivery import build_matrix_card_content

        # 先尝试从映射文件查找已有 DM
        room_id = None
        mapping = {}
        
        # 读取映射文件
        try:
            if os.path.exists(DM_MAPPING_FILE):
                with open(DM_MAPPING_FILE, "r") as f:
                    mapping = json.load(f)
        except Exception as e:
            logger.warning("读取 DM 映射文件失败: %s", e)
        
        # 查找已有的 DM room
        room_id = mapping.get(user_id)
        if room_id:
            logger.info("找到已有 DM room: %s -> %s", user_id[:20], room_id)
        
        # 如果没有找到，尝试创建或查找 DM
        if not room_id:
            room_id = await self.find_dm_room_with_token(user_id, access_token)
            if room_id:
                logger.info("找到已有 DM: %s -> %s", user_id[:20], room_id)
        
        if not room_id:
            room_id = await self.create_dm_with_token(user_id, access_token)
            if room_id:
                logger.info("创建新 DM: %s -> %s", user_id[:20], room_id)
        
        if not room_id:
            logger.error("无法创建或找到 DM: %s", user_id[:20])
            return None
        
        # 保存映射关系
        mapping[user_id] = room_id
        try:
            os.makedirs(os.path.dirname(DM_MAPPING_FILE), exist_ok=True)
            with open(DM_MAPPING_FILE, "w") as f:
                json.dump(mapping, f)
            logger.info("已保存 DM 映射: %s -> %s", user_id[:20], room_id)
        except Exception as e:
            logger.warning("保存 DM 映射失败: %s", e)
        
        # 构建卡片内容
        content = build_matrix_card_content(semantic_type, payload, card_id)
        
        # 通过 HTTP API 发送
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {access_token}"}
                txn_id = f"tianshu_card_{int(asyncio.get_event_loop().time() * 1000)}"
                encoded_room_id = urllib.parse.quote(room_id, safe='')
                url = f"{self._homeserver}/_matrix/client/r0/rooms/{encoded_room_id}/send/m.room.message/{txn_id}"
                async with session.put(url, headers=headers, json=content) as resp:
                    if resp.status < 300:
                        data = await resp.json()
                        event_id = data.get("event_id")
                        logger.info("发送卡片消息成功: room=%s event=%s semantic_type=%s", 
                                   room_id, event_id[:16] if event_id else "N/A", semantic_type)
                        return event_id
                    else:
                        text = await resp.text()
                        logger.error("发送卡片消息失败: %s %s", resp.status, text[:200])
                        return None
        except Exception as e:
            logger.exception("发送卡片消息异常: %s", e)
            return None

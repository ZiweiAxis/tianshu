# @diting 审批回复监听器
# 独立运行 Matrix sync 监听 @diting 发送的审批消息的回复
# 当用户在 DM 中回复"批准"/"拒绝"时，调用谛听的 /cheq/approve API

import asyncio
import aiohttp
import logging
import os
from typing import Optional, Callable, Awaitable

from src.config import (
    MATRIX_HOMESERVER,
    DITING_MATRIX_TOKEN,
)
from src.core.approval_reply import (
    lookup_by_reply_to,
    consume_approval_reply,
    remove_from_pending,
)

logger = logging.getLogger(__name__)

# 谛听 API 地址
DITING_API_BASE = os.getenv("DITING_CHAIN_URL", "http://diting:8080/chain").replace("/chain", "")


class DitingApprovalListener:
    """@diting 审批回复监听器：监听 Matrix DM 中对审批消息的回复"""
    
    def __init__(self):
        self._homeserver = MATRIX_HOMESERVER
        self._token = DITING_MATRIX_TOKEN
        self._user_id: Optional[str] = None
        self._running = False
        self._sync_task: Optional[asyncio.Task] = None
        
    async def start(self) -> bool:
        """启动监听器"""
        if not self._homeserver or not self._token:
            logger.warning("DitingApprovalListener: 缺少配置，跳过启动")
            return False
            
        # 获取 @diting 的 user_id
        domain = self._homeserver.replace("http://", "").replace("https://", "").rstrip("/")
        if ":" in domain:
            domain = domain.rsplit(":", 1)[0]
        self._user_id = f"@diting:{domain}"
        
        logger.info("DitingApprovalListener: 启动监听 %s", self._user_id)
        self._running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        return True
    
    async def stop(self) -> None:
        """停止监听器"""
        self._running = False
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("DitingApprovalListener: 已停止")
    
    async def _sync_loop(self) -> None:
        """Matrix sync 循环"""
        logger.info("[DitingApprovalListener] sync 循环开始")
        backoff = 2.0
        max_backoff = 60.0
        next_batch = ""
        first_sync = True  # 第一次同步标志
        
        while self._running:
            try:
                async with aiohttp.ClientSession() as session:
                    params = {
                        "timeout": 30000,
                        # 第一次同步获取所有房间，之后增量获取
                        "full_state": "true" if first_sync else "false",
                    }
                    first_sync = False  # 之后使用增量同步
                    if next_batch:
                        params["since"] = next_batch
                    
                    headers = {"Authorization": f"Bearer {self._token}"}
                    
                    async with session.get(
                        f"{self._homeserver}/_matrix/client/r0/sync",
                        params=params,
                        headers=headers,
                    ) as resp:
                        if resp.status != 200:
                            logger.warning("[DitingApprovalListener] sync 返回 %s", resp.status)
                            await asyncio.sleep(min(backoff, max_backoff))
                            backoff = min(backoff * 2, max_backoff)
                            continue
                        
                        data = await resp.json()
                        next_batch = data.get("next_batch", "")
                        backoff = 2.0
                        
                        # 第一次同步时，主动获取所有房间列表
                        if first_sync:
                            try:
                                async with session.get(
                                    f"{self._homeserver}/_matrix/client/r0/joined_rooms",
                                    headers=headers,
                                ) as resp_rooms:
                                    if resp_rooms.status == 200:
                                        data_rooms = await resp_rooms.json()
                                        all_rooms = data_rooms.get("joined_rooms", [])
                                        logger.info("[DitingApprovalListener] 初始房间列表: %d 个: %s", 
                                                   len(all_rooms), all_rooms[:5])
                            except Exception as e:
                                logger.warning("[DitingApprovalListener] 获取房间列表失败: %s", e)
                        
                        # 处理已加入房间的消息
                        rooms_data = data.get("rooms") or {}
                        join_rooms = rooms_data.get("join", {})
                        logger.info("[DitingApprovalListener] 当前加入房间数: %d, 房间列表: %s", 
                                    len(join_rooms), list(join_rooms.keys())[:5])
                        
                        for room_id, room_data in join_rooms.items():
                            timeline = room_data.get("timeline") or {}
                            events = timeline.get("events", [])
                            
                            for event in events:
                                await self._handle_event(room_id, event)
                                
            except asyncio.CancelledError:
                logger.info("[DitingApprovalListener] 任务取消")
                break
            except aiohttp.ClientError as e:
                logger.warning("[DitingApprovalListener] 网络异常: %s", e)
                await asyncio.sleep(min(backoff, max_backoff))
                backoff = min(backoff * 2, max_backoff)
            except Exception as e:
                logger.warning("[DitingApprovalListener] 异常: %s", e)
                await asyncio.sleep(min(backoff, max_backoff))
                backoff = min(backoff * 2, max_backoff)
        
        logger.info("[DitingApprovalListener] sync 循环结束")
    
    async def _handle_event(self, room_id: str, event: dict) -> None:
        """处理收到的消息事件"""
        event_type = event.get("type")
        if event_type != "m.room.message":
            return
        
        # 跳过自己发的消息
        sender = event.get("sender", "")
        if sender == self._user_id:
            return
        
        content = event.get("content", {})
        body = content.get("body", "").strip().lower()
        msgtype = content.get("msgtype", "m.text")
        
        # 获取 in_reply_to
        in_reply_to = ""
        if content.get("m.in_reply_to"):
            in_reply_to = content["m.in_reply_to"].get("event_id", "")
        
        logger.info("[DitingApprovalListener] 收到消息: room=%s sender=%s body=%s in_reply_to=%s",
                    room_id, sender, body[:30] if body else "", in_reply_to)
        
        # 检查是否为审批回复
        if msgtype != "m.text" or not body:
            return
        
        # 解析审批操作
        approved = None
        is_approve_all = False
        
        if body in ("批准", "approve", "ok", "y", "yes"):
            approved = True
        elif body in ("批准所有", "批准全部", "approve all", "yes all"):
            approved = True
            is_approve_all = True
        elif body in ("拒绝", "reject", "deny", "n", "no"):
            approved = False
        else:
            # 尝试解析 "批准 <ID>" 格式
            import re
            match = re.match(r"^(批准|approve|ok|y|yes)\s+([0-9a-f-]+)", body, re.IGNORECASE)
            if match:
                approved = True
        
        if approved is None:
            logger.debug("[DitingApprovalListener] 非审批命令，跳过")
            return
        
        # 调用谛听 API（支持通过 in_reply_to 或房间内最后一条待审批）
        await self._process_approval(room_id, sender, in_reply_to, approved, is_approve_all)
    
    async def _process_approval(
        self,
        room_id: str,
        sender: str,
        in_reply_to: str,
        approved: bool,
        is_approve_all: bool,
    ) -> None:
        """处理审批操作"""
        cheq_ids = []
        
        if is_approve_all:
            # 批准所有
            from src.core.approval_reply import get_all_pending_global
            all_pending = get_all_pending_global()
            cheq_ids = [cheq_id for cheq_id, _ in all_pending]
            logger.info("[DitingApprovalListener] 批准所有: %d 个", len(cheq_ids))
        elif in_reply_to:
            # 通过 in_reply_to 查找
            result = lookup_by_reply_to(room_id, in_reply_to)
            if result:
                cheq_id, base_url = result
                cheq_ids = [cheq_id]
                logger.info("[DitingApprovalListener] 通过 in_reply_to 找到: %s", cheq_id[:16])
            else:
                logger.warning("[DitingApprovalListener] 未找到对应的审批请求: in_reply_to=%s", in_reply_to)
        else:
            # 没有 in_reply_to，尝试获取该房间最后一条待审批
            from src.core.approval_reply import get_last_pending
            result = get_last_pending(room_id)
            if result:
                cheq_id, base_url = result
                cheq_ids = [cheq_id]
                logger.info("[DitingApprovalListener] 通过房间最后待审批找到: %s", cheq_id[:16])
            else:
                logger.warning("[DitingApprovalListener] 该房间无待审批请求: room_id=%s", room_id)
        
        if not cheq_ids:
            return
        
        # 调用谛听 API
        results = []
        for cheq_id in cheq_ids:
            url = f"{DITING_API_BASE}/cheq/approve?id={cheq_id}&approved={'true' if approved else 'false'}"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status < 300:
                            remove_from_pending(room_id, cheq_id)
                            results.append(f"{cheq_id[:8]}...")
                            logger.info("DitingApprovalListener: 审批成功 cheq_id=%s approved=%s", cheq_id, approved)
                        else:
                            logger.warning("DitingApprovalListener: 谛听返回错误状态: %s", resp.status)
            except Exception as e:
                logger.warning("DitingApprovalListener: 调用谛听失败: %s", e)
        
        # 发送确认消息
        if results:
            msg = f"✅ 已{'批准' if approved else '拒绝'} {len(results)} 个请求: {', '.join(results)}"
            await self._send_message(room_id, msg)
    
    async def _send_message(self, room_id: str, body: str) -> None:
        """发送消息到房间"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {self._token}"}
                content = {"msgtype": "m.text", "body": body}
                await session.put(
                    f"{self._homeserver}/_matrix/client/r0/rooms/{room_id}/send/m.room.message",
                    headers=headers,
                    json=content,
                )
        except Exception as e:
            logger.warning("[DitingApprovalListener] 发送确认消息失败: %s", e)


# 全局实例
_listener: Optional[DitingApprovalListener] = None


async def start_diting_listener() -> bool:
    """启动 @diting 审批监听器"""
    global _listener
    if _listener:
        logger.warning("DitingApprovalListener 已启动")
        return True
    
    _listener = DitingApprovalListener()
    return await _listener.start()


async def stop_diting_listener() -> None:
    """停止 @diting 审批监听器"""
    global _listener
    if _listener:
        await _listener.stop()
        _listener = None

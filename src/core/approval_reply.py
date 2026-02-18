# 审批消息与「回复即批准」：记录投递到 Matrix 的审批 event_id → cheq_id，供 channel bot 收到回复时代调谛听

from typing import Optional, Tuple, List
import time

# (room_id, event_id) -> (request_id/cheq_id, gateway_base_url, created_at)
_store: dict = {}
# 待审批队列：room_id -> [ (cheq_id, gateway_base_url, created_at), ... ] （按时间正序，最早的在前）
_pending_queue: dict = {}
# 保留最近 1 小时
_TTL_SEC = 3600


def record_approval_message_debug(room_id: str, event_id: str, request_id: str, gateway_base_url: str) -> None:
    """投递审批消息到 Matrix 后调用，记录 event_id 与 cheq_id 的对应关系。"""
    if room_id and event_id and request_id:
        _store[(room_id, event_id)] = (request_id, (gateway_base_url or "").rstrip("/"), time.time())
        # 加入待审批队列
        if room_id not in _pending_queue:
            _pending_queue[room_id] = []
        _pending_queue[room_id].append((request_id, (gateway_base_url or "").rstrip("/"), time.time()))


def lookup_by_reply_to(room_id: str, in_reply_to_event_id: str) -> Optional[Tuple[str, str]]:
    """根据「回复的目标 event_id」查 cheq_id 与 gateway_base_url；过期条目会删除并不返回。"""
    now = time.time()
    key = (room_id, in_reply_to_event_id)
    if key not in _store:
        return None
    request_id, gateway_base_url, created = _store[key]
    if now - created > _TTL_SEC:
        del _store[key]
        return None
    return (request_id, gateway_base_url)


def get_last_pending(room_id: str) -> Optional[Tuple[str, str]]:
    """获取指定房间最后一条待审批请求。"""
    now = time.time()
    queue = _pending_queue.get(room_id, [])
    # 倒序查找最后一个未过期的
    for cheq_id, base_url, created in reversed(queue):
        if now - created <= _TTL_SEC:
            return (cheq_id, base_url)
    return None


def get_all_pending(room_id: str) -> List[Tuple[str, str]]:
    """获取指定房间所有待审批请求。"""
    now = time.time()
    queue = _pending_queue.get(room_id, [])
    result = []
    for cheq_id, base_url, created in queue:
        if now - created <= _TTL_SEC:
            result.append((cheq_id, base_url))
    return result


def consume_approval_reply(room_id: str, event_id: str) -> None:
    """批准/拒绝已处理，可移除记录（避免同一回复被重复处理）。"""
    _store.pop((room_id, event_id), None)


def remove_from_pending(room_id: str, cheq_id: str) -> None:
    """从待审批队列中移除指定 CHEQ ID。"""
    queue = _pending_queue.get(room_id, [])
    _pending_queue[room_id] = [(cid, url, t) for cid, url, t in queue if cid != cheq_id]


def get_last_pending_global() -> Optional[Tuple[str, str]]:
    """获取任意房间最后一条待审批请求（全局查找）。"""
    now = time.time()
    # 遍历所有 pending queue
    for room_id, queue in _pending_queue.items():
        for cheq_id, base_url, created in reversed(queue):
            if now - created <= _TTL_SEC:
                return (cheq_id, base_url)
    return None


def get_all_pending_global() -> List[Tuple[str, str]]:
    """获取所有待审批请求（全局查找）。"""
    now = time.time()
    result = []
    for room_id, queue in _pending_queue.items():
        for cheq_id, base_url, created in queue:
            if now - created <= _TTL_SEC:
                result.append((cheq_id, base_url))
    return result


def record_approval_message(room_id: str, event_id: str, request_id: str, gateway_base_url: str) -> None:
    """投递审批消息到 Matrix 后调用，记录 event_id 与 cheq_id 的对应关系。"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[record_approval] 记录审批: room=%s, event=%s, cheq=%s", room_id, event_id, request_id)
    record_approval_message_debug(room_id, event_id, request_id, gateway_base_url)
    logger.info("[record_approval] 记录后 store size=%d, queue size=%d", len(_store), len(_pending_queue))

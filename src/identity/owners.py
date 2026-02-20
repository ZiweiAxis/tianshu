# E3-S1：人类/Owner 登记与解析
# 可登记人类身份（邮箱、工号、飞书 user_id）；按标识检索唯一匹配或候选列表；Owner 存在性可查询
# E11-S4：读写经 storage 后端

import uuid
from typing import Any, Dict, List, Optional

BUCKET_OWNERS = "owners"
BUCKET_OWNERS_INDEX = "owners_index"  # key = "type:value", value = { "owner_id": "..." }


def _store():
    from src.storage import get_backend
    return get_backend()


def _index_key(identifier_type: str, identifier_value: str) -> str:
    return f"{identifier_type.strip().lower()}:{(identifier_value or '').strip()}"


def register_owner(
    identifier_type: str,
    identifier_value: str,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """
    登记人类/Owner。identifier_type 如 email、employee_id、feishu_user_id。
    若该 (type, value) 已存在则返回已有 owner_id；否则创建并返回新 owner_id。
    """
    store = _store()
    ival = (identifier_value or "").strip()
    if not ival:
        raise ValueError("identifier_value 不能为空")
    key = _index_key(identifier_type, ival)
    existing = store.get(BUCKET_OWNERS_INDEX, key)
    if existing:
        return existing["owner_id"]
    owner_id = f"owner-{uuid.uuid4().hex[:8]}"
    store.set(BUCKET_OWNERS, owner_id, {
        "owner_id": owner_id,
        "identifiers": {identifier_type: identifier_value},
        "extra": extra or {},
    })
    store.set(BUCKET_OWNERS_INDEX, key, {"owner_id": owner_id})
    return owner_id


def add_owner_identifier(owner_id: str, identifier_type: str, identifier_value: str) -> bool:
    """为已存在 Owner 追加标识（如同一人多个邮箱）。"""
    store = _store()
    o = store.get(BUCKET_OWNERS, owner_id)
    if not o:
        return False
    key = _index_key(identifier_type, (identifier_value or "").strip())
    existing = store.get(BUCKET_OWNERS_INDEX, key)
    if existing and existing.get("owner_id") != owner_id:
        return False
    o = dict(o)
    o.setdefault("identifiers", {})[identifier_type] = identifier_value
    store.set(BUCKET_OWNERS, owner_id, o)
    store.set(BUCKET_OWNERS_INDEX, key, {"owner_id": owner_id})
    return True


def lookup_owners(
    identifier_type: Optional[str] = None,
    identifier_value: Optional[str] = None,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    按标识检索。若 (identifier_type, identifier_value) 精确匹配则返回单条；
    若仅 query 则按任意标识值模糊匹配返回候选列表。
    """
    store = _store()
    if identifier_type is not None and identifier_value is not None:
        key = _index_key(identifier_type, identifier_value)
        existing = store.get(BUCKET_OWNERS_INDEX, key)
        if existing:
            o = store.get(BUCKET_OWNERS, existing["owner_id"])
            return [o] if o else []
        return []
    if query:
        q = (query or "").strip().lower()
        candidates = []
        for owner_id in store.list_keys(BUCKET_OWNERS):
            data = store.get(BUCKET_OWNERS, owner_id)
            if not data:
                continue
            for _t, val in (data.get("identifiers") or {}).items():
                if val and q in str(val).lower():
                    candidates.append(data)
                    break
        return candidates
    return [store.get(BUCKET_OWNERS, k) for k in store.list_keys(BUCKET_OWNERS) if store.get(BUCKET_OWNERS, k)]


def owner_exists(identifier_type: str, identifier_value: str) -> bool:
    """Agent 注册流程可调用：拟绑定 Owner 是否存在。"""
    key = _index_key(identifier_type, identifier_value)
    return _store().get(BUCKET_OWNERS_INDEX, key) is not None


def get_owner(owner_id: str) -> Optional[Dict[str, Any]]:
    """按 owner_id 取 Owner 信息。"""
    v = _store().get(BUCKET_OWNERS, owner_id)
    return dict(v) if v else None


# E8-S3：Owner 收告警/通知需投递到其飞书会话；登记 Owner 的渠道 receive_id
BUCKET_OWNER_CHANNEL = "owner_channel"  # key=owner_id, value={ receive_id, receive_id_type }


def set_owner_channel(owner_id: str, receive_id: str, receive_id_type: str = "chat_id") -> bool:
    """登记 Owner 的飞书接收目标（chat_id 或 open_id），用于推送告警/通知。"""
    if not get_owner(owner_id):
        return False
    _store().set(BUCKET_OWNER_CHANNEL, owner_id, {"receive_id": receive_id, "receive_id_type": receive_id_type})
    return True


def get_owner_channel(owner_id: str) -> Optional[Dict[str, Any]]:
    """获取 Owner 的飞书接收目标，无则返回 None。"""
    v = _store().get(BUCKET_OWNER_CHANNEL, owner_id)
    return dict(v) if v else None


# Telegram 用户标识支持
def register_telegram_owner(telegram_user_id: str) -> str:
    """注册 Telegram 用户对应的 Owner"""
    return register_owner("telegram_user_id", telegram_user_id)


def lookup_telegram_owner(telegram_user_id: str) -> Optional[str]:
    """查询 Telegram 用户对应的 Owner"""
    results = lookup_owners("telegram_user_id", telegram_user_id)
    return results[0]["owner_id"] if results else None


def get_or_create_telegram_owner(telegram_user_id: str) -> str:
    """获取或创建 Telegram 用户对应的 Owner"""
    existing = lookup_telegram_owner(telegram_user_id)
    if existing:
        return existing
    return register_telegram_owner(telegram_user_id)

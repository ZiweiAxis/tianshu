# E020-S081: Owner 注册 API
# POST /api/v1/owners/register - 注册新 Owner

import logging
from typing import Any, Dict, Optional

import aiohttp.web

from config import ADMIN_TOKEN

logger = logging.getLogger(__name__)

BUCKET_OWNERS = "owners"


def _store():
    from storage import get_backend
    return get_backend()


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _verify_admin_token(request: aiohttp.web.Request) -> Optional[str]:
    """
    验证 Authorization header 中的 admin token。
    返回错误信息字符串，如果验证失败；返回 None 如果验证成功。
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return "缺少 Authorization header 或格式错误"
    
    token = auth_header[7:]  # 去掉 "Bearer " 前缀
    if token != ADMIN_TOKEN:
        return "无效的 admin token"
    
    return None


def _check_owner_exists(owner_id: str) -> bool:
    """检查 owner_id 是否已存在"""
    store = _store()
    return store.get(BUCKET_OWNERS, owner_id) is not None


async def owners_register_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """
    POST /api/v1/owners/register
    注册新 Owner（仅 admin 可调用）
    
    Request body:
    {
        "owner_id": "diting",
        "identities": {
            "system": {"type": "diting", "name": "Diting"}
        },
        "channels": []
    }
    
    Response:
    - 成功: {"ok": true, "owner_id": "..."}
    - 失败: {"ok": false, "error": "..."}
    """
    # 1. 验证 admin token
    auth_error = _verify_admin_token(request)
    if auth_error:
        logger.warning(f"Owner 注册失败 - 权限验证失败: {auth_error}")
        return aiohttp.web.json_response({"ok": False, "error": auth_error}, status=401)
    
    # 2. 解析请求体
    try:
        body = await request.json()
    except Exception as e:
        return aiohttp.web.json_response({"ok": False, "error": f"无效 JSON: {e}"}, status=400)
    
    # 3. 提取并验证必填字段
    owner_id = (body.get("owner_id") or "").strip()
    if not owner_id:
        return aiohttp.web.json_response({"ok": False, "error": "缺少 owner_id"}, status=400)
    
    # 4. 检查唯一性 - owner_id 不能已存在
    if _check_owner_exists(owner_id):
        return aiohttp.web.json_response({"ok": False, "error": f"Owner 已存在: {owner_id}"}, status=409)
    
    # 5. 获取可选字段
    identities = body.get("identities", {})
    channels = body.get("channels", [])
    extra = body.get("extra", {})
    
    # 6. 存储 Owner
    store = _store()
    now = _utc_now()
    owner_data: Dict[str, Any] = {
        "owner_id": owner_id,
        "identities": identities,
        "channels": channels,
        "extra": extra,
        "created_at": now,
        "updated_at": now,
    }
    
    # 7. 建立 identities 索引（如果提供了 identities）
    # 遍历 identities 建立反向索引，便于后续查询
    for identity_type, identity_data in identities.items():
        if isinstance(identity_data, dict):
            # 新结构: {"type": "diting", "name": "Diting"} 或 {"address": "xxx@email.com"}
            # 建立索引 key: identity_type:value
            if "type" in identity_data and "name" in identity_data:
                # 系统身份: type:name
                index_key = f"{identity_type}:{identity_data['type']}"
            elif "address" in identity_data:
                # 邮箱: email:address
                index_key = f"{identity_type}:{identity_data['address']}"
            elif "id" in identity_data:
                # 员工ID: employee:id
                index_key = f"{identity_type}:{identity_data['id']}"
            else:
                continue
            
            # 存储索引
            store.set("owners_index", index_key, {"owner_id": owner_id})
    
    store.set(BUCKET_OWNERS, owner_id, owner_data)
    
    logger.info(f"Owner 注册成功: {owner_id}")
    return aiohttp.web.json_response({
        "ok": True,
        "owner_id": owner_id,
        "message": "Owner 注册成功"
    })

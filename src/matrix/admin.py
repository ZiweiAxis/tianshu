# Synapse Admin API 调用
# 用于创建和管理 Matrix 用户

import hmac
import hashlib
import logging
import secrets
from typing import Optional, Tuple

import aiohttp

from src.config import (
    SYNAPSE_ADMIN_URL,
    SYNAPSE_ADMIN_SHARED_SECRET,
    MATRIX_HOMESERVER,
)

logger = logging.getLogger(__name__)


async def _get_admin_token() -> Optional[str]:
    """
    通过 shared_secret 获取 admin access_token
    返回 token 或 None
    """
    if not SYNAPSE_ADMIN_URL or not SYNAPSE_ADMIN_SHARED_SECRET:
        return None
    
    # 备用方案：直接使用密码登录获取 admin token
    # Synapse 中 admin 用户的密码通常就是 shared_secret
    try:
        login_url = f"{SYNAPSE_ADMIN_URL.replace('/_synapse/admin/v1/register', '')}/_matrix/client/v3/login"
        payload = {
            "type": "m.login.password",
            "identifier": {
                "type": "m.id.user",
                "user": "admin",
            },
            "password": SYNAPSE_ADMIN_SHARED_SECRET,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(login_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("access_token")
    except Exception as e:
        logger.warning("通过登录获取 admin token 失败: %s", e)
    
    # 原始方案：使用 HMAC 注册
    admin_url = f"{SYNAPSE_ADMIN_URL}/_synapse/admin/v1/register"
    
    async with aiohttp.ClientSession() as session:
        nonce = await _get_nonce(admin_url, session)
        if not nonce:
            return None
        
        # 使用 admin 用户登录获取 token
        mac = _generate_mac(nonce, "admin", SYNAPSE_ADMIN_SHARED_SECRET, admin=True)
        
        payload = {
            "username": "admin",
            "password": SYNAPSE_ADMIN_SHARED_SECRET,
            "admin": True,
            "nonce": nonce,
            "mac": mac,
        }
        
        try:
            async with session.post(admin_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("access_token")
        except Exception as e:
            logger.warning("获取 admin token 失败: %s", e)
    return None


async def generate_user_login_token(user_id: str) -> Optional[str]:
    """
    通过 Admin API 直接生成用户的登录 token（绕过密码登录限速）
    返回 token 或 None
    """
    if not SYNAPSE_ADMIN_URL or not SYNAPSE_ADMIN_SHARED_SECRET:
        return None
    
    # 直接获取 admin token（使用 shared_secret 作为密码）
    admin_token = None
    try:
        login_url = f"{SYNAPSE_ADMIN_URL.replace('/_synapse/admin/v1/register', '')}/_matrix/client/v3/login"
        payload = {
            "type": "m.login.password",
            "identifier": {
                "type": "m.id.user",
                "user": "admin",
            },
            "password": SYNAPSE_ADMIN_SHARED_SECRET,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(login_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    admin_token = data.get("access_token")
                else:
                    logger.warning("获取 admin token 失败 HTTP %s", resp.status)
    except Exception as e:
        logger.warning("获取 admin token 异常: %s", e)
    
    if not admin_token:
        logger.warning("无法获取 admin token")
        return None
    
    # 清理 user_id
    clean_user_id = user_id.lstrip("@")
    
    url = f"{SYNAPSE_ADMIN_URL}/_synapse/admin/v1/users/{clean_user_id}/login"
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json={}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("access_token")
                else:
                    text = await resp.text()
                    logger.warning("生成用户登录 token 失败 HTTP %s: %s", resp.status, text)
        except Exception as e:
            logger.warning("生成用户登录 token 异常: %s", e)
    return None


async def set_user_password(user_id: str, password: str) -> bool:
    """
    通过 Admin API 设置用户密码
    user_id: 完整的 Matrix 用户 ID（如 @diting:xyin.oicp.net）
    """
    if not SYNAPSE_ADMIN_URL:
        return False
    
    # 直接获取 admin token（使用 shared_secret 作为密码）
    admin_token = None
    try:
        login_url = f"{SYNAPSE_ADMIN_URL.replace('/_synapse/admin/v1/register', '')}/_matrix/client/v3/login"
        payload = {
            "type": "m.login.password",
            "identifier": {
                "type": "m.id.user",
                "user": "admin",
            },
            "password": SYNAPSE_ADMIN_SHARED_SECRET,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(login_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    admin_token = data.get("access_token")
    except Exception as e:
        logger.warning("获取 admin token 异常: %s", e)
    
    if not admin_token:
        # 备用：尝试用 _get_admin_token
        admin_token = await _get_admin_token()
    
    if not admin_token:
        logger.warning("无法获取 admin token")
        return False
    
    # user_id 应该是完整的 Matrix ID（如 @diting:xyin.oicp.net）
    # 不需要清理，直接 URL 编码
    import urllib.parse
    encoded_user_id = urllib.parse.quote(user_id, safe='')
    
    url = f"{SYNAPSE_ADMIN_URL}/_synapse/admin/v2/users/{encoded_user_id}"
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    payload = {
        "password": password,
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.put(url, json=payload, headers=headers) as resp:
                if resp.status in (200, 201):
                    logger.info("用户密码设置成功: %s", user_id)
                    return True
                else:
                    text = await resp.text()
                    logger.warning("设置用户密码失败 HTTP %s: %s", resp.status, text)
                    return False
        except Exception as e:
            logger.warning("设置用户密码异常: %s", e)
            return False


async def _get_nonce(admin_url: str, session: aiohttp.ClientSession) -> str:
    """获取 Synapse Admin API 的 nonce"""
    try:
        async with session.get(admin_url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("nonce", "")
    except Exception as e:
        logger.warning("获取 nonce 失败: %s", e)
    return ""


def _generate_mac(nonce: str, username: str, password: str, admin: bool = False, user_type: Optional[str] = None) -> str:
    """
    使用 shared_secret 对注册信息进行 HMAC-SHA1 签名
    消息格式: nonce + NUL + username + NUL + password + NUL + admin/notadmin (+ NUL + user_type)
    """
    global SYNAPSE_ADMIN_SHARED_SECRET
    secret = SYNAPSE_ADMIN_SHARED_SECRET or ""
    
    mac = hmac.new(
        key=secret.encode('utf-8'),
        digestmod=hashlib.sha1,
    )
    mac.update(nonce.encode('utf-8'))
    mac.update(b"\x00")
    mac.update(username.encode('utf-8'))
    mac.update(b"\x00")
    mac.update(password.encode('utf-8'))
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    
    if user_type:
        mac.update(b"\x00")
        mac.update(user_type.encode('utf-8'))
    
    return mac.hexdigest()


async def create_matrix_user(
    username: str,
    password: Optional[str] = None,
    displayname: Optional[str] = None,
    admin: bool = False,
    fixed_password: bool = False,
) -> Tuple[str, str]:
    """
    调用 Synapse Admin API 创建 Matrix 用户
    返回: (user_id, access_token)
    如果用户已存在，返回 (user_id, None)
    
    fixed_password: 如果为 True，使用固定密码格式，便于后续登录获取 token
    """
    if not SYNAPSE_ADMIN_URL or not SYNAPSE_ADMIN_SHARED_SECRET:
        raise ValueError("SYNAPSE_ADMIN_URL 或 SYNAPSE_ADMIN_SHARED_SECRET 未配置")

    admin_url = f"{SYNAPSE_ADMIN_URL}/_synapse/admin/v1/register"
    
    # 生成随机密码或使用固定密码
    if password is None:
        if fixed_password:
            # 使用固定密码格式，便于后续登录获取 token
            password = f"{username}_tianshu_pwd"
        else:
            password = secrets.token_hex(16)
    
    # 清理 username（不能包含 @ 或 :）
    clean_username = username.lstrip("@").split(":")[0]
    
    async with aiohttp.ClientSession() as session:
        # 首先获取 nonce
        nonce = await _get_nonce(admin_url, session)
        if not nonce:
            raise Exception("无法获取 nonce")
        
        # 生成 MAC 签名
        mac = _generate_mac(nonce, clean_username, password, admin)
        
        payload = {
            "username": clean_username,
            "password": password,
            "displayname": displayname or clean_username,
            "admin": admin,
            "must_change_password": False,
            "nonce": nonce,
            "mac": mac,
        }
        
        try:
            async with session.post(admin_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user_id = data.get("user_id")
                    access_token = data.get("access_token")
                    logger.info("创建 Matrix 用户成功: %s", user_id)
                    return user_id, access_token
                elif resp.status in (400, 401):
                    # 用户已存在，尝试通过登录获取 token
                    error_data = await resp.json()
                    error_msg = str(error_data.get("error", ""))
                    if "already exists" in error_msg or "User ID already taken" in error_msg:
                        logger.info("用户 %s 已存在，尝试通过登录获取 token", clean_username)
                        # 尝试使用密码登录获取 token
                        if fixed_password:
                            try:
                                return await _get_user_token(clean_username, password)
                            except Exception as login_err:
                                logger.warning("登录获取 token 失败: %s", login_err)
                        # 返回用户ID但 token 为 None
                        domain = MATRIX_HOMESERVER.replace("http://", "").replace("https://", "").rstrip("/")
                        # 去掉端口
                        if ":" in domain:
                            domain = domain.rsplit(":", 1)[0]
                        existing_user_id = f"@{clean_username}:{domain}"
                        return existing_user_id, None
                    else:
                        raise Exception(f"创建用户失败: {error_data}")
                else:
                    text = await resp.text()
                    raise Exception(f"创建用户失败 HTTP {resp.status}: {text}")
        except aiohttp.ClientError as e:
            logger.exception("Admin API 调用失败: %s", e)
            raise


async def _get_user_token(username: str, password: str) -> Tuple[str, str]:
    """
    通过密码登录获取用户 token
    返回: (user_id, access_token)
    """
    if not MATRIX_HOMESERVER:
        raise ValueError("MATRIX_HOMESERVER 未配置")
    
    login_url = f"{MATRIX_HOMESERVER}/_matrix/client/v3/login"
    
    payload = {
        "type": "m.login.password",
        "identifier": {
            "type": "m.id.user",
            "user": username,
        },
        "password": password,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(login_url, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                user_id = data.get("user_id")
                access_token = data.get("access_token")
                logger.info("用户登录成功: %s", user_id)
                return user_id, access_token
            else:
                text = await resp.text()
                raise Exception(f"用户登录失败 HTTP {resp.status}: {text}")


async def ensure_diting_user() -> Tuple[str, str]:
    """
    确保谛听用户存在，不存在则创建
    返回: (user_id, access_token)
    """
    from src.config import MATRIX_HOMESERVER
    
    # 从 homeserver 提取域名 (去掉 http:// 和端口)
    homeserver = MATRIX_HOMESERVER or "http://xyin.oicp.net:8008"
    # 去掉 http:// 或 https://
    domain = homeserver.replace("http://", "").replace("https://", "")
    # 去掉端口
    if ":" in domain:
        domain = domain.rsplit(":", 1)[0]
    
    username = "diting"
    displayname = "谛听"
    fixed_password = f"{username}_tianshu_pwd"
    
    # 先尝试通过 Admin API 设置密码（如果用户已存在，这会重置密码）
    try:
        full_user_id = f"@{username}:{domain}"
        await set_user_password(full_user_id, fixed_password)
    except Exception as e:
        logger.warning("设置谛听用户密码失败: %s", e)
    
    # 尝试创建用户或登录获取 token
    try:
        user_id, token = await create_matrix_user(username, displayname=displayname, fixed_password=True)
        
        # 如果用户已存在但没有 token，尝试登录获取
        if user_id and not token:
            # 优先方案：使用 Admin API 直接生成登录 token（绕过密码登录限速）
            try:
                token = await generate_user_login_token(user_id)
                if token:
                    logger.info("通过 Admin API 生成谛听登录 token 成功")
                    return user_id, token
            except Exception as gen_err:
                logger.warning("通过 Admin API 生成 token 失败: %s", gen_err)
            
            # 后备方案：尝试使用固定密码登录
            try:
                token = await _get_user_token(username, fixed_password)
                if token:
                    return user_id, token
            except Exception as login_err:
                logger.warning("登录获取 token 失败: %s", login_err)
            
            logger.warning("谛听用户已存在但无法获取 token，请检查配置")
            return user_id, None
            
        return user_id, token
    except Exception as e:
        logger.error("创建谛听用户失败: %s", e)
        raise


async def ensure_agent_user(agent_id: str) -> Tuple[str, str]:
    """
    确保 Agent 用户存在，不存在则创建
    返回: (user_id, access_token)
    """
    from src.config import MATRIX_HOMESERVER
    
    # 从 homeserver 提取域名
    homeserver = MATRIX_HOMESERVER or "xyin.oicp.net:8008"
    
    username = f"agent-{agent_id}"
    displayname = f"Agent {agent_id}"
    
    try:
        user_id, token = await create_matrix_user(username, displayname=displayname, fixed_password=True)
        
        # 如果用户已存在但没有 token
        if user_id and not token:
            logger.warning("Agent 用户 %s 已存在但无法获取 token", username)
            
        return user_id, token
    except Exception as e:
        logger.error("创建 Agent 用户失败: %s", e)
        raise

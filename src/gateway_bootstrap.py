# 网关用户自举：无 MATRIX_GATEWAY_TOKEN 时通过 Synapse Admin 注册 API 自动创建并持久化 token
# 依赖：Synapse 配置了 registration_shared_secret，本模块与天枢共用同一 REGISTRATION_SHARED_SECRET

import hmac
import hashlib
import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# 默认网关本地用户名（与 MATRIX_GATEWAY_USER @gateway:matrix.local 对应）
GATEWAY_USERNAME = "gateway"
GATEWAY_PASSWORD = "gateway-ziwei-bootstrap"


def _generate_mac(nonce: str, username: str, password: str, admin: str, shared_secret: str) -> str:
    # Synapse: HMAC-SHA1(key=secret, content=nonce\\0user\\0password\\0admin) 无末尾 NUL
    mac = hmac.new(
        shared_secret.encode("utf-8"),
        digestmod=hashlib.sha1,
    )
    parts = (nonce, username, password, admin)
    for i, part in enumerate(parts):
        mac.update(part.encode("utf-8"))
        if i < len(parts) - 1:
            mac.update(b"\x00")
    return mac.hexdigest()


def bootstrap_gateway_token() -> bool:
    """
    若 MATRIX_GATEWAY_TOKEN 未设置：先尝试从文件读取；否则用 REGISTRATION_SHARED_SECRET 向 Synapse 注册
    并写入 token 文件。成功后设置 os.environ["MATRIX_GATEWAY_TOKEN"]，返回 True。
    若已配置 token 或无需自举，返回 True；失败返回 False。
    """
    if os.getenv("MATRIX_GATEWAY_TOKEN"):
        return True

    token_file = os.getenv("MATRIX_GATEWAY_TOKEN_FILE", "/data/gateway_token")
    if os.path.isfile(token_file):
        try:
            with open(token_file) as f:
                token = f.read().strip()
            if token:
                os.environ["MATRIX_GATEWAY_TOKEN"] = token
                logger.info("已从 %s 加载网关 token", token_file)
                return True
        except OSError as e:
            logger.warning("读取网关 token 文件失败: %s", e)

    secret = os.getenv("REGISTRATION_SHARED_SECRET") or os.getenv("SYNAPSE_REGISTRATION_SHARED_SECRET")
    if not secret:
        logger.warning("未配置 MATRIX_GATEWAY_TOKEN 且无 REGISTRATION_SHARED_SECRET，网关需手动配置")
        return False

    base = (os.getenv("MATRIX_HOMESERVER") or "").rstrip("/")
    if not base:
        logger.error("MATRIX_HOMESERVER 未设置，无法调用 Synapse 注册")
        return False

    register_url = f"{base}/_synapse/admin/v1/register"
    last_err = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(register_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            nonce = data.get("nonce")
            break
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < 4:
                import time
                time.sleep(3 * (attempt + 1))
                continue
        except Exception as e:
            logger.error("获取注册 nonce 失败: %s", e)
            return False
    else:
        logger.error("请求 Synapse 失败（已重试）: %s", last_err)
        return False
    if not nonce:
        logger.error("Synapse 未返回 nonce，可能未配置 registration_shared_secret")
        return False

    admin_flag = "notadmin"
    mac = _generate_mac(nonce, GATEWAY_USERNAME, GATEWAY_PASSWORD, admin_flag, secret)
    body = {
        "nonce": nonce,
        "username": GATEWAY_USERNAME,
        "password": GATEWAY_PASSWORD,
        "admin": False,
        "mac": mac,
    }
    body_bytes = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        register_url,
        data=body_bytes,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        token = data.get("access_token")
        if not token:
            logger.error("注册响应中无 access_token: %s", data)
            return False
        os.environ["MATRIX_GATEWAY_TOKEN"] = token
        logger.info("已通过 Synapse 注册 API 创建网关用户 @%s:matrix.local", GATEWAY_USERNAME)
        try:
            os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
            with open(token_file, "w") as f:
                f.write(token)
            logger.info("已写入网关 token 到 %s", token_file)
        except OSError as e:
            logger.warning("写入 token 文件失败（下次启动将重新注册）: %s", e)
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        if "already exists" in body or "M_USER_IN_USE" in body:
            logger.warning("网关用户已存在，请将已有 access_token 写入 %s 或设置 MATRIX_GATEWAY_TOKEN", token_file)
        else:
            logger.error("注册网关用户失败: %s %s", e.code, body)
        return False
    except Exception as e:
        logger.error("注册网关用户失败: %s", e)
        return False

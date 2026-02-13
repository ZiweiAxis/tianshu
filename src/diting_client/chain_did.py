# I-018：天枢对接谛听链上 DID 接口
# 注册时写入 DID 文档；心跳时可选查询验真（GET）；不阻塞主流程，失败仅打日志

import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import aiohttp

from src.config import DITING_CHAIN_URL

logger = logging.getLogger(__name__)

# DID 命名：did:ziwei:<链标识>:<agent_id>，与谛听 I-016 约定一致
DID_PREFIX = "did:ziwei:local:"


def _base() -> str:
    base = (DITING_CHAIN_URL or "").strip().rstrip("/")
    return base


def agent_id_to_did(agent_id: str) -> str:
    """将天枢 agent_id 转为链上 DID（与谛听链子模块约定一致）。"""
    return f"{DID_PREFIX}{agent_id}"


async def register_did_on_chain(
    agent_id: str,
    owner_id: str,
    public_key: str = "",
    environment_fingerprint: str = "",
) -> bool:
    """
    向谛听链子模块注册/更新 DID 文档（POST /chain/did/register）。
    若未配置 DITING_CHAIN_URL 则跳过并返回 True。
    public_key / environment_fingerprint 可后续由智能体上报补齐；MVP 可为占位。
    """
    base = _base()
    if not base:
        logger.debug("未配置 DITING_CHAIN_URL，跳过链上 DID 注册")
        return True
    did = agent_id_to_did(agent_id)
    payload = {
        "id": did,
        "publicKey": public_key or f"tianshu-pk-{agent_id}",
        "environmentFingerprint": environment_fingerprint or "",
        "owner": owner_id,
        "status": "active",
    }
    url = f"{base}/did/register"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 200 and resp.status < 300:
                    logger.info("链上 DID 注册成功 agent_id=%s did=%s", agent_id, did)
                    return True
                logger.warning(
                    "谛听 DID 注册返回 %s: %s",
                    resp.status,
                    await resp.text(),
                )
                return False
    except Exception as e:
        logger.exception("链上 DID 注册失败 agent_id=%s: %s", agent_id, e)
        return False


async def get_did_from_chain(did: str) -> Optional[Dict[str, Any]]:
    """
    从谛听链子模块查询 DID 文档（GET /chain/did/{did}）。
    若未配置 DITING_CHAIN_URL 或查询失败返回 None。
    """
    base = _base()
    if not base:
        return None
    url = f"{base}/did/{quote(did, safe='')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 404:
                    return None
                logger.debug("谛听 DID 查询 %s 返回 %s", did, resp.status)
                return None
    except Exception as e:
        logger.debug("链上 DID 查询失败 did=%s: %s", did, e)
        return None

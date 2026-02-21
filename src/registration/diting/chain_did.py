"""
链上 DID 注册模块
"""
import os
import logging
from typing import Dict, Any

import aiohttp

logger = logging.getLogger(__name__)

DITING_CHAIN_URL = os.getenv("DITING_CHAIN_URL", "http://diting:8080/chain")


async def register_did_on_chain(agent_id: str, owner_id: str) -> Dict[str, Any]:
    """
    在链上注册 DID
    
    Args:
        agent_id: Agent ID
        owner_id: Owner ID
    
    Returns:
        {"ok": True, "did": "did:agent:xxx"} 或 {"ok": False, "error": "..."}
    """
    url = f"{DITING_CHAIN_URL}/register"
    payload = {
        "agent_id": agent_id,
        "owner_id": owner_id,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return {"ok": True, "did": data.get("did", f"did:agent:{agent_id}")}
                else:
                    error_text = await response.text()
                    logger.error(f"链上DID注册失败: {response.status} - {error_text}")
                    return {"ok": False, "error": f"HTTP {response.status}: {error_text}"}
    except aiohttp.ClientError as e:
        logger.error(f"链上DID注册请求失败: {e}")
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.error(f"链上DID注册异常: {e}")
        return {"ok": False, "error": str(e)}

# E-P7 联调：天枢注册时调用谛听链上 DID，并可从谛听查询
# 需先启动谛听（chain.enabled: true），并设置 DITING_CHAIN_URL
# 运行: DITING_CHAIN_URL=http://127.0.0.1:8080/chain pytest tests/test_e2e_chain_did.py -v

import os
import urllib.request
import urllib.error
import json

import pytest

from src.registration.human_initiated import register_agent_by_human
from src.diting_client.chain_did import agent_id_to_did


def _get_did_from_diting(base_url: str, did: str) -> dict:
    """GET /chain/did/{did}，返回 JSON 或抛异常。"""
    from urllib.parse import quote
    url = f"{base_url.rstrip('/')}/did/{quote(did, safe='')}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


@pytest.mark.skipif(
    not os.getenv("DITING_CHAIN_URL"),
    reason="联调需设置 DITING_CHAIN_URL 并启动谛听（chain.enabled: true）",
)
def test_register_then_get_did_from_chain():
    """
    天枢注册 Agent（notify_diting=True）后，谛听链上应能查到对应 DID。
    前置：谛听已启动且 chain.enabled=true；DITING_CHAIN_URL 指向谛听 /chain 基址。
    """
    base = os.environ["DITING_CHAIN_URL"].strip().rstrip("/")
    r = register_agent_by_human(
        "email", "e2e-chain@example.com",
        agent_display_id="e2e-chain-bot",
        ensure_owner_registered=True,
        notify_diting=True,
    )
    assert r["ok"] is True, r.get("error", r)
    agent_id = r["agent_id"]
    did = agent_id_to_did(agent_id)

    try:
        doc = _get_did_from_diting(base, did)
    except urllib.error.URLError as e:
        pytest.skip(f"谛听不可达（请先启动 diting 并开启 chain）: {e}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pytest.fail(f"DID 未上链（谛听可能未收到注册或 chain 未启用）: {did}")
        raise

    assert doc.get("id") == did
    assert "publicKey" in doc
    assert doc.get("status") == "active"

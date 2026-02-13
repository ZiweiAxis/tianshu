# 端到端串联测试：不启真实 Matrix/飞书，内存存储下验证完整流程
# 参见 docs/e2e-testing.md

import pytest

from src.registration.human_initiated import register_agent_by_human
from src.identity import (
    register_owner,
    list_relationships_for_diting,
    get_agent_relationships,
    register_sub_agent,
    allocate_agent_id,
)
from src.approval.callback import handle_approval_callback, get_approval_result
from src.core.delivery_log import (
    record_delivery_start,
    record_delivery_done,
    query_delivery_log,
    get_delivery_status,
    STATUS_DELIVERED,
)
from src.ops.metrics import (
    get_owner_agent_list,
    get_collaboration_chains_summary,
    query_ops,
)


# ---------- 健康探针 ----------


@pytest.mark.asyncio
async def test_e2e_health_and_ready():
    """E2E：/health、/ready 返回 200 且 body 含约定字段。"""
    import aiohttp.web
    from aiohttp.test_utils import TestServer, TestClient
    from src.main import health, ready

    app = aiohttp.web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            r = await client.get("/health")
            assert r.status == 200
            data = await r.json()
            assert data.get("status") == "ok"

            r2 = await client.get("/ready")
            assert r2.status == 200
            data2 = await r2.json()
            assert data2.get("ready") is True


# ---------- 身份与注册 ----------


def test_e2e_identity_registration_flow():
    """E2E：登记 Owner → 人发起注册 Agent → 绑定 → 关系与 Owner 列表可见。"""
    owner_id = register_owner("email", "e2e-owner@example.com")
    assert owner_id.startswith("owner-")

    out = register_agent_by_human(
        "email", "e2e-owner@example.com",
        agent_display_id="e2e-agent-1",
        ensure_owner_registered=True,
        notify_diting=False,
    )
    assert out.get("ok") is True
    agent_id = out["agent_id"]
    assert agent_id.startswith("tianshu-agent-")

    rels = list_relationships_for_diting()
    assert any(r["agent_id"] == agent_id and r.get("owner_id") == owner_id for r in rels)

    agent_list = get_owner_agent_list(owner_id)
    assert agent_list.get("type") == "agent_list"
    assert any(a["agent_id"] == agent_id for a in agent_list.get("items", []))


# ---------- 审批回调 ----------


def test_e2e_approval_callback_flow():
    """E2E：审批回调写入结果 → 可查询；同一 request_id 幂等。"""
    request_id = "e2e-approval-req-1"
    first = handle_approval_callback(request_id, approved=True, approver_id="ou_approver", comment="同意")
    assert first.get("ok") is True
    assert first.get("result", {}).get("approved") is True

    got = get_approval_result(request_id)
    assert got is not None
    assert got["request_id"] == request_id
    assert got["approved"] is True

    second = handle_approval_callback(request_id, approved=False, approver_id="other", comment="")
    assert second.get("ok") is True
    assert second.get("idempotent") is True
    assert get_approval_result(request_id)["approved"] is True  # 仍为第一次结果


# ---------- 投递与日志 ----------


def test_e2e_delivery_log_flow():
    """E2E：记录投递开始 → 完成 → 查询日志与单条状态。"""
    target = {"channel": "feishu", "receive_id": "oc_e2e", "receive_id_type": "chat_id"}
    delivery_id = record_delivery_start("approval_request", target, payload_summary="E2E 审批")
    assert delivery_id

    ok = record_delivery_done(delivery_id, STATUS_DELIVERED, feishu_message_id="om_e2e")
    assert ok is True

    status = get_delivery_status(delivery_id)
    assert status is not None
    assert status["delivery_id"] == delivery_id
    assert status["status"] == STATUS_DELIVERED
    assert status.get("feishu_message_id") == "om_e2e"

    log = query_delivery_log(by_receive_id="oc_e2e", limit=10)
    assert log.get("total", 0) >= 1
    assert any(e["delivery_id"] == delivery_id for e in log.get("items", []))


# ---------- 协作链 ----------


def test_e2e_collaboration_chain_flow():
    """E2E：主 Agent 登记 Sub-agent → 查协作关系与摘要（协作链摘要仅含已绑定 Owner 的 Agent）。"""
    from src.identity import bind_agent_owner

    owner_id = register_owner("email", "e2e-chain-owner@example.com")
    main_id = allocate_agent_id(display_id="e2e-main-chain")
    sub_id = allocate_agent_id(display_id="e2e-sub-chain")
    assert bind_agent_owner(main_id, owner_id) is True
    assert register_sub_agent(main_id, sub_id) is True

    rel_main = get_agent_relationships(main_id)
    assert rel_main is not None
    assert sub_id in (rel_main.get("sub_agent_ids") or [])

    rel_sub = get_agent_relationships(sub_id)
    assert rel_sub is not None
    assert rel_sub.get("main_agent_id") == main_id

    summary = get_collaboration_chains_summary()
    assert summary.get("type") == "collaboration_chains_summary"
    assert len(summary.get("chains", [])) >= 1
    chain = next((c for c in summary["chains"] if c.get("main_agent_id") == main_id), None)
    assert chain is not None
    assert main_id in chain.get("agent_ids", [])
    assert sub_id in chain.get("agent_ids", [])

    ops_collab = query_ops(by_collaboration=True)
    assert ops_collab.get("type") == "collaboration_chains_summary"

# E4-S6、E4-S1、E4-S2、E4-S2b、E4-S3 验收

import pytest

from src.discovery import get_discovery_payload
from src.registration import (
    register_agent_by_human,
    check_owner_for_registration,
    list_owner_candidates,
    get_owner_info,
    create_pairing_code,
    submit_pairing_code,
)
from src.identity import get_agent_owner, get_agent, register_owner


def test_get_discovery_payload():
    """E4-S6：Agent 可解析端点信息。"""
    payload = get_discovery_payload()
    assert "matrix_homeserver" in payload
    assert "version" in payload


def test_register_agent_by_human_success():
    """E4-S1：提交 Owner 与 Agent 标识，校验后落库并绑定。"""
    r = register_agent_by_human("email", "alice@example.com", agent_display_id="bot-a")
    assert r["ok"] is True
    assert "agent_id" in r and r["agent_id"].startswith("tianshu-agent-")
    assert r["owner_id"].startswith("owner-")
    assert get_agent_owner(r["agent_id"]) == r["owner_id"]
    assert get_agent(r["agent_id"])["display_id"] == "bot-a"


def test_register_agent_by_human_display_id_unique():
    """E4-S1：Agent 标识全局唯一。"""
    register_agent_by_human("employee_id", "E99", agent_display_id="unique-bot")
    r = register_agent_by_human("employee_id", "E98", agent_display_id="unique-bot")
    assert r["ok"] is False
    assert "已存在" in r["error"]


def test_register_agent_by_human_owner_auto_register():
    """E4-S1：Owner 不存在时可先登记。"""
    r = register_agent_by_human("feishu_user_id", "ou_new_user", ensure_owner_registered=True)
    assert r["ok"] is True
    assert get_agent_owner(r["agent_id"]) == r["owner_id"]


def test_register_agent_by_human_notify_diting():
    """E4-S4：notify_diting=True 时不报错（未配置 URL 时跳过通知）。"""
    r = register_agent_by_human("email", "diting-notify@x.com", notify_diting=True)
    assert r["ok"] is True


# ---------- E4-S2 Owner 存在判断 ----------


def test_check_owner_for_registration_not_exists():
    """E4-S2：不存在时返回明确失败。"""
    r = check_owner_for_registration("email", "nonexistent@x.com")
    assert r["exists"] is False
    assert "不存在" in r["error"]


def test_check_owner_for_registration_exists():
    """E4-S2：存在时返回 owner_id，可进入后续步骤。"""
    register_owner("email", "owner-s2@x.com")
    r = check_owner_for_registration("email", "owner-s2@x.com")
    assert r["exists"] is True
    assert r["owner_id"].startswith("owner-")


def test_list_owner_candidates():
    """E4-S2b：模糊检索返回候选列表。"""
    register_owner("employee_id", "E100")
    register_owner("employee_id", "E101")
    r = list_owner_candidates("E10")
    assert "candidates" in r
    assert len(r["candidates"]) >= 2


def test_get_owner_info():
    """E4-S2b：确认后可根据 owner_id 查信息。"""
    oid = register_owner("email", "info@x.com")
    r = get_owner_info(oid)
    assert r["ok"] is True
    assert r["owner_id"] == oid


# ---------- E4-S3 配对码 ----------


def test_create_pairing_code_and_submit():
    """E4-S3：生成配对码、人类输入后校验通过并完成绑定。"""
    oid = register_owner("email", "pairing@x.com")
    cr = create_pairing_code(oid, ttl_seconds=60, agent_display_name="TestBot")
    assert cr["ok"] is True
    code = cr["pairing_code"]
    assert len(code) == 6
    assert "registration_confirm_payload" in cr

    sr = submit_pairing_code(code)
    assert sr["ok"] is True
    assert sr["agent_id"].startswith("tianshu-agent-")
    assert sr["owner_id"] == oid
    assert get_agent_owner(sr["agent_id"]) == oid


def test_submit_pairing_code_invalid():
    """E4-S3：无效或过期配对码返回失败。"""
    r = submit_pairing_code("INVALID")
    assert r["ok"] is False
    assert "无效" in r["error"] or "过期" in r["error"]


# ---------- E4-S5 上线登记与心跳 ----------


def test_agent_online_register_and_heartbeat():
    """E4-S5：已有身份上线登记与心跳，状态可查。"""
    from src.identity import (
        agent_online_register,
        agent_heartbeat,
        get_agent_online_status,
        list_online_agents,
    )
    oid = register_owner("email", "presence@x.com")
    r = register_agent_by_human("email", "presence@x.com", ensure_owner_registered=False)
    assert r["ok"] is True
    aid = r["agent_id"]

    reg = agent_online_register(aid)
    assert reg["ok"] is True
    assert reg["status"] == "online"

    status = get_agent_online_status(aid)
    assert status["online"] is True
    assert status["last_seen_ts"] is not None

    hb = agent_heartbeat(aid, status="busy")
    assert hb["ok"] is True
    status2 = get_agent_online_status(aid)
    assert status2["status"] == "busy"

    assert aid in list_online_agents()


def test_agent_online_register_fail_when_not_registered():
    """E4-S5：未注册身份调用上线登记返回失败。"""
    from src.identity import agent_online_register
    r = agent_online_register("tianshu-agent-nonexistent")
    assert r["ok"] is False
    assert "不存在" in r["error"]

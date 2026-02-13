# E3 验收：身份与关系（Owner 登记、Agent 身份、Agent–Owner 绑定与主从链）

import pytest

from src.identity import (
    register_owner,
    lookup_owners,
    owner_exists,
    allocate_agent_id,
    get_agent,
    set_agent_matrix_id,
    bind_agent_owner,
    register_sub_agent,
    get_agent_owner,
    get_owner_agent_ids,
    get_sub_agent_ids,
    get_main_agent_id,
    list_relationships_for_diting,
)


# ---------- E3-S1 Owner 登记与解析 ----------


def test_register_owner():
    oid = register_owner("email", "alice@example.com")
    assert oid.startswith("owner-")
    assert owner_exists("email", "alice@example.com")


def test_lookup_owners_unique():
    register_owner("feishu_user_id", "ou_abc")
    found = lookup_owners("feishu_user_id", "ou_abc")
    assert len(found) == 1
    assert found[0]["identifiers"].get("feishu_user_id") == "ou_abc"


def test_lookup_owners_candidates():
    register_owner("employee_id", "E001")
    register_owner("employee_id", "E002")
    cand = lookup_owners(query="E00")
    assert len(cand) >= 2


def test_owner_exists():
    assert owner_exists("email", "alice@example.com") is True
    assert owner_exists("email", "nonexistent@x.com") is False


# ---------- E3-S2 Agent 身份标识 ----------


def test_allocate_agent_id():
    aid1 = allocate_agent_id()
    aid2 = allocate_agent_id()
    assert aid1 != aid2
    assert aid1.startswith("tianshu-agent-")
    assert get_agent(aid1) is not None
    assert get_agent(aid1)["agent_id"] == aid1


def test_set_agent_matrix_id():
    aid = allocate_agent_id()
    assert set_agent_matrix_id(aid, "@bot:matrix.example") is True
    assert get_agent(aid)["matrix_id"] == "@bot:matrix.example"


# ---------- E3-S3 绑定与主从链 ----------


def test_bind_agent_owner():
    oid = register_owner("email", "owner@x.com")
    aid = allocate_agent_id()
    assert bind_agent_owner(aid, oid) is True
    assert get_agent_owner(aid) == oid
    assert aid in get_owner_agent_ids(oid)


def test_register_sub_agent():
    main = allocate_agent_id()
    sub = allocate_agent_id()
    assert register_sub_agent(main, sub) is True
    assert get_main_agent_id(sub) == main
    assert sub in get_sub_agent_ids(main)


def test_list_relationships_for_diting():
    oid = register_owner("email", "diting@x.com")
    aid = allocate_agent_id()
    bind_agent_owner(aid, oid)
    sub = allocate_agent_id()
    register_sub_agent(aid, sub)
    rows = list_relationships_for_diting()
    assert any(r["agent_id"] == aid and r["owner_id"] == oid for r in rows)
    assert any(sub in r.get("sub_agents", []) for r in rows if r["agent_id"] == aid)

# E4-S2 / E4-S2b：Agent 自主注册 — Owner 存在判断与多候选
# Agent 可查询拟绑定 Owner 是否存在；不存在则明确失败；存在则进入后续步骤；多候选时返回列表，人类确认后回传 owner_id

from typing import Any, Dict, List

from src.identity import lookup_owners, get_owner


def check_owner_for_registration(
    identifier_type: str,
    identifier_value: str,
) -> Dict[str, Any]:
    """
    E4-S2：Agent 查询拟绑定 Owner 是否存在。
    - 不存在：返回 { "exists": False, "error": "..." }，不进入配对码流程。
    - 唯一存在：返回 { "exists": True, "owner_id": "..." }，可进入配对码流程。
    - 支持按邮箱、工号、feishu_user_id 等检索（精确匹配）。
    """
    owners = lookup_owners(
        identifier_type=(identifier_type or "").strip(),
        identifier_value=(identifier_value or "").strip(),
    )
    if not owners:
        return {"exists": False, "error": "拟绑定 Owner 不存在，请先登记"}
    if len(owners) == 1:
        return {"exists": True, "owner_id": owners[0]["owner_id"]}
    # 精确匹配不应出现多条；若有多条则视为多候选
    return {
        "exists": True,
        "candidates": [
            {"owner_id": o["owner_id"], "identifiers": o.get("identifiers", {})}
            for o in owners
        ],
    }


def list_owner_candidates(query: str) -> Dict[str, Any]:
    """
    E4-S2b：模糊检索 Owner 候选列表（如按姓名、邮箱片段）。
    Agent 与人类确认「我是谁」后，用选定的 owner_id 调用创建配对码。
    """
    if not (query or "").strip():
        return {"candidates": []}
    owners = lookup_owners(query=(query or "").strip())
    return {
        "candidates": [
            {"owner_id": o["owner_id"], "identifiers": o.get("identifiers", {})}
            for o in owners
        ],
    }


def get_owner_info(owner_id: str) -> Dict[str, Any]:
    """Agent 确认唯一 Owner 后，可查其信息（如用于展示或推送目标）。"""
    o = get_owner(owner_id)
    if not o:
        return {"ok": False, "error": "Owner 不存在"}
    return {"ok": True, "owner_id": o["owner_id"], "identifiers": o.get("identifiers", {})}

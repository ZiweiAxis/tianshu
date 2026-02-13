# Agent 注册流程（E4）
from src.registration.human_initiated import register_agent_by_human
from src.registration.agent_self_register import (
    check_owner_for_registration,
    list_owner_candidates,
    get_owner_info,
)
from src.registration.pairing_code import create_pairing_code, submit_pairing_code

__all__ = [
    "register_agent_by_human",
    "check_owner_for_registration",
    "list_owner_candidates",
    "get_owner_info",
    "create_pairing_code",
    "submit_pairing_code",
]

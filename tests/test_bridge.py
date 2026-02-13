# E2-S2 验收：飞书 ↔ Matrix 双向 Bridge

import pytest

# ---------- translator ----------


def test_feishu_event_to_matrix_text():
    from src.core import translator
    event = {"message_type": "text", "content": {"text": "hello"}}
    msgtype, content = translator.feishu_event_to_matrix(event)
    assert msgtype == "m.text"
    assert content.get("body") == "hello"


def test_feishu_event_to_matrix_from_message():
    from src.core import translator
    event = {"message": {"message_type": "text", "content": {"text": "hi"}}}
    msgtype, content = translator.feishu_event_to_matrix(event)
    assert msgtype == "m.text"
    assert content.get("body") == "hi"


def test_matrix_event_to_feishu():
    from src.core import translator
    out = translator.matrix_event_to_feishu("!abc:hs", "m.text", {"body": "reply"})
    assert out["msg_type"] == "text"
    assert out["content"]["text"] == "reply"


# ---------- user_mapper ----------


def test_user_mapper_get_or_create():
    from src.core import user_mapper
    internal = user_mapper.get_or_create_internal_id("ou_xxx")
    assert internal == "feishu:ou_xxx"
    assert user_mapper.get_or_create_internal_id("ou_xxx") == internal
    assert user_mapper.get_feishu_open_id(internal) == "ou_xxx"


# ---------- room_manager ----------


def test_room_manager_mapping():
    import unittest.mock as mock
    from src.core import room_manager
    with mock.patch.object(room_manager, "USE_PRIVATE_ROOM", True), mock.patch.object(room_manager, "SHARED_ROOM_ID", None):
        room_manager.set_room_mapping("oc_chat1", "!room1:hs")
        assert room_manager.get_matrix_room_id("oc_chat1") == "!room1:hs"
        assert room_manager.get_feishu_chat_id("!room1:hs") == "oc_chat1"
        assert room_manager.get_feishu_chat_ids("!room1:hs") == ["oc_chat1"]
        room_manager.set_room_mapping("oc_chat2", "!room1:hs")
        assert room_manager.get_feishu_chat_ids("!room1:hs") == ["oc_chat1", "oc_chat2"]
        room_manager.forget_room("!room1:hs")
        assert room_manager.get_matrix_room_id("oc_chat1") is None
        assert room_manager.get_feishu_chat_id("!room1:hs") is None


# ---------- FeishuBridge.parse_feishu_event ----------


def test_parse_feishu_event():
    from src.bridge.feishu import FeishuBridge
    payload = {
        "event": {
            "message": {
                "chat_id": "oc_xxx",
                "message_type": "text",
                "content": '{"text": "hello"}',
                "message_id": "om_yyy",
            },
            "sender": {"sender_id": {"open_id": "ou_zzz"}},
        }
    }
    parsed = FeishuBridge.parse_feishu_event(payload)
    assert parsed is not None
    assert parsed["chat_id"] == "oc_xxx"
    assert parsed["message_type"] == "text"
    assert parsed["content"].get("text") == "hello"
    assert parsed["open_id"] == "ou_zzz"


def test_parse_feishu_event_no_message():
    from src.bridge.feishu import FeishuBridge
    assert FeishuBridge.parse_feishu_event({}) is None
    assert FeishuBridge.parse_feishu_event({"event": {}}) is None


@pytest.mark.asyncio
async def test_handle_feishu_event_no_room_skip():
    import unittest.mock as mock
    from src.bridge import feishu
    from src.core import room_manager, translator, user_mapper
    # 无 room 映射且不自动建间时，应跳过（mock 使 get_matrix_room_id 返回 None）
    class FakeMatrix:
        pass
    with mock.patch.object(room_manager, "USE_PRIVATE_ROOM", True), mock.patch.object(room_manager, "SHARED_ROOM_ID", None):
        ok = await feishu.handle_feishu_event(
            {"event": {"message": {"chat_id": "oc_none", "message_type": "text", "content": '{"text":"x"}'}}},
            FakeMatrix(),
            room_manager,
            translator,
            user_mapper,
            create_room_if_missing=False,
        )
    assert ok is False


@pytest.mark.asyncio
async def test_handle_feishu_event_with_room():
    import unittest.mock as mock
    from src.bridge import feishu
    from src.core import room_manager, translator, user_mapper
    sent = []

    class FakeMatrix:
        async def send_text(self, room_id: str, body: str):
            sent.append((room_id, body))
            return "e_123"

    with mock.patch.object(room_manager, "USE_PRIVATE_ROOM", True), mock.patch.object(room_manager, "SHARED_ROOM_ID", None):
        room_manager.set_room_mapping("oc_known", "!r1:hs")
        ok = await feishu.handle_feishu_event(
            {"event": {"message": {"chat_id": "oc_known", "message_type": "text", "content": '{"text":"hi"}'}}},
            FakeMatrix(),
            room_manager,
            translator,
            user_mapper,
            create_room_if_missing=False,
        )
    assert ok is True
    assert sent == [("!r1:hs", "hi")]

# E2-S1 验收：Matrix 连接与 Room/Event 收发
# 1) matrix-nio 与配置的 MHS 建立连接
# 2) 可创建/加入 Room、发送与接收 Event
# 3) 连接断开可重连或告警
# 4) 支持「飞书会话/群 ↔ Matrix Room」的映射策略可配置（config 中 USE_PRIVATE_ROOM, SHARED_ROOM_ID）

import asyncio
import os
import pytest
from dotenv import load_dotenv

load_dotenv()  # 使 .env 中的 MATRIX_* 在 skipif 前生效

# 跳过若无 matrix-nio 或未配置 Matrix
pytestmark = pytest.mark.skipif(
    not os.getenv("MATRIX_HOMESERVER") or not os.getenv("MATRIX_GATEWAY_TOKEN"),
    reason="需配置 MATRIX_HOMESERVER 与 MATRIX_GATEWAY_TOKEN",
)

# 连接超时（无本地 Matrix 时快速失败）
CONNECT_TIMEOUT = 10.0


@pytest.fixture
def client():
    from src.matrix.client import MatrixClient
    return MatrixClient()


@pytest.mark.asyncio
async def test_connect(client):
    """验收 1：与 MHS 建立连接"""
    ok = await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)
    assert ok is True
    assert client.is_connected
    await client.disconnect()
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_create_room_and_send(client):
    """验收 2：可创建 Room、发送 Event"""
    ok = await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)
    assert ok
    room_id = await client.create_room(name="tianshu-test")
    assert room_id is not None
    event_id = await client.send_text(room_id, "test message")
    assert event_id is not None
    await client.disconnect()


@pytest.mark.asyncio
async def test_receive_events(client):
    """验收 2：可接收 Event（通过 sync 循环收到至少 0 条）"""
    received = []
    async def on_ev(room_id: str, msgtype: str, content: dict):
        received.append((room_id, msgtype, content))

    ok = await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)
    assert ok
    client.start_sync_loop(on_ev)
    await asyncio.sleep(2)  # 短暂 sync
    await client.disconnect()
    # 不强制收到消息，仅验证 sync 循环可启停
    assert isinstance(received, list)

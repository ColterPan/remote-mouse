"""
Integration tests for server.py.

These start the real aiohttp app in-process and talk to it with a real
WebSocket client, but plug in FakeController so no actual input happens.
"""

import asyncio

import aiohttp
import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import make_mocked_request

from remote_mouse import server
from remote_mouse.input_controller import FakeController
from remote_mouse.security import FailedAuthLimiter
from remote_mouse.server import (
    CLOSE_PAIRING_RESET,
    CLOSE_UNAUTHORIZED,
    CLOSE_VERSION_MISMATCH,
    AuthState,
    BackgroundServer,
    ServerContext,
    create_app,
    disconnect_all,
    private_network_only,
)
from remote_mouse.tls import create_ssl_context, ensure_certificate

TOKEN = "test-token-abcdefghijklmnop"


@pytest.fixture
def ctx():
    return ServerContext(
        auth=AuthState(TOKEN),
        controller=FakeController(),
        limiter=FailedAuthLimiter(max_failures=3, lockout_seconds=60),
    )


@pytest.fixture
async def client(aiohttp_client, ctx):
    return await aiohttp_client(create_app(ctx))


async def connect(client, token=TOKEN, version=1):
    """Open a WebSocket, authenticate, and return (ws, first_reply)."""
    ws = await client.ws_connect("/ws")
    await ws.send_json({"t": "auth", "token": token, "v": version})
    reply = await ws.receive_json()
    return ws, reply


async def roundtrip(ws):
    """Send a ping and wait for the pong: guarantees earlier messages were handled."""
    await ws.send_json({"t": "ping"})
    while True:
        reply = await ws.receive_json()
        if reply["t"] == "pong":
            return


async def wait_for(predicate, timeout=2.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


class TestPages:
    async def test_index_is_served_with_security_headers(self, client):
        response = await client.get("/")
        assert response.status == 200
        assert "<title>Remote Mouse</title>" in await response.text()
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
        assert response.headers["X-Frame-Options"] == "DENY"

    async def test_javascript_has_module_safe_content_type(self, client):
        response = await client.get("/static/js/app.js")
        assert response.status == 200
        assert response.content_type == "text/javascript"

    async def test_path_traversal_is_blocked(self, client):
        response = await client.get("/static/../server.py")
        assert response.status in (403, 404)


class TestAuthentication:
    async def test_correct_token_gets_hello(self, client):
        ws, reply = await connect(client)
        assert reply["t"] == "hello"
        assert reply["v"] == 1
        await ws.close()

    async def test_wrong_token_is_rejected_and_closed(self, client, ctx):
        ws, reply = await connect(client, token="wrong-token-xxxxxxxxxxxxx")
        assert reply == {"t": "error", "reason": "unauthorized"}
        closing = await ws.receive()
        assert closing.type == WSMsgType.CLOSE
        assert ws.close_code == CLOSE_UNAUTHORIZED
        assert ctx.controller.calls == []

    async def test_first_message_must_be_auth(self, client):
        ws = await client.ws_connect("/ws")
        await ws.send_json({"t": "move", "dx": 1, "dy": 1})
        assert (await ws.receive_json())["reason"] == "unauthorized"

    async def test_version_mismatch_is_reported(self, client):
        ws, reply = await connect(client, version=99)
        assert reply["reason"] == "version"
        await ws.receive()
        assert ws.close_code == CLOSE_VERSION_MISMATCH

    async def test_lockout_after_repeated_failures(self, client):
        for _ in range(3):
            ws, _ = await connect(client, token="wrong-token-xxxxxxxxxxxxx")
            await ws.close()
        with pytest.raises(aiohttp.WSServerHandshakeError) as excinfo:
            await client.ws_connect("/ws")
        assert excinfo.value.status == 429

    async def test_auth_timeout_closes_socket(self, client, monkeypatch):
        monkeypatch.setattr(server, "AUTH_TIMEOUT_SECONDS", 0.05)
        ws = await client.ws_connect("/ws")
        message = await ws.receive()
        assert message.type == WSMsgType.CLOSE
        assert ws.close_code == CLOSE_UNAUTHORIZED

    async def test_foreign_origin_is_refused(self, client):
        with pytest.raises(aiohttp.WSServerHandshakeError) as excinfo:
            await client.ws_connect("/ws", headers={"Origin": "https://evil.example"})
        assert excinfo.value.status == 403

    async def test_foreign_host_header_is_refused(self, client):
        # DNS rebinding: the browser thinks it's talking to evil.example.
        response = await client.get("/", headers={"Host": "evil.example:8765"})
        assert response.status == 403

    async def test_auth_timeout_counts_as_failure(self, client, ctx, monkeypatch):
        monkeypatch.setattr(server, "AUTH_TIMEOUT_SECONDS", 0.05)
        for _ in range(3):
            ws = await client.ws_connect("/ws")
            await ws.receive()
        assert ctx.limiter.is_locked("127.0.0.1")

    async def test_closing_before_auth_is_not_a_wrong_guess(self, client, ctx):
        for _ in range(5):
            ws = await client.ws_connect("/ws")
            await ws.close()
        await wait_for(lambda: not ctx.pending)
        assert not ctx.limiter.is_locked("127.0.0.1")
        ws, reply = await connect(client)
        assert reply["t"] == "hello"
        await ws.close()

    async def test_pending_connections_are_capped_per_address(self, client, ctx, monkeypatch):
        monkeypatch.setattr(server, "MAX_PENDING_PER_IP", 1)
        idle = await client.ws_connect("/ws")  # never sends a token
        await wait_for(lambda: ctx.pending.get("127.0.0.1") == 1)
        with pytest.raises(aiohttp.WSServerHandshakeError) as excinfo:
            await client.ws_connect("/ws")
        assert excinfo.value.status == 503
        await idle.close()
        await wait_for(lambda: not ctx.pending)

    async def test_pending_connections_are_capped_overall(self, ctx):
        ctx.pending = {f"10.0.0.{i}": 1 for i in range(server.MAX_PENDING_TOTAL)}
        assert not ctx.reserve_pending("10.0.1.1")

    async def test_parallel_guesses_cannot_bypass_lockout(self, client, monkeypatch):
        monkeypatch.setattr(server, "MAX_PENDING_PER_IP", 10)
        sockets = [await client.ws_connect("/ws") for _ in range(4)]  # all pass the upgrade
        for ws in sockets[:3]:
            await ws.send_json({"t": "auth", "token": "wrong-token-xxxxxxxxxxxxx", "v": 1})
            await ws.receive_json()
        # Locked now — even the correct token on the 4th socket is refused.
        await sockets[3].send_json({"t": "auth", "token": TOKEN, "v": 1})
        assert (await sockets[3].receive_json())["reason"] == "unauthorized"

    async def test_too_many_clients_are_refused(self, client, monkeypatch):
        monkeypatch.setattr(server, "MAX_CLIENTS", 1)
        ws, _ = await connect(client)
        await roundtrip(ws)
        with pytest.raises(aiohttp.WSServerHandshakeError) as excinfo:
            await client.ws_connect("/ws")
        assert excinfo.value.status == 503
        await ws.close()


class TestCommands:
    async def test_commands_reach_the_controller(self, client, ctx):
        ws, _ = await connect(client)
        await ws.send_json({"t": "move", "dx": 5, "dy": -2})
        await ws.send_json({"t": "click", "b": "right"})
        await ws.send_json({"t": "text", "s": "hi"})
        await ws.send_json({"t": "key", "k": "v", "mods": ["ctrl"]})
        await roundtrip(ws)
        assert ctx.controller.calls == [
            ("move", 5.0, -2.0),
            ("click", "right", 1),
            ("type_text", "hi"),
            ("press_key", "v", ("ctrl",)),
        ]
        await ws.close()

    async def test_bad_message_gets_error_but_session_continues(self, client, ctx):
        ws, _ = await connect(client)
        await ws.send_str("{ nonsense")
        assert (await ws.receive_json())["t"] == "error"
        await ws.send_json({"t": "move", "dx": 1, "dy": 1})
        await roundtrip(ws)
        assert ctx.controller.calls == [("move", 1.0, 1.0)]
        await ws.close()

    async def test_binary_and_repeated_auth_messages_are_ignored(self, client, ctx):
        ws, _ = await connect(client)
        await ws.send_bytes(b"\x00\x01")
        await ws.send_json({"t": "auth", "token": TOKEN, "v": 1})
        await roundtrip(ws)
        assert ctx.controller.calls == []
        await ws.close()

    async def test_controller_errors_do_not_kill_session(self, client, ctx):
        def explode(dx, dy):
            raise RuntimeError("OS refused input")

        ctx.controller.move = explode
        ws, _ = await connect(client)
        await ws.send_json({"t": "move", "dx": 1, "dy": 1})
        await roundtrip(ws)  # still answering → session alive
        await ws.close()

    async def test_held_buttons_are_released_on_disconnect(self, client, ctx):
        ws, _ = await connect(client)
        await ws.send_json({"t": "down", "b": "left"})
        await roundtrip(ws)
        await ws.close()
        await wait_for(lambda: ("release_button", "left") in ctx.controller.calls)

    async def test_released_buttons_are_not_released_twice(self, client, ctx):
        ws, _ = await connect(client)
        await ws.send_json({"t": "down", "b": "left"})
        await ws.send_json({"t": "up", "b": "left"})
        await roundtrip(ws)
        await ws.close()
        await wait_for(lambda: not ctx.sockets)
        assert ctx.controller.calls.count(("release_button", "left")) == 1


class _DyingSocket:
    """Fake WebSocket: delivers some messages, then fails when we reply."""

    def __init__(self, messages):
        self._messages = list(messages)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)

    async def send_json(self, data):
        raise ConnectionResetError("Cannot write to closing transport")


async def test_buttons_released_even_when_reply_fails():
    """Wi-Fi drops while dragging: the pong can't be sent, the button must still be let go."""
    controller = FakeController()
    text = WSMsgType.TEXT
    ws = _DyingSocket(
        [
            aiohttp.WSMessage(text, '{"t":"down","b":"left"}', None),
            aiohttp.WSMessage(text, '{"t":"ping"}', None),
            aiohttp.WSMessage(text, '{"t":"move","dx":1,"dy":1}', None),
        ]
    )
    await server._command_loop(ws, controller)
    assert controller.calls == [("press_button", "left"), ("release_button", "left")]


class TestClientTracking:
    async def test_client_count_callback(self, aiohttp_client):
        counts = []
        ctx = ServerContext(AuthState(TOKEN), FakeController(), on_client_change=counts.append)
        client = await aiohttp_client(create_app(ctx))
        ws, _ = await connect(client)
        await roundtrip(ws)
        await ws.close()
        await wait_for(lambda: counts == [1, 0])

    async def test_connected_callback_receives_address(self, aiohttp_client):
        seen = []
        ctx = ServerContext(AuthState(TOKEN), FakeController(), on_client_connected=seen.append)
        client = await aiohttp_client(create_app(ctx))
        ws, _ = await connect(client)
        await roundtrip(ws)
        assert seen == ["127.0.0.1"]
        await ws.close()

    async def test_disconnect_all_closes_phones(self, client, ctx):
        ws, _ = await connect(client)
        await roundtrip(ws)
        await disconnect_all(ctx)
        message = await ws.receive()
        assert message.type == WSMsgType.CLOSE
        assert ws.close_code == CLOSE_PAIRING_RESET


async def test_public_addresses_are_refused_by_middleware():
    request = make_mocked_request("GET", "/").clone(remote="8.8.8.8")

    async def handler(_request):
        return web.Response(text="should not get here")

    with pytest.raises(web.HTTPForbidden):
        await private_network_only(request, handler)


async def test_private_addresses_pass_middleware():
    request = make_mocked_request("GET", "/").clone(remote="192.168.1.9")

    async def handler(_request):
        return web.Response(text="ok")

    response = await private_network_only(request, handler)
    assert response.text == "ok"


class TestBackgroundServer:
    """End-to-end over real HTTPS on a random free port."""

    def _start(self, tmp_path, ctx):
        info = ensure_certificate(tmp_path, ["localhost"], ["127.0.0.1"])
        background = BackgroundServer(ctx, "127.0.0.1", 0, create_ssl_context(info))
        background.start()
        return background

    async def test_https_websocket_and_pairing_reset(self, tmp_path, ctx):
        background = await asyncio.to_thread(self._start, tmp_path, ctx)
        url = f"https://127.0.0.1:{background.bound_port}/ws"
        try:
            async with aiohttp.ClientSession() as session:
                # ssl=False: the test trusts the self-signed cert, like the phone does.
                ws = await session.ws_connect(url, ssl=False)
                await ws.send_json({"t": "auth", "token": TOKEN, "v": 1})
                assert (await ws.receive_json())["t"] == "hello"

                await asyncio.to_thread(background.reset_pairing, "brand-new-token-1234567890")
                message = await ws.receive()
                assert message.type == WSMsgType.CLOSE
                assert ctx.auth.token == "brand-new-token-1234567890"

                ws2 = await session.ws_connect(url, ssl=False)
                await ws2.send_json({"t": "auth", "token": TOKEN, "v": 1})
                assert (await ws2.receive_json())["reason"] == "unauthorized"
                await ws2.close()
        finally:
            await asyncio.to_thread(background.stop)

    async def test_port_in_use_raises(self, tmp_path, ctx):
        first = await asyncio.to_thread(self._start, tmp_path, ctx)
        try:
            second = BackgroundServer(ctx, "127.0.0.1", first.bound_port, None)
            with pytest.raises(OSError):
                await asyncio.to_thread(second.start)
        finally:
            await asyncio.to_thread(first.stop)

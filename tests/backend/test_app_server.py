import asyncio
import json
from pathlib import Path

import pytest

from nightwatch.agents.app_server import CodexAppServer


def test_start_creates_nested_workspace_and_degrades_when_launch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        workspace = tmp_path / "missing" / "nested" / "codex-workspace"
        monkeypatch.setenv("NW_CODEX_WORKSPACE", str(workspace))

        async def fail_to_launch(*args: object, **kwargs: object) -> None:
            raise OSError("codex unavailable")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fail_to_launch)
        server = CodexAppServer("codex", "test-key", timeout_seconds=5)

        await server.start()

        assert workspace.is_dir()
        assert (workspace.parent / "codex-home").is_dir()
        assert server.available is False
        assert "OSError" in server.message

    asyncio.run(exercise())


def test_dynamic_tool_calls_are_executed_by_typed_backend_broker() -> None:
    async def exercise() -> None:
        events: list[dict[str, object]] = []
        writes: list[dict[str, object]] = []

        async def tool(name: str, arguments: object) -> dict[str, object]:
            assert name == "nw_find_project_containers"
            assert arguments == {"project": "AniReminder"}
            return {"ok": True, "matches": [{"project": "AniReminder"}]}

        async def capture(event: dict[str, object]) -> None:
            events.append(event)

        server = CodexAppServer("codex", "test-key", timeout_seconds=5, tool_executor=tool)

        async def write(value: dict[str, object]) -> None:
            writes.append(value)

        server._write = write  # type: ignore[method-assign]
        server._event_sink = capture
        await server._handle_tool_call(9, {"tool": "nw_find_project_containers", "arguments": '{"project":"AniReminder"}'})

        assert [event["status"] for event in events] == ["running", "completed"]
        assert writes[0]["id"] == 9
        result = writes[0]["result"]
        assert isinstance(result, dict) and result["success"] is True
        content = result["contentItems"]
        assert isinstance(content, list)
        assert json.loads(content[0]["text"])["matches"][0]["project"] == "AniReminder"

    asyncio.run(exercise())


def test_streamed_agent_message_delta_is_retained_until_turn_completion() -> None:
    class Process:
        def __init__(self, stdout: asyncio.StreamReader) -> None:
            self.stdout = stdout
            self.returncode: int | None = None

    async def exercise() -> None:
        server = CodexAppServer("codex", "test-key", timeout_seconds=5)
        stream = asyncio.StreamReader()
        server._process = Process(stream)  # type: ignore[assignment]
        server._turn_waiter = asyncio.get_running_loop().create_future()
        stream.feed_data(b'{"method":"item/agentMessage/delta","params":{"threadId":"thread","turnId":"turn","itemId":"message","delta":"Verified answer"}}\n')
        stream.feed_data(b'{"method":"turn/completed","params":{"turn":{"status":"completed"}}}\n')
        stream.feed_eof()

        await server._reader()

        assert await server._turn_waiter == "Verified answer"

    asyncio.run(exercise())


def test_reader_executes_dynamic_tool_calls_with_string_request_ids() -> None:
    class Process:
        def __init__(self, stdout: asyncio.StreamReader) -> None:
            self.stdout = stdout
            self.returncode: int | None = None

    async def exercise() -> None:
        server = CodexAppServer("codex", "test-key", timeout_seconds=5)
        stream = asyncio.StreamReader()
        server._process = Process(stream)  # type: ignore[assignment]
        received: list[tuple[str | int, dict[str, object]]] = []

        async def handle(request_id: str | int, params: dict[str, object]) -> None:
            received.append((request_id, params))

        server._handle_tool_call = handle  # type: ignore[method-assign]
        stream.feed_data(b'{"id":"tool-request-1","method":"item/tool/call","params":{"tool":"nw_get_topology","arguments":{}}}\n')
        stream.feed_eof()

        await server._reader()
        await asyncio.sleep(0)

        assert received == [("tool-request-1", {"tool": "nw_get_topology", "arguments": {}})]

    asyncio.run(exercise())


def test_turn_completion_uses_the_final_agent_message_in_turn_items() -> None:
    class Process:
        def __init__(self, stdout: asyncio.StreamReader) -> None:
            self.stdout = stdout
            self.returncode: int | None = None

    async def exercise() -> None:
        server = CodexAppServer("codex", "test-key", timeout_seconds=5)
        stream = asyncio.StreamReader()
        server._process = Process(stream)  # type: ignore[assignment]
        server._turn_waiter = asyncio.get_running_loop().create_future()
        stream.feed_data(b'{"method":"turn/completed","params":{"threadId":"thread","turn":{"id":"turn","status":"completed","items":[{"id":"message","type":"agentMessage","text":"Final verified answer"}]}}}\n')
        stream.feed_eof()

        await server._reader()

        assert await server._turn_waiter == "Final verified answer"

    asyncio.run(exercise())

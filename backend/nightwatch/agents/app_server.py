from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ToolExecutor = Callable[[str, object], Awaitable[dict[str, object]]]
EventSink = Callable[[dict[str, object]], Awaitable[None]]

logger = logging.getLogger("nightwatch.app_server")


class CodexAppServer:
    """Small stdio-only Codex app-server client used for evidence-only synthesis.

    The process has no Nightwatch tools, no Docker socket, and disabled command tools. The
    backend supplies a redacted read-only evidence snapshot as turn input instead.
    """

    def __init__(self, command: str, api_key: str | None, *, timeout_seconds: float, model: str = "gpt-5.6-luna", dynamic_tools: list[dict[str, object]] | None = None, tool_executor: ToolExecutor | None = None) -> None:
        self._command = command
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._model = model
        self._process: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._reader_task: asyncio.Task[None] | None = None
        self._thread_id: str | None = None
        self._thread_ids: dict[str, str] = {}
        self._turn_healthy = False
        self._turn_waiter: asyncio.Future[str] | None = None
        self._turn_parts: list[str] = []
        self._streamed_message_ids: set[str] = set()
        self._lock = asyncio.Lock()
        self._error: str | None = None
        self._dynamic_tools = dynamic_tools or []
        self._tool_executor = tool_executor
        self._event_sink: EventSink | None = None
        self._last_turn_engine: str | None = None
        self._active_conversation_id: str | None = None
        self._turn_evidence: list[dict[str, object]] = []
        self._last_evidence: list[dict[str, object]] = []

    @property
    def available(self) -> bool:
        return self._connected

    @property
    def _connected(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def message(self) -> str:
        if self.available:
            return f"Codex app-server is connected with {len(self._dynamic_tools)} typed Nightwatch tools."
        return self._error or "Codex app-server is not connected; Nightwatch will use its evidence-only fallback."

    @property
    def last_turn_engine(self) -> str | None:
        return self._last_turn_engine

    @property
    def tool_count(self) -> int:
        return len(self._dynamic_tools)

    @property
    def last_evidence(self) -> list[dict[str, object]]:
        return list(self._last_evidence)

    def configure_tools(self, dynamic_tools: list[dict[str, object]], tool_executor: ToolExecutor) -> None:
        if self.available:
            raise RuntimeError("Codex app-server tools must be configured before startup.")
        self._dynamic_tools = dynamic_tools
        self._tool_executor = tool_executor

    async def start(self) -> None:
        if self._connected or not self._api_key:
            return
        workspace = Path(os.environ.get("NW_CODEX_WORKSPACE", "/app/backend/data/codex-workspace"))
        codex_home = workspace.parent / "codex-home"
        try:
            workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
            codex_home.mkdir(mode=0o700, parents=True, exist_ok=True)
            environment = {
                "PATH": os.environ.get("PATH", ""),
                "OPENAI_API_KEY": self._api_key,
                "CODEX_API_KEY": self._api_key,
                "HOME": str(codex_home),
                "CODEX_HOME": str(codex_home),
            }
            self._process = await asyncio.create_subprocess_exec(
                self._command,
                "app-server",
                "--stdio",
                "--disable",
                "shell_tool",
                "--disable",
                "unified_exec",
                "-c",
                'sandbox_mode="read-only"',
                "-c",
                'approval_policy="never"',
                "-c",
                'model="gpt-5.6-luna"',
                cwd=str(workspace),
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._reader_task = asyncio.create_task(self._reader(), name="nightwatch-codex-app-server")
            await self._request("initialize", {"clientInfo": {"name": "nightwatch", "title": "Nightwatch", "version": "0.1.0"}, "capabilities": {"experimentalApi": True}})
            await self._notify("initialized", {})
            await self._request("account/login/start", {"type": "apiKey", "apiKey": self._api_key})
        except (OSError, RuntimeError, TimeoutError, TypeError) as exc:
            if self._error is None:
                self._error = f"Codex app-server unavailable: {type(exc).__name__}."
            await self.close()

    def thread_id_for(self, conversation_id: str) -> str | None:
        return self._thread_ids.get(conversation_id)

    async def answer(
        self,
        question: str,
        evidence: str,
        on_event: EventSink | None = None,
        *,
        conversation_id: str = "default",
        stored_thread_id: str | None = None,
    ) -> str | None:
        if not self._connected:
            return None
        async with self._lock:
            thread_id = await self._ensure_thread(conversation_id, stored_thread_id)
            if not thread_id:
                return None
            self._thread_id = thread_id
            self._turn_parts = []
            self._turn_evidence = []
            self._streamed_message_ids = set()
            self._event_sink = on_event
            self._active_conversation_id = conversation_id
            self._turn_waiter = asyncio.get_running_loop().create_future()
            prompt = (
                "Answer the user with verified operational facts. Use the relevant Nightwatch tools first, "
                "especially for questions about projects, containers, routes, incidents, or deployments. "
                "Before claiming a prior project or blank service is absent, call nw_get_action_context; runtime topology alone is not authoritative. "
                "For a request to create a named Dokploy project or blank service, inspect the project inventory "
                "and prepare one exact approval-gated action plan using the names already supplied; do not ask for "
                "repository or port details unless the user asked to deploy code. For a follow-up to connect an existing service to a repository and domain, use nw_prepare_inferred_deployment. If the user explicitly states an application port, include it in the tool call; otherwise use repository evidence. "
                "Do not reveal hidden reasoning, do not invent facts, and say when evidence is insufficient. "
                "Use concise Markdown.\n\n"
                f"Question: {question}\n\nObserved evidence:\n{evidence}"
            )
            try:
                await self._request("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": prompt}], "sandboxPolicy": {"type": "readOnly"}})
                answer = await asyncio.wait_for(self._turn_waiter, timeout=self._timeout_seconds)
                if answer:
                    self._last_turn_engine = "codex_app_server"
                    self._turn_healthy = True
                    self._last_evidence = list(self._turn_evidence)
                return answer
            except (RuntimeError, TimeoutError) as exc:
                logger.warning("Codex app-server turn failed: %s", exc)
                self._error = f"Codex app-server turn failed: {type(exc).__name__}."
                self._turn_healthy = False
                return None
            finally:
                self._turn_waiter = None
                self._event_sink = None
                self._active_conversation_id = None

    async def close(self) -> None:
        process, self._process = self._process, None
        self._thread_id = None
        self._thread_ids.clear()
        self._turn_healthy = False
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()

    async def _request(self, method: str, params: dict[str, object]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._write({"id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(future, timeout=10)

    async def _notify(self, method: str, params: dict[str, object]) -> None:
        await self._write({"method": method, "params": params})

    async def _write(self, value: dict[str, object]) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("Codex app-server is not running.")
        self._process.stdin.write((json.dumps(value) + "\n").encode())
        await self._process.stdin.drain()

    async def _reader(self) -> None:
        assert self._process and self._process.stdout
        try:
            while line := await self._process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                message_id = message.get("id")
                if isinstance(message_id, int) and message_id in self._pending:
                    future = self._pending.pop(message_id)
                    if "error" in message:
                        error = message.get("error")
                        detail = error.get("message") if isinstance(error, dict) else None
                        future.set_exception(RuntimeError(detail if isinstance(detail, str) else "Codex app-server rejected the request."))
                    else:
                        result = message.get("result")
                        future.set_result(result if isinstance(result, dict) else {})
                    continue
                params = message.get("params")
                if not isinstance(params, dict):
                    continue
                if message.get("method") == "item/tool/call" and isinstance(message_id, (int, str)) and not isinstance(message_id, bool):
                    asyncio.create_task(self._handle_tool_call(message_id, params), name="nightwatch-codex-tool")
                    continue
                if message.get("method") == "item/agentMessage/delta":
                    item_id = params.get("itemId")
                    delta = params.get("delta")
                    if isinstance(item_id, str) and isinstance(delta, str):
                        self._streamed_message_ids.add(item_id)
                        self._turn_parts.append(delta)
                    continue
                if message.get("method") == "item/completed":
                    item = params.get("item")
                    if isinstance(item, dict) and item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
                        item_id = item.get("id")
                        if not isinstance(item_id, str) or item_id not in self._streamed_message_ids:
                            self._turn_parts.append(item["text"])
                if message.get("method") == "turn/completed" and self._turn_waiter and not self._turn_waiter.done():
                    turn = params.get("turn")
                    completed = isinstance(turn, dict) and turn.get("status") == "completed"
                    if isinstance(turn, dict) and not completed:
                        error = turn.get("error")
                        detail = error.get("message") if isinstance(error, dict) else None
                        self._error = f"Codex app-server turn failed: {detail}" if isinstance(detail, str) else "Codex app-server did not complete the current turn."
                    final_items = turn.get("items") if isinstance(turn, dict) else None
                    final_messages = [
                        item["text"]
                        for item in final_items
                        if isinstance(item, dict)
                        and item.get("type") == "agentMessage"
                        and isinstance(item.get("text"), str)
                    ] if isinstance(final_items, list) else []
                    text = "\n".join(dict.fromkeys(final_messages or self._turn_parts)).strip()
                    self._turn_waiter.set_result(text if completed and text else "")
        except Exception:
            logger.warning("Codex app-server reader stopped", exc_info=True)
        finally:
            if self._turn_waiter and not self._turn_waiter.done():
                self._turn_waiter.set_result("")

    async def _ensure_thread(self, conversation_id: str, stored_thread_id: str | None) -> str | None:
        existing = self._thread_ids.get(conversation_id) or stored_thread_id
        if existing:
            try:
                resumed = await self._request("thread/resume", {"threadId": existing, "dynamicTools": self._dynamic_tools})
                thread = resumed.get("thread") if isinstance(resumed, dict) else None
                thread_id = thread.get("id") if isinstance(thread, dict) else None
                if isinstance(thread_id, str):
                    self._thread_ids[conversation_id] = thread_id
                    return thread_id
            except (RuntimeError, TimeoutError):
                logger.info("Codex thread resume failed for persisted conversation; starting a new scoped thread.")
        workspace = Path(os.environ.get("NW_CODEX_WORKSPACE", "/app/backend/data/codex-workspace"))
        created = await self._request("thread/start", {
            "model": self._model, "cwd": str(workspace), "dynamicTools": self._dynamic_tools,
            "developerInstructions": "You are NightWatch, a highly capable read-only operations agent. Use typed NightWatch tools before answering. Search for a resource, then inspect its detail, metrics, project, routes, incidents, deployments, and bounded logs when relevant. Distinguish observed facts, configured facts, inferences, and unavailable evidence. Include source names and observation times. Never guess project-to-container relationships. For a named project and optional blank service, inspect current projects and prepare one approval-gated action plan using those names. When the user also requests repository hosting, a Dockerfile/build type, a domain, or a port, prepare exactly one deployment plan instead: it creates or reuses the project and service, then configures and deploys it. The user must explicitly approve the exact plan in the UI before infrastructure changes. You cannot run shell commands or access Docker directly.",
        })
        thread = created.get("thread") if isinstance(created, dict) else None
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str):
            self._error = "Codex app-server did not return a conversation thread id."
            return None
        self._thread_ids[conversation_id] = thread_id
        return thread_id

    async def _handle_tool_call(self, request_id: int | str, params: dict[str, object]) -> None:
        tool = params.get("tool")
        if not isinstance(tool, str) or self._tool_executor is None:
            result = {"contentItems": [{"type": "inputText", "text": json.dumps({"ok": False, "error": "Nightwatch tool is unavailable."})}], "success": False}
            await self._write({"id": request_id, "result": result})
            return
        arguments = params.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = None
        if isinstance(arguments, dict) and self._active_conversation_id:
            arguments = {**arguments, "__conversation_id": self._active_conversation_id}
        started = asyncio.get_running_loop().time()
        if self._event_sink is not None:
            await self._event_sink({"type": "tool", "tool": tool, "status": "running", "arguments": arguments})
        try:
            output = await self._tool_executor(tool, arguments)
            evidence = output.get("evidence")
            if isinstance(evidence, list):
                self._turn_evidence.extend(item for item in evidence if isinstance(item, dict))
            success = bool(output.get("ok", False))
            result = {"contentItems": [{"type": "inputText", "text": json.dumps(output, default=str)}], "success": success}
        except Exception:
            logger.exception("Nightwatch dynamic tool failed", extra={"tool": tool})
            output = {"ok": False, "error": "Nightwatch could not collect that observation safely."}
            result = {"contentItems": [{"type": "inputText", "text": json.dumps(output)}], "success": False}
        await self._write({"id": request_id, "result": result})
        if self._event_sink is not None:
            await self._event_sink({"type": "tool", "tool": tool, "status": "completed" if result["success"] else "failed", "duration_ms": int((asyncio.get_running_loop().time() - started) * 1000), "result": output})

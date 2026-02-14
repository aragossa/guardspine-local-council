"""Lightweight MCP client for stdio transport."""

import asyncio
import json
import re
from typing import Any

# Maximum number of framing iterations to prevent infinite loops (NASA-002).
_MAX_READ_ITERATIONS = 10_000


class MCPClient:
    """Connects to an MCP server over stdio (JSON-RPC with Content-Length framing)."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._read_lock = asyncio.Lock()

    # Allowed characters in command tokens: alphanumeric, hyphens, dots,
    # underscores, forward/back slashes, colons, @, and equals.
    _SAFE_TOKEN_RE = re.compile(r"^[\w.\-/@:=+]+$")

    async def connect(self, command: list[str], env: dict[str, str] | None = None) -> None:
        """Spawn the MCP server subprocess and complete the initialize handshake.

        Each token in *command* is validated against a safe-character allowlist
        to prevent command-injection via malicious arguments (SAF-014).
        """
        for token in command:
            if not self._SAFE_TOKEN_RE.match(token):
                raise ValueError(
                    f"Unsafe character in command token: {token!r}. "
                    "Only alphanumeric, -, _, ., /, \\, :, @, = are allowed."
                )
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        # MCP initialize handshake
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "guardspine-hook", "version": "0.1.0"},
        })
        # Send initialized notification (no id, no response expected)
        await self._send_notification("notifications/initialized", {})

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the MCP server and return the result."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        return result

    async def close(self) -> None:
        """Terminate the MCP server process."""
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
        self._process = None

    async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        assert self._process and self._process.stdin and self._process.stdout
        self._request_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        await self._write_message(msg)
        return await self._read_response(self._request_id)

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response)."""
        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        await self._write_message(msg)

    async def _write_message(self, msg: dict[str, Any]) -> None:
        """Write a message using Content-Length framing."""
        assert self._process and self._process.stdin
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._process.stdin.write(header + body)
        await self._process.stdin.drain()

    async def _read_response(self, expected_id: int) -> Any:
        """Read Content-Length framed messages until we get our response.

        Both the outer message loop and the inner header-parsing loop are
        bounded by ``_MAX_READ_ITERATIONS`` to satisfy NASA Power-of-10
        rule 2 (all loops must have a fixed upper bound).
        """
        assert self._process and self._process.stdout
        async with self._read_lock:
            for _msg_iter in range(_MAX_READ_ITERATIONS):
                # Read headers until empty line
                content_length = 0
                for _hdr_iter in range(_MAX_READ_ITERATIONS):
                    line = await self._process.stdout.readline()
                    if not line:
                        raise ConnectionError("MCP server closed stdout")
                    text = line.decode("ascii").strip()
                    if text == "":
                        break
                    if text.lower().startswith("content-length:"):
                        content_length = int(text.split(":", 1)[1].strip())
                else:
                    raise RuntimeError("Header parsing exceeded maximum iterations")

                # Business rule: skip empty frames (content_length == 0).
                # An MCP server may send keep-alive or empty-body frames;
                # these carry no JSON-RPC payload and are safely ignored.
                if content_length == 0:
                    continue

                body = await self._process.stdout.readexactly(content_length)
                data = json.loads(body)

                # Skip notifications (no id)
                if "id" not in data:
                    continue

                if data.get("id") == expected_id:
                    if "error" in data:
                        err = data["error"]
                        raise RuntimeError(f"MCP error {err.get('code')}: {err.get('message')}")
                    return data.get("result")
            else:
                raise RuntimeError("Response reading exceeded maximum iterations")

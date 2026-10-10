"""5.5 以 Streamable HTTP 方式（MCP 2025-03-26 规范）暴露 MySQL MCP Server。

运行（终端 1）：uv run python 03_MySQLMCPServerTest/streamableHttpServer.py
端点：http://127.0.0.1:8000/mcp   （单一端点，POST 发请求；需要时响应可升级为 SSE 流）
"""
import contextlib
import logging
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

sys.path.insert(0, str(Path(__file__).parent))
from mysqlMCPServer import mcp  # noqa: E402

logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# stateless=True：每个请求独立处理，不在服务端保存会话 —— 便于水平扩展
session_manager = StreamableHTTPSessionManager(
    app=mcp,
    event_store=None,
    json_response=False,
    stateless=True,
)


async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        logger.info("Application started with StreamableHTTP session manager!")
        try:
            yield
        finally:
            logger.info("Application shutting down...")


starlette_app = Starlette(
    debug=True,
    routes=[Mount("/mcp", app=handle_streamable_http)],
    lifespan=lifespan,
)


if __name__ == "__main__":
    print(f"MySQL MCP Streamable HTTP server: http://{HOST}:{PORT}/mcp")
    uvicorn.run(starlette_app, host=HOST, port=PORT, log_level="info")

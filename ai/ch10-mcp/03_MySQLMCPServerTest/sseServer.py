"""5.4 以 HTTP + SSE 方式（MCP 2024-11-05 规范）暴露 MySQL MCP Server。

运行（终端 1）：uv run python 03_MySQLMCPServerTest/sseServer.py
端点：GET  http://127.0.0.1:8000/sse        建立 SSE 长连接（服务端 -> 客户端推送）
      POST http://127.0.0.1:8000/messages/  客户端发送 JSON-RPC 请求（URL 带 session_id）

原课程用 FastAPI；这里改用 Starlette（与 MCP 官方 SDK 示例一致，少一个依赖）。
FastAPI 本身就是基于 Starlette 的，原理完全一样。
"""
import os
import sys
from pathlib import Path

import uvicorn
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route

sys.path.insert(0, str(Path(__file__).parent))
from mysqlMCPServer import mcp  # noqa: E402  (导入时已加载 .env)

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# 客户端通过 POST /messages/?session_id=xxx 发送消息，两条通道靠 session_id 关联
sse = SseServerTransport("/messages/")


async def handle_sse(request):
    """GET /sse：建立 SSE 长连接，并把读写流交给 MCP Server。"""
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())
    return Response()


app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ],
)


if __name__ == "__main__":
    print(f"MySQL MCP SSE server: http://{HOST}:{PORT}/sse")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

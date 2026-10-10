"""5.3 ~ 5.5 MySQL MCP Server 接口测试（不需要大模型）。

运行：
    uv run python 03_MySQLMCPServerTest/mysqlMCPServerTest.py                         # stdio（自动拉起 server）
    uv run python 03_MySQLMCPServerTest/mysqlMCPServerTest.py --transport sse         # 需先启动 sseServer.py
    uv run python 03_MySQLMCPServerTest/mysqlMCPServerTest.py --transport streamable  # 需先启动 streamableHttpServer.py
"""
import argparse
import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

HERE = Path(__file__).parent


@asynccontextmanager
async def open_streams(transport: str, base_url: str):
    """三种传输方式最终都得到 (read_stream, write_stream)，上层 ClientSession 的用法完全一样。"""
    if transport == "stdio":
        params = StdioServerParameters(command=sys.executable, args=[str(HERE / "mysqlMCPServer.py")])
        async with stdio_client(params) as (r, w):
            yield r, w
    elif transport == "sse":
        async with sse_client(url=f"{base_url}/sse") as (r, w):
            yield r, w
    else:
        async with streamablehttp_client(url=f"{base_url}/mcp") as (r, w, _get_session_id):
            yield r, w


async def run(transport: str, base_url: str) -> None:
    async with open_streams(transport, base_url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            print(f"[{transport}] connected to {init.serverInfo.name}\n")

            resources = await session.list_resources()
            print("Resources:", [str(r.uri) for r in resources.resources])

            content = await session.read_resource("mysql://students_info/data")
            print("\nmysql://students_info/data:\n" + content.contents[0].text)

            tools = await session.list_tools()
            print("\nTools:", [t.name for t in tools.tools])

            for sql in [
                "SHOW TABLES",
                "SELECT i.StuName, s.score FROM students_info i JOIN students_score s ON i.StuNum = s.StuNum",
            ]:
                result = await session.call_tool("execute_sql", {"query": sql})
                print(f"\n> {sql}\n{result.content[0].text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable"], default="stdio")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    asyncio.run(run(args.transport, args.base_url))

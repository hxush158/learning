"""4.2 四则运算 MCP Server 接口测试（不需要大模型、不需要任何 Key）。

运行：uv run python 02_CalculatorMCPServerTest/calculatorMCPServerTest.py
"""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).parent

server_params = StdioServerParameters(
    # 用当前虚拟环境的 python，避免系统 python 没装 mcp
    command=sys.executable,
    args=[str(HERE / "calculatorMCPServer.py")],
    env=None,
)


async def run() -> None:
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"Server: {init.serverInfo.name}  capabilities: {init.capabilities}\n")

            tools = await session.list_tools()
            print("Supported tools:", [t.name for t in tools.tools])
            (HERE / "output.txt").write_text(str(tools), encoding="utf-8")

            for name in ["add", "subtract", "multiply", "divide"]:
                result = await session.call_tool(name, arguments={"a": 6, "b": 3})
                print(f"{name}(6, 3) = {result.content[0].text}")

            result = await session.call_tool("divide", arguments={"a": 1, "b": 0})
            print(f"divide(1, 0) -> isError={result.isError}: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(run())

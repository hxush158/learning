"""4.2 自定义四则运算 MCP Server + 大模型 测试。

运行：
    uv run python 02_CalculatorMCPServerTest/clientChatTest.py              # 只连计算器
    uv run python 02_CalculatorMCPServerTest/clientChatTest.py --with-amap  # 同时连高德地图（多 Server）

参考问题：3加4等于几 / 调用工具计算3+2 / 调用工具计算3*2 / 调用工具计算3/2
"""
import argparse
import asyncio
from pathlib import Path

from mcp_chat.chat_client import run_chat

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-amap", action="store_true", help="同时加载高德地图 MCP Server")
    args = parser.parse_args()
    name = "servers_config.with_amap.json" if args.with_amap else "servers_config.json"
    asyncio.run(run_chat(str(Path(__file__).parent / name)))

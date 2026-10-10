"""5.3 ~ 5.5 大模型 + MySQL MCP Server 对话测试。

运行：
    uv run python 03_MySQLMCPServerTest/clientChatTest.py                         # stdio
    uv run python 03_MySQLMCPServerTest/clientChatTest.py --transport sse         # 先启动 sseServer.py
    uv run python 03_MySQLMCPServerTest/clientChatTest.py --transport streamable  # 先启动 streamableHttpServer.py

参考问题：
- 有哪些表可以使用
- 查询学生信息表中数据
- 查询学生成绩表中分数最高的
- 对学生信息表和学生成绩表进行联表查询，生成每个学生姓名、成绩
- 将学生姓名为张三的改为钱八，并获取最新的信息表
"""
import argparse
import asyncio
from pathlib import Path

from mcp_chat.chat_client import run_chat

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable"], default="stdio")
    args = parser.parse_args()
    asyncio.run(run_chat(str(Path(__file__).parent / f"servers_config.{args.transport}.json")))

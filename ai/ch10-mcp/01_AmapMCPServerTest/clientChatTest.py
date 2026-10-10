"""3.5 MCP Client 测试：大模型 + 高德地图 MCP Server（stdio，通过 npx 启动）。

运行：uv run python 01_AmapMCPServerTest/clientChatTest.py

参考问题：
- 这个113.93029,22.53291经纬度对应的地方是哪里
- 深圳红树林的经纬度坐标是多少
- 112.10.22.229这个IP所在位置
- 深圳的天气如何
- 我要从深圳市南山区中兴大厦骑行到宝安区宝安体育馆，帮我规划下路径
- 测量下从深圳市南山区中兴大厦到宝安区宝安体育馆驾车距离是多少
- 深圳市南山区中石化的加油站有哪些，需要有POI的ID
- POI为B020016GPH的详细信息
"""
import asyncio
from pathlib import Path

from mcp_chat.chat_client import run_chat

if __name__ == "__main__":
    asyncio.run(run_chat(str(Path(__file__).parent / "servers_config.json")))

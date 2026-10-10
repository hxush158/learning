"""3.4 高德地图 MCP Server 功能接口测试（不需要大模型）。

运行：uv run python 01_AmapMCPServerTest/amapMCPServerTest.py
需要：Node.js（npx）+ .env 中的 AMAP_MAPS_API_KEY
"""
import asyncio
import os
import shutil
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_chat.config import load_project_env

load_project_env()
AMAP_MAPS_API_KEY = os.getenv("AMAP_MAPS_API_KEY")

server_params = StdioServerParameters(
    command=shutil.which("npx") or "npx",
    args=["-y", "@amap/amap-maps-mcp-server"],
    # 注意要带上 PATH 等系统变量，否则 npx 内部找不到 node
    env={**os.environ, "AMAP_MAPS_API_KEY": AMAP_MAPS_API_KEY or ""},
)


async def call(session: ClientSession, name: str, **arguments) -> None:
    result = await session.call_tool(name, arguments=arguments)
    print(f"\n### {name}({arguments})\n{result.content[0].text[:800]}")


async def run() -> None:
    if not AMAP_MAPS_API_KEY:
        raise SystemExit("请先在 .env 中设置 AMAP_MAPS_API_KEY")
    if not shutil.which("npx"):
        raise SystemExit("找不到 npx，请先安装 Node.js：https://nodejs.org")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Supported tools:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")
            (Path(__file__).parent / "output.txt").write_text(str(tools), encoding="utf-8")

            # 1、经纬度 -> 行政区划地址（经纬度查询工具：http://www.jsons.cn/lngcode/）
            await call(session, "maps_regeocode", location="114.05571,22.52245")
            # 2、地址 -> 经纬度
            await call(session, "maps_geo", address="广东省深圳市福田区")
            # 3、IP 定位
            await call(session, "maps_ip_location", ip="112.10.22.229")
            # 4、天气
            await call(session, "maps_weather", city="上海")
            # 5、骑行路径规划（苏州虎丘区 -> 相城区）
            await call(session, "maps_bicycling", origin="120.57345,31.2953", destination="120.64239,31.36889")
            # 6、距离测量：type 1 驾车 / 0 直线 / 3 步行
            await call(session, "maps_distance", origins="120.57345,31.2953", destination="120.64239,31.36889", type="1")
            # 7、关键词搜索
            await call(session, "maps_text_search", keywords="中石化加油站", city="深圳")
            # 其余接口：maps_direction_walking / maps_direction_driving / maps_direction_transit_integrated
            #          maps_around_search / maps_search_detail，用法同上


if __name__ == "__main__":
    asyncio.run(run())

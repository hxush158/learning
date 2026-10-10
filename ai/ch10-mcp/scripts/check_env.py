"""一键自检：依赖 / 配置 / 各个 MCP Server 是否可用。

运行：uv run python scripts/check_env.py
没有配置的部分会显示 SKIP，不会报错退出。
"""
import asyncio
import os
import shutil
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OK, FAIL, SKIP = "\033[32mOK\033[0m", "\033[31mFAIL\033[0m", "\033[33mSKIP\033[0m"
results = []


def report(name: str, status: str, detail: str = "") -> None:
    results.append(status)
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))


def check_imports() -> None:
    import importlib.metadata as md

    in_venv = Path(sys.prefix).resolve() == (ROOT / ".venv").resolve()
    print(f"Python: {sys.executable}" + ("" if in_venv else "   <-- 不是工程的 .venv！请用 uv run python ... 运行"))
    try:
        mcp_ver = md.version("mcp")
    except md.PackageNotFoundError:
        mcp_ver = "未安装"
    if mcp_ver.startswith("2."):
        report("mcp SDK", FAIL, f"{mcp_ver}：本课程代码需要 mcp<2，请用 uv run 运行 / 在工程目录执行 uv sync")
    else:
        try:
            import mcp.server.fastmcp  # noqa: F401
            from mcp.client.streamable_http import streamablehttp_client  # noqa: F401

            report("mcp SDK", OK, mcp_ver)
        except Exception as e:  # noqa: BLE001
            import traceback

            report("mcp SDK", FAIL, f"{mcp_ver}，但导入失败：{e!r}")
            traceback.print_exc()
    for pkg in ["mysql-connector-python", "uvicorn", "langgraph", "langchain-mcp-adapters", "langchain-openai"]:
        try:
            report(pkg, OK, md.version(pkg))
        except md.PackageNotFoundError:
            report(pkg, FAIL, "未安装，请执行 uv sync")


def check_pure_logic() -> None:
    from mcp_chat.chat_client import extract_json
    from mcp_chat.config import load_servers_config

    assert extract_json('{"tool": "add", "arguments": {"a": 1, "b": 2}}')["tool"] == "add"
    assert extract_json('```json\n{"tool": "add", "arguments": {}}\n```')["tool"] == "add"
    assert extract_json("好的，结果是 3") is None
    cfg = load_servers_config(ROOT / "02_CalculatorMCPServerTest" / "servers_config.json")
    srv = cfg["mcpServers"]["calculator"]
    assert srv["command"] == sys.executable and Path(srv["args"][0]).is_file()
    report("客户端解析逻辑", OK)


async def check_calculator() -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "02_CalculatorMCPServerTest" / "calculatorMCPServer.py")]
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        res = await s.call_tool("multiply", {"a": 6, "b": 7})
        assert float(res.content[0].text) == 42.0
    report("calculator MCP Server (stdio)", OK, "6*7=42")


async def check_mysql() -> None:
    host, port = os.getenv("MYSQL_HOST", "127.0.0.1"), int(os.getenv("MYSQL_PORT", "3306"))
    try:
        socket.create_connection((host, port), timeout=2).close()
    except OSError:
        report("MySQL MCP Server", SKIP, f"{host}:{port} 未启动（docker compose up -d）")
        return
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "03_MySQLMCPServerTest" / "mysqlMCPServer.py")]
    )
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        res = await s.list_resources()
        uris = [str(x.uri) for x in res.resources]
    if uris:
        report("MySQL MCP Server (stdio)", OK, ", ".join(uris))
    else:
        report("MySQL MCP Server (stdio)", FAIL, "没有读到表，检查 .env 账号密码 / 数据是否导入")


def check_amap() -> None:
    if not os.getenv("AMAP_MAPS_API_KEY"):
        report("高德地图", SKIP, "未配置 AMAP_MAPS_API_KEY")
        return
    if not shutil.which("npx"):
        report("高德地图 (npx)", FAIL, "未安装 Node.js")
        return
    report("高德地图", OK, "已配置 Key，运行 01_AmapMCPServerTest/amapMCPServerTest.py 做完整测试")


def check_llm() -> None:
    try:
        from mcp_chat.chat_client import LLMClient
        from mcp_chat.config import LLMConfig

        cfg = LLMConfig()
    except ValueError as e:
        report("大模型", SKIP, str(e))
        return
    if cfg.api_key.startswith("sk-xxx"):
        report("大模型", SKIP, "LLM_API_KEY 还是示例值")
        return
    reply = LLMClient(cfg).get_response([{"role": "user", "content": "只回复两个字：你好"}])
    report("大模型", FAIL if reply.startswith("I encountered an error") else OK, f"{cfg.chat_model}: {reply[:60]}")


async def main() -> None:
    from mcp_chat.config import load_project_env

    if not (ROOT / ".env").exists():
        print("提示：还没有 .env，先执行  cp .env.example .env  再填写\n")
    load_project_env()
    check_imports()
    check_pure_logic()
    for coro in (check_calculator, check_mysql):
        try:
            await coro()
        except Exception as e:  # noqa: BLE001
            report(coro.__name__, FAIL, repr(e))
    check_amap()
    check_llm()
    print(f"\nnode: {shutil.which('node') or '未安装'}   docker: {shutil.which('docker') or '未安装'}")
    sys.exit(1 if FAIL in results else 0)


if __name__ == "__main__":
    asyncio.run(main())

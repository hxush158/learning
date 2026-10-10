"""4.1 自定义四则运算 MCP Server（FastMCP）。

默认 stdio 模式（由客户端以子进程方式拉起，不需要手动运行）。
也可以作为独立 HTTP 服务运行（第 6 节 LangGraph 示例可选用）：
    uv run python 02_CalculatorMCPServerTest/calculatorMCPServer.py --transport streamable-http --port 8001
    -> 端点 http://127.0.0.1:8001/mcp
"""
import argparse
import logging
import sys
import warnings

# mcp 1.9.x + 新版 pydantic-settings 的无害警告
warnings.filterwarnings("ignore", message=".*incomplete definition.*")

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import TextContent  # noqa: E402

# stdio 模式下 stdout 是协议通道，日志必须写到 stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("calculator_mcp_server")

mcp = FastMCP("calculator")


@mcp.tool()
async def add(a: float, b: float) -> list[TextContent]:
    """执行加法运算

    Args:
        a: 第一个数字
        b: 第二个数字
    """
    logger.info(f"Add operation: {a} + {b}")
    return [TextContent(type="text", text=str(a + b))]


@mcp.tool()
async def subtract(a: float, b: float) -> list[TextContent]:
    """执行减法运算

    Args:
        a: 第一个数字
        b: 第二个数字
    """
    logger.info(f"Subtract operation: {a} - {b}")
    return [TextContent(type="text", text=str(a - b))]


@mcp.tool()
async def multiply(a: float, b: float) -> list[TextContent]:
    """执行乘法运算

    Args:
        a: 第一个数字
        b: 第二个数字
    """
    logger.info(f"Multiply operation: {a} * {b}")
    return [TextContent(type="text", text=str(a * b))]


@mcp.tool()
async def divide(a: float, b: float) -> list[TextContent]:
    """执行除法运算

    Args:
        a: 被除数
        b: 除数（不能为 0）
    """
    logger.info(f"Divide operation: {a} / {b}")
    if b == 0:
        raise ValueError("Division by zero is not allowed")
    return [TextContent(type="text", text=str(a / b))]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.transport != "stdio":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        logger.info(f"calculator MCP server listening on http://{args.host}:{args.port}")
    mcp.run(transport=args.transport)

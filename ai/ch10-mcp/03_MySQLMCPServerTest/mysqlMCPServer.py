"""5. 自定义 MySQL MCP Server（低层 Server API）。

- Resources：每张表一个资源 mysql://<table>/data（读前 100 行）
- Tools：execute_sql（执行任意 SQL）

同一个 `mcp` 对象被三种传输方式复用：
    stdio            -> 直接运行本文件（由客户端以子进程拉起）
    SSE              -> sseServer.py
    Streamable HTTP  -> streamableHttpServer.py

⚠️ execute_sql 允许执行任意 SQL（含 UPDATE/DELETE），仅用于本地学习，请勿连接生产库。
"""
import asyncio
import logging
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.lowlevel import Server
from mcp.types import Resource, TextContent, Tool
from mysql.connector import Error, connect
from pydantic import AnyUrl

# 工程根目录的 .env（不依赖当前工作目录）
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# stdio 模式下 stdout 是协议通道，日志写到 stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mysql_mcp_server")


def get_db_config() -> dict:
    config = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DATABASE"),
        "charset": "utf8mb4",
        "collation": "utf8mb4_general_ci",
    }
    if not all([config["user"], config["password"], config["database"]]):
        logger.error("MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE are required (check .env)")
        raise ValueError("Missing required database configuration")
    return config


mcp = Server("mysql_mcp_server")


@mcp.list_resources()
async def list_resources() -> list[Resource]:
    """把数据库中的每张表作为一个资源。"""
    try:
        with connect(**get_db_config()) as conn, conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"Found tables: {tables}")
            return [
                Resource(
                    uri=f"mysql://{t}/data",
                    name=f"Table: {t}",
                    mimeType="text/plain",
                    description=f"Data in table: {t}",
                )
                for t in tables
            ]
    except Error as e:
        logger.error(f"Failed to list resources: {e}")
        return []


@mcp.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """读取 mysql://<table>/data 对应表的前 100 行（CSV 文本）。"""
    uri_str = str(uri)
    logger.info(f"Reading resource: {uri_str}")
    if not uri_str.startswith("mysql://"):
        raise ValueError(f"Invalid URI scheme: {uri_str}")

    table = uri_str[len("mysql://"):].split("/")[0]
    # 表名不能用参数化，做白名单校验防止 SQL 注入
    if not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise ValueError(f"Invalid table name: {table}")

    try:
        with connect(**get_db_config()) as conn, conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM `{table}` LIMIT 100")
            columns = [d[0] for d in cursor.description]
            rows = [",".join(map(str, r)) for r in cursor.fetchall()]
            return "\n".join([",".join(columns)] + rows)
    except Error as e:
        logger.error(f"Database error reading resource {uri}: {e}")
        raise RuntimeError(f"Database error: {e}")


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="execute_sql",
            description="Execute an SQL query on the MySQL server",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The SQL query to execute"}},
                "required": ["query"],
            },
        )
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    logger.info(f"Calling tool: {name} with arguments: {arguments}")
    if name != "execute_sql":
        raise ValueError(f"Unknown tool: {name}")
    query = (arguments or {}).get("query")
    if not query:
        raise ValueError("Query is required")

    config = get_db_config()
    try:
        with connect(**config) as conn, conn.cursor() as cursor:
            cursor.execute(query)
            if cursor.description:  # 有结果集：SELECT / SHOW / DESC ...
                columns = [d[0] for d in cursor.description]
                rows = [",".join(map(str, r)) for r in cursor.fetchall()]
                return [TextContent(type="text", text="\n".join([",".join(columns)] + rows))]
            # INSERT / UPDATE / DELETE ...
            conn.commit()
            return [TextContent(type="text", text=f"Query executed successfully. Rows affected: {cursor.rowcount}")]
    except Error as e:
        logger.error(f"Error executing SQL '{query}': {e}")
        return [TextContent(type="text", text=f"Error executing query: {e}")]


async def main() -> None:
    from mcp.server.stdio import stdio_server

    config = get_db_config()
    logger.info(f"Starting MySQL MCP server (stdio): {config['host']}:{config['port']}/{config['database']} as {config['user']}")
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

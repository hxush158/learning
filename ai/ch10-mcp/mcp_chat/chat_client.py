"""通用 MCP 聊天客户端（对应原课程 5 份几乎相同的 clientChatTest.py）。

一个 servers_config.json 里可以混合三种传输方式：
    stdio:            {"command": "python", "args": ["server.py"], "env": {...}}
    sse:              {"url": "http://127.0.0.1:8000/sse"}                      （或显式 "transport": "sse"）
    streamable_http:  {"url": "http://127.0.0.1:8000/mcp", "transport": "streamable_http"}
url 以 /sse 结尾默认按 sse 处理，其他 url 默认按 streamable_http 处理。

工作方式与原课程一致：把 MCP 的 tools / resources 描述写进 system prompt，
让大模型输出约定格式的 JSON 来“调用”工具（纯 prompt 方式，不依赖模型的 function calling）。

相对原版的修正：
1. 不再把用户输入转成小写（原版会把 POI ID “B020016GPH” 变成 “b020016gph” 导致查询失败）
2. 支持一轮对话内连续调用多个工具（如：先地理编码拿经纬度，再做路径规划）
3. 能解析模型包在 ```json 代码块里的 JSON
4. 工具结果只取文本内容，而不是把整个 pydantic 对象 repr 塞给模型
5. 用 AsyncExitStack 管理连接，退出时不再出现 cancel scope 报错
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .config import LLMConfig, load_servers_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# 屏蔽 httpx 每个请求一行的日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("mcp_chat")

MAX_TOOL_ROUNDS = 5


# ----------------------------------------------------------------------------
# Tool / Resource 描述
# ----------------------------------------------------------------------------
class Tool:
    def __init__(self, name: str, description: str, input_schema: Dict[str, Any]) -> None:
        self.name = name
        self.description = description or ""
        self.input_schema = input_schema or {}

    def format_for_llm(self) -> str:
        args_desc = []
        for param_name, param_info in self.input_schema.get("properties", {}).items():
            desc = param_info.get("description") or param_info.get("title") or "No description"
            line = f"- {param_name} ({param_info.get('type', 'any')}): {desc}"
            if param_name in self.input_schema.get("required", []):
                line += " (required)"
            args_desc.append(line)
        return f"Tool: {self.name}\nDescription: {self.description.strip()}\nArguments:\n" + "\n".join(args_desc)


class Resource:
    def __init__(self, uri: str, name: str, description: Optional[str], mime_type: Optional[str]) -> None:
        self.uri = uri
        self.name = name
        self.description = description
        self.mime_type = mime_type

    def format_for_llm(self) -> str:
        return f"URI: {self.uri}\nName: {self.name}\nDescription: {self.description}\nMimeType: {self.mime_type}"


# ----------------------------------------------------------------------------
# MCP Server 连接
# ----------------------------------------------------------------------------
class Server:
    """一个 MCP Server 的会话。"""

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self.session: Optional[ClientSession] = None
        self._exit_stack = AsyncExitStack()
        self.tools: List[Tool] = []
        self.resources: List[Resource] = []

    @property
    def transport(self) -> str:
        if "command" in self.config:
            return "stdio"
        t = self.config.get("transport")
        if t:
            return t.replace("-", "_")
        return "sse" if self.config["url"].rstrip("/").endswith("/sse") else "streamable_http"

    async def initialize(self) -> None:
        transport = self.transport
        logger.info(f"Connecting to MCP server [{self.name}] via {transport} ...")
        if transport == "stdio":
            command = self.config["command"]
            if command == "npx":
                command = shutil.which("npx") or command
                if not shutil.which("npx"):
                    raise RuntimeError("找不到 npx，请先安装 Node.js：https://nodejs.org")
            env = self.config.get("env")
            for k, v in (env or {}).items():
                if isinstance(v, str) and "${" in v:
                    logger.warning(f"[{self.name}] 环境变量 {k} 未设置（{v}），请检查 .env")
            params = StdioServerParameters(
                command=command,
                args=self.config.get("args", []),
                env={**os.environ, **env} if env else None,
                cwd=self.config.get("cwd"),
            )
            read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        elif transport == "sse":
            read, write = await self._exit_stack.enter_async_context(sse_client(url=self.config["url"]))
        elif transport == "streamable_http":
            read, write, _get_session_id = await self._exit_stack.enter_async_context(
                streamablehttp_client(url=self.config["url"])
            )
        else:
            raise ValueError(f"未知的 transport: {transport}")

        self.session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        init_result = await self.session.initialize()
        caps = init_result.capabilities

        if caps.tools:
            result = await self.session.list_tools()
            self.tools = [Tool(t.name, t.description, t.inputSchema) for t in result.tools]
        if caps.resources:
            try:
                result = await self.session.list_resources()
                self.resources = [
                    Resource(str(r.uri), r.name, r.description, r.mimeType) for r in result.resources
                ]
            except Exception as e:  # 有的 server 声明了能力但没实现
                logger.warning(f"[{self.name}] list_resources failed: {e}")
        logger.info(f"[{self.name}] ready: {len(self.tools)} tools, {len(self.resources)} resources")

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], retries: int = 2, delay: float = 1.0) -> str:
        assert self.session, f"Server {self.name} not initialized"
        for attempt in range(1, retries + 1):
            try:
                logger.info(f"[{self.name}] call_tool {tool_name} {arguments}")
                result = await self.session.call_tool(tool_name, arguments)
                text = _content_to_text(result.content)
                return f"[ERROR] {text}" if result.isError else text
            except Exception as e:
                logger.warning(f"Error executing tool: {e}. Attempt {attempt} of {retries}.")
                if attempt == retries:
                    raise
                await asyncio.sleep(delay)
        return ""

    async def read_resource(self, uri: str) -> str:
        assert self.session, f"Server {self.name} not initialized"
        logger.info(f"[{self.name}] read_resource {uri}")
        result = await self.session.read_resource(uri)
        return "\n".join(getattr(c, "text", "") or str(c) for c in result.contents)

    async def cleanup(self) -> None:
        try:
            await self._exit_stack.aclose()
        except Exception as e:  # 关闭子进程/连接时的噪音不影响结果
            logger.debug(f"cleanup {self.name}: {e}")
        self.session = None


def _content_to_text(content: List[Any]) -> str:
    parts = []
    for c in content:
        if getattr(c, "type", None) == "text":
            parts.append(c.text)
        else:
            parts.append(str(c))
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# LLM 调用（直接用 requests 调 OpenAI 兼容接口，便于看清楚底层报文）
# ----------------------------------------------------------------------------
class LLMClient:
    def __init__(self, cfg: LLMConfig) -> None:
        self.url = cfg.chat_completions_url
        self.api_key = cfg.api_key
        self.model = cfg.chat_model

    def get_response(self, messages: List[Dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": 4000}
        try:
            resp = requests.post(self.url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting LLM response: {e}")
            if e.response is not None:
                logger.error(f"Status code: {e.response.status_code}, body: {e.response.text}")
            return f"I encountered an error: {e}. Please try again or rephrase your request."


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中解析 JSON：支持纯 JSON、```json 代码块、前后带少量文字的情况。"""
    text = text.strip()
    candidates = [text]
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        candidates.append(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


SYSTEM_PROMPT = """You are a helpful assistant with access to these resources and tools:

resources:
{resources}

tools:
{tools}

Choose the appropriate resource or tool based on the user's question. If no resource or tool is needed, reply directly.

IMPORTANT: When you need to read a resource, respond ONLY with this exact JSON object, nothing else:
{{"resource": "resource-name", "uri": "resource-URI"}}

IMPORTANT: When you need to use a tool, respond ONLY with this exact JSON object, nothing else:
{{"tool": "tool-name", "arguments": {{"argument-name": "value"}}}}

You may call tools one after another (one JSON per reply) if the task needs several steps,
e.g. first convert an address to coordinates, then plan a route.

After receiving a tool's or resource's result:
1. Transform the raw data into a natural, conversational response
2. Keep responses concise but informative
3. Focus on the most relevant information
4. Answer in the same language as the user

Please use only the resources or tools that are explicitly defined above."""


# ----------------------------------------------------------------------------
# 会话：用户 <-> LLM <-> MCP Servers
# ----------------------------------------------------------------------------
class ChatSession:
    def __init__(self, servers: List[Server], llm_client: LLMClient) -> None:
        self.servers = servers
        self.llm = llm_client

    async def _dispatch(self, call: Dict[str, Any]) -> Optional[str]:
        """如果 LLM 输出的是工具/资源调用，执行并返回结果；否则返回 None。"""
        if "tool" in call:
            name, args = call["tool"], call.get("arguments") or {}
            for s in self.servers:
                if any(t.name == name for t in s.tools):
                    try:
                        return f"Tool '{name}' result:\n{await s.call_tool(name, args)}"
                    except Exception as e:
                        return f"Error executing tool {name}: {e}"
            return f"No server found with tool: {name}"
        if "uri" in call or "resource" in call:
            uri = call.get("uri") or call.get("resource")
            for s in self.servers:
                if any(r.uri == uri for r in s.resources):
                    try:
                        return f"Resource '{uri}' content:\n{await s.read_resource(uri)}"
                    except Exception as e:
                        return f"Error reading resource {uri}: {e}"
            return f"No server found with resource: {uri}"
        return None

    async def answer(self, messages: List[Dict[str, str]], user_input: str) -> str:
        messages.append({"role": "user", "content": user_input})
        for _ in range(MAX_TOOL_ROUNDS):
            reply = await asyncio.to_thread(self.llm.get_response, messages)
            call = extract_json(reply)
            result = await self._dispatch(call) if call else None
            messages.append({"role": "assistant", "content": reply})
            if result is None:
                return reply
            logger.info(f"LLM requested: {json.dumps(call, ensure_ascii=False)}")
            messages.append({"role": "system", "content": result})
        # 工具轮数用完，让模型基于已有结果直接作答
        messages.append({"role": "system", "content": "Now answer the user directly without calling more tools."})
        reply = await asyncio.to_thread(self.llm.get_response, messages)
        messages.append({"role": "assistant", "content": reply})
        return reply

    async def start(self) -> None:
        try:
            for s in self.servers:
                await s.initialize()

            tools_desc = "\n\n".join(t.format_for_llm() for s in self.servers for t in s.tools) or "(none)"
            res_desc = "\n\n".join(r.format_for_llm() for s in self.servers for r in s.resources) or "(none)"
            messages: List[Dict[str, str]] = [
                {"role": "system", "content": SYSTEM_PROMPT.format(resources=res_desc, tools=tools_desc)}
            ]

            print("\n已连接 MCP Server：" + ", ".join(s.name for s in self.servers))
            print("输入问题开始对话，输入 quit / exit 退出。\n")
            while True:
                try:
                    user_input = (await asyncio.to_thread(input, "user: ")).strip()
                except (KeyboardInterrupt, EOFError):
                    break
                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit"):
                    break
                reply = await self.answer(messages, user_input)
                print(f"\nassistant: {reply}\n")
        finally:
            # 按相反顺序关闭，避免 anyio cancel scope 报错
            for s in reversed(self.servers):
                await s.cleanup()


async def run_chat(config_path: str) -> None:
    """入口：python clientChatTest.py 时调用。"""
    llm_cfg = LLMConfig()
    servers_cfg = load_servers_config(config_path)
    servers = [Server(name, cfg) for name, cfg in servers_cfg["mcpServers"].items()]
    await ChatSession(servers, LLMClient(llm_cfg)).start()

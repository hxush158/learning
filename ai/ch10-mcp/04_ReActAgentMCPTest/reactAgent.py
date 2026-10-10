"""6. LangGraph 预置 ReAct Agent + MCP Server（langchain-mcp-adapters）。

与 01~03 的区别：这里不再靠 prompt 约定 JSON，而是用模型原生的 function calling，
MCP 工具被 langchain-mcp-adapters 自动转换成 LangChain Tool。

运行：
    uv run python 04_ReActAgentMCPTest/reactAgent.py                      # 交互式对话（流式输出）
    uv run python 04_ReActAgentMCPTest/reactAgent.py -q "3乘以4等于多少"   # 单个问题
    uv run python 04_ReActAgentMCPTest/reactAgent.py --verbose -q "深圳的天气如何"   # 打印完整消息链
    uv run python 04_ReActAgentMCPTest/reactAgent.py --save-graph          # 导出 agent 结构图 graph.png（需联网）

MCP Server：
    - calculator：默认以 stdio 子进程拉起；加 --calc-url http://127.0.0.1:8001/mcp 则改连独立运行的
      calculatorMCPServer.py --transport streamable-http --port 8001
    - 高德地图：.env 中有 AMAP_MAPS_API_KEY 时，连接高德官方远程 Streamable HTTP 端点；没有则跳过
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, List

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from mcp_chat.config import LLMConfig, load_project_env

HERE = Path(__file__).parent
CALCULATOR = HERE.parent / "02_CalculatorMCPServerTest" / "calculatorMCPServer.py"


def build_llm():
    """统一用 OpenAI 兼容接口：通义千问 / DeepSeek / OpenAI 都可以，在 .env 里切换。"""
    cfg = LLMConfig()
    return init_chat_model(
        model=cfg.chat_model,
        model_provider="openai",
        base_url=cfg.api_base,
        api_key=cfg.api_key,
        temperature=0,
    )


def build_mcp_connections(calc_url: str | None) -> dict:
    connections: dict[str, Any] = {}
    if calc_url:
        connections["calculator"] = {"url": calc_url, "transport": "streamable_http"}
    else:
        connections["calculator"] = {
            "command": sys.executable,
            "args": [str(CALCULATOR)],
            "transport": "stdio",
        }

    amap_key = os.getenv("AMAP_MAPS_API_KEY")
    if amap_key:
        # 高德官方托管的远程 MCP Server（也可用 SSE：https://mcp.amap.com/sse?key=...）
        connections["amap-maps"] = {
            "url": f"https://mcp.amap.com/mcp?key={amap_key}",
            "transport": "streamable_http",
        }
    else:
        print("（未配置 AMAP_MAPS_API_KEY，只加载 calculator 工具）")
    return connections


def parse_messages(messages: List[Any]) -> None:
    """打印 Human / AI / Tool 消息链，便于理解 ReAct 的 思考 -> 调用工具 -> 观察 循环。"""
    print("=== 消息解析结果 ===")
    for idx, msg in enumerate(messages, 1):
        msg_type = msg.__class__.__name__
        print(f"\n消息 {idx}  类型: {msg_type}")
        print(f"内容: {msg.content if msg.content else '<空>'}")
        if msg_type == "AIMessage":
            for tc in getattr(msg, "tool_calls", []) or []:
                print(f"  工具调用 -> {tc['name']}({tc['args']})  id={tc['id']}")
            usage = (getattr(msg, "response_metadata", {}) or {}).get("token_usage")
            if usage:
                print(f"  令牌使用: {usage}")
        if msg_type == "ToolMessage":
            print(f"  工具名称: {getattr(msg, 'name', '')}  调用ID: {getattr(msg, 'tool_call_id', '')}")
        print("-" * 50)


async def ask(agent, question: str, config: dict, verbose: bool) -> None:
    if verbose:
        resp = await agent.ainvoke({"messages": [HumanMessage(content=question)]}, config)
        parse_messages(resp["messages"])
        print(f"\nassistant: {resp['messages'][-1].content}\n")
        return

    print("assistant: ", end="", flush=True)
    async for chunk, metadata in agent.astream(
        {"messages": [HumanMessage(content=question)]}, config=config, stream_mode="messages"
    ):
        if metadata.get("langgraph_node") == "tools":  # 跳过工具原始输出
            continue
        if chunk.content:
            print(chunk.content, end="", flush=True)
    print("\n")


async def run_agent(args) -> None:
    load_project_env()
    llm = build_llm()

    client = MultiServerMCPClient(build_mcp_connections(args.calc_url))
    tools = await client.get_tools()
    print("已加载工具:", ", ".join(t.name for t in tools))

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content="你是一个AI助手。需要计算时调用计算器工具，涉及地理位置、天气、路线时调用高德地图工具。"),
        checkpointer=InMemorySaver(),  # 短期记忆：同一 thread_id 内记住上下文
    )

    if args.save_graph:
        out = HERE / "graph.png"
        out.write_bytes(agent.get_graph().draw_mermaid_png())
        print(f"Graph visualization saved as {out}")

    config = {"configurable": {"thread_id": "1"}}

    if args.question:
        await ask(agent, args.question, config, args.verbose)
        return

    print("输入问题开始对话，输入 quit / exit 退出。示例：3乘以4等于多少 / 深圳的天气如何\n")
    while True:
        try:
            q = (await asyncio.to_thread(input, "user: ")).strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not q:
            continue
        if q.lower() in ("quit", "exit"):
            break
        await ask(agent, q, config, args.verbose)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--question", help="只问一个问题后退出")
    parser.add_argument("--verbose", action="store_true", help="非流式，打印完整消息链")
    parser.add_argument("--calc-url", help="calculator 改用 Streamable HTTP，例如 http://127.0.0.1:8001/mcp")
    parser.add_argument("--save-graph", action="store_true", help="导出 agent 结构图 graph.png")
    asyncio.run(run_agent(parser.parse_args()))

# 第10章 MCP 技术应用与开发 —— 可运行工程

学习课程第10章《MCP技术应用与开发》时，将课程示例代码整理、修复并重构为可直接运行的工程。课程讲义不包含在本仓库中。

## 本章内容

| 目录 | 对应讲义 | 内容 | 需要什么 |
|---|---|---|---|
| `02_CalculatorMCPServerTest` | §4 | 用 **FastMCP** 自己写一个四则运算 MCP Server | 不需要 Key，**建议从这里开始** |
| `01_AmapMCPServerTest` | §3 | 接入高德地图官方 MCP Server（npx 启动，stdio） | Node.js + 高德 Key |
| `03_MySQLMCPServerTest` | §5 | 用**低层 Server API** 写 MySQL MCP Server（Resources + Tools），分别以 **stdio / SSE / Streamable HTTP** 三种传输方式运行 | Docker |
| `04_ReActAgentMCPTest` | §6 | LangGraph `create_react_agent` + `langchain-mcp-adapters`，用模型原生 function calling 调 MCP 工具 | 大模型 Key |
| `mcp_chat/` | — | 公共代码：通用 MCP 聊天客户端（原来 5 份重复的 `clientChatTest.py` 合成一份） | |

每个目录都有两类脚本：
- `*ServerTest.py` —— **不需要大模型**，直接用 MCP SDK 调 Server，看清楚协议层面的 `initialize / list_tools / call_tool / read_resource`
- `clientChatTest.py` —— 大模型 + MCP 的对话程序

## 1. 安装

前置：[uv](https://docs.astral.sh/uv/)（`brew install uv`）。§3 需要 Node.js（`brew install node`），§5 需要 Docker Desktop。

```bash
cd ch10-mcp
uv sync                    # 自动安装 Python 3.11 + 全部依赖到 .venv
cp .env.example .env       # 然后编辑 .env，填大模型 Key 等
uv run python scripts/check_env.py   # 自检，没配的部分显示 SKIP
```

> ⚠️ **不要直接 `pip install mcp`**：现在默认会装到 mcp 2.x，它把 `FastMCP`、`streamablehttp_client` 都改了名，课程代码会直接报错。本工程在 `pyproject.toml` 里固定了 `mcp>=1.9.4,<1.10`。

### 大模型配置

`.env` 里配置任意 **OpenAI 兼容**接口即可（原课程写死了阿里云百炼国内站）：

| 服务 | LLM_BASE_URL | LLM_CHAT_MODEL |
|---|---|---|
| 阿里云百炼 国际站 | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | `qwen-plus` / `qwen-max` |
| 阿里云百炼 国内站 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

## 2. 运行

所有命令都在 `ch10-mcp` 根目录执行。

### §4 自定义四则运算 MCP Server
```bash
uv run python 02_CalculatorMCPServerTest/calculatorMCPServerTest.py   # 协议层测试，无需 Key
uv run python 02_CalculatorMCPServerTest/clientChatTest.py            # 大模型对话：“调用工具计算3*2”
uv run python 02_CalculatorMCPServerTest/clientChatTest.py --with-amap  # 同时挂两个 Server
```

### §3 高德地图 MCP Server
Key 申请：<https://lbs.amap.com/api/mcp-server/create-project-and-key>，填到 `.env` 的 `AMAP_MAPS_API_KEY`。
```bash
uv run python 01_AmapMCPServerTest/amapMCPServerTest.py   # 逐个调用地图工具（地理编码、天气、路线、搜索…）
uv run python 01_AmapMCPServerTest/clientChatTest.py      # “我要从深圳市南山区中兴大厦骑行到宝安区宝安体育馆，帮我规划下路径”
```

### §5 MySQL MCP Server（三种传输方式）
```bash
docker compose up -d       # 启动 MySQL 8.0，首次启动自动导入 students_info / students_score 两张表
```

| 传输方式 | 终端 1（服务端） | 终端 2（客户端） |
|---|---|---|
| stdio | 不需要，客户端自动拉起子进程 | `uv run python 03_MySQLMCPServerTest/clientChatTest.py` |
| SSE | `uv run python 03_MySQLMCPServerTest/sseServer.py` | `uv run python 03_MySQLMCPServerTest/clientChatTest.py --transport sse` |
| Streamable HTTP | `uv run python 03_MySQLMCPServerTest/streamableHttpServer.py` | `uv run python 03_MySQLMCPServerTest/clientChatTest.py --transport streamable` |

把 `clientChatTest.py` 换成 `mysqlMCPServerTest.py`（参数相同）就是不经过大模型的协议层测试。

参考问题：有哪些表可以使用 / 查询学生成绩表中分数最高的 / 对学生信息表和学生成绩表进行联表查询，生成每个学生姓名、成绩 / 将学生姓名为张三的改为钱八，并获取最新的信息表

重置数据：`docker compose down -v && docker compose up -d`

> `execute_sql` 工具可以执行任意 SQL（包括 UPDATE / DELETE），只用于本地学习库。

### §6 LangGraph ReAct Agent + MCP
```bash
uv run python 04_ReActAgentMCPTest/reactAgent.py                              # 交互式，流式输出
uv run python 04_ReActAgentMCPTest/reactAgent.py --verbose -q "3乘以4等于多少"  # 打印 思考→工具调用→观察 的完整消息链
```
calculator 默认用 stdio 拉起；想体验远程方式：先运行
`uv run python 02_CalculatorMCPServerTest/calculatorMCPServer.py --transport streamable-http --port 8001`，
再给 agent 加 `--calc-url http://127.0.0.1:8001/mcp`。配置了高德 Key 时会自动连高德官方远程 MCP（`https://mcp.amap.com/mcp`）。

## 3. 相对原课程代码的改动

| 问题 | 处理 |
|---|---|
| 依赖未锁版本，现在装到的 mcp 2.x 不兼容 | `pyproject.toml` + uv 管理，固定 mcp 1.9.x |
| `clientChatTest.py` 复制了 5 份，只差传输方式 | 合并成 `mcp_chat/chat_client.py`，按配置自动选 stdio / sse / streamable_http |
| 用户输入被 `.lower()`，POI ID `B020016GPH` 变成小写后查不到 | 去掉 |
| 每轮只能调一次工具，路线规划（先地址转坐标再规划）做不完 | 一轮最多连续 5 次工具调用 |
| 模型输出 `` ```json `` 代码块时解析失败、工具不会被调用 | 兼容代码块 / 前后带文字的 JSON |
| 6 份 `.env` 分散各处，API Key 还要另设系统环境变量；MySQL 密码明文写在代码包里 | 根目录统一一个 `.env`（已加入 `.gitignore`），提供 `.env.example` |
| `servers_config.json` 里 `python xxx.py` 依赖当前目录、可能用到系统 Python | 自动换成虚拟环境的解释器 + 绝对路径，任何目录都能运行 |
| docker-compose 挂载的 `my.cnf` 实际是空目录；5.7 镜像来自阿里云仓库且不支持 Apple Silicon；SQL 要手动导入 | 官方 `mysql:8.0`，SQL 自动初始化 |
| `read_resource` 拼接表名有 SQL 注入风险 | 表名白名单校验 |
| `from asyncio import timeout`（3.11+ 才有）、`from click import command` 等无用导入 | 删除 |
| §6 写死 DeepSeek | 与其他示例共用 `.env` 里的大模型配置 |

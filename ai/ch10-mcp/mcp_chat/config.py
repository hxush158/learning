"""配置相关：统一加载工程根目录的 .env，解析 servers_config.json。

原课程代码的问题：每个子目录各有一份 .env，API Key 又要求另外设置成系统环境变量，
而且 servers_config.json 里的 "python xxx.py" 依赖当前工作目录。这里统一处理。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

# 工程根目录 = mcp_chat 的上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_env() -> None:
    """加载工程根目录下的 .env（不覆盖已经存在的系统环境变量）。"""
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def resolve_env_vars(data: Any) -> Any:
    """递归替换字符串中的 ${VAR_NAME} 占位符。"""
    if isinstance(data, dict):
        return {k: resolve_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_env_vars(v) for v in data]
    if isinstance(data, str):
        return os.path.expandvars(data)
    return data


def load_servers_config(file_path: str | Path) -> Dict[str, Any]:
    """读取 servers_config.json，并把 stdio 服务器里的相对路径解析为相对于配置文件所在目录。

    - "command": "python"  -> 当前虚拟环境的解释器（sys.executable），避免用到系统 python 缺依赖
    - 以 .py 结尾的相对路径参数 -> 绝对路径，这样从任何目录运行都可以
    """
    file_path = Path(file_path).resolve()
    with open(file_path, "r", encoding="utf-8") as f:
        config = resolve_env_vars(json.load(f))

    base_dir = file_path.parent
    for srv in config.get("mcpServers", {}).values():
        if "command" not in srv:
            continue
        if srv["command"] in ("python", "python3"):
            srv["command"] = sys.executable
        srv["args"] = [
            str((base_dir / a).resolve()) if a.endswith(".py") and not os.path.isabs(a) else a
            for a in srv.get("args", [])
        ]
        srv.setdefault("cwd", str(base_dir))
    return config


class LLMConfig:
    """大模型配置（OpenAI 兼容接口）。"""

    def __init__(self) -> None:
        load_project_env()
        # 兼容原课程使用的 DASHSCOPE_API_KEY
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.chat_model = os.getenv("LLM_CHAT_MODEL")

        missing = [n for n, v in [("LLM_API_KEY", self.api_key), ("LLM_BASE_URL", self.base_url),
                                  ("LLM_CHAT_MODEL", self.chat_model)] if not v]
        if missing:
            raise ValueError(f"请在工程根目录的 .env 中配置: {', '.join(missing)}（参考 .env.example）")

    @property
    def api_base(self) -> str:
        """不带 /chat/completions 的 base url（LangChain 用）。"""
        url = self.base_url.rstrip("/")
        suffix = "/chat/completions"
        return url[: -len(suffix)] if url.endswith(suffix) else url

    @property
    def chat_completions_url(self) -> str:
        """完整的 /chat/completions 地址（原生 requests 调用用）。"""
        return self.api_base + "/chat/completions"

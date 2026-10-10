# -*- coding: utf-8 -*-
"""
财务慧眼 · AI 财报风险体检助手 —— 配置模块
从环境变量或本地 .env 文件读取 DeepSeek API 配置。
"""
import os
from pathlib import Path

# DeepSeek API 配置（openai SDK 兼容）
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def load_env_file(path: Path | str | None = None) -> None:
    """加载项目根目录下的 .env 文件（若存在），不覆盖已设置的环境变量。"""
    env_path = Path(path) if path else Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# 启动时自动加载 .env（若存在）
load_env_file()

# 刷新：加载 .env 后重新读取
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)


def get_api_key() -> str:
    """返回可用的 API Key；优先 Streamlit Cloud secrets，其次环境变量/本地 .env。"""
    # Streamlit Community Cloud 后台配置的 secrets
    try:
        import streamlit as st
        if "DEEPSEEK_API_KEY" in st.secrets:
            return str(st.secrets["DEEPSEEK_API_KEY"]).strip()
    except Exception:  # noqa: BLE001
        pass
    return (DEEPSEEK_API_KEY or os.environ.get("DEEPSEEK_API_KEY", "")).strip()

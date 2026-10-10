# -*- coding: utf-8 -*-
"""
财务慧眼 · 结论词云生成模块
对 AI 解读文本做中文分词（jieba）+ 停用词过滤，按科研色卡配色生成词云图。
依赖：jieba、wordcloud；中文字体使用系统微软雅黑。
失败时抛出异常，由调用方降级提示，不影响主流程。
"""
from __future__ import annotations

import io
import re

# 科研色卡（与界面一致）
CLOUD_COLORS = ["#2F74B8", "#507D39", "#D45959", "#E2A479", "#5E379D", "#5A97D0", "#C27B7B"]

# 停用词：通用虚词、指代、AI 套话，避免词云被无意义词占据
STOP_WORDS = set(
    "的 了 和 与 及 在 是 我 我们 你 他 她 它 这 那 有 为 以 于 对 从 到 被 把 让 向 "
    "公司 企业 该 此 其 之 等 中 内 后 前 时 个 项 家 种 方面 情况 数据 指标 说明 显示 "
    "可以 需要 应该 可能 能够 通过 进行 以及 或者 而且 但是 因为 所以 如果 虽然 然而 "
    "分析 解读 建议 报告 工具 本作品 我们 你们 他们 大家 今年 目前 以上 如下 如下所述 "
    "deepseek ai AI 说明 提示 注意 总体 整体 综合 可见 由此 综上 此外 同时 另外".split()
)

# 词云画布尺寸
W, H = 900, 480


def _pick_font_path() -> str:
    """找一个可用的中文字体：优先仓库内置开源字体，其次 Windows 系统字体。"""
    import os
    root = os.path.dirname(os.path.abspath(__file__))
    # 1) 仓库根目录内置开源字体（Streamlit Cloud / Linux 服务器用这个）
    for name in ["SimHei.ttf", "fonts/SimHei.ttf"]:
        p = os.path.join(root, name)
        if os.path.exists(p):
            return p
    # 2) Windows 本地开发
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("未找到可用中文字体")


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 过滤：长度≥2、非纯数字标点、非停用词。"""
    import jieba

    tokens = []
    for tok in jieba.cut(text):
        tok = tok.strip()
        if len(tok) < 2:
            continue
        if tok in STOP_WORDS:
            continue
        if re.fullmatch(r"[\d\.\,\%\-\—]+", tok):
            continue
        if not re.search(r"[一-鿿A-Za-z]", tok):
            continue
        tokens.append(tok)
    return tokens


def make_wordcloud(text: str, width: int = W, height: int = H) -> bytes:
    """把 AI 解读文本生成词云 PNG，返回 PNG 字节。调用方 st.image(bytes) 即可。"""
    from wordcloud import WordCloud

    tokens = _tokenize(text)
    if len(tokens) < 8:
        raise ValueError(f"有效分词仅 {len(tokens)} 个，不足以生成词云")

    freq: dict[str, int] = {}
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1

    wc = WordCloud(
        font_path=_pick_font_path(),
        width=width,
        height=height,
        background_color="white",
        colormap=None,
        color_func=lambda *args, **kwargs: CLOUD_COLORS[hash(args[0]) % len(CLOUD_COLORS)],
        max_words=60,
        prefer_horizontal=0.9,
        margin=8,
    )
    wc.generate_from_frequencies(freq)
    img = wc.to_image()

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

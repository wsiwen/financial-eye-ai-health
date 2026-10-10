# -*- coding: utf-8 -*-
"""
财务慧眼 · AI 解读模块
调用 DeepSeek（OpenAI 兼容接口）对财务指标做自然语言解读、风险提示与行动建议。
未配置 API Key 或调用失败时，自动降级为基于规则的本地解读，保证演示不中断。
"""
from __future__ import annotations

import json

import config

SYSTEM_PROMPT = (
    "你是一名专业的财务分析师助手，服务对象是中小企业财务人员和管理者。"
    "你将收到一家A股上市公司的财务指标数据（多期），请完成以下任务：\n"
    "1. 分四个维度解读：偿债能力、营运能力、盈利能力、现金流质量；指出每维度的核心变化（对比前一期）和含义；\n"
    "2. 识别风险点：结合给出的风险预警，说明风险的成因和可能的后果；\n"
    "3. 给出可执行的管理建议（具体、贴近实务）；\n"
    "4. 用一两句话做整体总结。\n"
    "要求：只依据给定数据，不得编造数据或引用外部事实；语言通俗易懂，避免堆砌术语；"
    "金额数字用万元/亿元表达时请自行换算并标注；输出为结构化Markdown，含小标题。"
)


def _build_user_content(indicators: dict, risks: list[dict], company: str, code: str) -> str:
    """把指标数据构造成给模型的结构化输入。"""
    periods = indicators["periods"]
    series = indicators["series"]
    latest = indicators["latest_index"]

    rows = []
    for i in range(min(2, len(periods))):  # 最近两期
        row = {"报告期": periods[i]}
        for key, values in series.items():
            if i < len(values) and values[i] is not None:
                row[INDICATOR_CN[key]] = round(values[i], 4) if abs(values[i]) < 1e15 else values[i]
        rows.append(row)

    payload = {
        "公司": company,
        "股票代码": code,
        "指标口径说明": {
            "流动比率/速动比率/现金比率": "倍",
            "资产负债率/毛利率/净利率/营业利润率/ROE/ROA/经营现金流占营收比": "百分比",
            "周转率": "次",
            "经营现金流净额": "元",
        },
        "最近两期指标": rows,
        "规则预警（通用阈值，供参考）": [
            {"指标": r["name"], "值": r["value"], "单位": r["unit"], "等级": r["level"], "说明": r["desc"]}
            for r in risks
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


INDICATOR_CN = {
    "current_ratio": "流动比率", "quick_ratio": "速动比率", "cash_ratio": "现金比率",
    "debt_ratio": "资产负债率", "ar_turnover": "应收账款周转率", "inv_turnover": "存货周转率",
    "asset_turnover": "总资产周转率", "gross_margin": "毛利率", "net_margin": "净利率",
    "operating_margin": "营业利润率", "roe": "净资产收益率ROE", "roa": "总资产报酬率ROA",
    "ocf_to_revenue": "经营现金流占营收比", "ocf_to_netprofit": "经营现金流占净利润比",
    "ocf_net": "经营现金流净额",
}


def ai_analyze(indicators: dict, risks: list[dict], company: str, code: str, api_key: str | None = None) -> str:
    """调用 DeepSeek 生成解读；失败或未配置 key 时降级为本地规则解读。"""
    key = api_key or config.get_api_key()
    if not key:
        return _local_fallback(indicators, risks, company)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=config.DEEPSEEK_BASE_URL)
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_content(indicators, risks, company, code)},
            ],
            temperature=0.2,
            timeout=120,
        )
        text = resp.choices[0].message.content.strip()
        return text if text else _local_fallback(indicators, risks, company)
    except Exception as exc:  # noqa: BLE001
        return _local_fallback(indicators, risks, company, reason=str(exc))


def ask_followup(question: str, indicators: dict, risks: list[dict], company: str, code: str,
                 ai_text: str, history: list[dict] | None = None, api_key: str | None = None) -> str:
    """基于已算指标与首份解读，回答用户的追问（交互式 Agent）。失败降级返回提示。"""
    key = api_key or config.get_api_key()
    if not key:
        return "⚠️ 未配置 DeepSeek API Key，追问功能暂不可用。可在左侧栏填入 Key 后重试。"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=config.DEEPSEEK_BASE_URL)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n用户已看过首份体检报告，现在就报告内容追问。"
             "请只依据给定的指标数据与首份报告回答，不得编造新数据；不知道就明说。"},
            {"role": "user", "content": _build_user_content(indicators, risks, company, code)},
        ]
        if ai_text:
            messages.append({"role": "assistant", "content": ai_text[:2000]})
        for h in (history or [])[-4:]:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": question})
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL, messages=messages, temperature=0.3, timeout=120,
        )
        return resp.choices[0].message.content.strip() or "（未获得有效回答，请换个问法）"
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ AI 回答失败：{str(exc)[:150]}。请稍后重试。"


def _local_fallback(indicators: dict, risks: list[dict], company: str, reason: str | None = None) -> str:
    """规则引擎本地解读（不依赖外部模型）。"""
    series = indicators["series"]
    periods = indicators["periods"]
    latest = indicators["latest_index"]
    lines = [f"## 财务慧眼 · {company} 财务风险体检（规则模式解读）", ""]
    if reason:
        lines.append(f"> 说明：AI 模型未启用（{reason[:200]}），以下为规则引擎自动解读。")

    def v(key):
        if key in series and latest < len(series[key]) and series[key][latest] is not None:
            return series[key][latest]
        return None

    lines.append(f"**报告期：{periods[latest] if periods else '—'}**")
    lines.append("")
    dims = [
        ("偿债能力", "debt_ratio", "流动比率", "current_ratio"),
        ("盈利能力", "net_margin", "毛利率", "gross_margin"),
        ("现金流质量", "ocf_net", "经营现金流占营收比", "ocf_to_revenue"),
    ]
    for dim, k1, k2, k3 in dims:
        seg = [f"### {dim}", ""]
        a, b = v(k1), v(k2)
        if a is not None and b is not None:
            seg.append(f"- {k1}：{a:,.2f}；{k2}：{b:,.2f}")
        elif a is not None:
            seg.append(f"- {k1}：{a:,.2f}")
        lines.extend(seg)

    lines.append("### 风险清单")
    lines.append("")
    if risks:
        for r in risks:
            lines.append(f"- **{r['name']}**（{r['value']:,.2f} {r['unit']}）：{r['desc']}")
    else:
        lines.append("- 未触发通用阈值风险，整体财务结构稳健。")
    lines.append("")
    lines.append("> 提示：接入 DeepSeek API Key 后可获得更深入、结合行业语境的完整解读。")
    return "\n".join(lines)

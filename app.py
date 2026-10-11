# -*- coding: utf-8 -*-
"""
慧眼 · AI 财报风险体检 Agent（Streamlit 主程序 v2）
运行：streamlit run app.py
五大页签：体检总览 / 指标明细 / 风险预警 / AI 解读 / 结论词云
"""
from __future__ import annotations

import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
import indicators as ind
from ai_analyzer import ai_analyze, ask_followup, INDICATOR_CN
from data_fetcher import fetch_financial_statements, get_company_name
from report_exporter import build_report_docx, build_report_markdown
from wordcloud_gen import make_wordcloud

st.set_page_config(page_title="慧眼 · AI 财报风险体检 Agent", page_icon="📊", layout="wide")

DEFAULT_CODE = "600519"
DEFAULT_PERIODS = 5

# 科研低饱和色板
C_BLUE = "#2F74B8"
C_GREEN = "#507D39"
C_RED = "#D45959"
C_ORANGE = "#E2A479"
C_PURPLE = "#5E379D"

# 全局主题注入：侧边栏 / 主按钮 / 标题统一色板
st.markdown(
    f"""
    <style>
    /* 侧边栏 */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #F0F4FA 0%, #E6EDF6 100%);
        border-right: 1px solid #D5DEEA;
    }}
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{
        color: {C_BLUE};
    }}
    /* 主按钮（开始体检） */
    section[data-testid="stSidebar"] button[kind="primary"],
    button[kind="primaryFormSubmit"] {{
        background: {C_BLUE} !important;
        border: none !important;
        border-radius: 6px !important;
    }}
    button[kind="primary"]:hover {{
        background: #245A8F !important;
    }}
    /* 主标题 */
    h1, h2, h3 {{ color: #1e3a8a !important; }}
    /* 分割线 */
    hr {{ border-color: #D5DEEA !important; }}
    /* Tab 栏居中 + 加大字号，像导航条（多选择器兜底） */
    .stTabs [data-baseweb="tab-list"],
    .stTabs [role="tablist"],
    div[data-testid="stTabs"] > div > div,
    div[class*="stTabs"] > div > div[class*="tab"] {
        justify-content: center !important;
        gap: 16px !important;
        padding: 8px 20px !important;
        background: #F0F5FB !important;
        border-radius: 10px !important;
        margin-bottom: 10px !important;
        display: flex !important;
    }
    .stTabs [data-baseweb="tab"],
    .stTabs [role="tab"],
    div[data-testid="stTabs"] button,
    div[class*="stTabs"] button {
        font-size: 18px !important;
        font-weight: 600 !important;
        padding: 10px 24px !important;
        color: #475569 !important;
    }
    /* Tab 栏选中色 */
    .stTabs [aria-selected="true"],
    div[data-testid="stTabs"] button[aria-selected="true"],
    div[class*="stTabs"] button[aria-selected="true"] {
        border-top: 3px solid {C_BLUE} !important;
        color: {C_BLUE} !important;
        background: #ffffff !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="正在拉取财报数据...", ttl=3600)
def load_statements(code: str, max_periods: int):
    return fetch_financial_statements(code, max_periods=max_periods)


@st.cache_data(show_spinner="AI 正在解读（约 10-30 秒）...", ttl=3600)
def cached_ai_analyze(code: str, periods: int, use_ai: bool, api_key: str):
    """按代码缓存 AI 解读结果。"""
    statements = load_statements(code, periods)
    company = statements.get("company_name") or get_company_name(code)
    indicators = ind.compute_indicators(statements)
    risks = ind.evaluate_risk(indicators)
    text = ai_analyze(indicators, risks, company, code, api_key=api_key or None) if use_ai else ""
    return text


def _company_bundle(code: str, max_periods: int):
    """抓取 + 计算，返回 (company, statements, balance_check, indicators, risks, score, signals)。"""
    statements = load_statements(code, max_periods)
    company = statements.get("company_name") or get_company_name(code)
    balance_check = ind.validate_balance_sheet(statements["balance"])
    indicators = ind.compute_indicators(statements)
    risks = ind.evaluate_risk(indicators)
    score = ind.health_score(indicators, risks)
    signals = ind.risk_signals(indicators)
    return company, statements, balance_check, indicators, risks, score, signals


def main():
    st.markdown(
        "<div style='font-size:42px;font-weight:800;color:#1e3a8a;margin-bottom:4px;text-align:center;'>慧眼 · AI 财报风险体检 Agent</div>"
        "<div style='font-size:15px;color:#64748b;margin:4px 0 18px;text-align:center;'>"
        "输入 A 股代码 → 三大报表勾稽校验 → 四维指标体检 → 行业对标 → 对话式 AI 解读（选题 7-①）</div>",
        unsafe_allow_html=True,
    )

    # ------------------------------------------------ 侧边栏
    with st.sidebar:
        st.header("⚙️ 配置")
        code = st.text_input("股票代码（A股）", value=DEFAULT_CODE).strip()
        code_b = st.text_input("对比股票代码（可选）", value="",
                               help="如 000858，留空则不对比").strip()
        max_periods = st.slider("分析期数", min_value=3, max_value=8, value=DEFAULT_PERIODS)
        api_key = st.text_input("DeepSeek API Key（留空使用 .env）", value="", type="password")
        use_ai = st.checkbox("启用 AI 深度解读", value=True)
        if st.button("开始体检", type="primary", use_container_width=True):
            st.session_state["trigger"] = (code, code_b, max_periods)

    trigger = st.session_state.get("trigger") or (code, code_b, max_periods)
    code, code_b, max_periods = trigger

    # ------------------------------------------------ 主公司数据
    try:
        company, statements, balance_check, indicators, risks, score, signals = _company_bundle(code, max_periods)
    except Exception as exc:  # noqa: BLE001
        st.error(f"数据获取失败（{code}）：{exc}")
        st.info("可尝试：1) 确认代码正确（如 600519、000001）；2) 稍后重试；3) 检查网络。")
        return

    # 对比公司（失败不阻断主流程）
    bundle_b = None
    if code_b:
        try:
            bundle_b = _company_bundle(code_b, max_periods)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"对比股票 {code_b} 数据获取失败，已跳过对比：{str(exc)[:100]}")

    periods = indicators["periods"]
    latest = indicators["latest_index"]

    # ------------------------------------------------ AI 解读（缓存）
    ai_text = cached_ai_analyze(code, max_periods, use_ai, api_key or "")

    # ------------------------------------------------ 五大页签
    t_overview, t_detail, t_risk, t_ai, t_cloud = st.tabs(
        ["🏠 体检总览", "📊 指标明细", "⚠️ 风险预警", "🤖 AI 解读", "☁️ 结论词云"]
    )

    # ================================================== Tab1 总览
    with t_overview:
        left, right = st.columns([1.1, 1])
        with left:
            # 总分仪表盘
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score["total"],
                title={"text": f"{company} 体检总分"},
                number={"font": {"size": 44}, "suffix": " / 100"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": C_GREEN if score["total"] >= 70 else (C_ORANGE if score["total"] >= 55 else C_RED)},
                    "steps": [{"range": [0, 55], "color": "#fdeeee"},
                              {"range": [55, 70], "color": "#fdf3ee"},
                              {"range": [70, 100], "color": "#eef5ec"}],
                },
            ))
            fig_g.update_layout(height=240, margin=dict(l=20, r=20, t=50, b=10))
            st.plotly_chart(fig_g, use_container_width=True)
            st.markdown(f"**健康等级：{score['grade']}**　|　" +
                        "　".join(score["detail"]))
        with right:
            st.markdown("**近 5 期风险信号灯**")
            cols = st.columns(len(signals))
            dot = {"ok": C_GREEN, "warn": C_ORANGE, "high": C_RED}
            label = {"ok": "安全", "warn": "预警", "high": "高危"}
            for col, s in zip(cols, signals):
                bg = dot[s["level"]]
                per = s["period"][2:]
                lab = label[s["level"]]
                col.markdown(
                    f"<div style='text-align:center;'>"
                    f"<div style='width:20px;height:20px;border-radius:50%;background:{bg};margin:6px auto;'></div>"
                    f"<div style='font-size:11px;color:#666;'>{per}</div>"
                    f"<div style='font-size:10px;color:#999;'>{lab}</div></div>",
                    unsafe_allow_html=True)
            high_n = sum(1 for r in risks if r["level"] == "high")
            warn_n = sum(1 for r in risks if r["level"] == "warn")
            st.caption(f"最新一期：🔴 高危 {high_n} 项 · 🟡 预警 {warn_n} 项 · "
                       f"勾稽校验 {sum(1 for r in balance_check if r['ok'])}/{len(balance_check)} 期通过")

        # 双股对比
        if bundle_b:
            cb, ib, rb, sb, sigb = bundle_b[0], bundle_b[3], bundle_b[4], bundle_b[5], bundle_b[6]
            st.markdown("---")
            st.markdown(f"**⚖️ 双股对比：{company}（{code}） vs {cb}（{code_b}）**")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("体检总分", f"{score['total']} vs {sb['total']}",
                      f"{score['total'] - sb['total']:+.1f}")
            c2.metric("健康等级", score["grade"].split()[0], sb["grade"].split()[0])
            gm = indicators["series"]["gross_margin"]
            gmb = ib["series"]["gross_margin"]
            gm_v = gm[latest] if latest < len(gm) and gm[latest] is not None else 0
            gmb_v = gmb[ib["latest_index"]] if ib["latest_index"] < len(gmb) and gmb[ib["latest_index"]] is not None else 0
            c3.metric("毛利率", f"{gm_v:.1f}% vs {gmb_v:.1f}%", f"{gm_v - gmb_v:+.1f}pt")
            dr = indicators["series"]["debt_ratio"]
            drb = ib["series"]["debt_ratio"]
            dr_v = dr[latest] if latest < len(dr) and dr[latest] is not None else 0
            drb_v = drb[ib["latest_index"]] if ib["latest_index"] < len(drb) and drb[ib["latest_index"]] is not None else 0
            c4.metric("资产负债率", f"{dr_v:.1f}% vs {drb_v:.1f}%", f"{dr_v - drb_v:+.1f}pt")

        # 四维卡片
        st.markdown("---")
        st.markdown("**四维指标速览（最新一期）**")
        dim_order = [("偿债能力", C_BLUE, ["current_ratio", "quick_ratio", "debt_ratio"]),
                     ("盈利能力", C_ORANGE, ["gross_margin", "net_margin", "roe"]),
                     ("营运能力", C_GREEN, ["inv_turnover", "asset_turnover"]),
                     ("现金流", C_PURPLE, ["ocf_to_revenue", "ocf_to_netprofit"])]
        cols = st.columns(4)
        for col, (dim, color, keys) in zip(cols, dim_order):
            with col:
                st.markdown(f"<div style='border-left:4px solid {color};padding-left:8px;'>"
                            f"<b style='color:{color};'>{dim}</b></div>", unsafe_allow_html=True)
                for key in keys:
                    values = indicators["series"][key]
                    if latest >= len(values) or values[latest] is None:
                        continue
                    v = values[latest]
                    unit = ind.INDICATOR_META[key][3]
                    if unit == "%":
                        st.metric(INDICATOR_CN.get(key, key), f"{v:,.2f}%")
                    else:
                        st.metric(INDICATOR_CN.get(key, key), f"{v:,.2f}{unit}")

    # ================================================== Tab2 指标明细
    with t_detail:
        st.markdown("**多期趋势（实线：本公司；红色虚线：行业参考均值）**")
        chart_keys = st.multiselect(
            "选择指标",
            options=["debt_ratio", "gross_margin", "net_margin", "roe", "current_ratio", "ocf_to_revenue"],
            default=["gross_margin", "debt_ratio", "roe"],
            format_func=lambda k: INDICATOR_CN.get(k, k),
        )
        fig = go.Figure()
        palette = [C_BLUE, C_GREEN, C_ORANGE, C_PURPLE, "#5A97D0", "#C27B7B"]
        for i, key in enumerate(chart_keys):
            values = indicators["series"][key]
            y = [None if v is None else round(v, 2) for v in values]
            fig.add_trace(go.Scatter(x=periods, y=y, mode="lines+markers",
                                     name=INDICATOR_CN.get(key, key), connectgaps=True,
                                     line=dict(color=palette[i % len(palette)], width=2.5)))
            # 行业均值基准线
            if key in ind.INDUSTRY_BENCHMARK:
                fig.add_hline(y=ind.INDUSTRY_BENCHMARK[key], line_dash="dash", line_color=C_RED,
                              annotation_text=f"行业均值 {ind.INDUSTRY_BENCHMARK[key]}",
                              annotation_font_color=C_RED)
        fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20),
                          legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"行业参考均值口径：{ind.INDUSTRY_NAME}（基于公开年报口径整理，仅作对标展示，非精确统计值）")

        # 四维雷达（健康分百分制）
        st.markdown("**四维健康度雷达（本公司得分 vs 行业参考线 70 分）**")
        dims = list(score["dims"].keys())
        own = [round(score["dims"][d] / 25 * 100, 1) for d in dims]
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatterpolar(r=own + own[:1], theta=dims + dims[:1],
                                       fill="toself", name=company, line=dict(color=C_BLUE)))
        fig_r.add_trace(go.Scatterpolar(r=[70] * (len(dims) + 1), theta=dims + dims[:1],
                                        name="行业参考线", line=dict(color=C_RED, dash="dash")))
        fig_r.update_layout(height=380, polar=dict(radialaxis=dict(range=[0, 100])))
        st.plotly_chart(fig_r, use_container_width=True)

        # 完整指标表
        with st.expander("查看全部 15 项指标明细", expanded=False):
            rows = []
            for key, (_, cn, dim, unit, formula) in ind.INDICATOR_META.items():
                values = indicators["series"][key]
                v = values[latest] if latest < len(values) else None
                rows.append({"维度": dim, "指标": cn, "最新值": f"{v:,.2f}{unit}" if v is not None else "—",
                             "口径": formula})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ================================================== Tab3 风险预警
    with t_risk:
        st.markdown("**风险清单（通用阈值自动评级，AI 会结合行业语境修正）**")
        if risks:
            for r in risks:
                if r["level"] == "high":
                    st.error(f"🔴 高风险｜{r['name']}：{r['value']:,.2f}{r['unit']} —— {r['desc']}")
                else:
                    st.warning(f"🟡 预警｜{r['name']}：{r['value']:,.2f}{r['unit']} —— {r['desc']}")
        else:
            st.success("✅ 未触发通用阈值风险，整体财务结构稳健。")
        st.caption("注：阈值为跨行业通用参考值；白酒等行业部分指标天然偏低，AI 解读会按行业语境修正规则误判。")
        with st.expander("报表勾稽校验详情（资产 = 负债 + 所有者权益）"):
            for item in balance_check:
                icon = "✅" if item["ok"] else "⚠️"
                st.markdown(f"{icon} **{item['period']}**：{item['detail']}")

    # ================================================== Tab4 AI 解读
    with t_ai:
        st.markdown("**首份 AI 解读报告**")
        if ai_text:
            st.markdown(ai_text)
        else:
            st.info("已关闭 AI 解读或未配置 API Key。")

        st.markdown("---")
        st.markdown("**💬 继续追问（基于本次指标，对话式分析）**")
        if "chat" not in st.session_state:
            st.session_state["chat"] = []
        for msg in st.session_state["chat"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        q = st.chat_input("例如：那它现金流为什么这么好？")
        if q:
            st.session_state["chat"].append({"role": "user", "content": q})
            with st.chat_message("user"):
                st.markdown(q)
            with st.chat_message("assistant"):
                with st.spinner("AI 思考中..."):
                    ans = ask_followup(q, indicators, risks, company, code, ai_text,
                                       st.session_state["chat"][:-1], api_key=api_key or None)
                    st.markdown(ans)
            st.session_state["chat"].append({"role": "assistant", "content": ans})

    # ================================================== Tab5 词云
    with t_cloud:
        st.markdown("**AI 解读关键词云（自动分词，替代大段文字快速浏览结论）**")
        if not ai_text:
            st.info("请先在侧边栏启用 AI 解读并生成报告。")
        else:
            try:
                png = make_wordcloud(ai_text)
                st.image(png, use_container_width=True, caption="关键词字号越大，表示 AI 解读中出现频次越高")
            except Exception as exc:  # noqa: BLE001
                st.warning(f"词云生成失败（不影响其他功能）：{str(exc)[:120]}")

    # ------------------------------------------------ 导出报告（底部）
    st.markdown("---")
    md_text = build_report_markdown(company, code, indicators, risks, ai_text, balance_check)
    docx_doc = build_report_docx(company, code, indicators, risks, ai_text, balance_check)
    buf_docx = io.BytesIO()
    docx_doc.save(buf_docx)
    dl1, dl2 = st.columns(2)
    dl1.download_button("⬇️ 下载 Markdown 报告", data=md_text.encode("utf-8"),
                        file_name=f"{company}-{code}-财报风险体检报告.md", use_container_width=True)
    dl2.download_button("⬇️ 下载 Word 报告", data=buf_docx.getvalue(),
                        file_name=f"{company}-{code}-财报风险体检报告.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True)

    st.caption("数据来源：AKShare（东方财富公开数据）· AI：DeepSeek · 仅供学习演示，不构成投资建议")


if __name__ == "__main__":
    main()

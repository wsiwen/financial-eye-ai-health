# -*- coding: utf-8 -*-
"""
财务慧眼 · 财务指标计算模块
计算偿债能力、营运能力、盈利能力、现金流质量四大维度指标，并做勾稽校验与风险预警。
公式口径参考：北交所《主要财务指标计算公式》、国证指数《主要财务指标计算公式》等公开口径；
平均余额 =（期初 + 期末）/ 2，使用相邻两期报表数据。
"""
from __future__ import annotations

import math

import pandas as pd

# ---------------------------------------------------------------- 指标定义
# (指标名, 中文名, 维度, 单位, 方向说明)
INDICATOR_META = {
    "current_ratio":       ("current_ratio",       "流动比率",        "偿债能力", "倍", "流动资产合计 / 流动负债合计"),
    "quick_ratio":         ("quick_ratio",         "速动比率",        "偿债能力", "倍", "(流动资产合计 - 存货) / 流动负债合计"),
    "cash_ratio":          ("cash_ratio",          "现金比率",        "偿债能力", "倍", "货币资金 / 流动负债合计"),
    "debt_ratio":          ("debt_ratio",          "资产负债率",      "偿债能力", "%",  "负债合计 / 资产总计 × 100"),
    "ar_turnover":         ("ar_turnover",         "应收账款周转率",  "营运能力", "次", "营业收入 / 平均应收账款"),
    "inv_turnover":        ("inv_turnover",        "存货周转率",      "营运能力", "次", "营业成本 / 平均存货"),
    "asset_turnover":      ("asset_turnover",      "总资产周转率",    "营运能力", "次", "营业收入 / 平均资产总计"),
    "gross_margin":        ("gross_margin",        "毛利率",          "盈利能力", "%",  "(营业收入 - 营业成本) / 营业收入 × 100"),
    "net_margin":          ("net_margin",          "净利率",          "盈利能力", "%",  "净利润 / 营业收入 × 100"),
    "operating_margin":    ("operating_margin",    "营业利润率",      "盈利能力", "%",  "营业利润 / 营业收入 × 100"),
    "roe":                 ("roe",                 "净资产收益率ROE", "盈利能力", "%",  "净利润 / 平均所有者权益 × 100"),
    "roa":                 ("roa",                 "总资产报酬率ROA", "盈利能力", "%",  "净利润 / 平均资产总计 × 100"),
    "ocf_to_revenue":      ("ocf_to_revenue",      "经营现金流/营收", "现金流",  "%",  "经营活动现金流量净额 / 营业收入 × 100"),
    "ocf_to_netprofit":    ("ocf_to_netprofit",    "经营现金流/净利", "现金流",  "%",  "经营活动现金流量净额 / 净利润 × 100"),
    "ocf_net":             ("ocf_net",             "经营现金流净额",  "现金流",  "元", "经营活动现金流量净额"),
}

# 通用参考阈值（可调；实际解读由 AI 结合行业修正）
RISK_RULES = {
    "current_ratio":    {"warn": 1.5,  "high": 1.0, "desc": "流动比率低于阈值，短期偿债能力偏弱"},
    "quick_ratio":      {"warn": 1.0,  "high": 0.6, "desc": "速动比率低于阈值，扣除存货后偿债能力不足"},
    "debt_ratio":       {"warn": 70.0, "high": 85.0, "desc": "资产负债率高于阈值，杠杆水平偏高"},
    "cash_ratio":       {"warn": 0.3,  "high": 0.15, "desc": "现金比率低于阈值，即时支付能力弱"},
    "gross_margin":     {"warn": 10.0, "high": 5.0,  "desc": "毛利率低于阈值，产品盈利空间薄"},
    "net_margin":       {"warn": 5.0,  "high": 0.0,  "desc": "净利率低于阈值，甚至可能亏损"},
    "roe":              {"warn": 6.0,  "high": 0.0,  "desc": "净资产收益率低于阈值，股东回报偏弱"},
    "ar_turnover":      {"warn": 3.0,  "high": 1.0,  "desc": "应收账款周转率低，回款慢、坏账风险高"},
    "inv_turnover":     {"warn": 3.0,  "high": 1.0,  "desc": "存货周转率低，库存积压风险高"},
}

RISK_LEVELS = {"ok": "正常", "warn": "预警", "high": "高风险"}

# ---------------------------------------------------------------- 行业参考基准
# 白酒行业参考均值（基于公开年报口径整理，仅用于对标展示，非精确统计值）
INDUSTRY_BENCHMARK = {
    "gross_margin": 75.0,   # %
    "net_margin": 20.0,     # %
    "roe": 18.0,            # %
    "debt_ratio": 35.0,      # %
    "current_ratio": 2.5,    # 倍
    "ocf_to_revenue": 20.0,  # %
}
INDUSTRY_NAME = "白酒行业参考均值"

# 维度构成（用于体检总分）
DIM_KEYS = {
    "偿债能力": ["current_ratio", "quick_ratio", "cash_ratio", "debt_ratio"],
    "营运能力": ["ar_turnover", "inv_turnover", "asset_turnover"],
    "盈利能力": ["gross_margin", "net_margin", "operating_margin", "roe", "roa"],
    "现金流": ["ocf_to_revenue", "ocf_to_netprofit"],
}


def _risk_of_indicator(key: str, value: float) -> str:
    """单个指标按通用阈值评级（复用 RISK_RULES），返回 ok/warn/high。"""
    rule = RISK_RULES.get(key)
    if rule is None:
        return "ok"
    if key == "debt_ratio":
        if value > rule["high"]:
            return "high"
        if value > rule["warn"]:
            return "warn"
    else:
        if value < rule["high"]:
            return "high"
        if value < rule["warn"]:
            return "warn"
    return "ok"


def health_score(indicators: dict, risks: list[dict] | None = None) -> dict:
    """
    体检总分：四维各 25 分，维内指标按规则评级映射（ok=满分 / warn=半分 / high=0）。
    返回 {total, grade, dims: {维度: 得分}, detail: [...]}。算法透明公开，可复算。
    """
    series = indicators["series"]
    latest = indicators["latest_index"]
    dim_scores: dict[str, float] = {}
    details: list[str] = []
    for dim, keys in DIM_KEYS.items():
        scores = []
        for key in keys:
            values = series.get(key, [])
            if latest >= len(values) or values[latest] is None:
                continue
            level = _risk_of_indicator(key, values[latest])
            per = {"ok": 1.0, "warn": 0.5, "high": 0.0}[level]
            scores.append(per)
        # 维内平均 × 25
        dim_scores[dim] = round(sum(scores) / len(scores) * 25, 1) if scores else 0.0
        details.append(f"{dim} {dim_scores[dim]:.1f}/25")
    total = round(sum(dim_scores.values()), 1)
    if total >= 85:
        grade = "A 健康"
    elif total >= 70:
        grade = "B 关注"
    elif total >= 55:
        grade = "C 警示"
    else:
        grade = "D 危险"
    return {"total": total, "grade": grade, "dims": dim_scores, "detail": details}


def risk_signals(indicators: dict) -> list[dict]:
    """近 N 期风险信号灯：每期按规则评级汇总，返回 [{period, level, high_n, warn_n}]，最新期在前。"""
    series = indicators["series"]
    periods = indicators["periods"]
    out = []
    n = len(periods)
    for i in range(n):
        high_n, warn_n = 0, 0
        for key, rule in RISK_RULES.items():
            values = series.get(key, [])
            if i >= len(values) or values[i] is None:
                continue
            lv = _risk_of_indicator(key, values[i])
            if lv == "high":
                high_n += 1
            elif lv == "warn":
                warn_n += 1
        ocf = series.get("ocf_net", [])
        if i < len(ocf) and ocf[i] is not None and ocf[i] < 0:
            high_n += 1
        level = "high" if high_n > 0 else ("warn" if warn_n > 0 else "ok")
        out.append({"period": periods[i], "level": level, "high_n": high_n, "warn_n": warn_n})
    return out



def _safe_div(a: float, b: float) -> float:
    """安全除法，除零或空值返回 NaN。"""
    if b is None or math.isnan(b) or abs(b) < 1e-9:
        return float("nan")
    return a / b


def _num(series: pd.Series, row: int) -> float | None:
    """取某期数值，空值返回 None。"""
    val = series.iloc[row]
    if pd.isna(val):
        return None
    return float(val)


def validate_balance_sheet(balance: pd.DataFrame, tolerance: float = 0.01) -> list[dict]:
    """勾稽校验：资产总计 ≈ 负债合计 + 所有者权益合计（容差 1%）。返回校验结果列表。"""
    results = []
    if balance.empty:
        return results
    assets = balance["资产总计"]
    liab = balance["负债合计"]
    equity = balance["所有者权益合计"]
    for i in range(len(balance)):
        a, l, e = assets.iloc[i], liab.iloc[i], equity.iloc[i]
        period = str(balance["报告期"].iloc[i])
        if pd.isna(a) or pd.isna(l) or pd.isna(e):
            results.append({"period": period, "ok": False, "detail": "科目数据缺失，无法校验"})
            continue
        expected = float(l) + float(e)
        diff = abs(float(a) - expected)
        ratio = diff / abs(float(a)) if abs(float(a)) > 1e-9 else 1.0
        results.append({
            "period": period,
            "ok": ratio <= tolerance,
            "detail": f"资产总计{a:,.0f} vs 负债+权益{expected:,.0f}，差异率{ratio * 100:.2f}%",
        })
    return results


def compute_indicators(statements: dict) -> dict:
    """
    计算各期指标。
    statements: fetch_financial_statements 返回值 {kind: DataFrame}，最新一期在前。
    返回 dict：{periods: [...], latest_index: int, series: {指标: [值...]}, raw: {...}}
    """
    bal, inc, cf = statements["balance"], statements["income"], statements["cashflow"]
    n = max(len(bal), len(inc), len(cf))
    periods = bal["报告期"].tolist() if not bal.empty else []

    series: dict[str, list[float | None]] = {k: [] for k in INDICATOR_META}
    raw: dict[str, list[float | None]] = {}

    def val_of(kind: str, col: str, i: int) -> float | None:
        df = statements[kind]
        if col not in df.columns or i >= len(df):
            return None
        return _num(df[col], i)

    for i in range(n):
        rev = val_of("income", "营业收入", i) or val_of("income", "营业总收入", i)
        cost = val_of("income", "营业成本", i)
        np_ = val_of("income", "净利润", i)
        op_profit = val_of("income", "营业利润", i)
        ca = val_of("balance", "流动资产合计", i)
        cl = val_of("balance", "流动负债合计", i)
        inv = val_of("balance", "存货", i)
        cash = val_of("balance", "货币资金", i)
        ar = val_of("balance", "应收账款", i)
        ta = val_of("balance", "资产总计", i)
        tl = val_of("balance", "负债合计", i)
        eq = val_of("balance", "所有者权益合计", i)
        ocf = val_of("cashflow", "经营活动现金流量净额", i)

        # 平均余额（期初=下一期，期末=本期）
        prev_rev = val_of("income", "营业收入", i + 1) or val_of("income", "营业总收入", i + 1)
        prev_cost = val_of("income", "营业成本", i + 1)
        prev_ar = val_of("balance", "应收账款", i + 1)
        prev_inv = val_of("balance", "存货", i + 1)
        prev_ta = val_of("balance", "资产总计", i + 1)
        prev_eq = val_of("balance", "所有者权益合计", i + 1)

        avg_ar = _safe_div((ar or 0) + (prev_ar or 0), 2) if (ar is not None and prev_ar is not None) else ar
        avg_inv = _safe_div((inv or 0) + (prev_inv or 0), 2) if (inv is not None and prev_inv is not None) else inv
        avg_ta = _safe_div((ta or 0) + (prev_ta or 0), 2) if (ta is not None and prev_ta is not None) else ta
        avg_eq = _safe_div((eq or 0) + (prev_eq or 0), 2) if (eq is not None and prev_eq is not None) else eq

        def keep(v):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return None
            return v

        values = {
            "current_ratio":    _safe_div(ca, cl),
            "quick_ratio":      _safe_div((ca or 0) - (inv or 0), cl) if ca is not None and inv is not None else None,
            "cash_ratio":       _safe_div(cash, cl),
            "debt_ratio":       _safe_div(tl, ta) * 100 if tl is not None and ta is not None else None,
            "ar_turnover":      _safe_div(rev, avg_ar),
            "inv_turnover":     _safe_div(cost or rev, avg_inv) if (cost is not None or rev is not None) else None,
            "asset_turnover":   _safe_div(rev, avg_ta),
            "gross_margin":     _safe_div((rev or 0) - (cost or 0), rev) * 100 if rev is not None and cost is not None else None,
            "net_margin":       _safe_div(np_, rev) * 100,
            "operating_margin": _safe_div(op_profit, rev) * 100,
            "roe":              _safe_div(np_, avg_eq) * 100,
            "roa":              _safe_div(np_, avg_ta) * 100,
            "ocf_to_revenue":   _safe_div(ocf, rev) * 100,
            "ocf_to_netprofit": _safe_div(ocf, np_) * 100 if (ocf is not None and np_ is not None and abs(np_) > 1e-9) else None,
            "ocf_net":          ocf,
        }
        for k, v in values.items():
            series[k].append(keep(v))

        raw.setdefault("营业收入", []).append(rev)
        raw.setdefault("营业成本", []).append(cost)
        raw.setdefault("净利润", []).append(np_)
        raw.setdefault("货币资金", []).append(cash)
        raw.setdefault("应收账款", []).append(ar)
        raw.setdefault("存货", []).append(inv)

    return {
        "periods": periods,
        "series": series,
        "raw": raw,
        "latest_index": 0,
    }


def evaluate_risk(indicators: dict) -> list[dict]:
    """基于通用阈值对最新一期做风险评级。返回风险项列表。"""
    risks = []
    latest = indicators["latest_index"]
    series = indicators["series"]
    for key, rule in RISK_RULES.items():
        if key not in series or latest >= len(series[key]):
            continue
        value = series[key][latest]
        if value is None:
            continue
        level = "ok"
        if key in ("debt_ratio",):
            if value > rule["high"]:
                level = "high"
            elif value > rule["warn"]:
                level = "warn"
        else:
            if value < rule["high"]:
                level = "high"
            elif value < rule["warn"]:
                level = "warn"
        if level != "ok":
            risks.append({
                "indicator": key,
                "name": INDICATOR_META[key][1],
                "value": value,
                "unit": INDICATOR_META[key][3],
                "level": level,
                "desc": rule["desc"],
            })
    # 现金流专项
    ocf = series.get("ocf_net", [])
    if latest < len(ocf) and ocf[latest] is not None and ocf[latest] < 0:
        risks.append({
            "indicator": "ocf_net",
            "name": "经营现金流净额",
            "value": ocf[latest],
            "unit": "元",
            "level": "high",
            "desc": "经营活动现金流为负，造血能力不足，资金链压力大",
        })
    risks.sort(key=lambda r: 0 if r["level"] == "high" else 1)
    return risks

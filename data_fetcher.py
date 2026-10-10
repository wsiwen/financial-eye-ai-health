# -*- coding: utf-8 -*-
"""
财务慧眼 · 数据获取模块
通过 AKShare 获取 A 股上市公司三大财务报表（资产负债表 / 利润表 / 现金流量表）。
优先使用东方财富接口，失败时回退新浪接口。
"""
from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------- 字段映射
# 东方财富接口列名（已通过实际抓取确认）→ 统一中文科目名
# 保留中文别名以兼容新浪回退接口
COLUMN_ALIASES: dict[str, list[str]] = {
    # 资产负债表
    "货币资金": ["MONETARYFUNDS", "货币资金"],
    "应收账款": ["ACCOUNTS_RECE", "应收账款"],
    "存货": ["INVENTORY", "存货"],
    "流动资产合计": ["TOTAL_CURRENT_ASSETS", "CURRENT_ASSETS", "流动资产合计"],
    "资产总计": ["TOTAL_ASSETS", "资产总计"],
    "流动负债合计": ["TOTAL_CURRENT_LIAB", "CURRENT_LIABILITIES", "流动负债合计"],
    "负债合计": ["TOTAL_LIABILITIES", "负债合计"],
    "所有者权益合计": ["TOTAL_EQUITY", "所有者权益合计", "股东权益合计"],
    "归属于母公司股东权益": ["TOTAL_PARENT_EQUITY", "归属于母公司股东权益合计", "所有者权益或股东权益合计"],
    # 利润表
    "营业总收入": ["TOTAL_OPERATE_INCOME", "营业总收入", "营业收入"],
    "营业收入": ["OPERATE_INCOME", "营业收入"],
    "营业成本": ["OPERATE_COST", "营业成本"],
    "营业利润": ["OPERATE_PROFIT", "营业利润"],
    "利润总额": ["TOTAL_PROFIT", "利润总额"],
    "净利润": ["NETPROFIT", "净利润"],
    "归母净利润": ["PARENT_NETPROFIT", "归属于母公司所有者的净利润"],
    # 现金流量表
    "经营活动现金流量净额": ["NETCASH_OPERATE", "经营活动产生的现金流量净额", "经营活动现金流量净额"],
    "投资活动现金流量净额": ["NETCASH_INVEST", "投资活动产生的现金流量净额", "投资活动现金流量净额"],
    "筹资活动现金流量净额": ["NETCASH_FINANCE", "筹资活动产生的现金流量净额", "筹资活动现金流量净额"],
    "现金及现金等价物净增加额": ["CCE_ADD", "现金及现金等价物净增加额", "现金及现金等价物的净增加额"],
    "期末现金及现金等价物余额": ["END_CCE", "期末现金及现金等价物余额", "现金及现金等价物余额"],
}

REPORT_DATE_COLS = ["REPORT_DATE", "报告日期", "报表日期"]


def _pick_columns(df: pd.DataFrame, cn_name: str) -> list[str]:
    """按别名列表返回 DataFrame 中实际命中的列名列表。"""
    aliases = COLUMN_ALIASES.get(cn_name, [cn_name])
    hit = []
    for alias in aliases:
        if alias in df.columns:
            hit.append(alias)
    return hit


def _get_series(df: pd.DataFrame, cn_name: str) -> pd.Series | None:
    """返回某科目的数值 Series（取命中的第一列），找不到返回 None。"""
    cols = _pick_columns(df, cn_name)
    if not cols:
        return None
    return pd.to_numeric(df[cols[0]], errors="coerce")


def normalize_symbol(code: str) -> tuple[str, str]:
    """把 '600519' / 'sh600519' / 'SH600519' 规范化为东财格式 ('SH600519', '600519')。"""
    code = str(code).strip().upper()
    if code.startswith(("SH", "SZ", "BJ")):
        prefix, digits = code[:2], code[2:]
    else:
        digits = code
        prefix = "SH" if digits.startswith(("6", "9")) else ("BJ" if digits.startswith(("4", "8")) else "SZ")
    return f"{prefix}{digits}", digits


# ---------------------------------------------------------------- 抓取主函数
def fetch_em_statement(symbol_em: str, kind: str) -> pd.DataFrame:
    """东方财富接口抓取。kind: 'balance' | 'income' | 'cashflow'"""
    import akshare as ak

    if kind == "balance":
        df = ak.stock_balance_sheet_by_report_em(symbol=symbol_em)
    elif kind == "income":
        df = ak.stock_profit_sheet_by_report_em(symbol=symbol_em)
    else:
        df = ak.stock_cash_flow_sheet_by_report_em(symbol=symbol_em)
    return df


def fetch_sina_statement(stock_sina: str, kind: str) -> pd.DataFrame:
    """新浪接口回退抓取。kind: 'balance' | 'income' | 'cashflow'"""
    import akshare as ak

    symbol_map = {"balance": "资产负债表", "income": "利润表", "cashflow": "现金流量表"}
    df = ak.stock_financial_report_sina(stock=stock_sina, symbol=symbol_map[kind])
    return df


def fetch_financial_statements(code: str = "600519", max_periods: int = 5) -> dict:
    """
    抓取三大报表，返回 {kind: DataFrame, company_name: str}。
    每个 DataFrame 保留 REPORT_DATE 列 + 映射后的统一中文科目列（每科目取最新命中列）。
    company_name 优先取自报表接口自带的证券简称，避免额外接口调用。
    """
    symbol_em, digits = normalize_symbol(code)
    stock_sina = symbol_em.lower()
    result: dict[str, pd.DataFrame] = {}
    company_name: str | None = None

    for kind in ("balance", "income", "cashflow"):
        df = None
        errors: list[str] = []
        try:
            df = fetch_em_statement(symbol_em, kind)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"东财接口失败: {exc}")
        if df is None or df.empty:
            try:
                df = fetch_sina_statement(stock_sina, kind)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"新浪接口失败: {exc}")

        if df is None or df.empty:
            raise RuntimeError(f"获取{kind}失败：{'；'.join(errors)}")

        if company_name is None and "SECURITY_NAME_ABBR" in df.columns:
            company_name = str(df["SECURITY_NAME_ABBR"].iloc[0])

        # 取报告日期列
        date_col = next((c for c in REPORT_DATE_COLS if c in df.columns), None)
        if date_col is None:
            raise RuntimeError(f"{kind}报表缺少报告日期列，实际列名: {list(df.columns)[:20]}")

        # 构建统一列：日期 + 各科目
        out = pd.DataFrame()
        out["报告期"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        for cn in COLUMN_ALIASES:
            series = _get_series(df, cn)
            if series is not None:
                out[cn] = series.values
        out = out.dropna(subset=["报告期"]).sort_values("报告期", ascending=False)
        out = out.head(max_periods).reset_index(drop=True)
        result[kind] = out

    result["company_name"] = company_name or digits
    return result


def get_company_name(code: str = "600519") -> str:
    """获取公司名称（东方财富个股信息接口）。"""
    import akshare as ak

    symbol_em, digits = normalize_symbol(code)
    try:
        df = ak.stock_individual_info_em(symbol=symbol_em)
        row = df[df["item"] == "股票简称"]
        if not row.empty:
            return str(row["value"].iloc[0])
    except Exception:  # noqa: BLE001
        pass
    return digits

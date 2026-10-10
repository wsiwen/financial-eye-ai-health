# 慧眼 · AI 财报风险体检 Agent

**大赛选题**：成都外国语学院首届 AI 数智创作大赛 · 附件1 选题 7-①《如何用 AI 做财务报表分析与风险提示》
**作品形式**：AI 辅助工具（可演示原型）
**作品名称**：慧眼·AI 财报风险体检agent
**团队**：国际商学院 · 外星人（乌思文）

## 一、这是什么

输入一个 A 股股票代码，工具自动完成：
1. **数据拉取**：通过 AKShare 获取上市公司资产负债表、利润表、现金流量表（东方财富接口优先，新浪接口回退）；
2. **勾稽校验**：核对"资产总计 = 负债合计 + 所有者权益合计"，保证数据质量；
3. **指标计算**：计算偿债能力、营运能力、盈利能力、现金流质量四大维度 15 项指标（公式口径见 `indicators.py`，参考北交所/国证公开口径）；
4. **规则预警**：基于通用阈值给出"正常 / 预警 / 高风险"三级风险提示；
5. **AI 解读**：调用 DeepSeek 大模型对指标做通俗化解读、风险归因与实务建议；
6. **报告导出**：一键导出 Markdown / Word 财务风险分析报告（Word 版式符合大赛文案规范）。

## 二、运行方法

### 1. 安装依赖（Python 3.11 已验证）

```bash
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 2. 配置 DeepSeek API Key

在项目根目录创建 `.env` 文件（已提供模板 `.env.example`）：

```
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

不配置 Key 也能运行——AI 解读会自动降级为"规则模式解读"，界面、指标、风险、导出功能不受影响。

### 3. 启动

```bash
streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`。侧边栏输入股票代码（如 `600519` 贵州茅台、`000001` 平安银行），点"开始体检"。

## 三、项目结构

```
financial-eye/
├── app.py              # Streamlit 主程序（界面 + 交互）
├── data_fetcher.py     # AKShare 数据获取（字段映射 + 接口回退）
├── indicators.py       # 财务指标计算 / 勾稽校验 / 风险规则
├── ai_analyzer.py      # DeepSeek 解读（提示词工程 + 本地降级）
├── report_exporter.py  # Markdown / Word 报告导出
├── config.py           # 配置读取（.env）
├── .env.example        # 环境变量模板
└── requirements.txt
```

## 四、指标口径与风险阈值（可追溯）

| 维度 | 指标 | 口径 |
|---|---|---|
| 偿债能力 | 流动比率 | 流动资产合计 / 流动负债合计 |
| 偿债能力 | 速动比率 | (流动资产合计 − 存货) / 流动负债合计 |
| 偿债能力 | 现金比率 | 货币资金 / 流动负债合计 |
| 偿债能力 | 资产负债率 | 负债合计 / 资产总计 × 100% |
| 营运能力 | 应收账款周转率 | 营业收入 / 平均应收账款 |
| 营运能力 | 存货周转率 | 营业成本 / 平均存货 |
| 营运能力 | 总资产周转率 | 营业收入 / 平均资产总计 |
| 盈利能力 | 毛利率 | (营业收入 − 营业成本) / 营业收入 × 100% |
| 盈利能力 | 净利率 | 净利润 / 营业收入 × 100% |
| 盈利能力 | 营业利润率 | 营业利润 / 营业收入 × 100% |
| 盈利能力 | ROE | 净利润 / 平均所有者权益 × 100% |
| 盈利能力 | ROA | 净利润 / 平均资产总计 × 100% |
| 现金流 | 经营现金流占营收比 | 经营活动现金流量净额 / 营业收入 × 100% |
| 现金流 | 经营现金流占净利润比 | 经营活动现金流量净额 / 净利润 × 100% |

风险阈值采用通用经验值（`indicators.py` 中 `RISK_RULES`，可调整），行业特性由 AI 解读时结合修正。

## 五、原创性与开源依据（用于《AI 使用过程说明》）

本作品采用"开源组件组装"方式构建，各层开源依据：
- **数据层**：[AKShare](https://github.com/akfamily/akshare)（MIT）——A股三大报表免费数据接口；
- **计算口径**：参考 [FinanceToolkit](https://github.com/JerBouma/FinanceToolkit)（MIT）的透明公式思路及北交所《主要财务指标计算公式》、国证指数《主要财务指标计算公式》公开口径；
- **界面模式**：参考 [GraBerry/financial-analyzer](https://github.com/GraBerry/financial-analyzer) 的中文 Streamlit 仪表盘设计；
- **AI 层**：自研提示词工程（见 `ai_analyzer.py`），调用 DeepSeek API；
- 主体代码（数据清洗、勾稽校验、指标计算、风险规则、AI 编排、报告生成）均为本作品原创。

*本工具输出仅供学习与演示，不构成投资建议。*

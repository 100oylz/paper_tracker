# FL Paper Update Tracker

面向「文档解析的数据隐私保护关键技术研究」方向的论文追踪工具，基于 DBLP API 每天自动抓取、筛选、去重并发布 GitHub Issue。项目自建实现，不复刻上游仓库。

## 双主线

- **DP** 文档解析、隐私合规与端侧部署（整合原 SCHED + VLM 两条线）
- **FL** 联邦学习与隐私保护

每条主线拥有独立的 keywords、venues 与 subtopics，公共 venue 在 `dblp.shared.venues` 中声明，运行时自动并入。

## 功能

- DBLP 搜索 API 查询：每线 primary keyword 全量扫描，命中新论文的 venue 才用 secondary keywords 补扫
- 年份过滤：默认 `current_year - 5` 到 `current_year + 1`，偏移量在 `runtime.year` 配置，无绝对下限
- 去重：单结果 ee/title 去重 + 每线全局去重，不同主线允许各自收录同一篇论文
- 富化：摘要抓取（OpenReview/Crossref/Semantic Scholar/arXiv/OpenAlex）、OpenCode Go 中文翻译、GitHub 代码链接提取、LLM 分诊（score/summary/subtopic）
- 双线 Issue：分别使用 `.github/issue-template-dp.md` / `issue-template-fl.md`
- 辅助脚本：Markdown 输出、摘要/DOI/代码链接回填、去重、分诊回填、月报、年度盘点、关键词建议

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 本地开发模式（不写 GITHUB_ENV，打印各线消息）
cd src && python main.py run --env=dev

# 模拟定时任务：primary keyword 优先 + 命中 venue 补扫
cd src && python main.py run --env=dev --primary_only

# 全量年份（关闭年份过滤与富化）
cd src && python main.py run --env=dev --all_years
```

## 配置

见 `config.yaml`：

- `dblp.shared.venues`：公共 venue，运行时并入每条主线
- `dblp.lines[]`：主线定义（`tag` / `name` / `enabled` / `keywords` / `venues` / `subtopics`）
- `runtime`：年份窗口、请求重试/限速、摘要/翻译/分诊开关与预算
- `enrich.subtopics`：分诊通用标签，运行时与各线 subtopics 合并

环境变量（`.env.example`）：

- `LLM_BASE_URL`：OpenCode Go 端点，默认 `https://opencode.ai/zen/go/v1`
- `LLM_API_KEY`：OpenCode Go API 密钥
- `LLM_MODELS`：逗号分隔的模型列表，按顺序 fallback；默认按官方定价选便宜模型（`deepseek-v4-flash,mimo-v2.5,hy3,kimi-k2.7-code`）
- `GITHUB_ENV`：本地模拟 GitHub Actions 时的输出文件

## 缓存

`cached/dblp.yaml` 顶层键为 `{主线tag}:{venue_query}`，例如 `DP:venue:ICML:`、`FL:venue:ICML:`。论文字段：`author`、`title`、`venue`、`year`、`type`、`access`、`key`、`doi`、`ee`、`url`、`abstract`、`abstract_cn`、`related_code`、`date_added`，以及分诊字段 `triage_score` / `triage_summary` / `subtopic`。

## 测试

```bash
python -m pytest tests/ -q
```

## 许可

仓库暂未指定 LICENSE，由维护者决定。

# Agent Guidance

> 面向自动化编码代理的项目说明。架构或约定变化时请同步更新本文件。

## 项目概述

**FL-paper-update-tracker** 追踪「面向文档解析的数据隐私保护关键技术研究」方向的最新论文。双主线并行：

1. **DP** 文档解析、隐私合规与端侧部署（整合原 SCHED + VLM）
2. **FL** 联邦学习与隐私保护

数据源为 DBLP 搜索 API（`https://dblp.org/search/publ/api`）。项目为自建实现，不复刻上游内容。

## 目录结构

```text
.
├── .github/
│   ├── workflows/          # watch / backfill / digest / keyword-suggest 等工作流
│   └── issue-template-*.md # 双线 Issue 模板
├── cached/
│   └── dblp.yaml           # 持久缓存（键 = {tag}:{venue_query}）
├── scripts/                # 辅助脚本（9 个）
├── src/
│   ├── main.py             # 主流程 CLI（fire）
│   └── tracker/            # 核心包
├── tests/                  # 离线 pytest
├── config.yaml             # 语义化分层配置
└── FL-Papers.md            # 生成的 Markdown 汇总
```

## 核心逻辑

### 配置解析（`src/tracker/config.py`）

- `parse_lines(cfg)` 返回 `(lines, keyword_to_line, subtopic_to_line, all_subtopics)`。
- `dblp.shared.venues` 自动并入每条主线并去重。
- `runtime_settings(cfg)` 用默认值合并 `runtime` 段。

### 主流程（`src/main.py`）

1. 加载配置与缓存。
2. 每条主线：primary keyword 全量扫描该线 venues；命中新论文的 venue 才用 secondary keywords 补扫。
3. 年份过滤 `current_year - min_offset` 到 `current_year + max_offset`；`--all_years` 关闭过滤并跳过富化。
4. 新论文写 `date_added`，随后按 `runtime` 开关执行摘要抓取、中文翻译、LLM 分诊。
5. 保存缓存；按 `subtopic` 归线；`prod` 写 `MSG_*` / `ISSUE_TITLE_TOPICS_*` 到 `GITHUB_ENV`。

### 去重

- 单结果内 `deduplicate_items_by_ee` 再 `deduplicate_items_by_title`。
- 每条主线独立全局去重集合（`ee` + `title`），跨 keyword 防重复。
- 不同主线允许各自收录同一篇论文。
- 空 `ee` 的条目始终保留（避免数据丢失）。

### 消息格式（`src/tracker/format.py`）

- `get_msg` 输出真实换行，`prod` 用 `GITHUB_ENV` heredoc 写入 `MSG_*`，避免转义符号进入 Issue。
- 有分诊字段时按 `subtopic` 分组、组内按 `triage_score` 降序；否则按普通行渲染。
- 链接顺序：PDF → CODE → PUB，缺失省略；venue 徽章由 `src/tracker/venue_meta.py` 提供。

### 缓存

- 顶层键格式：`{tag}:{venue_query}`，如 `DP:venue:ICML:`、`FL:streamid:journals/tmlr:`。
- 写入使用 `allow_unicode=True, sort_keys=False, indent=2`。
- 新增字段需保持向后兼容：旧条目缺字段时按空值处理。

### 富化

- `src/tracker/abstracts.py`：摘要优先级 OpenReview → Crossref → Semantic Scholar → arXiv → OpenAlex；中文翻译走 OpenCode Go 多模型 fallback；GitHub 链接提取写入 `related_code`。
- `src/tracker/enrich.py`：`triage_score`（0-5）、`triage_summary`（中文 ≤60 字）、`subtopic`。永不抛异常，失败留空待下次补抓。
- `src/tracker/llm_client.py`：仅使用 OpenCode Go（默认 `https://opencode.ai/zen/go/v1`），环境变量 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODELS`，默认按定价选便宜模型（`deepseek-v4-flash,mimo-v2.5,hy3,kimi-k2.7-code`）并按顺序 fallback。

### 联系邮箱

- 配置文件中不再使用 `mails` 字段；如需在 Crossref/OpenAlex 请求中附带礼貌联系邮箱，通过环境变量 `CONTACT_EMAIL` 设置，默认空。

## 运行

```bash
cd src && python main.py run --env=dev [--primary_only] [--all_years]
cd src && python main.py run --env=dev --skip_enrich
python scripts/convert_cache_to_md.py
python scripts/fetch_abstracts.py --year all
python scripts/fetch_dois.py --year all
python scripts/fetch_related_code.py --year all
python scripts/enrich_backfill.py --dry-run --limit 0
python scripts/monthly_digest.py
python scripts/make_year_issues.py --years 2025,2026
python scripts/suggest_keywords.py --no-probe
```

## 测试

```bash
python -m pytest tests/ -q
```

## 维护提示

- 新增 venue：在对应主线的 `venues` 或 `dblp.shared.venues` 追加 plain query。
- 新增主线：在 `dblp.lines` 追加唯一 `tag`，并在 `scripts/convert_cache_to_md.py` 检查 venue 映射。
- 修改年份窗口：只改 `runtime.year`，不要恢复绝对年份下限。
- 改消息格式：编辑 `src/tracker/format.py` 与 `venue_meta.py`，并同步测试与模板。
- 不要弱化 `request` 的限速/退避参数；DBLP 未公布明确限额。

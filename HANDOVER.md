# 交接文档（给下一个 Agent）

> 更新时间：2026-08-05
> 交接人：Codex（当前会话）
> 仓库：`git@github.com:100oylz/paper_tracker.git`

## 1. 项目目标

继续维护「面向文档解析的数据隐私保护关键技术研究」论文追踪器，当前为**双主线**：

- **DP**：文档解析、隐私合规与端侧部署（由原 SCHED + VLM 两条线合并）
- **FL**：联邦学习与隐私保护（本次新增）

数据源为 DBLP 搜索 API。项目自建实现，不复刻任何外部仓库内容。

## 2. 已完成

- 配置重构为 DP + FL 双线：
  - DP 合并原 SCHED/VLM 的全部 keywords、venues、subtopics，共 10 个关键词、29 个专属 venue。
  - FL 新增 15 个关键词：`federated learning`、`federated optimization`、`personalized federat`、`cross-device federat`、`cross-silo federat`、`horizontal federat`、`vertical federat`、`federated distillation`、`secure aggregation`、`communication efficient federat`、`heterogeneous federat`、`federated unlearning`、`federated continual learning`、`federated graph learning`、`federated domain adaptation`。
- 分诊规则与 LLM 提示已覆盖 DP/FL 双线；`DEFAULT_SUBTOPICS` 增加联邦学习子方向。
- Issue 模板改为 `.github/issue-template-dp.md` / `.github/issue-template-fl.md`，labels 为 `dp-line` / `fl-line`。
- 7 个 GitHub Actions workflow 全部注册为 active；旧用户名 `youngfish42` 全部替换为 `100oylz`，邮箱统一为 `100oylz@users.noreply.github.com`。
- 仓库历史已强制重建并推送：根提交 `30a7262`，后续 `2b17685`（fast 探测模式）与 `abf9b1f`（探测缓存），无外部元素（`docs/superpowers/` 已删除）。
- 5 年论文探测完成：run `30990174620`（`--skip_enrich` 快扫，2h7m），缓存 62 个键、4573 篇论文；已生成并提交 `FL-Papers.md`；创建 issue #1（dp-line）与 #2（fl-line）。
- 新增 `--skip_enrich` 快扫模式：保留 5 年年份过滤，跳过摘要/翻译/分诊，供全量首扫使用；watch workflow 的 dispatch 自动启用，定时增量仍保留富化。
- workflow 推送改用 `git add -A` + `git commit`，确保 `FL-Papers.md` 等新生成文件会被提交。
- `convert_cache_to_md.py` 已补充 FL 与缺失 venue 映射（TMLR/TIFS/TDSC/TKDE/Big Data/CIKM/ICDAR/SOUPS 等）。
- 测试：`37 passed`（`python -m pytest tests/ -q`）。

## 3. 当前状态

- `watch.yml` active，cron `0 0 * * *`（`TZ: Asia/Shanghai`），每日增量扫描（primary-only + 富化）。
- `keyword-suggest.yml`、`monthly-digest.yml`、`backfill-*`、`fetch-all-years.yml` 均已注册。
- 初始 4573 篇论文尚未做摘要/翻译/LLM 分诊富化；可用 `scripts/fetch_abstracts.py`、`scripts/enrich_backfill.py` 等回填，每日增量任务会富化后续新论文。

## 4. 环境与运行方式

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd src && python main.py run --env=dev            # 本地开发模式
cd src && python main.py run --env=dev --primary_only
cd src && python main.py run --env=dev --skip_enrich  # 快速 5 年探测
cd src && python main.py run --env=dev --all_years

python scripts/convert_cache_to_md.py
python scripts/fetch_abstracts.py --year all
python scripts/fetch_dois.py --year all
python scripts/monthly_digest.py
python scripts/make_year_issues.py --years 2025,2026
python -m pytest tests/ -q
```

## 5. 关键配置

- 本地 `.env`（gitignore，不入库）：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODELS` / `CONTACT_EMAIL` / `GITHUB_ENV`
- 缓存键格式：`{主线tag}:{venue_query}`，如 `DP:venue:ICML:`、`FL:streamid:journals/tmlr:`
- 年份过滤在 `runtime.year`（`min_offset: 5`、`max_offset: 1`）
- 摘要抓取优先级：OpenReview → Crossref → Semantic Scholar → arXiv → OpenAlex
- LLM 分诊与中文翻译共用 OpenCode Go 多模型 fallback；失败不中断主流程，字段留空待下次补抓

## 6. 注意事项

- 不要弱化 `request` 段的限速/退避参数（DBLP 无公开限额，保守 6-9s/次）。
- 不要恢复 2020 年份绝对下限。
- AI 服务仅使用 OpenCode Go（`https://opencode.ai/zen/go/v1`），Secrets 只放三件套。
- 不同主线允许各自收录同一篇论文；同主线内跨 keyword 全局去重。
- 消息渲染使用真实换行，`prod` 通过 `GITHUB_ENV` heredoc 写入 `MSG_*`，不要再退回 `$'...'` 转义写法。

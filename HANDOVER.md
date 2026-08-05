# 交接文档（给下一个 Agent）

> 更新时间：2026-08-05
> 交接人：Codex（当前会话）
> 仓库：`git@github.com:100oylz/paper_tracker.git`

## 1. 项目目标

从零重建并继续维护「面向文档解析的数据隐私保护关键技术研究」论文追踪器，当前为**双主线**：

- **DP**：文档解析、隐私合规与端侧部署（由原 SCHED + VLM 两条线合并）
- **FL**：联邦学习与隐私保护（本次新增）

数据源为 DBLP 搜索 API。项目自建实现，不复刻任何外部仓库内容。

## 2. 本次已完成

- 配置重构为 DP + FL 双线：
  - DP 合并原 SCHED/VLM 的全部 keywords、venues、subtopics，共 10 个关键词、29 个专属 venue。
  - FL 新增 15 个关键词：`federated learning`、`federated optimization`、`personalized federat`、`cross-device federat`、`cross-silo federat`、`horizontal federat`、`vertical federat`、`federated distillation`、`secure aggregation`、`communication efficient federat`、`heterogeneous federat`、`federated unlearning`、`federated continual learning`、`federated graph learning`、`federated domain adaptation`。
- 分诊规则与 LLM 提示已覆盖 DP/FL 双线；`DEFAULT_SUBTOPICS` 增加联邦学习子方向。
- Issue 模板改为 `.github/issue-template-dp.md` / `.github/issue-template-fl.md`，labels 为 `dp-line` / `fl-line`。
- 所有 workflow 已改为 DP/FL 环境变量与模板；旧用户名 `youngfish42` 全部替换为 `100oylz`，邮箱统一为 `100oylz@users.noreply.github.com`。
- 删除 `docs/superpowers/` 外部工具设计文档，README/AGENTS 已同步为双线说明。
- 测试：`37 passed`（`python -m pytest tests/ -q`）。

## 3. 当前待办 / 观察

1. 强制重建仓库历史：删除旧 `.git` 后以单一干净 commit 重新初始化并 force push 到 `origin/main`。
2. 验证 GitHub Actions 注册（上次提交带 `[skip ci]`，`watch.yml` 尚未被注册）：
   - `gh api repos/100oylz/paper_tracker/actions/workflows`
3. 触发 5 年论文探测（2021-2027，`runtime.year` 为 `min_offset: 5` / `max_offset: 1`）：
   - `gh workflow run watch.yml --repo 100oylz/paper_tracker`
   - 运行完成后应提交缓存并创建 DP / FL 两条线的初始 Issue。
4. 确认定时任务：`watch.yml` 已有 cron `0 0 * * *`，`TZ: Asia/Shanghai`；每日只做 primary-only 增量扫描。

## 4. 环境与运行方式

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd src && python main.py run --env=dev            # 本地开发模式
cd src && python main.py run --env=dev --primary_only
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
- 消息渲染的换行是字面 `\n`，配合 `GITHUB_ENV` 的 `$'...'` 引用解析为真实换行，不要改成真实换行。

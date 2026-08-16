# VLAM Paper Update Tracker

一个**通过 DBLP API 检索、由 GitHub Actions 全托管运行的论文追踪工具**：定时自动抓取、筛选、去重并发布 GitHub Issue，面向 **视觉-语言-动作模型（Vision-Language-Action Model, VLA / VLAM）与具身智能** 方向。无需本地常驻进程，抓取、富化、更新 Markdown、发 Issue 全部在 CI 中完成。

## 工作原理

1. **检索**：调用 [DBLP Search API](https://dblp.org/search/api) 按主线关键词与 venue 全量扫描。
2. **托管**：GitHub Actions 定时（schedule）或手动（workflow_dispatch）触发，抓取结果写入 `cached/dblp.yaml` 并渲染 `VLAM-Papers.md`，自动提交回仓库。
3. **发布**：发现新论文时，用 Issue 模板创建 GitHub Issue 推送通知。

## 追踪主线

- **VLAM** 视觉-语言-动作模型与具身智能：VLA / 多模态大模型、机器人学习、机器人操作与导航、视觉运动控制、指令跟随、sim2real 迁移等。

主线拥有独立的 keywords、venues 与 subtopics，公共 venue 在 `dblp.shared.venues` 中声明，运行时自动并入。

## 功能

- DBLP 搜索 API 查询：primary keyword 全量扫描，命中新论文的 venue 才用 secondary keywords 补扫
- 年份过滤：默认 `current_year - 5` 到 `current_year + 1`，偏移量在 `runtime.year` 配置，无绝对下限
- 去重：单结果 ee/title 去重 + 主线全局去重
- 富化：摘要抓取（OpenReview/Crossref/Semantic Scholar/arXiv/OpenAlex）、OpenCode Go 中文翻译、GitHub 代码链接提取、LLM 分诊（score/summary/subtopic）
- Issue 通知：使用 `.github/issue-template-vlam.md` 模板
- 辅助脚本：Markdown 输出、摘要/DOI/代码链接回填、去重、分诊回填、月报、年度盘点、关键词建议

## GitHub Actions 工作流

仓库内工作流（`.github/workflows/`）即全部托管逻辑：

- `watch.yml` — 每日定时抓取增量新论文（schedule 驱动的主入口）
- `fetch-all-years.yml` — 手动触发，全量年份扫描并更新 Markdown
- `backfill-abstracts.yml` / `backfill-dois.yml` — 回填缺失的摘要与 DOI
- `monthly-digest.yml` — 月度盘点，`keyword-suggest.yml` — 关键词建议
- `close-all-issues.yml` — 批量关闭 Issue

## 本地调试

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 本地开发模式（不写 GITHUB_ENV，打印主线消息）
cd src && python main.py run --env=dev

# 模拟定时任务：primary keyword 优先 + 命中 venue 补扫
cd src && python main.py run --env=dev --primary_only

# 全量年份（关闭年份过滤与富化）
cd src && python main.py run --env=dev --all_years

# 快速 5 年探测（保留年份过滤，跳过摘要/翻译/分诊）
cd src && python main.py run --env=dev --skip_enrich
```

## 配置

见 `config.yaml`：

- `dblp.shared.venues`：公共 venue，运行时并入主线
- `dblp.lines[]`：主线定义（`tag` / `name` / `enabled` / `keywords` / `venues` / `subtopics`）
- `runtime`：年份窗口、请求重试/限速、摘要/翻译/分诊开关与预算
- `enrich.subtopics`：分诊通用标签，运行时与主线 subtopics 合并

环境变量（`.env.example`）：

- `LLM_BASE_URL`：OpenCode Go 端点，默认 `https://opencode.ai/zen/go/v1`
- `LLM_API_KEY`：OpenCode Go API 密钥
- `LLM_MODELS`：逗号分隔的模型列表，按顺序 fallback
- `GITHUB_ENV`：本地模拟 GitHub Actions 时的输出文件

## 缓存

`cached/dblp.yaml` 顶层键为 `VLAM:{venue_query}`，例如 `VLAM:venue:CVPR:`、`VLAM:streamid:conf/corl:`。论文字段：`author`、`title`、`venue`、`year`、`type`、`access`、`key`、`doi`、`ee`、`url`、`abstract`、`abstract_cn`、`related_code`、`date_added`，以及分诊字段 `triage_score` / `triage_summary` / `subtopic`。

## 测试

```bash
python -m pytest tests/ -q
```

## 许可

仓库暂未指定 LICENSE，由维护者决定。

---

# 📦 使用说明（给接收方）

> 这一节是给**拿到这个分支的人**的完整上手步骤。按顺序做即可。

## 0. 你需要准备什么

- 一个 GitHub 仓库（可以 fork 本仓库，或把代码推到你自己的仓库）
- 一个 **OpenCode Go API 密钥**（用于摘要中文翻译 + LLM 分诊；没有也能跑，只是没有翻译和分诊）

## 1. 把代码放到你的仓库

任选其一：

```bash
# 方式 A：直接 clone 本分支，推到你自己的仓库
git clone -b vlam-tracker <本仓库地址> my-vlam-tracker
cd my-vlam-tracker
git remote set-url origin <你的仓库地址>
git push -u origin vlam-tracker:main   # 推到你仓库的 main 分支
```

或 fork 后把 `vlam-tracker` 分支设为你的工作分支。

## 2. 配置 GitHub Secrets（必需）

进入你的仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加：

| Secret | 说明 | 是否必需 |
|---|---|---|
| `LLM_API_KEY` | OpenCode Go API 密钥 | 富化（翻译/分诊）需要；没有则跳过富化 |
| `LLM_BASE_URL` | 端点，默认 `https://opencode.ai/zen/go/v1` | 可选 |
| `LLM_MODELS` | 模型列表，逗号分隔按序 fallback | 可选 |
| `MAIL_TO` | 新论文邮件通知收件邮箱 | 可选（不配就不发邮件） |
| `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | 发邮件用的 SMTP 服务 | 配了 `MAIL_TO` 才需要 |

> 仓库的 `GITHUB_TOKEN` 由 Actions 自动提供，无需手动配置；`watch.yml` 里 `permissions: write-all` 已授权提交与发 Issue。

## 3. 启用并触发

1. 推送到仓库后，进入 **Actions** 标签页，按提示启用工作流。
2. **首次先做一次全量抓取**：手动运行 `Fetch All Years Papers`（workflow_dispatch）。这一步会抓取近 5 年全部命中论文并生成 `VLAM-Papers.md`。
3. 之后 `Run DBLP Watch` 会**每天定时**（cron `0 0 * * *`，UTC）抓取增量新论文；有新结果时自动：
   - 更新 `VLAM-Papers.md` 并提交回仓库
   - 创建 GitHub Issue（标签 `vlam-line`）
   - 若配置了 `MAIL_TO`，发送邮件通知

> 想改抓取频率，编辑 `.github/workflows/watch.yml` 里的 `cron` 表达式。

## 4. 调整追踪方向（改关键词 / venue）

全部在 `config.yaml` 的 `dblp.lines[0]`（tag 为 `VLAM`）里改：

- **加/删关键词** → 改 `keywords:` 列表。**第一条是 primary keyword**（每日增量扫描的入口），放最宽、最有代表性的词（当前是 `vision language action`）。
- **加/删期刊会议** → 改 `venues:` 列表。用 DBLP 的 venue 标识，如 `venue:CVPR:`（会议）或 `streamid:conf/corl:` / `streamid:journals/tro:`（stream/期刊）。
- **改分类标签** → 改 `subtopics:`，LLM 分诊会把论文归到这些标签。

> 关键词写法：DBLP 是子串/词干匹配、默认 AND、不区分大小写、只匹配标题。用词根截断（如 `robot learning` 同时命中 learn/learning）并用空格分隔，比完整短语更宽。

改完关键词/venue 后，**重新跑一次 `Fetch All Years Papers`** 让历史数据按新配置补齐。

## 5. 常见问题

- **没有新论文 / Issue**：先看 Actions 里 `Run DBLP Watch` 的日志，确认请求成功；关键词太窄或 venue 拼写错误会导致零命中。
- **没有中文翻译/分诊**：检查 `LLM_API_KEY` 是否配置、额度是否足够。
- **想停掉邮件**：把 `MAIL_TO` secret 删掉或留空即可。
- **本地验证配置**：见上方「本地调试」，先 `cd src && python main.py run --env=dev --skip_enrich` 快速探测命中量。

# PROGRESS · OpenHire `openhire-mcp` v0.1「哨兵」

> 一页进度台账。新条目置顶。恢复会话请先读 `README.md` 再读本文件，勿重做已完成工作。

**当前状态：v0.1 已公开发布 + 上架官方 MCP Registry（2026-07-15）· M1–M4 完成 · 118 tests green**
- GitHub：https://github.com/gzchenhao/openhire （main，tag v0.1.1）
- Release v0.1.0（含快照 `openhire-index.db.gz`，URL 稳定）：https://github.com/gzchenhao/openhire/releases/tag/v0.1.0
- PyPI：https://pypi.org/project/openhire/0.1.1/ （`pipx install openhire`）
- **官方 MCP Registry：`io.github.gzchenhao/openhire` v0.1.1**（`registry.modelcontextprotocol.io`；PulseMCP/mcp.so 会自动同步）
- Smithery：v0.1 **放弃**（无本地 stdio 网页入口，见 `reports/010`）。
- **常设仅剩：每周手动刷新快照**（`docs/maintainer-snapshot-refresh.md`）。

---

## 2026-07-15 — v0.2 启动：分发与种子用户（GitHub 门面第一批，详见 reports/012）

- **`uvx openhire serve` 零失败已验**（陌生人第一条命令）：从 PyPI 现装、空索引下用官方 MCP stdio 客户端握手 → initialize + 列出 5 工具 + `search_jobs` 调用不报错。与注册表 `packageArguments: serve` 对齐。
- **README 补三样**：顶部 30s Quickstart GIF **占位**（待用户录 `docs/quickstart.gif`，清单在 012）；**Works with**（Claude Desktop/Cursor/Windsurf 配置）；**FAQ 五条**。
- **Issue 模板**：`.github/ISSUE_TEMPLATE/` 加 `company_request.yml`（社区钩子）+ `bug_report.yml` + `config.yml`。
- **About/topics**：已用 `gh repo edit` 设描述 + homepage(PyPI) + 16 个 topics。
- **待用户**：录 Quickstart GIF（≤30s/≤5MB）回我替换占位。

---

## 2026-07-12 — 真机验收修复 campaign（报告 003 → 逐项修，详见 reports/004）

**P0-1 写路径挂死 — ✅ 已修复**
- 根因：真库为 SQLite rollback-journal 模式，长驻 stdio server 的流式读（search/check 遍历 11,825 行）阻塞 watch_intent 写；async 事件循环里表现为 4 分钟挂死。apply 秒回是因当时无重叠读，证伪「写路径整体挂死」。
- 复现对照：rollback-journal 读活跃时写 5.46s 后 `database is locked`；WAL 下 0.004s 提交。
- 修复：`db/session.py` SQLite 引擎启用 `journal_mode=WAL` + `busy_timeout=5000` + `synchronous=NORMAL` + `check_same_thread=False`。真库已持久转 WAL。
- 验证：新增 `tests/test_concurrency.py`（2 项）；全量 **100 passed**；T3 真库重跑（fp `88ba1102edb9205d`，4 线程读压下）watch_intent **0.046s** 返回、只落匿名数据。

**P0-2 datePosted 造假 + ghost_score 恒 0 — ✅ 已修复**
- 根因：入库丢弃 ATS 真实发布日，`first_seen_at`/`verified_at` 全写抓取时刻（全库 1 个 distinct）；ghost 用 first_seen（岗龄≈0）+ relist=0 → 恒 0。DeepSeek 未污染日期。
- 修复：`Job` 加 `posted_at`/`updated_at` 列 + migrate；ingest 落库真实发布日、ghost 以真实岗龄为锚；`job_posting` 的 `datePosted` 用 posted_at、新增 `days_open`；新增 **免费** `ohp backfill-dates` 重抓 ATS 回填（不重跑抽取）。
- 回填真库：96/0，真实发布日 11446，ghost 重算 11825。回归：`mongodb:7727896` days_open=110（≈3.6 月）、ghost 0→0.3565；全库 ghost min0/median0.081/max1.0，**57.7% >0**。新增 `tests/test_posting_dates.py`。

**API 定型 5 项免费项 — ✅ 完成（107 passed）**
- required_skills(AND)；min_salary 加 currency + 拆 require_stated_salary（未标薪资默认保留）；remote_scope 枚举 + eligible_regions；MCP `apply`→`authorize_application`；get_company_info 去 verified、last_crawled_at→index_built_at；watch_intent 加 fingerprint_notice。
- role_family：参数+空列已冻结，**数据待跑**——报价 ≈¥29（¥50 硬上限），**等用户批准**。

**role_family 抽取 — ✅ 已批准跑完**：新增 `classify_role_family_with_usage` + 断点续跑成本封顶的 `rebuild_role_family` + CLI `ohp extract-role-family`。全量 11,825/11,825 标注、0 失败、**¥17.53**（低于 ¥29 估价）。分布 eng4207/sales3373/ops2621/…。回归达标：`--role-family engineering` 搜索 0 条 sales；两个附录 B 销售岗均 role_family=sales。

**附录 B 回归 — ✅**：`tests/test_appendix_b.py`（5 job_id 各锁一个契约：datePosted/销售岗排除/Ashby 写路径/荷兰无薪资岗保留-排除）。

**文案红线 — ✅**：README 标语 + CLI 帮助/横幅「简历永不离开设备」→「简历不经过我们服务器，也不被我们存储」。

**测试基线：112 passed。** 报告 003 的 P0-1/P0-2/6 项 API 定型/文案/附录 B 回归全部完成。

**CLI 真机体验 7 步单 — ✅ 交付**（`reports/005`，新手向：每步一命令 + 预期输出 + 出错时截图哪里；预期输出为真库副本+临时目录实跑截取）。
**顺手修一处小摩擦：** `ohp apply` 原来无论是否 `--no-open` 都打印「申请页（已打开）」；改为按实际结果打印「已在浏览器打开」/「请手动打开」。112 passed 不变。

**下一步：** 用户按 `reports/005` 亲跑最后一轮验收 → 通过即开 **M4**。

---

## 2026-07-12（续）— M4 就绪修复 + M4 启动

**两处 M4 就绪修复 — ✅（114 passed）**
- ① `ohp search` 回显行漏掉 `--role-family`/`--limit` → 补上。
- ② `ohp watch` + `watch_intent` 加可选 `required_skills`(AND) + `role_family`（非破坏；`_clean_filters` 白名单 + `check_watches` 透传）。实测 watch 加这两参数后命中不再混入销售/SA 岗。新增 2 项服务测试。

**M4 代码就绪 — ✅（118 passed，详见 reports/006）**
- 首跑数据（用户拍板混合）：快照=GitHub Release 资产、仅 jobs/companies、**零用户态**（构建时红线校验，违规即失败）。`ohp bootstrap` 默认 拉快照→增量刷新→打印快照龄；`--fresh` 现抓（启发式免费）；`--deepseek` 自带 key。开跑前先声明将做什么。新增 `pipeline/snapshot.py`、`ohp bootstrap`、`ohp snapshot-build`、`db.session.dispose_engine`、`config.SNAPSHOT_URL`、`tests/test_snapshot.py`(4)。
- 实测：真快照 96/11825·13.2MB·零用户态校验通过；bootstrap 全流程（安装 96/11825 龄3天→刷新 新323/更340/下线452）✓；护栏（已有索引提示 --force）✓。
- pipx：wheel 73KB 无数据大文件 → 全新隔离 venv 安装 → `ohp version`/命令齐全 ✓。终端用户 pipx 装后 config 可直接 `command: "ohp"`。
- README：design_refs→真 Markdown，隐私口径收窄。
- **待用户拍板**：GitHub 仓库地址、是否发 PyPI、是否落地 `smithery.yaml`（草案在 006）、快照刷新节奏。MCP 目录提交材料清单已备好、**未提交**。

**M4 发布准备 — 四项拍板已落地（详见 reports/007）**
- ① GitHub：个人账号下 `openhire` 仓库（URL 待用户名，`pyproject`/README/`smithery`/`config` 里占位 `OWNER`，拿到用户名我一次性 wire）。
- ② PyPI：查得 `openhire` **未被占用 → 沿用**（无需改名）；CLI 保持 `ohp`。
- ③ `smithery.yaml` **已落地**（stdio + 可选 OPENHIRE_DATABASE_URL）。
- ④ 快照每周手动刷新：维护者操作卡 `docs/maintainer-snapshot-refresh.md`。
- 另：`.gitignore` 补 `.pypirc`/token/WAL/`*.db.gz` 防护；`pyproject` 加 `[project.urls]`；sdist+wheel 构建通过。
- **发布日操作单 `reports/007`**：GitHub/PyPI 双新手逐步指引，标注【可代劳】步骤；红线 token 只进本机 env/.pypirc、不进 git。

**M4 已发布上线 — ✅（详见 reports/008）**
- GitHub：https://github.com/gzchenhao/openhire （main，72 文件，commit 2d361db）。
- Release v0.1.0：资产 `openhire-index.db.gz` 13.2MB，下载 URL 与 `config.SNAPSHOT_URL` 一致（HTTP 200）。
- PyPI：https://pypi.org/project/openhire/0.1.0/ （`pipx install openhire` 全网可装）。
- 端到端实测：全新 venv 从 PyPI 装 → `ohp bootstrap` 拉发布快照（96/11825，龄4天）→ 刷新（新457/更594/下581）→ `ohp search --role-family engineering` 干净。
- 红线执行：代码库零密钥（.env/.pypirc/*.db 被 .gitignore 挡，push 前核对暂存区）；快照零用户态（构建时校验）；PyPI token 仅 .pypirc、GitHub 用 gh keyring。

**仅剩：** Smithery 目录提交（`smithery.yaml` 已在库，提交前字段给用户过目、不擅自提交）；快照每周刷新（`docs/maintainer-snapshot-refresh.md`）。

---

## 2026-07-11 — M4 前真机验收准备

**已完成**
- 建立常设工作制度：新增 `CLAUDE.md`（新会话恢复指引 + 工作约定 + 隐私红线 + 关键路径），补记本 `PROGRESS.md`（回填 M1–M3）。
- 核对真机事实：默认 DB URL = `sqlite:///C:/Users/gdche/.openhire/openhire.db`（绝对路径，11,825 职位 / 96 公司 / 全量 deepseek 抽取）；`ohp.exe` 在 `.venv\Scripts\`，**不在系统 PATH**。

**关键决策**
- Claude Desktop 接入 `command` 用 `ohp.exe` 全路径（因未上 PATH，且 M4 才做 pipx/uvx）。这是**预判的头号发布阻塞项**：陌生开发者裸装无法直接 `command: "ohp"`。
- serve 阶段 DB 走绝对路径默认值 → Claude Desktop 从任意 cwd 启动都命中同一份数据，无需在 config 里配 env。

**下一步**
- 交付真机验收三件套（Claude Desktop 分步接入指引 + 5 条验收对话由用户亲跑 + CLI `init→watch→apply` 体验清单）。
- 用户跑完反馈摩擦点 → 按 v0.1 发布阻塞项处理 → 再开 M4（pipx/uvx 打包、正式 README、提交 MCP 目录）。

**已发现并修复的摩擦（发布阻塞项 #1）**
- `ohp search` / `check` 只打印 apply URL，**不打印 `job_id`**，而 `ohp apply` 恰需 `job_id` 参数 → 新手搜完不知道 apply 该敲什么。已修 `_print_job`：每条结果新增 `id=<job_id>` 及 `# 投递：ohp apply <job_id>` 提示行。98 测试仍全绿。

**待用户确认**
- 真机 5 条对话与 CLI 清单跑下来的摩擦点（报错/看不懂/步骤多），逐条反馈。

---

## 2026-07-10 — M3 验收通过（求职者旅程 CLI）

**已完成（验收证据）**
- 求职者旅程 CLI：`ohp init --scan <dir>` / `watch` / `check` / `apply` / `status`，客户端状态在 `~/.openhire`。
- `init` 本地扫描仓库导出技能指纹（按扩展名 + 依赖清单 → 技能标签，规范化），先确认后落盘；代码/内容不出机器，匿名 id 形如 `#a3f9`。
- `apply <job_id>` 打开链接**前**先在终端打印 JD 摘要（公司/职位/薪资/技能/JD 要点），`[Y/n]` 授权后再跳 —— 修复 Greenhouse embed 表单无 JD 上下文的问题。落 receipt 到 `~/.openhire/receipts.jsonl` + 服务端 `Application`。
- 实测链路：watch → 新 JD 入库 → `check` 增量浮现；apply 全流程 + receipt。**98 项测试全绿**。

**关键决策**
- `check_watches` 以 `last_notified_at` 为游标（None=基线返回当前全部匹配），修复首拉返回 0 的问题。
- stdio 无服务端推送 → `check` 为客户端主动拉取。

---

## 2026-07-09 — DeepSeek 全量抽取重建

**已完成（验收证据）**
- 新增 DeepSeek OpenAI 兼容后端（`base_url=https://api.deepseek.com`, `model=deepseek-chat`, key 从 `DEEPSEEK_API_KEY`）。
- 先抽 100 条对比启发式确认质量提升 → 分批断点续跑全量：**11,825/11,825 转换，0 失败，实际花费 ¥27.03**（硬上限 ¥50，超则停）。
- 抽取结果保留原启发式值作回退列（`*_fallback`），可对比/回滚。
- 合并策略：skills 永远用 LLM；remote/salary 保留权威 ATS 值（除非 ATS 缺失）—— 修复朴素全量替换导致的 remote(48 改)/salary(43 失) 回退。
- 复测「远程 Rust/K8s 基础设施岗」搜索：Top 8 中销售岗归零，回归确认。

**关键决策**
- 用最便宜 `deepseek-chat`；先 100 条抽样报差异、确认再全量；超 ¥50 先停问用户 —— 均按用户要求落地。
- 共享连接池 `httpx.Client` + 24 workers（原每调用新建连接过慢）。

---

## 2026-07（M2）— MCP 服务端（四工具 + apply）

**已完成（验收证据）**
- FastMCP 服务 `openhire`，5 个工具：`search_jobs` / `get_company_info` / `watch_intent` / `check_watches` / `apply`。
- 通过 5 条 Claude Desktop 验收对话脚本（搜索 / 公司信任 / 常驻意向 / 跨会话拉取 / 隐私红线对抗）+ 2 条内部验收。
- 红线②落地：排序函数签名锁死 `f(match_quality, freshness)`，无任何付费参数（`test_ranking.py`）。
- `search_jobs` 服务端只做硬过滤 + 固定排序，精排留客户端。
- `apply` 结构上无 resume 参数 —— 无法接收简历；`assert_no_resume` 拒绝 resume/cv/file/email 等键 → `ERR_RESUME_NEVER_TRANSMITTED`。

---

## 2026-07（M1）— 数据管线

**已完成（验收证据）**
- 从公开 ATS API 入库（Greenhouse / Lever / Ashby），零爬虫；96 家已验证公司（含 anthropic/openai/cohere/mistral 等）。
- 五协议字段：`verified_at` / `source` / `ghost_score` / `response_sla_days`(v0.1 恒 NULL) / `apply_channel`。
- 变更/下线/重挂检测；`ghost_score = min(1.0, 0.15*relist_count + max(0, days_since_first_seen-45)/90*0.5)`（纯函数、可注入时钟）。
- **apply_channel 修复**：21 家嵌入式公司（4,188 职位）全部重生成，DB 不变量「0 个非 ATS 宿主」，全部 HTTP 200 直达具体职位；补自动化测试「apply_channel 必须直达具体职位」。
- Postgres 优先 schema，SQLite 为开发默认；方言感知 TypeDecorator（StringArray / JSONDict / TZDateTime 修复 SQLite naive datetime）。

**关键决策**
- 嵌入页无法可靠直达时，回退 Greenhouse `/embed/job_app` 官方申请表单（CoreWeave 等案例）。

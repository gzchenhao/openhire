# Handoff: OpenHire v0.1「哨兵」— MCP 职位协议服务

## Overview

OpenHire 是一个面向 AI Agent 的招聘数据协议层：求职者的 Agent（Claude Desktop / Cursor / CLI）通过 MCP 查询**直接来自雇主官网/ATS 公开接口**的职位数据，匹配在本地完成，简历永不上传。本交接包定义 v0.1「哨兵」的完整实现范围：**一个真实可运行的 MCP Server + CLI + 数据管线**，聚焦「全球远程 AI/Infra 岗位」，约 100 家公司，全部走公开 ATS API（零爬虫对抗）。

商业与战略背景见 `design_refs/OpenHire 开聘协议.dc.html`（路演 Deck，含附录 A1–A4）。**v0.1 不做**：雇主端、计费、Sponsored、网页前端。

## About the Design Files

`design_refs/` 内的 HTML 文件是**设计参考**（浏览器直接打开即可交互），展示意图中的外观与行为，**不是可复用的生产代码**。任务是在真实技术栈中实现本文档描述的系统；CLI 输出样式、文案、交互节奏请对照 `OpenHire v0.1 哨兵.dc.html` 复刻。`support.js` / `deck-stage.js` 仅为预览运行时，与产品无关。

## Fidelity

- **CLI / MCP 对话流、文案、隐私叙事：高保真** — 命令名、输出文案、确认流程按设计稿逐字实现（中文文案可先做英文版，键名不变）。
- **后端架构：功能规格** — 数据库/管线按本文档的契约实现，内部结构可自行优化。

## v0.1 实现范围

### 技术栈（建议，可替换但需说明理由）

- Python 3.11+，官方 `mcp` SDK（FastMCP），stdio transport
- Postgres 15+（本地开发可 SQLite 起步，但 schema 按 Postgres 写）
- `httpx` 异步抓取；调度用 APScheduler 或 cron
- LLM 抽取：可插拔接口（默认 Anthropic API，环境变量注入 key），只在 content_hash 变化时调用
- 打包：`pipx install openhire` / `uvx openhire`

### 数据源（仅此三家，v0.1 不加爬虫）

- Greenhouse: `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`（公开，免鉴权）
- Lever: `GET https://api.lever.co/v0/postings/{site}?mode=json`
- Ashby: `GET https://api.ashbyhq.com/posting-api/job-board/{jobBoardName}`

种子公司：自行构建 100 家「远程友好 + AI/Infra 在招」名单。发现方法：各 ATS 的板块 URL 指纹（`boards.greenhouse.io/x`、`jobs.lever.co/x`、`jobs.ashbyhq.com/x`）+ 知名 AI 公司 careers 页反查。**tenant slug 必须运行时验证**（请求 200 且返回 jobs 数组才入库）。礼貌频控：每 tenant ≥ 30 分钟间隔，全局并发 ≤ 5。

### 数据库 Schema（协议五字段是核心，不可省）

```sql
CREATE TABLE companies (
  id TEXT PRIMARY KEY,              -- slug
  name TEXT NOT NULL,
  ats_vendor TEXT NOT NULL,         -- greenhouse | lever | ashby
  ats_tenant TEXT NOT NULL,
  careers_url TEXT,
  verified BOOLEAN DEFAULT FALSE,   -- v0.3 雇主认领用，先留字段
  last_crawled_at TIMESTAMPTZ
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,              -- {company_id}:{ats_job_id}
  company_id TEXT REFERENCES companies(id),
  title TEXT NOT NULL,
  description_raw TEXT,
  skills TEXT[] DEFAULT '{}',       -- LLM 抽取，小写规范化
  remote_policy TEXT,               -- remote | hybrid | onsite | unknown
  salary_min INT, salary_max INT, salary_currency TEXT,
  salary_inferred BOOLEAN DEFAULT FALSE,
  location TEXT,
  first_seen_at TIMESTAMPTZ NOT NULL,
  verified_at TIMESTAMPTZ NOT NULL, -- 协议字段①：最后一次确认在源头存活
  delisted_at TIMESTAMPTZ,
  relist_count INT DEFAULT 0,
  ghost_score REAL DEFAULT 0,       -- 协议字段③
  response_sla_days INT,            -- 协议字段④（v0.1 恒为 NULL，雇主认领后才有）
  source TEXT NOT NULL,             -- 协议字段②：employer_site | ats_public_api
  apply_channel TEXT NOT NULL,      -- 协议字段⑤：永远是雇主自己的申请 URL
  content_hash TEXT NOT NULL
);

CREATE TABLE watches (
  watch_id TEXT PRIMARY KEY,        -- w_xxxx
  fingerprint TEXT NOT NULL,        -- 匿名，客户端生成，形如 #a3f9
  filters JSONB NOT NULL,           -- { skills[], remote, min_salary, ... }
  created_at TIMESTAMPTZ DEFAULT now(),
  last_notified_at TIMESTAMPTZ,
  active BOOLEAN DEFAULT TRUE
);

CREATE TABLE applications (
  receipt_id TEXT PRIMARY KEY,      -- r_xxxx
  job_id TEXT REFERENCES jobs(id),
  fingerprint TEXT NOT NULL,
  authorized BOOLEAN NOT NULL,      -- 必须为 true 才允许写入
  delivered_via TEXT NOT NULL,      -- v0.1 恒为 employer_site
  created_at TIMESTAMPTZ DEFAULT now()
  -- 禁止出现任何 PII 列。永远。
);
```

### 管线逻辑

1. **摄取循环**：按 freshness tier 轮询（近 7 天有变动的公司 6h 一次，其余 24h）。
2. **变更检测**：对每条 JD 算 `content_hash`（title+description 规范化后 sha256），未变则只刷新 `verified_at`。
3. **LLM 抽取**（仅 hash 变化时）：抽 `skills[]`、`remote_policy`、薪资（JD 无薪资则置 NULL——v0.1 不做推断，`salary_inferred` 留给 v0.2）。
4. **下架检测**：源头消失的 job 置 `delisted_at`，不删行。
5. **重挂检测**：同公司内 `normalize(title)` 相同且旧条目 `delisted_at` 非空 → 新条目 `relist_count = 旧值+1`，`first_seen_at` 继承旧值。
6. **ghost_score v0 公式**（写成纯函数+单测）：
   `ghost_score = min(1.0, 0.15 * relist_count + max(0, days_since(first_seen_at) - 45) / 90 * 0.5)`
   直觉：反复重挂、长期挂着不下架 → 分数升高。公式必然会迭代，先保证可解释、可测试。

### MCP 工具契约（四个，签名与响应字段照此实现）

完整示例见 `design_refs/OpenHire Protocol Spec.dc.html`。

1. `search_jobs(skills?, remote?, min_salary?, limit=20)` → JobPosting[]。服务端只做**硬过滤**（skills 交集、remote、salary），排序 = 匹配度×新鲜度的固定函数；精排留给客户端 Agent。每条结果必含五个协议字段。
2. `watch_intent(fingerprint, filters)` → `{ watch_id, status }`。
3. `check_watches(fingerprint)` → 自上次通知以来的新命中。stdio 无服务端推送，v0.1 用「客户端拉取」：MCP 客户端每次会话开始时调用；CLI `ohp watch --daemon` 每 30 分钟轮询并发系统通知。
4. `get_company_info(company_id)` → `{ verified, ghost_score_avg, active_jobs, last_crawled_at }`。聚合信号，永不返回任何个体候选人数据。
5. `apply(job_id, fingerprint, authorized)` → `{ delivered_via: "employer_site", receipt_id, resume_transmitted: false }`。v0.1 实现 = 校验 `authorized===true` → 记录 receipt → 返回 `apply_channel` URL 由客户端打开浏览器。**本工具拒绝任何文件/简历参数；请求含简历内容直接报错。**（直写 ATS 需雇主 API key，属 v0.3 雇主认领。）

### CLI 命令（对照哨兵设计稿）

- `ohp serve` — 启动 stdio MCP server
- `ohp init --scan <dir>` — 本地扫描个人仓库生成技能指纹：语言占比 + 依赖名 → 技能标签；**代码永不上传**；输出 `~/.openhire/fingerprint.json`（含随机短 id 如 `#a3f9`）；扫描前必须交互确认，文案见设计稿 STEP 2
- `ohp search --skills auto --remote --min-salary 600000`
- `ohp watch ...` — 注册常驻意向（安装引导的落点，见设计稿 STEP 3）
- `ohp apply <job_id>` — 打印岗位摘要 → 确认 → 打开 apply_channel → 记录 receipt
- `ohp status` — 当前指纹、watch、receipt 列表

### 三条隐私红线（写成自动化测试，CI 必须绿）

1. **简历/PII 永不过服务器**：`applications` 与 `watches` 无 PII 列（schema 测试）；`apply` 拒绝文件上传（API 测试）；服务端日志不落请求体。
2. **排序不可购买**：排序函数是 `f(匹配度, 新鲜度)` 的纯函数，无任何付费参数（单测锁死函数签名）。
3. **只为结果付费**：v0.1 无计费代码。禁止提前埋曝光计费逻辑。

### 里程碑（每个完成后停下汇报验收，再继续）

- **M1 数据管线**（1–2 天）：≥80 家公司验证入库，≥800 条在架职位，五协议字段全部有值（sla 为 NULL 合法），freshness 循环跑通。
- **M2 MCP Server**（1–2 天）：四工具在 Claude Desktop 实测可用；`search_jobs` 返回含 `verified_at`/`ghost_score`。
- **M3 watch + apply**（1 天）：新 JD 入库 → `check_watches` 命中；`ohp apply` 全流程 + receipt。
- **M4 发布**（1–2 天）：pipx/uvx 可装；隐私红线测试全绿；README（照 `design_refs/openhire-mcp README.dc.html` 转成真 Markdown）；提交 MCP 目录（Smithery 等）。

## Screens / Views（设计参考对照表）

- `OpenHire v0.1 哨兵.dc.html` — **本次实现的主对照**。四步旅程：安装→指纹→watch→命中与授权。CLI 输出的符号系统（`$`/`✓`/`?`/`▸`/`#`/`⬥`）、确认文案、「服务器所见」面板逐字对照。
- `OpenHire Protocol Spec.dc.html` — 协议五字段 + 四工具 JSON 契约（实现以此为准）。
- `openhire-mcp README.dc.html` — GitHub README 的设计稿，M4 时转成真 README.md。
- `OpenHire 交互原型.dc.html` — 求职者/广告主双端全景（广告主端为 v0.2+ 参考，勿实现）。
- `OpenHire Landing Page.dc.html` — 官网（后续另行实现，非本次范围）。
- `OpenHire 开聘协议.dc.html` — 战略 Deck；附录 A3 有接口现实与合规红线。

## Interactions & Behavior

- 每个改变状态的命令都要**显式确认**（`[Y/n]`），确认文案含隐私说明（照设计稿）。
- `apply` 成功后显示：`✓ 已直达雇主 ATS · 来源 = 你自己 · 响应 SLA 7 日起算`（v0.1 SLA 未知时省略 SLA 段）。
- 错误信息风格：`ERR_RANKING_NOT_FOR_SALE` 式的大写蛇形错误码 + 一句人话解释。

## State Management / 数据流

- 客户端状态：`~/.openhire/`（fingerprint.json、config.toml、receipts.jsonl）。
- 服务端无用户账号体系——fingerprint 即身份，可随时丢弃重建。

## Design Tokens（后续 Web UI 用；CLI 遵循符号系统即可）

- 深色：bg `#0E1310` · panel `#141B16` · border `#263029` · 文本 `#E9EEE9` · muted `#9AA69D`
- 强调：绿 `#4ADE87`（信任/匹配）· 琥珀 `#E5B85C`(风险/Sponsored) · 红 `#E07A6B`（错误）
- 字体：JetBrains Mono（数据/协议）+ Noto Sans SC / Inter（正文）

## Assets

无图片资产。全部视觉由代码实现；字体走 Google Fonts。

## Files

- `design_refs/*.dc.html` — 上述设计参考（双击可开；`support.js`/`deck-stage.js` 为预览运行时）
- 本 README — 唯一实现规范来源；与设计稿冲突时，以本 README 的数据契约为准、以设计稿的文案交互为准

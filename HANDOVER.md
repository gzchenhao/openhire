# OpenHire 技术交底手册（for Claude Code /worktree /goal）

> 放置位置：把本文件保存为 `C:\openhire\HANDOVER.md`。
> **Working directory = `C:\openhire`**（git 仓库根，含 pyproject.toml / src / tests / reports）。worktree 从这里创建。

## 0. 恢复记忆的正确顺序
1. 读 `CLAUDE.md`（工作制度）→ 2. 读 `PROGRESS.md`（进展台账）→ 3. 读 `reports/`（001–012+，每份自足）→ 4. 本手册。禁止重做已完成工作。

## 1. 项目是什么
OpenHire（开聘）：面向 AI Agent 的招聘数据协议层。MCP server + CLI，直连雇主官网 ATS 公开接口的一手职位数据；匹配在用户本机完成，服务器只见匿名指纹。**已公开发布**：
- GitHub: https://github.com/gzchenhao/openhire （main，署名 gzchenhao，Co-Authored-By: Claude 保留）
- PyPI: openhire 0.1.1（`pipx install openhire`，CLI 命令 `ohp`）
- 官方 MCP Registry: `io.github.gzchenhao/openhire`（server.json 在仓库）
- 快照: GitHub Release v0.1.0 资产 `openhire-index.db.gz`（13.2MB，每周刷新，见 docs/maintainer-snapshot-refresh.md）

## 2. 技术栈与结构
- Python 3.11+，官方 MCP SDK（FastMCP，stdio）、SQLAlchemy、httpx、Typer CLI；打包 hatchling。
- SQLite（WAL + busy_timeout=5000 + synchronous=NORMAL——P0-1 写锁修复，勿回退）；schema 兼容 Postgres（OPENHIRE_DATABASE_URL 可切）。
- `src/openhire/`: db/(schema·models·types[TZDateTime 全库 aware-UTC]·session[dispose_engine]) · ats/(greenhouse·lever·ashby) · pipeline/(ingest·extract·ghost_score·hashing·crawler·seed_runner·backfill·snapshot·ranking) · seed/candidates.py · mcp_server.py · service.py · cli.py · config.py
- 抽取：可插拔，DeepSeek（`DEEPSEEK_API_KEY` 于 `.env`）或免费启发式；**只在 content_hash 变化时调用**；花钱操作一律：先报价 → 用户批准 → ¥50 硬上限 → 分批可续跑。
- 数据源仅三家公开 ATS：Greenhouse / Lever / Ashby，96 家公司；礼貌频控（并发≤5、每 tenant≥30min）。

## 3. 协议五字段（API 已定型，勿破坏）
`verified_at` · `source` · `ghost_score`（基于真实 posted_at 岗龄+relist，纯函数+单测锁定）· `response_sla_days`（v0.1 恒 NULL）· `apply_channel`（resolve_apply_channel 强制 ATS 官方域名+job_id 直达，嵌入页回退 embed/job_app）。
另有 `posted_at`（ATS 真实发布日，**永不用抓取时间兜底**——P0-2 教训）· `days_open` · `remote_scope`(worldwide/region_locked/country_locked) + `eligible_regions` · `role_family`（DeepSeek 标注）· `required_skills`(AND) vs `skills`(OR) · `require_stated_salary`（独立开关，默认 False）。

## 4. MCP 五工具（契约已冻结）
`search_jobs`（服务端只做硬过滤+f(match,freshness) 固定排序，精排留客户端）· `watch_intent`（返回含 fingerprint 持久化警告；支持 required_skills/role_family）· `check_watches` · `get_company_info`（仅聚合信号；`verified` 已移除，恢复须待雇主认领功能）· `authorize_application`（原名 apply；三个标量参数，**结构上无法携带简历**；记录授权→返回雇主链接，不投递）。

## 5. 三条隐私红线（CI 强制，任何改动不得破坏）
1. 简历/PII 永不过服务器——watches/applications 无 PII 列（schema 内省测试）；对外文案统一口径「简历不经过我们的服务器，也不被我们存储」（**不得**写"永不离开你的电脑"——chat 宿主下为假）。
2. 排序不可购买——rank_score(match_quality, freshness) 签名 inspect 锁死 + 源码扫描禁 sponsored/boost/bid/paid。
3. 只为结果付费——v0.1 无计费代码，禁提前埋曝光计费。
附加红线：快照零用户态（snapshot-build 构建时校验 watches/applications=0，违规即失败）；token/密钥只进本机 `.env`/`.pypirc`/keyring，绝不进代码与 git。

## 6. 测试基线
**118+ passed**（privacy/ranking/snapshot/concurrency/posting_dates/appendix_b 等）。任何任务交付前全量 pytest 必须全绿。附录 B 回归 job_id（tests/test_appendix_b.py）勿删。

## 7. 工作制度（沿用）
- 每完成里程碑/工作日：更新 PROGRESS.md；完整汇报写 `reports/NNN-主题.md`（编号递增、自足、Markdown），最后一行告知路径。
- 用户是代码新手：需要用户亲手做的事，给分步、无术语指引；花钱/发布/对外提交类动作一律先请示。
- git 身份：user.name=gzchenhao（repo-local 已配）；不重写已发布历史。
- 每次会话结束提醒：备份 C:\openhire（除 .venv）→ U 盘。

## 8. 当前状态与下一步（2026-07-27）
- M1–M4 全部完成并发布；分发阶段进行中：知乎已发布，Show HN 待发（HN 新号发帖受限，养号中）。
- 常设维护：每周快照刷新（snapshot-build → 更新 Release 资产，文件名不变）。
- v0.2 方向（用户已拍板先 1 后 2）：①分发与种子用户（README GIF、社区互动、公司收录 issue 钩子）→ ②国内 ATS 适配器（北森/Moka）。之后：雇主认领 + response_sla 落地。
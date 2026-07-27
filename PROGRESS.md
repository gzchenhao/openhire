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

## 2026-07-27 — 015 v0.2.0 已发布（✅ 7 项验收 6 项达成；Registry 一步待授权，详见 reports/015 + BLOCKED.md）

**当前状态：v0.2.0 已上线 PyPI + GitHub Release + 新快照 · 155 tests green · 本单花费 ¥11.59**

- **PyPI 0.2.0 ✅** https://pypi.org/project/openhire/0.2.0/ —— 全新隔离 venv 从 PyPI 实装验证：`ohp version`=0.2.0、`all_vendors()` 含 **beisen**、MCP stdio 握手列出 **5 工具**、`search_jobs` 调用无误。（上传前先用同法验过本地 wheel。）
- **GitHub Release v0.2.0 ✅**（变更说明，**0 资产**）；**快照资产仍留在 v0.1.0 稳定 URL**，`ohp bootstrap` 跨版本不断链。
- **新快照 ✅** 公司 **125** · 职位 **16,316** · 18.3MB · 零用户态校验通过；**时序合规**：PyPI `14:19:09Z` → 资产 `14:35:26Z`（资产更晚）。真·新用户端到端（PyPI 0.2.0 + 已发布快照）：「龄 0 天前」，且 `--currency CNY --role-family engineering --min-salary 300000` 能搜到**宇树岗**。
- **ingest 未强制 `--all`：** freshness 未到期、索引本就是当日的；强刷会用 heuristic 覆盖刚花钱买的 DeepSeek 抽取结果。
- **⏳ 唯一未完成：官方 Registry 仍是 0.1.1。** `mcp-publisher publish` 报 **401 token expired**（011 那枚 JWT 已过期）。按止损条款**不自行找回/重置凭据**，改走官方 device-code 登录并把码交给用户浏览器授权，截至收工未完成授权 → 已写 `BLOCKED.md`（含一步解除办法）。**不影响用户安装**：`pipx install openhire` 拿到的已是 0.2.0。
- **下一步：** 用户授权后跑一条 `mcp-publisher publish` 即可；三方目录（glama/mcp.so/PulseMCP）仍需主动提交（对外动作待批）。

---

## 2026-07-27 — 015 任务 C 完成：DeepSeek 补抽取 ¥11.59（过程记录）

- **试点核费率：** `--limit 50` → CNY 0.12（¥0.0024/岗），且实测**只动 heuristic 岗**（deepseek 11,825→11,875、heuristic 4,491→4,441），范围正确。
- **skills 补全：** 4,441/4,441 更新 · 0 失败 · **CNY 9.49**（in 3,552,869 / out 297,585 tok）。
- **role_family 补全：** 1,405/1,405 标注 · 0 失败 · **CNY 1.98**。全库 `role_family` **NULL 归零**；分布 engineering 6,221 / sales 4,071 / ops 3,859 / marketing 615 / product 608 / data 503 / other 248 / design 191。
- **合计花费 ¥11.59**（0.12 + 9.49 + 1.98），在 ¥15 硬停内。
- **质量验收：** 附录 B 回归全绿（155 passed）；`engineering` 里**真·销售岗 0 条**（"Salesforce Engineer" 属平台研发，非销售）；经典陷阱判对——Sales Engineer 119/119→sales、Solutions Architect 385/387→sales、Solutions Engineer 186/192→sales。
- **北森数据完好：** 622 岗全部重抽，CNY **月薪值与 period 一字未改**（merge 策略保留 ATS 薪资），中文 JD 现在能抽出 skills（c++/stl/linux/robotics…）。
- **已备妥发布件：** 0.2.0 已 bump（pyproject/__init__/server.json ×2，README 的 mcp-name 未动）；`python -m build` + `twine check` 双 PASSED；**净 venv 装本地 wheel 实测 `ohp version`=0.2.0、MCP 握手列出 5 工具**；`mcp-publisher` v1.8.0 已重装。

---

## 2026-07-27 — 015 任务 A/B 完成（进行中）

- **A 薪资可比性 ✅：** `jobs` 加 `salary_period`（annual|monthly）+ migrate 回填（存量 15,694 annual / 北森 622 monthly）；`JobRecord.salary_period` 默认 annual、北森置 monthly；服务端 `--min-salary` 用 SQL `case` 归一（月薪 ×12 **仅用于比较**，存储值一字不改）；`job_posting` 输出 `salary_period`；CLI 显示 `/月` 后缀。`rank_score` 签名未动。新增 17 项单测（含 25K-50K 月薪对 300000 年薪门槛的**边界**：300000 收、600000 收、600001 不收；NULL 视作 annual 不被 ×12）。
- **实测证据：** `--min-salary 300000 --currency CNY` → 宇树「高级研发项目经理 CNY 25000–50000/月」**在结果里**（修复前必被丢弃）；`--min-salary 700000` → 该岗消失，只剩 40K-70K/月、30K-60K/月 等年化后确实过线的岗。
- **B 中文控制台 ✅：** 根因是 GBK（cp936）编不了 `¥`(U+00A5)，且 `▸ ⬥` 同样编不了 → 运行时输出也会崩。双保险：① `console.py::_harden_stdio()` 对 stdout/stderr 设 `errors="replace"`（保留控制台原编码，改用 UTF-8 会让中文变乱码）；② CLI 文案里的裸 `¥` 全改 `CNY`。`PYTHONIOENCODING=gbk` 下两条 `--help` 均**无 traceback、exit 0**。顺带把 `search --role-family` 的过时 help「(v0.1: unpopulated → no-op)」改成与现实一致。
- **测试：155 passed / 0 failed / 0 skipped**（138 + 17）。
- **下一步：** C DeepSeek 补抽取（先 --limit 50 试点核费率）→ D 发布链条。

---

## 2026-07-27 — 015 开工回执：v0.2.0 发布全链条（进行中）

- **目标：** A 加 `salary_period` 修 CNY 月薪被年薪门槛误杀；B 修中文 GBK 控制台 `--help` 崩溃 + 过时 help 文案；C DeepSeek 补抽取（≤¥15 硬停）；D bump 0.2.0 → PyPI → 全新 venv 验证 → Registry → GitHub Release → **最后**才刷快照。
- **铁律已记：** PyPI 0.2.0 未经全新环境验证前**绝不动 Release 快照资产**（否则 0.1.1 用户拉到含 beisen 的快照会遇到不认识的 vendor）。
- **核验已过：** pytest **138 passed / 0 failed / 0 skipped**；pyproject + server.json 均 0.1.1；twine 6.2.0 / build 1.5.1 可用；`.pypirc` 与 `.env` 的 DEEPSEEK_API_KEY 均存在（内容不打印）；`mcp-publisher` 不在 PATH，仅剩 `~/.config/mcp-publisher/token.json` → 需按官方文档重装。
- **已查实：** `rebuild_extraction` 本就只选 `extraction_source != 'deepseek'`，**无需加范围参数**；`merge_extraction` 保留既有 ATS 薪资（故北森 CNY 月薪不会被 LLM 覆盖）。
- **待补量：** heuristic 岗 **4,491** 条（非任务书估的 2,070，因 013 那趟 ingest 也留了 2,399 条）、`role_family` NULL **1,405** 条 → 按 M4 费率估合计约 ¥12，仍在 ¥15 硬停内；先 `--limit 50` 试点核费率。
- **最大风险：** 补抽取实际花费超预估；`mcp-publisher` 重装后登录态失效（若失效→停写 BLOCKED.md，不自行重置任何凭据）。

---

## 2026-07-27 — 014 自动驾驶/具身智能覆盖扩张（✅ 完成，详见 reports/014）

- **A 摸底（40 行矩阵）：** 飞书招聘覆盖最广（≥10 家目标公司）但**判不可抓** —— 职位列表是 GET `/api/v1/search/job/posts`，参数带字节跳动 `_signature` 反爬签名 + 滑块验证码 SDK，裸 curl 只返回 HTML 壳；按「不许硬闯」**就地停手**。**北森 `<tenant>.zhiye.com` 可抓** —— `POST /api/Jobad/GetJobAdPageList`，无签名/无 cookie，裸 curl 200。故 **vendor #1 = 北森**（任务书「摸底数据说了算」的预案生效）。
- **踩坑记录：** ① 只看 HTTP 200 会认错公司（`horizon.*`=汉森、`ikingtec`=云圣智能、`galaxis`=凯乐士、`yushi`=雨时），必须核 `<title>`；② 北森 `DisplayFields` 不带就不返回 PostDate/LocNames/Salary，看起来像「数据稀疏」；③ 自定义域名可能是白标 ATS（`career.limxdynamics.com` 实为飞书）。
- **B 北森适配器：** 新增 `ats/beisen.py`（覆写 POST+分页 fetch、模块级 Semaphore(2) 频控）+ `base.py` 加 beisen apply 分支与按 tenant 推导的 apply host + 20 项单测（真实 fixture）。**入库 11 家 / 622 岗，`posted_at` 覆盖 100%**（零值日期一律 NULL，不用抓取时刻兜底）；薪资按月存 CNY 不折年薪；11/11 apply_channel HTTP 200，浏览器人工核对逐项吻合。
- **补洞：** 新岗 `role_family` 全 NULL 会被 `--role-family` 过滤器完全排除（622 条国内岗隐身）。付费通道禁用，故加**免费**标题关键词分类 `ohp extract-role-family --heuristic`（拿不准留 NULL，不挡将来 DeepSeek 续跑）：标注 3086 · 仍 NULL 1405 · ¥0。
- **C 海外补齐：** 逐家 live 验证后新增 **18 家 / 1,448 岗**（Zoox、Aurora、Wayve、Figure、Motional、Kodiak、1X、Waabi、Torc、Agility、Saronic、Standard Bots、Dexterity、Bot Auto、Path/Carbon Robotics、Ambi、Collaborative Robotics）。
- **库存：** 公司 96 → **124**；在招 → **14,232**。**测试 138 passed / 0 failed / 0 skipped**（118+20）。全程 ¥0。
- **⚠️ 遗留待决策：** `jobs` 表无薪资周期字段，CNY 月薪与 USD 年薪同列比较 → `--min-salary` 会系统性误杀国内岗。建议 015 加 `salary_period` 或服务层按币种归一。其余见 reports/014 第七节。

---

## 2026-07-27 — 014 任务 A 关键结论：飞书=不可抓，北森=可抓（过程记录）

- **飞书招聘（覆盖最广，≥10 家）判定「不可公开抓取」：** 浏览器实测其职位列表是 **GET `/api/v1/search/job/posts`，查询参数带字节跳动 `_signature` 反爬签名**（同页还加载 `verify.snssdk.com` 验证码 SDK）。裸 curl 无签名 → 返回「猎头平台」HTML 壳。按任务书「需破解签名/验证码者一律判不可抓、不许硬闯」→ **停手，写进矩阵**。
- **北森 zhiye.com 判定「可抓」✅：** `POST https://<tenant>.zhiye.com/api/Jobad/GetJobAdPageList`，body `{portalId,pageIndex,pageSize}`，**无签名、无 cookie、裸 curl 200**（宇树实测 `Count:81`）。`portalId` 直接写在页面 HTML 的 `"PortalId":"…"`，可自举。
- **注意（P0-2 教训）：** 北森 `PostDate` 大量为 `0001-01-01T00:00:00` 零值 → 必须落 NULL，**严禁**用抓取时刻兜底。
- **由此定 vendor #1 = 北森**（飞书虽覆盖更广但不可抓）。

---

## 2026-07-27 — 014 开工回执：自动驾驶/具身智能覆盖扩张（进行中）

- **目标：** ① 国内 ≥30 家自动驾驶/具身智能公司的 ATS 归属摸底（矩阵+证据）；② 按摸底结果做「覆盖第一」的国内 vendor 适配器（≥8 家 / ≥300 岗）；③ 海外目标行业种子补齐 ≥12 家。
- **顺序：** 0 核验 → A 摸底（先于一切编码）→ B 适配器 → C 海外种子 → D 报告/提交。每完成一步回写本文件。
- **核验已过：** `pytest -q` = **118 passed / 0 failed / 0 skipped**；已读 `ats/base|greenhouse|lever|ashby` 与 `seed/candidates.py`，新 vendor 照 `ATSClient` 模式加进 `ats/__init__.py` 的 `_CLIENTS`。
- **最大风险：** 国内 ATS（飞书/Moka/北森）多为带 cookie/CSRF 的 POST 接口，可能全部拿不到免登录 JSON。若「可得」公司 <5 家，按止损条款停在任务 A，矩阵+结论即为合格交付——**不硬闯签名/验证码/登录墙**。
- **地界：** 零花费（强制 heuristic）；不发 PyPI、不动版本号/server.json/Release；现有测试断言不改不删不 skip。

---

## 2026-07-27 — 013 v0.2 分发收尾：快照刷新 + README 演示 + 四方收录核查（✅ 完成，详见 reports/013）

- **A 快照已刷新（¥0）：** `ohp ingest`（强制 heuristic）→ 96 家 / 新 2399 / 下架 2057 → `ohp snapshot-build` **公司 96 · 职位 14224**（11,825→14,224，无倒退）、零用户态校验通过 → `gh release upload --clobber`。验证三重：资产 `updatedAt=2026-07-27T05:52:55Z`；SNAPSHOT_URL `HTTP 200` + `Last-Modified` 为今日；临时库 `ohp bootstrap` 报**「龄 0 天前」**。
- **顺手修 op card 两个坑**（`docs/maintainer-snapshot-refresh.md`）：① `ohp ingest --once` **命令不存在**（裸 `ohp ingest` 才是一次性）；② **默认会花钱** —— `OPENHIRE_EXTRACTOR=auto` 在有 `DEEPSEEK_API_KEY` 时选 DeepSeek，等于对 4,553 条变更 JD 付费重抽；已加 `heuristic` 强制与说明。上传步骤改为 `gh` CLI + 三步验证。
- **B README 演示：** 占位 → `docs/quickstart.svg`（24.5KB，无外链；已剥掉 rich 默认的 cdnjs 字体）。三步**全真跑**：隔离 `PIPX_HOME` 里 `pipx install openhire`（PyPI 0.1.1）→ `ohp bootstrap`（下新快照）→ `ohp search`。job_id `mongodb:7727896` 等均可在新快照查到，零伪造；`src/` 未改（monkeypatch 只在临时脚本）。
- **C 四方收录（2026-07-27 只读查证）：** 官方 Registry ✅ 已收录（`count:1`、`status:active`、v0.1.1）；PulseMCP ❌「No servers found.」；mcp.so ❌ `servers:[], total:0`；glama.ai ❌ 只有 OpenAIRE/openhive-mcp 等模糊匹配，`gzchenhao` 0 次。
- **⚠️ 推翻旧假设：** 「PulseMCP/mcp.so 会自动同步」**不成立** —— 官方收录已 12 天，三家一个都没同步。要收录须**主动提交**（对外动作，留待下一单批准）。
- **测试：** 收尾复跑 **118 passed / 0 failed / 0 skipped**，与基线一致。
- **下一步：** ① 是否授权向 glama/mcp.so/PulseMCP 主动提交；② 快照刷新可考虑 GitHub Actions 每周定时。

---

## 2026-07-27 — 013 开工回执：v0.2 分发收尾（进行中）

- **目标：** ① 刷新 Release 快照（欠约两周，上次 2026-07-14）；② README 顶部占位换成真实静态终端演示；③ 核查四方 MCP 目录收录状态（只读）。
- **顺序：** 0 核验 → A 快照 → B 演示 → C 收录 → D 报告/提交。每完成一步回写本文件。
- **核验已过：** `pytest -q` = **118 passed / 0 failed / 0 skipped**；`gh release view v0.1.0` 资产 `openhire-index.db.gz` 存在（updatedAt 2026-07-14T03:03Z, 13.2MB）。
- **最大风险：** ingest 用免费启发式重跑可能改写既有 DeepSeek 抽取字段，导致快照质量倒退——按合并策略（skills-only merge）应无损，构建后核对职位/公司数不低于 96/11.8k 再上传；若倒退则不上传并如实记录。
- **地界：** 本单零花费（禁 DeepSeek）；只改 README/docs/reports/PROGRESS；不碰 src/tests/server.json/版本号；站外只读。

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

# CLAUDE.md — OpenHire 工作约定（每个会话必读）

## 新会话恢复指引（开工前先做这三步）

1. **先读 `README.md`** — 了解产品定位、五个协议字段、三条隐私红线、安装与工具（公开版 README）。
2. **再读 `PROGRESS.md`** — 了解已完成到哪一步、关键决策与理由、下一步、待用户确认事项。
3. **禁止重做已完成的工作。** M1–M4 已全部完成，**v0.1 已公开发布**（见下方发布状态、PROGRESS.md 验收证据）。除非用户明确要求返工，不要重建已完成的里程碑。

## 发布状态（最新 v0.6.0 · 2026-09-14；v0.1 首发 2026-07-15）

- **GitHub：** https://github.com/gzchenhao/openhire （owner `gzchenhao`，main，最新 tag v0.6.0）
- **v0.6.0（2026-09-14）：** 雇主认领落地（`seed/claims.py` + SLA + 四类更正 + `--unverify`）、
  `refresh_index` 工具（单雇主、6h 节流）、`ohp numbers` 管道、`ghost_reason`、`--company` 过滤、`collapse`。
- **GitHub Pages（2026-09-15 开启）：** https://gzchenhao.github.io/openhire/ ，源 = `main` 分支 `/docs`。
  **注意：`docs/` 整个目录就是站点根，放进去即等于公开发布。** 月报页因此被误发过一次，已撤到 `report-draft/`。
- **v0.5.0（2026-09-12）：** `role_group`（同岗多城市共享的分组键，不折叠行）+ `offset` 分页，
  两者都是给 client agent 省 `limit` 预算和 context 的；返回结构未变，老客户端不受影响。
- **v0.4.1–0.4.3：** auto-bootstrap 改为后台线程（托管市场探测不再超时）、版本号三处对齐
  （包 / `ohp version` / `serverInfo.version`，各有测试钉死）、幂等注解与实现对齐。
- **v0.4.0（2026-09-11）：** `serve` 空索引自动拉快照（`uvx openhire serve` 零配置）、`--transport sse|streamable-http`、五个工具带 annotations、`Dockerfile`、`mcpb/`（Claude Desktop 扩展，uv 运行时；Release v0.4.0 附 `openhire-0.4.0.mcpb`）、`docs/PRIVACY.md`、`docs/brand/` 图标。
- **上架进度（025/026）：** 魔搭 ✅ 已上线可部署 · Claude 扩展目录 ✅ 已提交 · Cline issue #2501 与 Docker PR #5055 审核中 · GitHub 精选 Registry 已申请排队。
- **Release v0.1.0：** https://github.com/gzchenhao/openhire/releases/tag/v0.1.0 （含快照资产 `openhire-index.db.gz`，URL 稳定不变）
- **PyPI：** https://pypi.org/project/openhire/0.5.0/ （`pipx install openhire` / `uvx openhire@latest serve`）
- **官方 MCP Registry：** `io.github.gzchenhao/openhire` v0.5.0（`registry.modelcontextprotocol.io`）。**推 `v*` tag 即由 `.github/workflows/publish-mcp-registry.yml` 用 OIDC 自动发布**（v0.3.1 起每次均如此），本地 `mcp-publisher` 只作备用；PulseMCP/mcp.so 自动同步。
- **Smithery：** v0.1 放弃（无本地 stdio 网页入口，见 `reports/010`）。
- 推送用 `gh`（keyring）；PyPI token 仅 `%USERPROFILE%\.pypirc`；`mcp-publisher` 二进制在 `.tools/mcp-publisher.exe`（gitignored，v1.8.1），其 GitHub 登录令牌会过期，过期时 `.tools/mcp-publisher login github` 重登。三者均**不进代码/git**。
- **发版铁律：PyPI 发布必须先于快照刷新**（老客户端会带旧代码读新数据）。
  **反过来同样会咬：新代码读老快照。** 2026-09-15 v0.6.0 带着 `companies` 的两个新列上了 PyPI，
  而已发布快照还是加列之前建的，于是新用户 `uvx openhire@latest serve` 第一次搜索就 
  `no such column: companies.response_sla_days`，每周快照工作流同时挂在 `ohp seed`。
  **已从根上修掉**：`init_db()` 现在会跑前向迁移（`db/migrate.py`），打开任何数据库都先补列，
  因为我们打开的库往往不是我们建的。加列之后**不需要**记第三条规矩，但要记得：
  改了模型列就跑一次 `gh workflow run refresh-snapshot.yml`，让公开快照带上新列。
- **`ohp.exe` 文件锁（已咬三次，按这个来）：** Claude Desktop 跑着 openhire MCP 时会占住
  `.venv\Scripts\ohp.exe`，`pip install -e .` 会在最后替换该文件时报 `WinError 32` 而中止，
  于是**包被卸载但没装回去**，表现为 `ModuleNotFoundError: No module named 'openhire'` +
  一片测试报错。Windows 连重命名运行中的 exe 也拒绝（`Device or resource busy`）。
  **正确顺序：改 venv 前先在 Claude Desktop 设置 → Developer 里停掉 openhire，或退出 Claude Desktop。**
  已经中招时：`pip install -e . --no-deps` 通常能把包装回去（只有 exe 那步失败），旧 exe 是转发壳、
  照样加载新包，那个 ERROR 是噪音不是故障 —— 但**必须重跑一次 pytest 确认**，不能靠推断。
- **备份：代码/reports/style-reference/设计文档 push 到公开仓库即等于备份。** 唯一不在公开仓库的工作内容是
  `drafts/`（gitignored，宣传文案与任务书），它镜像在私有仓库 **https://github.com/gzchenhao/openhire-private** ，
  用 `.venv/Scripts/python.exe scripts/backup_drafts.py` 同步（幂等；检测到 `.env` 等密钥形态文件会拒绝执行）。
  `.env` / API key **永不进任何仓库**（含私有），存密码管理器。`dist/`、`.tools/`、本地 DB 均可重建，不必备份。
- 再发新版流程：改 README `mcp-name` 保持不变 → bump 版本 → `twine upload` → 改 `server.json` 版本 → `mcp-publisher publish`。

## 常设工作制度（持续遵守）

1. **进度记录：** 每完成一个里程碑、或每个工作日结束时，更新 `PROGRESS.md`：
   - 日期
   - 已完成（含验收证据：测试数、实测输出、花费等可核对的事实）
   - 关键决策及理由
   - 下一步
   - 待用户确认事项
   控制在一页以内；新进展追加在顶部（倒序），旧条目保留。
2. **恢复指引常驻：** 本文件顶部的「新会话恢复指引」始终保留并保持最新。
3. **每次会话结束前主动提醒用户：** 「今日请备份 `C:\openhire` 到 U 盘。」
4. **里程碑节奏：** 每完成一个里程碑停下，对照验收标准向用户汇报后再继续。
5. **汇报归档：** 每次完成任务后的完整汇报，除在终端显示外，**同时写入 `C:\openhire\reports\`**。
   - 文件名 = 递增编号 + 主题，如 `001-真机验收三件套.md`、`002-M4打包.md`。
   - Markdown 格式，**自足完整**：不依赖终端上下文，单独打开也能看懂（含背景、做了什么、证据、结论、下一步）。
   - 每次干完活的**最后一行**告诉用户：「汇报已写入 C:\openhire\reports\xxx.md」。
   - 编号取 `reports\` 里现有最大编号 +1（补零三位）。
6. **每周快照刷新：已自动化（017）。** `.github/workflows/refresh-snapshot.yml` 每周一 06:10 UTC 自动跑（也可在 Actions 手动 Run workflow）：下载已发布快照 → 重新 seed → 免费启发式全量刷新 → `ohp snapshot-build` → 覆盖上传同名资产。**工作流零密钥**（只用 GitHub 自动下发的 per-run token，权限仅 `contents: write`），失败靠 GitHub 默认邮件通知仓库主。
   人工只剩**月度一条命令**的 LLM 精抽（CI 无 key，只能跑启发式）：
   ```
   ohp extract-rebuild --backend glm       # 补 skills（套餐内，现金 ¥0）
   ohp extract-role-family --backend glm   # 补 role_family
   ```
   跑完按 `docs/maintainer-snapshot-refresh.md` 手动 build + upload 一次，让精抽结果进到公开快照。

## 当前观察期（开工时先看这里，到期主动向领导汇报）

| 观察项 | 起 | 到期 | 到期要做什么 |
|---|---|---|---|
| **月报页点名后的雇主反应** | 2026-09-19 | **2026-10-03** | 领导定的 14 天观察期。期间**不做任何对外推广**，只看有没有雇主投诉、认领或要求移除。到期向领导汇报：收到几条、分别是什么性质、要不要继续点名。 |

**每次开工要主动查的四个入口**（有动静立刻处理，不等到期）：
1. GitHub issues（`gh issue list --repo gzchenhao/openhire`）—— 雇主认领模板会落在这里
2. 邮箱 `gdchenhao@qq.com`（认领的非 GitHub 通道，我读不到，**需要提醒领导自己看**）
3. 知乎通知与评论（https://www.zhihu.com/notifications）
4. **X 每日一轮**（领导 2026-09-20 授权，不请示）：先看 Mentions，再去搜当天的 MCP 讨论
   （`MCP server` / `modelcontextprotocol` / `uvx` / `ghost jobs`，用 `f=live` 看最新），
   **只在真有事实可加的贴下回复，第一条回复不放链接**。记账在 `drafts/x-engagement-log.md`。
   详见记忆 `social-engagement-duty`。

观察期结束后删掉这一行，换成下一个观察项；没有观察项时保留表头写「无」。

## 对外文案的四条硬规矩（体验官 Round 3 定，第 4 条 2026-09-15 补）

1. **数字只准引用 `docs/numbers.json`。** 跑 `ohp numbers` 生成，写文案时照抄，**不准凭记忆写**。
   「139 家」在所有文章里出现过，而表里是 140 行——那不是写错数，是**两个不同的问题共用了一个标签**。
   文件里每个字段名都说清了它数的是什么（`companies_in_index` vs `employers_with_live_postings`）。
   百分比对外一律取整并标注实测日期，索引每周刷新，小数必然漂移。
2. **人设：主叙事是「深科技猎头，覆盖智驾与具身」**（领导 2026-09-14 批准）。
   「用 AI 结对写代码」只作为**方法说明**出现，绝不作为身份——写成「我不是程序员，是个 PM」会让
   同一个号在一个月里出现三张名片，读者连着刷到会觉得「这人谱系好满」，可信度反而掉。
3. **零破折号。** 这是 023 号定的行文规矩，但 Round 3 实测四篇文章里有 11 处——**规矩是我们自己破的**。
   已全部清零，往后写完自查一遍。
4. **描述雇主行为的动词，必须有对应字段撑着。** 尤其是「重挂 / 反复重新发布 / 刷新排序」——
   这类词说的是**雇主主动做了一件事**，只有 `relist_count > 0` 的行才配得上。
   全库 16,153 条在架里只有 279 条（1.73%）重挂过，**国内（北森 + Moka）1,655 条里是 0 条**。
   脉脉第一条帖写了「国内 39.5% 挂了很久**且反复重挂**」——那个 39.5% 是 `ghost_score` 超阈值的比例，
   而国内岗位的 ghost_score 里重挂项恒为 0，**「且反复重挂」四个字是凭空加的**。
   这和规矩 1 是同一类错误：规矩 1 是数字凭记忆写，这条是**动词凭印象写**，而后者更危险——
   数字写错是失准，**动词写错是指控**，雇主可以拿它来质疑我们全部内容的公信力。
   自查方法：文案里每出现一个描述雇主主观意图的词（重挂、不管了、弃坑、刷排序），
   先回答「哪个字段能证明」；答不上来就删掉，改写成我们真正量到的东西（在架天数）。

## 三条隐私红线（CI 强制，永不可破）

1. 简历或任何 PII **绝不**经过服务端 —— 只有匿名指纹过网。
2. 排序**绝不**是付费参数 —— 只是 f(匹配度, 新鲜度) 的纯函数，签名锁死。
3. 雇主只为已授权、已交付的结果付费 —— 绝不为曝光付费（v0.1 无任何计费代码）。

对应自动化测试见 `tests/test_privacy.py`、`tests/test_ranking.py`。改动排序/服务层/apply 后必须跑 `pytest` 确认全绿。

## 关键路径与事实

- 代码根：`C:\openhire\src\openhire`
- 数据库（默认，绝对路径）：`C:\Users\gdche\.openhire\openhire.db`（2026-09-03 快照：22,976 行 / 活跃 15,841 / 139 公司；精抽存量已全部清偿，role_family 空值 = 0）
- CLI 可执行文件：`C:\openhire\.venv\Scripts\ohp.exe`（**未在系统 PATH 上** —— 接入 Claude Desktop 时须写全路径）
- 抽取后端（可插拔，`--backend` 选）：
  - **GLM（默认首选，017 起）** —— `glm-5.3-flash`，走领导的 coding 套餐，**现金 ¥0**。key 从 `.env` 的 `ZHIPU_API_KEY` 读。base_url 必须是 `https://open.bigmodel.cn/api/coding/paas/v4`（标准 `/api/paas/v4` 对套餐 key 报 1113）。两个坑已在代码里处理并有测试锁死：① 必须发 `thinking:{"type":"disabled"}` 且 `max_tokens ≥ 1024`（reasoning token 先于 content 从额度里扣，额度小会返回空串）；② flash 输出带 ```json 围栏，解析须剥。
  - DeepSeek（`deepseek-chat`，`DEEPSEEK_API_KEY`）—— 按次计费，017 起不再默认使用。
  - 启发式（免费离线，CI 与 `bootstrap` 用）。
  - **血统不造假：** 每行 `jobs.extraction_source` 如实记录是谁抽的（`glm` / `deepseek` / `heuristic`）；重抽只挑「不属任何 LLM 源」的行，两个 LLM 后端不会互刷。
  - serve / search 阶段不需要任何 key。
- 设计交接文档：`design_handoff_openhire_v01\README.md`（唯一权威规格）；`design_refs\*.html` 仅供交互参考，**不复用其代码**。
- **抓取边界判例（020 复核定档）：** 响应体自带密钥、IV 页面明文可得的传输编码 = 可解（等价多绕几道的 base64，如 Moka 的 AES 信封）；请求签名、验证码、登录墙 = 访问控制，不可破（如飞书 `_signature`）。若某 vendor 把密钥移出响应体（JS 派生/会话挑战/轮换），即视为升级成访问控制——**立即停抓该 vendor 并记录**，不做逆向。
- **抽取/解析规则变更要影响存量数据：必须先失效 content_hash**，否则重抓一律被判「未变」而空转（020 福瑞泰克「元/天→假月薪」修复的教训）。

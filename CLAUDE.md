# CLAUDE.md — OpenHire 工作约定（每个会话必读）

## 新会话恢复指引（开工前先做这三步）

1. **先读 `README.md`** — 了解产品定位、五个协议字段、三条隐私红线、安装与工具（公开版 README）。
2. **再读 `PROGRESS.md`** — 了解已完成到哪一步、关键决策与理由、下一步、待用户确认事项。
3. **禁止重做已完成的工作。** M1–M4 已全部完成，**v0.1 已公开发布**（见下方发布状态、PROGRESS.md 验收证据）。除非用户明确要求返工，不要重建已完成的里程碑。

## 发布状态（最新 v0.6.4 · 2026-09-23；v0.1 首发 2026-07-15）

- **GitHub：** https://github.com/gzchenhao/openhire （owner `gzchenhao`，main，最新 tag v0.6.4）
- **v0.6.4（2026-09-23，同日第三版）：** 回答领导「还有无其他缺陷」时查出两条数据层缺陷（`reports/052`）：
  ① 共享技能词表的正则没加词边界，`rust` 命中 trust、`scala` 命中 scalable，**2,930 条 rust 标签里 2,432 条（83%）JD 里没这个词**；
  ② `extraction_source` 记的是「问了谁」不是「谁答的」：LLM 抽取失败静默退回启发式、每周重抓在内容变化时用启发式覆盖 skills
  但不动来源戳，**3,098 条在架行（19%）顶着 deepseek/glm 的章、装的是启发式列表**，且因此被月度精抽跳过（它只挑非 LLM 源）。
  修法：词表全部加边界（`_bounded`，`c\+\+` 保留尾部开放）；`ExtractionResult.extractor` 由抽取器自己签名、ingest 照签盖章；
  `scripts/clean_skill_noise.py` 修存量（无证据的词表标签删掉；启发式列表冒 LLM 章的重打标签并如实盖 heuristic）。
  **教训进「血统不造假」那条：来源戳必须由产出结果的那个抽取器写，调用方不许按「计划用谁」盖章。**
- **v0.6.3（2026-09-23，同日第二版）：** 体验测试（三个小马智行感知工程师人设 + 复现者，只用 MCP 工具，`reports/051`）
  抓到的十条可复现缺陷全修：`refresh_index` 崩溃（asyncio.run 在事件循环里 → 工作线程）；**排序 freshness 原来取
  `verified_at`（索引构建时间，每行相同），改成雇主自己的时钟（最后改动否则发布日，180 天线性）**；`role_family=null`
  的新岗不再被过滤掉；`check_watches` 全量排序后取 100 条并报 `total_matching / truncated`；中文技能别名表
  （感知/占用网络/点云/多传感器融合/视觉/目标检测/定位/规控）+ 半命中结果报 `unknown_skills`；`remote_scope`
  国家码按词边界匹配、读不出的回 `unknown` 不再假报 `worldwide`；`watch_intent` 拒绝未知键、支持 `company`；
  `get_company_info` 认名字；文远知行加中文名；`xiaopeng` 租户改名「小鹏汇天 XPeng AeroHT」（它是飞行汽车 + 工厂，
  不是小鹏汽车智驾）。**改名要等快照刷新才进公开库**（已手动触发 refresh-snapshot.yml）。
- **v0.6.2（2026-09-23）：** 对外文案改成搜索优先（GitHub 描述 / `server.json` / `pyproject` / MCP `instructions`，
  搜索引擎已是第二大来源，Google+Bing+Baidu 14 天 11 人，比知乎的 4 多）；MCP `instructions` 里加数据出处署名；
  工具 docstring 里那个硬编码的 67% 删掉改指 `numbers.json`；README 加 Cursor 一键安装按钮；**mcpb 依赖钉到当前版本**。
- **v0.6.1（2026-09-22）：** 把 9/14 之后攒在 main 上的 44 个 commit 一次性发出去。
  **发版铁律新增第三条：修好不等于发好。** 体验官 Round 5 抓到我们「修复速度是小时级、发布速度是周级，
  用户拿到的是乘积，而这周乘积为零」：0.6.0 的首搜必崩修复在 main 上躺了 8 天，
  GitHub Releases 还停在 v0.5.1（v0.6.0 连 Release 都没有），README 指的 `.mcpb` 是 404，
  PyPI 页面挂的 mcpb 还是 0.5.1。
  **往后每次改动用户可见行为，当天就要走完：PyPI → 打 tag → 建 Release → 挂 mcpb → 文案版本号同步。**
  版本号一共**五处**：`pyproject.toml`、`server.json`（两处）、`mcpb/manifest.json`、**`mcpb/pyproject.toml`**、`README.md`。
  **第五处是 2026-09-23 才发现的，而且是最要命的一处：** `.mcpb` 里跑的是 `uv run --directory <bundle> src/server.py`，
  真正装什么由 `mcpb/pyproject.toml` 的 `dependencies = ["openhire==X"]` 决定，manifest 里的版本号只是标签。
  v0.6.1 的 mcpb 标签写 0.6.1、依赖钉 0.5.1，**所有双击安装的用户一直在跑 0.5.1**。
  `tests/test_release.py` 现在把五处钉死到 `pyproject.toml`，版本不一致测试就红。
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
   ohp extract-rebuild --backend deepseek --ceiling 15       # 补 skills（约 ¥0.0022/条）
   ohp extract-role-family --backend deepseek --ceiling 15   # 补 role_family
   ```
   跑完按 `docs/maintainer-snapshot-refresh.md` 手动 build + upload 一次，让精抽结果进到公开快照。

## 当前观察期（开工时先看这里，到期主动向领导汇报）

| 观察项 | 起 | 到期 | 到期要做什么 |
|---|---|---|---|
| **月报页点名后的雇主反应** | 2026-09-19 | **2026-10-03** | 领导定的 14 天观察期。期间**不主动宣传月报页本身**（不发链接、不点名转述），只看有没有雇主投诉、认领或要求移除。**工具本身照常推广**（领导 2026-09-23 确认：我此前记成「不做任何对外推广」是记宽了）。到期向领导汇报：收到几条、分别是什么性质、要不要继续点名。 |

**每次开工要主动查的四个入口**（有动静立刻处理，不等到期）：
1. GitHub issues（`gh issue list --repo gzchenhao/openhire`）—— 雇主认领模板会落在这里
2. 邮箱 `gdchenhao@qq.com`（认领的非 GitHub 通道，我读不到，**需要提醒领导自己看**）
3. 知乎通知与评论（https://www.zhihu.com/notifications）
3.5 **体验报告附件：看 `C:\Users\gdche\Downloads` 里有没有新的 `吐槽-*.md` / `体验报告-*.md`。**
   Gmail 连接器**只给附件 id、不给内容**；`RAW` 能取到整封 MIME，但要把 12KB base64 手抄进文件，有损坏风险。
   **约定（2026-09-22 定）：领导把附件下载到 Downloads 就行，我自己去读，不必再拖进对话。**
   **绝不为此索取邮箱授权码 / 应用专用密码** —— 那是整个邮箱的读取权（银行、验证码、私人往来都在里面），
   为一个 5KB 的附件付这个代价不成比例，而且那串密钥还得长期保管、泄露后果远重于一个 API key。
4. **X 每日一轮**（领导 2026-09-20 授权，不请示）：先看 Mentions，再去搜当天的 MCP 讨论
   （`MCP server` / `modelcontextprotocol` / `uvx` / `ghost jobs`，用 `f=live` 看最新），
   **只在真有事实可加的贴下回复，第一条回复不放链接**。记账在 `drafts/x-engagement-log.md`。
   详见记忆 `social-engagement-duty`。

观察期结束后删掉这一行，换成下一个观察项；没有观察项时保留表头写「无」。

## 对外文案的五条硬规矩（体验官 Round 3 定，第 4 条 2026-09-15 补，第 5 条 2026-09-23 补）

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

5. **主句是底座，不是楔子（领导 2026-09-23 批准，见 `reports/050`）。** 对外第一句永远是
   **「让 AI 助手直接从雇主自己的系统里替你找工作，简历不出你的电脑」**；「原始发布日 / 在架天数」只作为
   「这是一手数据、平台给不了」的**证据**放第二句，不是产品。**「幽灵」两个字对外不再使用**（协议字段名
   `ghost_score` 不动，文案一律说「在架时长」）。内容配比**一比一**：每写一篇在架时长，配一篇雷达 / 工作流
   （让助手盯岗、`--company` 查一家全部在招、某岗位哪些公司在开）。知乎选题流水线按此筛。
   月报页点名与「中立即生命」有张力，10-03 到期按定位重议，不只看有没有投诉。

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
  - **DeepSeek（默认首选，2026-09-20 起）** —— `--backend deepseek`，key 从 `.env` 的 `DEEPSEEK_API_KEY` 读。
    `deepseek-chat` 现在指向 `deepseek-flash`（另有 `deepseek-v4-pro`，**不用**：抽技能是结构化提取不是强推理，
    flash 是实测过的那个）。**实测单价 ¥0.0022/条**，2026-09-20 全量 3,035 条花 **¥6.57**、零失败。
    `--ceiling` 是 CNY 硬停（默认 50，跑全量时给 15 就够）。
  - **GLM —— 已停用（2026-09-20 领导决定不再续订）。** 四个 key 当天实测全死：
    #1/#2 是 `1309`「GLM Coding Plan 套餐已到期」、#3 是 401、#4 是 `1113` 余额不足。
    代码仍保留 GLM 后端可用，但**不要再默认走它**。已把 `1309` 归入死 key 判定并抛 `KeysExhausted`，
    因为它原本被当成限流、还提示「重跑会续上」——**重跑不会续费**。
  - 启发式（免费离线，CI 与 `bootstrap` 用）。
  - **血统不造假：** 每行 `jobs.extraction_source` 如实记录是谁抽的（`glm` / `deepseek` / `heuristic`）；重抽只挑「不属任何 LLM 源」的行，两个 LLM 后端不会互刷。
  - serve / search 阶段不需要任何 key。
- 设计交接文档：`design_handoff_openhire_v01\README.md`（唯一权威规格）；`design_refs\*.html` 仅供交互参考，**不复用其代码**。
- **抓取边界判例（020 复核定档）：** 响应体自带密钥、IV 页面明文可得的传输编码 = 可解（等价多绕几道的 base64，如 Moka 的 AES 信封）；请求签名、验证码、登录墙 = 访问控制，不可破（如飞书 `_signature`）。若某 vendor 把密钥移出响应体（JS 派生/会话挑战/轮换），即视为升级成访问控制——**立即停抓该 vendor 并记录**，不做逆向。
- **抽取/解析规则变更要影响存量数据：必须先失效 content_hash**，否则重抓一律被判「未变」而空转（020 福瑞泰克「元/天→假月薪」修复的教训）。

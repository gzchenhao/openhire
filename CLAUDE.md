# CLAUDE.md — OpenHire 工作约定（每个会话必读）

## 新会话恢复指引（开工前先做这三步）

1. **先读 `README.md`** — 了解产品定位、五个协议字段、三条隐私红线、安装与工具（公开版 README）。
2. **再读 `PROGRESS.md`** — 了解已完成到哪一步、关键决策与理由、下一步、待用户确认事项。
3. **禁止重做已完成的工作。** M1–M4 已全部完成，**v0.1 已公开发布**（见下方发布状态、PROGRESS.md 验收证据）。除非用户明确要求返工，不要重建已完成的里程碑。

## 发布状态（最新 v0.8.35 · 2026-10-30；v0.1 首发 2026-07-15）

- **GitHub：** https://github.com/gzchenhao/openhire （owner `gzchenhao`，main，最新 tag v0.8.4 由 Actions 建）
- **v0.8.35（2026-10-30，云端会话，`reports/109`）：** 领导批四件：**行业筛选** `seed/sectors.py`（176 家各一个行业：智驾 29、具身 42、AI 基础设施 55、其他 50；新种子不标行业测试就红），`search_jobs(sector=)`、盯岗键 `sector`、每行带 `sector`；**查公司页**加「不开会员，五分钟查一家公司」与外包派遣一段，订阅文件已重建（EarlyTip 两道关过，变长不用通知）；**`check_employer(message_text=)`** 本机扫私信骗局说法，托管端点拒收（`ERR_LOCAL_ONLY`，私信可能带用户个人信息）；任何文字多一项 `outsourcing_words`（只列字样不下结论）。1017 tests。
- **v0.8.34（2026-10-30，云端会话，`reports/107`、`108`）：** 模拟求职者第一晚（10 人设、US$7.70）两条 high 修：中英混写标题判级别（`测试Leader`）；`read_board` 摘要从岗位职责截、`ats_job_id` 取全文；地点 China / Bay Area 展开、空结果 `unknown_location` 与 `filters_applied` 全回显。108 号知乎痛点地图（433 条手读，12 类）。
- **v0.8.33（2026-10-29，云端会话，`reports/105`、`106`）：** **模拟求职者夜测**（领导的 Claude API 赠送额度 US$96，11-11 过期）：`scripts/persona_test.py` 10 个人设，Opus 5.5 当助手、Sonnet 5.5 当求职者、Opus 5.5 按十条承诺评分；默认 `--backend local` 在本机内存里起 OpenHire、用索引临时副本（托管端点经 MCP connector 五次只通一次）；key 名 `OPENHIRE_PERSONA_API_KEY`（不与精抽混用），累计上限 US$80；本机待办 29 每晚跑到 11-10，云端定时任务「模拟求职者测试日读」每天 10:37 核结果并修。首轮修四处：refresh_index 结果带 `delisted` 与 `counts_note`；盯岗文案的定时提醒改成 check_watches；长指纹重复登记不再说撞了别人；无雇主日期行的 ghost_reason 标「至少」；search_jobs 说明写清 `ic` 含哪些级别、不知道级别先问。**给领导的 PowerShell 命令不许重写 `.env`**（`Set-Content` 在 5.1 按 GBK 存，10-29 把 `.env` 弄成 python-dotenv 读不了，已转回 UTF-8）。1009 tests。
- **v0.8.32（2026-10-29，云端会话，`reports/102`）：** 连接向导两处（本机验收发现）：页脚 PRIVACY.md 改绝对链接（托管端点无 docs 目录，原 404）；剪贴板被拒时复制按钮给提示。同日种子表：ClickHouse、Wayve、Amplitude、Carbon Robotics 从 Greenhouse 搬到 Ashby（本机核实，公司 id 不变，下周快照自动下架旧行）。本机 10-28 精抽约 ¥18、快照已上传；EarlyTip 栏目核对逐段一致。995 tests。
- **v0.8.31（2026-10-28，云端会话，`reports/101`）：** **在架口径变严（领导批）：没下架且雇主系统 30 天内返回过才算在架**，30 天从索引里最新一次核验往回算（不按日历，旧索引不会被清空）。`service.verified_cutoff` / `live_clause` 一处定义：搜索、盯岗、`get_company_info`（新增 `unverified_over_30d`）、`live_employer_count`、`ohp numbers`（新增 `postings_unverified_over_30d`）都用它；全部过期的雇主空结果 `status: not_verified_recently`。抓取器照旧不动抓不到的板的行。10-26 快照新口径：172 家、20,019 条、过期 177（ClickHouse），Wayve / Amplitude 239 条 11-02 起超期。`numbers.json` 与 README 已改。994 tests。
- **v0.8.30（2026-10-28，云端会话，`reports/100`）：** 098 方案领导批「全部都做」，当天落地。① **`seniority`**（`pipeline/extract.seniority_from_title`，标题免费规则，读取时算，不改快照）：intern / junior / senior / staff / lead / manager / director / unknown，别名 `ic` 与 `management`；`search_jobs(seniority=…)`、`watch_intent` 的 `seniority`、`ohp search/watch --seniority`；产品 / 项目 / 客户经理这类不带人的先去掉再判，中文「经理」单独不算信号，没写级别就 unknown；**硬过滤，排序函数不动**；60 个真实标题的表格测试。② 每条岗位带 **`date_source`、`dates_in_words`（中英各一句）、`check_before_apply`**（code + 中英，只从量到的事实生成）；`read_board` 结果也带。③ **`index_status`**：下载中四个读数据的工具返回 preparing（`check_watches` 不动标记），失败 unavailable；空结果带 `status` + 固定 `headline`（`service.EMPTY_HEADLINES` 五种）；`_do_bootstrap` 改 `preserve_user_state=True`（下载期间登记的盯岗不丢）。④ `watch_intent` 返回 `matching_now` + `what_happens_next`，`check_watches` 带 `summary`（首次是基线）。⑤ 服务器指令与提示词：开搜前问 IC / 管理与年限，第一轮 5 条六栏，日期用 dates_in_words 原句，首次拉取不说成新岗。⑥ **连接向导** `docs/connect.html` = 托管 `/connect`（测试钉住一字不差；两段 prompt 与 README 一字不差；两个首页和求职清单第 1 步都链过去）；README 加 VS Code（Copilot）`.vscode/mcp.json` 与一键链接；**网页搜索入口不做，等 12 月律师意见**。`tests/test_prompts.py` 的 `NOT_TOOLS` 白名单收结果字段名。988 tests。
- **v0.8.29（2026-10-28，云端会话，`reports/098`）：** **首发盯岗缺陷**（用户赵杭铨 10-28 六条反馈里的一条）：首次启动先 init_db 再由后台线程整文件换成公开快照，快照只有 companies / jobs，于是第一个会话里 `watch_intent` / `authorize_application` 报 `no such table: watches`，重启才好；**托管端点每次冷启动都重下快照，所以它上面的盯岗从来没成功过**，而体检只查 initialize / tools/list。修：`_do_bootstrap` 装完快照立刻 `init_db()`；`tests/test_first_run_watch.py`（撤掉修复即红）；`scripts/hosted_mcp_check.py` 加 watch_intent / check_watches 往返（部署与每日体检都跑）。其余五条的方案在 098（字段翻译成人话、seniority 过滤、index_status、盯岗说明、五条六栏清单，进 0.8.30 待领导点头；**网页搜索入口建议不做、等 12 月律师意见，先做连接向导页**）。回信稿私库 `reply-to-zhao-hangquan-2026-10-28.md`。893 tests。
- **v0.8.28（2026-10-27，云端会话，`reports/095`）：** **「查公司」订阅文件**（领导：EarlyTip 上的查公司要像「顶会归档」一样单独开栏目、跟我们实时同步、不用另行通知）。`docs/check-company.json`（schema 1，`src/openhire/check_company_feed.py` 从页面按白名单重新生成 `html`，带 `sha256`）同时发在 github.io、托管端点 `/check-company.json`、CNB 镜像；EarlyTip 定时拉、sha256 变了才换、拉不到留旧份（任务书私库 `earlytip-check-company-column-brief-2026-10-27.md`，领导转达）。**改查公司页：改 docs 与包里两份 → 跑 `scripts/build_check_company_feed.py` → 测试绿 → 推 main**，忘了跑脚本测试就红；查公司页的官方网址必须都在求职清单里（清单改网址、查公司页不跟着改也红）。换订阅地址或格式要升 schema、提前告知 EarlyTip、旧的留 30 天。892 tests。**10-28 EarlyTip 栏目上线** https://earlytip.com/check-company.html （每 6 小时拉，**10-29 起顺序 onrender → CNB → github.io**；页脚「点评由 AI 生成」那句只在这页去掉；EarlyTip 说上线后不再另行通知，有问题走反馈入口，此事关闭；`reports/099`、`103`）。EarlyTip 另有两道关（可见文字含 求职 / 招聘 / 岗位 / mcp / 安装 / OpenHire 任一即拒；新内容短于上一份一半即拒），已照抄进 `check_company_feed.earlytip_gate`、测试与生成脚本：**改查公司页先想这两道关**，缩到一半以下要先经领导告知 EarlyTip、再带 `--allow-shrink` 生成，词关永远不放行。
- **v0.8.27（2026-10-22，云端会话，`reports/092`）：** **DeepSeek 全价时段代码锁**（领导：「这个要锁定以后必须是闲时跑，价格相差一倍的，请替我省点」）。起因：本机 10-22 上午北京时间 11:11 到 11:24 跑岗位族精抽（8,195 条、¥12.50），技能精抽 11:24 起也在全价时段，规则 9 写了但只靠会话记得。`pipeline/pricing.py`：工作日北京时间 08:30 到 12:30、13:30 到 18:30 拒绝（DeepSeek 全价时段前后各加 30 分钟，本机时钟偏慢；节假日按工作日算，宁可等）；`DeepSeekExtractor._call` 发请求前查，所以每一次 DeepSeek 调用都被锁住，`extract()` 退回免费启发式并如实盖 heuristic 章，GLM 不受影响；两条付费精抽每批之前查，全价时段一条不跑、跨进全价时段在批次边界停、进度已存；`extract-rebuild` / `extract-role-family` / `extract-sample` / `bootstrap --deepseek` 报 `ERR_DEEPSEEK_FULL_PRICE`、说几点再来、退出码 1。**没有开关**（测试钉住 pricing.py 不读环境变量、`_call` 先查再发）；DeepSeek 改时段就改常量发版。conftest 把测试时钟钉在周六。882 tests。部署工作流同日修一处：「有更新版本就让位」原来把 PyPI 缓存里的旧版本也当成更新、没部署就退出（0.8.27 首次部署 run 39740258981 因此红），改为只有严格更新才让位（`sort -V`），重跑 run 39740682988 全绿。
- **v0.8.26（2026-10-22，云端会话，`reports/091`）：** 本机 10-22 上午补跑暴露的问题。① **抓取并发锁跨事件循环**：Moka、北森、理想三个适配器的模块级 `asyncio.Semaphore` 会绑定第一次排队时的事件循环，`ohp ingest --seed`（校验与抓取各一个 `asyncio.run()`）抓香港 15 家时崩溃；`ats/base.py` 新增 `PerLoopSemaphore`（每个循环一把锁），三家改用，`tests/test_per_loop_semaphore.py` 6 条（含用旧写法复现原错误、全包禁止模块级 asyncio 锁、三家 Moka 两次抓取端到端）。**规矩：模块里不许再有模块级 asyncio 锁，测试会红。** ② Windows 上 `test_bootstrap_reopens_the_index_after_installing` 标为非 Windows 才跑（那是 POSIX 才有的读旧文件情形，Windows 替换开着的文件直接报错）。③ 门户目录：禾赛浏览器核过（飞书，160 岗，有 JD 无日期）；**地平线是大易 wecruit（hotjob.cn），不是 Wintalent**，281 岗、无日期，接口未评估前不读。④ **CNB 镜像实测可匿名下载、与 GitHub 原件同字节**，README 加直链与 `OPENHIRE_SNAPSHOT_URL` 用法（原「等 CNB 跑通再写」那条了结）。⑤ `hosted/Dockerfile` 安装重试 15 分钟；`scripts/backup_drafts.py` 调 git 时去掉 `GITHUB_TOKEN` / `GH_TOKEN`（本机环境里那个只读公开仓库的 token 是外联系统 `profiler/github_http.py` 读的，压过 gh 登录态让私库同步失败）。853 tests。**报告编号：** 090 是本机写的（10-22 上午补跑），云端这次用 091。
- **v0.8.25（2026-10-21，云端会话，`reports/089`）：** **求职清单中英双语**（领导：「不是一行中文一行英文那种，是用户可以选择页面语言那种」）：同一个 `docs/checklist.html` 里中文整块在前、英文整块在后，右上角「中文 / English」切换；默认按 `?lang=` → 上次选择（localStorage）→ 浏览器语言；无 JS 两块都显示。Chromium 实测六种组合全对。**改清单要中英两块一起改**，测试钉住两块都在、中文在前。页脚反馈链接改成议题模板 `checklist_feedback.yml`（标签 `checklist`，不收个人信息）；新增月度工作流 `check-links.yml`（`scripts/check_page_links.py` 打开两页所有外链，404 / 410 才红，超时只报不红：12333.gov.cn 与 labour.gov.hk 对数据中心地址拒答）。**用户反馈闭环**：邮箱日检定时任务的提示词加一条，`checklist` 标签议题与本机知乎日检上报的清单意见一律当天改页、记更新记录、发版。宣传稿（知乎专文 + 投稿 + X 英文帖 + 领英）在私库，本机待办第 16 条。847 tests。
- **v0.8.24（2026-10-21，云端会话）：** 领导要求求职清单页也带雇主认领那句（与托管首页、github.io 首页一致），`tests/test_hosted.py` 钉住。
- **v0.8.23（2026-10-21，云端会话）：** 领导发现两个首页不一样（github.io 项目主页有雇主认领那句，Render 说明页没有）。托管首页补齐：求职清单、查公司、门户目录（新路由 `/portals`，由登记表渲染，测试钉住与 `docs/portals.html` 相同）、雇主页、隐私、源码与 CNB 镜像的链接，页脚同一句雇主认领。**规矩：两个首页列的页面和页脚那句要一致**，`tests/test_hosted.py` 钉住。847 tests。
- **v0.8.22（2026-10-21，云端会话，`reports/088`）：** **「查公司」独立页** https://openhire-vlny.onrender.com/check-company （`docs/check-company.html` 与 `src/openhire/pages/check-company.html` 一字不差）。起因：领导想在 earlytip.com（**个人备案**，登记在领导名下）加入口指向求职清单，EarlyTip 项目经理会话复核后要求目标页只含「核公司去哪些官方网站」和「识别骗局」，**不出现求职流程、岗位、安装引导、/mcp、产品名，不出现「求职」「招聘」「岗位」字样，标题「查公司」，页脚只留反馈链接，永远免费无注册**；退出条件：收费、页面出现岗位或安装引导、域名不可达超过一周，任一发生入口当天撤。**这些条件钉在 `tests/test_hosted.py`，改坏了发不出去；要变先告知 EarlyTip 线。** `?from=earlytip` 接受不记录（主机无访问日志）。EarlyTip 另提的「OpenHire 面向国内是否落入网络招聘服务」进 12 月律师清单。0.8.20 是误发的空版本（脚本中途失败、只 bump 了版本号），0.8.21 是求职清单加「值得收藏的原因」与更新记录。847 tests。
- **v0.8.19（2026-10-21，云端会话）：** 领导问「中国用户能打开求职清单吗」（github.io 国内不稳），当场加：托管端点多一个 `/checklist`（`src/openhire/pages/checklist.html` 随包发布，测试钉住与 `docs/checklist.html` 一字不差，改一处要同步另一处），国内地址 https://openhire-vlny.onrender.com/checklist 写进页面顶部、README、`check_employer.checklist_url_cn`、提示词、服务器指令。部署工作流改成两轮「请求部署 + 等 15 分钟」（0.8.18 第一轮 Render 接受了却停在旧版 20 分钟，CDN 还没拿到新包）。
- **v0.8.18（2026-10-21，云端会话，`reports/087`）：** 领导第二批裁定。① **求职清单** `docs/checklist.html`（七步，每步写明「OpenHire 做」还是「你自己做、去哪里」，官方网址给全，含反诈骗三步；天眼查只指它自己的免费服务，代查不做）；第六个提示词 `job_checklist`；`check_employer` 带 `checklist_url`；服务器指令让助手对新手主动给这页。② **`authorize_application` 幂等**：同指纹同岗位第二次返回第一条回执（`already_authorized`），不写新记录，`idempotentHint` 真；9 月三件旧议题全关。③ **带货 prompt 一律用「装机加提问」合并版**（本机任务书 `cloud-brief-2026-10-21-merged-prompt.md`，领导定）：README 中英、docs、私库 `install-copy-blocks.md` 定稿、两篇知乎稿、周表定时任务模板；旧稿「重启你自己」是错的。④ 所有描述（pyproject、server.json ≤100 字符、四份插件清单、README、docs 首页）加 HR 岗位族、国内镜像（文案句：国内网络不用代理，GitHub 打不开也能拿到索引，同一份数据）、求职清单；托管地址各处统一为 `https://openhire-vlny.onrender.com/mcp`（README、PRIVACY、hosted.py 默认值、部署工作流默认值原来都写预定地址）。GitHub 仓库描述那一行要本机 `gh repo edit`（本机待办 13）。845 tests。
- **v0.8.17（2026-10-21，云端会话，`reports/086`）：** 领导 10-21 一批裁定的落地。① **`hr` 岗位族**（吸引 HR 留意）：分类表、DeepSeek 提示词、免费标题规则（`extract.is_hr_title`，10-19 快照实测 414 / 18,158 在架，「机器人事业部」里的人事、校招标题里的「招聘」都不算）；`ohp reclassify-hr` 免费幂等，每周快照工作流跑；`role_family` 认 recruiting / people / 招聘 等别名；未分类行按标题规则判（43% 在架行还没分类，否则 hr 筛选会混进工程师）；标题搜「人事」不再命中机器人事业部；两个付费抽取默认跳过已下架（`--include-delisted` 才算）。② **国内镜像**：`.cnb.yml` 第二条流水线把快照搬到 CNB Release `snapshot`（只用 CNB 自带令牌，GitHub 零密钥；ETag 没变就不下载；匿名复核），`tests/cnb_mirror` 在本地 mock 上 16 项全过，**CNB 上的第一次真跑排在本机待办第 6 条**；客户端默认地址失败自动换镜像（`config.SNAPSHOT_MIRRORS`），用户自设地址不换；README 加 PyPI 镜像和代码镜像，**镜像下载直链等 CNB 跑通再写进 README**。③ **香港 15 家进种子表**（176 家候选）：AIFT、UiPath、Lynx Analytics；Atoms（板名 ATOMS Careers page）、科大讯飞；壁仞、黑芝麻、天数智芯、昆仑芯、思谋、埃斯顿、第四范式；Outsight、Eka、General Robotics；香港地点认 HKG 和区名（简体九龙、沙田、大埔不算：重庆、东莞、梅州也有）；门户目录加禾赛（飞书）、地平线（Wintalent，未评估），浏览器核实排在本机待办第 7 条。④ 天眼查客户端按天眼查自己的 CLI 修三处：300000 是查无（not_verified / no_record），余额不足是 300006，日期按北京时间读（以前早一天）。**天眼查「代查」没做**：天眼查用户协议禁止把数据提供给第三方、要求数据只在境内（香港可以）存储使用、不支持境外 IP、禁止经云服务商网络访问，Render 在美国，四条都撞；要做得先拿天眼查书面许可并换香港主机，等领导定（`reports/086` 第四节）。840 tests。
- **v0.8.16（2026-10-21，云端会话，`reports/086`）：** **托管端点能用了：https://openhire-vlny.onrender.com/mcp**（Render 免费档，`HOSTED_URL` 变量已设）。0.8.15 的 `/mcp` 一律 421：FastMCP 在构造时按默认 127.0.0.1 开了只认 localhost 的 Host 校验，绑 0.0.0.0 后没重算；`configure_http()` 按实际绑定地址重算（本机回环照旧防 DNS rebinding）。首次下载快照后 `/healthz` 一直报空库：下载期间有读者占着旧连接，装完再 `dispose_engine()` 一次。部署工作流加 `scripts/hosted_mcp_check.py`（发版后与每日都向 `/mcp` 发 initialize 和 tools/list）；**调 Render 部署钩子必须带 `ref=<提交号>`**（不带时 Render 部署它上次拉到的旧提交，0.8.16、0.8.17 首次部署都停在旧版 20 分钟；带了之后不认识的提交回 404，工作流每 30 秒重试），0.8.17 运行 39531602040 一分钟上线。证据：run 39528918270，`/healthz` 报 0.8.16、155 家、32,360 条，`/mcp` 答 initialize 与 tools/list（11 个工具）。**服务器是 11 个工具、5 个提示词**（本机会话 10-20 核出，CLAUDE.md 原写 12 是错的）。Render 免费档没有持久磁盘，每次休眠唤醒都重下快照，约 10 秒。
- **v0.8.15（2026-10-20，云端会话，`reports/084`）：** 领导 10-20 确认**红线继续坚守**，并要求 083 的四点落地。① **六家新雇主进种子表**（本机从官网核实、云端现读）：Moka 的星尘 astribot/144861、魔视 motovis/38410、嬴彻 inceptio-ai/150619、DeepSeek high-flyer/140576（租户名是幻方），北森的魔法原子 magiclab、摩尔线程 mthreads；**云端能直接连 Moka 和北森**（`ohp read-board` 现读成功），不必等本机。读板认 Moka 新网址 `/social-recruitment/`、`/campus-recruitment/`；Moka 校招门户（智源）我们的读法打不开，待研究。新增只读工作流 `probe-boards.yml`（workflow_dispatch，云端触发、看日志）。
  ② **门户目录 27 家**：加非夕、百川（飞书）、灵初（只链 BOSS）、因时、灵心巧手、光轮（官网文字）、无问芯穹（空壳）、珞石（**钉钉招聘，新系统，评估前不读**）、智源（Moka 校招）；公开页加一句可复制给有浏览器的助手的话。③ **每周本周新发**：`new_postings_window.py --list`，第一期（10-19 快照）国内 14、海外 35，稿在私库 `weekly/`；定时任务「具身本周新发周表」每周一 14:51 UTC 自动出表写稿。numbers.json 按 10-19 快照：152 家、18,158 条。785 tests。
  **「本机待办」直连本机（领导 10-20：最好不经他复制粘贴）：** 私库 `local-inbox.md`，云端写日常活，本机每晚定时任务先做它再做知乎和 GitHub 日检；要领导在场的活不进队列。**备忘录** 私库 `memo-for-howard.md`（飞书 HR 授权、飞书合作两件领导的事），定时任务「领导备忘录周四提醒」每周四 08:50 香港时间。Render 注册领导授权由本机做：Gmail 邮箱、名字 OpenHire、到密码框停下等领导（任务书 `local-session-prompt-2026-10-20.md`）。EarlyTip 10-16 审核本机已跑：原 83 个 id 全在、现 122 条、问题 0。
- **v0.8.14（2026-10-19，云端会话，`reports/082`）：** 回答领导 10-15 三问。① **不用背咒语**：`add_employer` 早已封装，0.8.14 的服务器指令让助手主动提「加进索引并盯住」和门户链接；**五个内置 MCP 提示词**（`src/openhire/prompts.py`：job_radar、track_employer、vet_employer、radar_check、new_this_week，参数有中文出中文版，老 SDK 不支持 title 时照样注册）；README Quickstart 加「What to say to it」可粘贴句子，带货稿从这里取。
  ② **门户目录**：`list_portals` 工具（第 11 个工具，验收测试钉住；10-21 前这里误写成第 12 个）、`ohp portals`、公开页 `docs/portals.html`（由 `seed/not_indexed.py` 生成，测试保证一致；登记表加 sector、last_checked、不登录能看到什么）。星动纪元在索引里（Moka）又有飞书门户：单列 `SECOND_PORTALS`，`get_company_info` 带 `also_posts_on`。**岗位级飞书链接不做**（要执行签名脚本批量读列表，越 2026-09 的访问控制线）。
  ③ Workday 翻页修（第二页起 `total` 报 0，旧代码停在 40）；快照换文件 Windows 重试 + 报占用者 + 失败放回旧库，测试连接全关；`org-events-audit --fresh` 留旧副本作基线，`--baseline / --expect-at-least / --must-include` 按 event_id 比对。781 tests（3.13、3.11）。
  **收录：** mcp.so 10-16 收录（#3845、#4473），Awesome-MCP-ZH #602 10-15 合并。**知乎承诺兑现：** `scripts/new_postings_window.py` 出「近 30 天新发」表（082 第三节），本机贴。Xbotics 许可 issue 交本机发。
- **v0.8.13（2026-10-15 夜，云端会话，`reports/081`）：** **盲区扫除第一步**（领导：「我要全垒打」）。① **`add_employer(url)` / `ohp add-employer`**：任何适配器读得了的板贴网址就进**本机**索引并当场抓一次，之后 search / watch / refresh / ghost_score 全有；`companies.user_added` 标记（模型、schema.sql、migrate 都加了列），**永不进公开快照**（`build_snapshot` 跳过、`install` 拒收），每周刷新时 `carry_over_user_state` 连 companies / jobs 一起搬；`remove_employer` 移除；`read_board` 结果带 `add_to_my_index` 和预填 issue 链接 `suggest_for_public_index`。
  ② **Workday 适配器**（`ats/workday.py`，租户键 `<account>.<wdN>/<site>`，列表 POST `/wday/cxs/.../jobs` 每页 20 条 + 详情 `startDate` 为发布日，先 GET 页面拿 cookie，CSRF 头可选）；`myworkdayjobs.com` 从封闭门户清单删掉；**云端连不上，按已知形状写，本机实测通过前不进种子表**（队列里排了 NVIDIA / 宏利 / Intel 三条 read-board）。③ Windows `file://` 路径修（`url2pathname`）。743 tests。
  **飞书系怎么绕（待领导定）：** 社区清单（Xbotics 471 条公众号链接，要先问许可；Lumina CC BY-NC）当发现层、公众号文章当一手源；`read_board --browser` 本机浏览器渲染读公开页（不登录、守 robots、被拦即停）要领导裁定是否触碰 2026-09 的 CLOSED 判定。
- **v0.8.12（2026-10-15 夜，云端会话，`reports/079` 第八节）：** **托管端点改走 Render 免费档。** Hugging Face 2026 年起个人免费账号只能建静态 Space，Docker / Gradio 要 PRO（本机会话触发部署时 `402 Payment Required`，run 38672012354；领导的 HF 账号与 `HF_TOKEN` 已建，留着备用）。
  `render.yaml` Blueprint（free、oregon、`hosted/Dockerfile`、autoDeploy 关、健康检查 `/livez`）；`hosted.py` 认 `RENDER_EXTERNAL_URL`、加 `/livez`；`deploy-hosted.yml` 按 secret 选主机（`RENDER_DEPLOY_HOOK` 走 Render，`HF_TOKEN` 走 HF），地址用仓库变量 `HOSTED_URL`（默认 `https://openhire.onrender.com`），每日体检 03:17 UTC 和每 10 分钟 keep-alive（免费实例 15 分钟没流量会睡）都只在 `HOSTED_URL` 设了才跑。
  本机会话负责：Render 用领导 GitHub 登录 → Blueprint 建服务 → `gh variable set HOSTED_URL` + 剪贴板 `gh secret set RENDER_DEPLOY_HOOK` → 手动跑工作流 → `/healthz` 报 0.8.12 → 改知乎 ChatGPT 句。Render 若要卡做 1 美元验证，停下报告领导。715 tests。
- **v0.8.11（2026-10-15，云端会话，`reports/079`）：** **托管端点**，给 ChatGPT 这类只收网址的客户端（领导裁定「那我们就挂吧，你来操作」）。`src/openhire/hosted.py`，`OPENHIRE_HOSTED=1` 时随 `ohp serve --transport streamable-http` 启动：首页 `/` 与 `/healthz`、instructions 加托管披露句、每地址 300 / 全站 3,000 每分钟限流、无状态 HTTP、不记访问日志、**快照刷新线程**（每 6 小时 HEAD 公开快照，变了就下载到 `openhire.db.staged` 并 SIGTERM 自己，`hosted/entrypoint.sh` 循环拉起，`serve()` 启动时先换文件再开库）。
  **换快照不丢 watches / applications**（`snapshot.stage_snapshot / activate_staged / carry_over_user_state`，`ohp bootstrap --force` 也保留了，0.8.4 路线图项关闭）。**SSRF 防线**：`verify/checks._get` 取用户给的域名 / 页面前先解析地址，私网、回环、链路本地、云元数据、`localhost` / `.internal`、非 80 / 443 端口一律不发，重定向手动跟最多 5 跳逐跳检查。
  部署目标 **Hugging Face Space（Docker，免费）**：`hosted/Dockerfile`（装 PyPI 的 `openhire==X`，**版本号第十二处 sed**）、`hosted/README.md`（Space front matter）、`.github/workflows/deploy-hosted.yml`（Release 成功后推 `hosted/` 到 Space、等 PyPI 有版本、等 `/healthz` 报版本；每天 03:17 UTC 健康检查）。**仓库 secret `HF_TOKEN` 由领导自己放**（HF 账号 → Write token → GitHub Settings → Secrets → Actions），没有 secret 部署步骤只打 notice。
  预定地址 `https://gzchenhao-openhire.hf.space/mcp`（README、PRIVACY §3、首页、instructions 四处口径一致：主机只见工具参数、不记查询、盯岗记录按指纹存在它的索引里、本机安装仍是推荐）。**云端连不上 huggingface.co，没有真机实测**，等 token 放好后由工作流验证；上线后改知乎文章那句 ChatGPT 括号。714 tests。
- **知乎文章稿（2026-10-14 夜，不发版，`reports/078`）：** 具身雇主 JD 信号扫描 `scripts/jd_signal_scan.py`（37 家、1,864 条在架、快照 10-13）：论文提及 6%（研究岗 25%；国内研究岗 76% 写成优先，海外 22%）、名校 1%、研究岗写年限 44% 对其他岗 69%、按年份看论文提及率持平。文章 10-14 13:58 UTC 已由本机发出：https://zhuanlan.zhihu.com/p/2093821857900257514 （基线阅读 1，stars 10；稿在私库 `zhihu-embodied-jd-signals-2026-10-14.md`，**10-15 按领导三条意见修订：带货段给可复制的 prompt、点名 ChatGPT、发完投稿到相关问题，见文案规矩第 7 条**）。**本机时钟比知乎服务端慢十几分钟**，本机记时间以服务端为准。**文案里的分析数字一律出自带日期的测量报告（078 这类）加 `numbers.json`，脚本进仓库让人重跑。**
- **v0.8.10（2026-10-14，云端会话，`reports/077` 第九节）：** EarlyTip 首版的读者侧审计本机跑完：**83 / 83，problem_count 0**（18 键、id 与 key 重算、黑窗、D10、撤回、待核实标记全过）；`event_date` 10 条、`amount` 46 条、`related` 20 条；不放链接域名命中 8 条。匹配实测高通（对外M&A，另一方 PickNik Robotics）、Boston Dynamics（高管流动，另一方 亚马逊）都命中，理想汽车 no_record。
  提给生产侧两条（经领导转达）：**D18** `Tesla` 与 `特斯拉` 两个规范名按 D4 合并；**D19** `庞伯特Pongbot` 中英粘连，改 `庞伯特` + 别名。读者侧同日修：导出里的公司 / 别名 / 另一方名按中英半边各算一次键（`events_for`），「庞伯特」「Pongbot」都能命中。本机队列已清空。
- **v0.8.9（2026-10-14，云端会话，`reports/077` 第八节）：** 领导两条裁定落地。① 律师过目域名清单 **12 月再议**（**12 月清单再加一问：OpenHire 面向国内用户是否落入《网络招聘服务管理规定》的网络招聘服务，EarlyTip 线 10-21 提出，`reports/088`**）（六个域名不放链接、其余普通链接的处理已够）。② **`org_events` 每条加 `amount`**（EarlyTip 从自家标题 / 推荐理由原样抄录、过了 D3 的金额，取不到 null），note 里融资类带「（数亿元）」，出处句改成「只转事件类型、日期、金额、来源域名和链接，不转标题」。十二处版本号到 0.8.9。
- **v0.8.8（2026-10-14，云端会话，`reports/077`）：** **EarlyTip 事件导出接入 `check_employer`**（新项 `org_events`）。EarlyTip 首版导出 10-14 上线（`earlytip.com/data/org_events.json`，schema 1，83 条回填，日常追加未启用），OpenHire 只做消费侧：
  整份公开文件一天一读到 `OPENHIRE_HOME/earlytip/`、本机比对，服务器看不到查谁；`company_key` 按规格二.1 复刻（`verify/org_events.py`）；只给类型 / 日期 / 域名 / 普通链接，**不转标题、推荐理由、金额**；
  六个域名不放链接（cs.com.cn、bloomberg.com、reuters.com、sina.com.cn、chinastarmarket.cn、cls.cn，含子域，比生产侧通知的三个多三个，是 OpenHire 自己的规矩）；撤回过滤、`company` 空跳过、`unverified` 透传；无记录 = `unavailable` + `no_record`。
  维护者审计 `ohp org-events-audit`（`--file` / `--fresh` / `--json`）从读者侧核规格，本机任务队列 `ALLOWED` 加了它。**云端连不上 earlytip.com（403）**，首版真实审计排在本机队列，结果回来再出 D 条目；提前于 10-12 预案的「满 90 天」接入，律师过目改为接入后补做（待领导定）。670 tests。
  **发版自检：PyPI、Release（run 38511414445）、mcpb 都好；Registry 工作流第三次误报，这次查到了真因**：列表接口每页 30 条、最旧在前，0.8.8 是第 31 个版本，第一页 0.1.1 到 0.8.7 里没有任何 isLatest，旧核对把它判「失败」，重跑又被 Registry 以 `duplicate version` 拒绝（即已发布）。核对改成 `scripts/registry_state.py`（`limit=100` 并跟 `metadata.nextCursor` 翻页；退出码 0 已标 latest / 2 在库里没翻标 / 1 不在 / 3 读不到）：在库里就算发布成功，没翻标或整段时间读不到只告警，只有「答了且不在」才红；「已发布？」一步按同一脚本判，Publish 一步把 `duplicate version` 当已发布，重跑不会再红。另外 `/v0/servers?search=` 这个接口 10-14 对 runner 常常 20 秒超时（validate 与 publish 秒回），脚本 curl 优先、urllib 兜底。不发版。
- **v0.8.7（2026-10-12，云端会话，`reports/076`）：** 两家系统首批六家雇主入种子表（Workable：Robotec.ai、Flexion Robotics、Andromeda Robotics、Agile Robots；SmartRecruiters：AeroVect、PAL Robotics），每家 10-12 本机真实读通后才进；Workable 接口把岗位按城市重复给出（同 shortcode 两条），解析层按 shortcode 合并、城市用分号连起，一岗一主键；索引来源说明三处加上两家。博世不入库（4,947 条多为客服技工）。656 tests。**快照重跑后 `ohp numbers` 重生成（10-13 02:54 UTC）：employers_with_live_postings 154、live_postings 18,145，README 四处 143 已改 154。** 10-12 的定时快照实际 15:13 UTC 才起跑（GitHub cron 常延迟数小时），没带上这六家；10-13 01:46 UTC 用 GitHub MCP 的 `actions_run_trigger` 手动触发了 `refresh-snapshot.yml`（**云端会话能触发 workflow_dispatch**，「触发不了工作流」只指 REST 建 tag 的 403）。
- **v0.8.6（2026-10-12，云端会话，`reports/075`）：** **Workable 与 SmartRecruiters 适配器**（073 做市商结论的落地：一个供应商写一次，长尾雇主边际成本为零）。Workable 走 Widget API（`apply.workable.com/api/v1/widget/accounts/<sub>?details=true`，`published_on` 裸日期存 UTC 零点）；
  SmartRecruiters 分页列表 + 每条详情（6 并发，单条失败不影响整批）。两家接进 `read_board` / 板 watch / `ohp seed`；`ATS_APPLY_HOSTS` 加 `apply.workable.com`、`jobs.smartrecruiters.com`。
  **云端连不上两家、文档站也打不开，适配器按文档写、18 条测试钉住；10-12 夜本机实测两家都通**（Robotec.ai 6 条，发布日 ats_reported；博世 4,947 条、德国 738 条，详情合并成功，`reports/075` 第五节）；索引来源说明没改，种子表还没有这两家的雇主。654 tests。
  本机任务脚本修了一处编码缺陷（main `60055b5`，不发版）：本机 `ohp --json` 在 PowerShell 管道里按 GBK 输出，脚本按 UTF-8 读，6/8 任务记成「退出码 0 无输出」；现强制子进程 UTF-8、解不出的字节替换不报错。
- **v0.8.5（2026-10-12，云端会话，`reports/072`）：** 领导四条指示的落地。① **装机文案点名五个助手**（README 主句与 Works with、`docs/employers.html`）：Claude、豆包、DeepSeek、Cursor、腾讯 WorkBuddy；
  豆包走本机 `ohp serve --transport streamable-http --port 8000` + 自定义连接器 `http://127.0.0.1:8000/mcp`（领导 10-12 在豆包工作里实测通过）；DeepSeek 经 Cherry Studio / Chatbox 这类客户端。文案规矩第 7 条。
  ② **「深科技」不再用**，一律英文 deep tech（CLAUDE.md 人设条、私库 15 份稿件已改；公开 reports 历史不动）。③ **封闭门户给浏览器提示**：`boards.py` 的 `BROWSER_HINT` 接在飞书 / Lark / Workday / SuccessFactors / Taleo / iCIMS 的拒绝理由后，
  `known_not_indexed_hint` 对有门户地址的雇主加一句「有浏览器工具的助手可以自己打开读，OpenHire 不入库、不标日期、不盯」；招聘网站（LinkedIn / JobsDB / BOSS）不加。回答领导「WorkBuddy 能读飞书而我们不能会不会尴尬」：
  谁都读不了飞书的列表接口（要签名；WorkBuddy 也没有雇主授权），能读的只是浏览器里渲染出来的那一页，和人一样；OpenHire 的价值在索引、日期、在架天数和盯岗，不在替人看一页。
  ④ **Registry 工作流核对步骤加重试**（6 次 × 10 秒）：0.8.2 与 0.8.3 都是发布成功后立刻核对、搜索索引还没更新而「失败」。⑤ **Gmail 托管**：见下方「每次开工要主动查的四个入口」第 2 条，Routine `OpenHire 邮箱日检`（trig_014FzhejmdLSWLn9mimarsMu）。636 tests。
- **v0.8.4（2026-10-11，云端会话，`reports/070`）：** ① `check_employer` 加 **`sanctions_screen`**：OFAC SDN 与综合名单（公开 CSV，无 key）下载到 `OPENHIRE_HOME/sanctions/` 每日一次，
  公司名**本机比对**（只剥法律形式后缀，不剥 group / holdings；双语名各试），命中报条目不报判决，拿不到名单报 `reason`；云端连不上 treasury.gov，要本机跑。
  ② **板也能盯**：`watch_intent` 收 `board_url`（只配 location / title），`check_watches` 现读板报 `new_matches` 与 `closed_since_last`，板不答复不标关闭；`read_board` 仍不入库（原因见 070 第二节）。
  **`ohp bootstrap` 整文件覆盖会清 watches / applications**，进路线图。③ **本机任务队列**：云端写私库 `local-tasks.json`（只收 `check-company` / `read-board`），
  本机 `.venv\Scripts\python.exe scripts\run_local_tasks.py --sync` 跑完回传 `drafts/local-results/`；两条命令新增 `--json`。634 tests。
- **v0.8.3（2026-10-11，云端会话，`reports/069`）：** 领导的真实求职场景要的雇主范围比索引三个行业大得多（求职者侧材料一律放私库 `openhire-private/job-search-*.md`，公开报告只留产品侧），于是加 **`read_board`**（CLI `ohp read-board <url>`）：
  贴招聘页 URL 现读雇主自己的板（Greenhouse / Lever / Ashby / Moka / 北森，任何行业，索引内外都行），板自己的日期与在架天数、雇主租户上的投递链接、`location` / `title` 过滤；
  **不入库**、无 skills / ghost_score / 重挂 / watch；封闭门户（飞书、Workday、SuccessFactors、Taleo、iCIMS、LinkedIn、JobsDB、BOSS）`ERR_UNSUPPORTED_BOARD` 加原因，不找别的路；
  每进程每板 15 分钟一次现读；板不答复不缓存、不说成雇主的问题。URL 解析在 `ats/boards.py`，网络调用在 `pipeline/crawler.fetch_board`（有事件循环时自动换工作线程），
  `service.py` 仍不许出现 httpx（`tests/test_three_nos.py`）。隐私说明 §3 加了对应一条。622 tests。
  **实测**：UiPath 3 条港岗、Airwallex 18、Lalamove 51、OKX 13、Animoca 3；猜错租户名的板如实报 404。下一步：按官网找板、公司註冊處开放接口（本机验证）、read_board 加 watch、Workable / SmartRecruiters。
- **v0.8.2（2026-10-11，云端会话，`reports/068`）：** 用 OpenHire 替领导找香港工作的实战修订：`check_employer(job_id=...)`（CLI `--job`，雇主与红线词筛查取自索引里那条岗位）；
  `unavailable` 项带 `reason`（`network` = 这次没连上来源，说明的是网络不是雇主；`no_record` / `http_status` = 来源答了）；`pending_user` 加香港与境外免费核验路径（公司註冊處 e-Services、
  警务处防騙視伏器、OpenCorporates）；红线词表补繁体写法与香港警方骗局特征。602 tests。推 main 即自动发版（PyPI 可信发布、tag、mcpb、Release、Registry），发完 `curl -s https://pypi.org/pypi/openhire/json` 核对。
  **云端容器出网白名单不含 rdap.org / web.archive.org / 雇主官网**，`check_employer` 的域名三项在云端一律 `reason: network`，要本机跑。求职者视角打分 76 / 100，路线图见 068 第二节第 4 条。
- **v0.8.1（2026-10-10，云端会话首次发版，`reports/067`）：** 只改说明和版本号：`check_employer` 工具说明加一句「助手已有天眼查工具或连接器（如腾讯 WorkBuddy 内置的）
  就直接用它补 `registry_record`，不要让用户去申请 key」，`tests/test_employer_check.py` 钉住。提交 `5bd4298` 在 main，全量 599 通过。
  **云端会话推不了 tag 也触发不了工作流**（git 代理只放行分支推送，REST API 建 tag 403，上报不绕）。0.8.1 由本机推 tag、手动跑 `release.yml` 发出：
  PyPI 可信发布首发成功（wheel + sdist）、mcpb 挂 Release、Registry 重跑成功。随后 `release.yml` **改为 main 上 `pyproject.toml` 版本号变了就自动发**：
  先跑全量测试，绿了才发 PyPI，再由 Actions 自己建 tag 和 Release；版本号没变的推送直接跳过。Registry 改为在 Release 成功后跑（`workflow_run`），已是最新则跳过。
  openpyxl 进了 dev extra（`uv lock` 已重生成），云端 `pip install -e ".[dev]"` 就是 599 全绿。
- **v0.8.0（2026-10-08，同日第三版，`reports/065`）：** 求职者一键企业背景查证 **`check_employer`**（CLI `ohp check-company`）。返回**查证清单**不是分数：
  每项五种状态（verified / not_verified / unavailable / not_applicable / pending_user）带来源与时间，结尾写明「不是判断」。免费项：索引里的在架数 / 中位在架天数 / 发布日来源 / 认领、
  或「已知未收录 + 原因」、或「已停止运营」；RDAP 域名注册日期；档案馆首次抓取；首页备案号；JD 红线词。付费项工商登记走天眼查 OpenAPI，**用求职者自己的 `TIANYANCHA_API_KEY`**（放在他机器上，我们看不到 key 也看不到他查谁），
  没 key 标 pending_user 并给三条路（设 key / 助手已有的天眼查 MCP / 爱企查与公示系统手动）。代码在 `src/openhire/verify/`（维护者脚本与求职者工具共用同一套检查）。
  **天眼查客户端没有真 key 实测**，领导有开放平台账号就给一个放 `.env`。**「token 批发中心」没做**：天眼查数据许可不许转售、代查会让我们服务端看到求职者查谁和付钱、收钱要营业主体；等领导定。
  隐私说明 §3 加了这个工具向谁发什么（公司名 / 域名，从不发用户信息）。
- **v0.7.0（2026-10-08，同日第二版，`reports/062`）：** **雇主自报岗位表**（`ats/self_reported.py`，来源 `employer_self_reported`）。
  领导要「傻瓜式」：HR 填一张六列 Excel（`docs/openhire-岗位表.xlsx`）用企业邮箱发来，我核实身份后 `scripts/import_employer_roster.py` 转成 `employers/<slug>.json` 并在
  `SELF_REPORTED_EMPLOYERS` 登记，适配器像读别家接口一样读它（raw.githubusercontent.com）。**四个条件写死在代码和测试里**：只收企业身份核实过的雇主；
  每行 `source=employer_self_reported` + `date_signal=self_reported`（雇主自己填的日期，不是系统时钟），`get_company_info` 带 `date_source`；
  发布日 / 续期日起 90 天自动下架，再发一次表才续；投递链接只信雇主自己域名的 https，否则送到我们核过的招聘页。排序、ghost_score、三条红线不动。
  这是我当天早些时候说「不做自建发岗」的**有条件撤回**：有身份核验、有标记、有到期、无 UI 无排序无收费，它就不是岗位库。
  雇主页 / 认领模板 / README 都把填表放第一条；**对外一律「贵公司」不写「贵司」**（领导 10-08 纠正，全仓库已改）。
  **身份核实阶梯（领导 10-08 问「怎么防缅北园区买域名冒充」，`reports/064`）：** 企业邮箱只是第一步。申请者自填「公司信息」页，`scripts/verify_employer.py` 自动核
  信用代码校验位 / 发件域名 / 首页 ICP 备案号 / RDAP 域名年龄（<180 天拒）/ 档案馆历史 / 公开电话在公司自己页面 / 足迹链接；人工只剩公示系统、工信部备案主办单位、回拨三件；
  `import_employer_roster.py` 对骗局特征词（境外高薪、包机票、不限经验、打字员、电销……）整行拒绝、投递邮箱必须在公司域名、`--verification` 必填；登记表 `verification` 字段非空才过测试。**一有举报先下架再问。**
  发版细节同 0.6.9：`pip install -e . --no-deps` 两次、mcpb `npx -y @anthropic-ai/mcpb pack`、PYTHONUTF8=1 twine。
- **v0.6.9（2026-10-08，`reports/060`、`reports/061`）：** 「已知未收录」登记表从 11 家到 19 家：穹彻智能、众擎（飞书）；云深处（只在 BOSS 直聘）、智平方、轻舟智航、鉴智、松延动力（官网无可读岗位列表：邮箱投递 / 飞书表单 / 纯 JS 壳 / robots 禁抓自家接口，我们遵守 robots）；
  **毫末智行「已停止运营」**（2025-11-29 停工通知，媒体报道；Moka 门户 2026-09-02 关停；haomo.ai 2026-10 跳无关站），**不给 opt-in**，提示句「告诉用户发生了什么，不要把人送去任何地方」。
  认领表单（中英）加「贵司的岗位目前发布在哪里」下拉和三条只读进入路径（飞书两个只读 scope / 官网机器可读页 / 换可公开读取的 ATS），README 同段。
  种子表加 5 家美国具身公司（Skild AI、Apptronik、Field AI、Dyna、Generalist，267 条），周一快照自动进库。`SECURITY.md` + GitHub 私密漏洞报告；根目录 `uv.lock`（第十二处版本，bump 后 `uv lock`）；`docs/numbers.json` 改由公开快照生成。
  **抽样结论（060）：** 28 家目标行业小团队零家带 JobPosting JSON-LD，**不做 JSON-LD 适配器**；国内小团队的缺口是结构性的（飞书 / BOSS / 自建页），只能雇主 opt-in。
  **发版流水账：** `pip install -e . --no-deps` 两次后 `test_version_matches_pyproject` 才绿（元数据）；mcpb 用 `npx -y @anthropic-ai/mcpb pack mcpb dist/openhire-X.mcpb`，解包核对 `dependencies = ["openhire==X"]`。
- **v0.6.8（2026-09-28，`reports/055`）：** 领导用 HR 人设（base 香港，智驾 / 具身的招聘岗）亲自跑了 Kimi 网页版和腾讯 WorkBuddy。
  修：**`title` 过滤**（岗位名里的词，任一命中；英文锚词首；HR 同义词组展开，因为分类表没有 HR 族、HR 岗归 ops）；
  **未知 `role_family` 拒绝**（`recruiting` 原来静默返回全库）；**香港 / Hong Kong / HK 同一地**，补一批只有一种写法的城市拼音；
  **快照下载续传 + 4 次重试**（Kimi 国内沙箱 20 MB 处超时，原来一次读超时整份作废、零重试）；
  服务器自己没拉到快照时工具结果带 `bootstrap_error` 和出路；**`ghost_score` 措辞指引进工具说明**（两个 agent 都把 1,616 天的岗叫「僵尸岗别投」）；
  README 加 WorkBuddy（`~/.workbuddy/mcp.json`，重启才加载）和「GitHub 不通」一段；PyPI / Registry / mcpb 描述不再带雇主数。
  **供给侧事实（不是缺陷）：** 索引里地点含香港的在架岗 8 条、无 HR 岗；但 WorkBuddy 说的「国内具身公司零 HR 岗」是翻页翻漏了（国内 HR 岗 16 条）。
  **待领导定：国内镜像**（魔搭要 token 进 Actions secret，打破零密钥；jsDelivr 切块不用密钥但国内可达性不稳；第三方 gh-proxy 不内置，镜像能篡改投递链接）。
  **twine 在 GBK 控制台打印「•」会崩**，上传前加 `PYTHONUTF8=1`。
- **v0.6.7（2026-09-24，`reports/054`）：** 用 `scripts/mcp_call.py`（进程内起当前版本）把三个求职人设 + 一个 HR 人设在 0.6.6 上重跑，
  十条修了九条半，又抓到 17 条当天修完：**排序新鲜度锚回发布日期**（0.6.3 锚在 updated_at 是错的，470 天被动过的岗压 3 天新岗）；
  感知别名扩到 detection / point cloud；城市别名（广州 ↔ 天河区等）；watch 可带 location；`truncated` 只在满页时为 true；
  蔚来进已知未收录表；**未声明参数（resume / cv / email …）直接拒绝**（FastMCP 默认静默丢）；claim 标题精确匹配写进 help。
  **测试防线：** conftest 里的 session 级守卫，`config.DATABASE_URL` 不是临时库就整个 session 失败。因为 9/23 夜里某次 agent 测试
  把本机索引 `~/.openhire/openhire.db` 写成了 1 行（已从快照副本恢复，坏文件留作 `openhire.db.wrecked-20260924`）。
  **规矩：agent 和 ad-hoc 脚本只准对临时库或备份副本跑；跑 agent 前先 `cp openhire.db openhire.db.bak-<日期>`。**
- **v0.6.6（2026-09-23，同日第五版，`reports/053`）：** 飞书雇主的合法路径。**理想汽车**第一方镜像适配器（vendor `lixiang`，
  `api-web.lixiang.com` 普通 GET，772 条社招含完整 JD，**无发布日期** → 行上带 `date_signal: not_reported_by_ats`，`get_company_info`
  报 `posting_dates_reported`）；**蔚来**适配器写好并测过但**停用**（`www.nio.cn` 的 EdgeOne 对我们的 httpx 回 567 安全策略拦截，
  按 020 视为访问控制，seed 行注释掉，等蔚来加白或授权）；**已知未收录雇主登记表** `seed/not_indexed.py`（Momenta、小马、智元等 10 家），
  搜索和 `get_company_info` 回门户 URL + 原因 + 雇主可授权的飞书只读 scope；三个新 Moka 租户（银河通用 / 月之暗面 / 阶跃星辰）。
  诚实修复：任何抽取器（启发式 / DeepSeek / GLM / Anthropic）**不许从光秃秃的标题里抽技能**；后续抓取拿不到 JD 时不覆盖已存的；
  没 JD 时 `remote_policy` 不读标题；投递 URL 只信 https 且只信租户自己的 host。525 tests。
  **飞书本身：官网只服务端渲染 `<title>`，列表接口要签名，无 feed / RSS / sitemap，判 CLOSED**；唯一完整路径是雇主在飞书开放平台
  授权 `hire:site_job_post:readonly`（模板在 `drafts/feishu-employer-optin-template.md`）。
- **v0.6.5（2026-09-23，同日第四版）：** 体验测试剩下的六个小项当天清零（领导：今日事今日毕）：`location` 过滤（中英文子串）；
  `limit<1` 报 `ERR_BAD_PAGE`（负 offset 仍夹到 0，那是 v0.5 的有意设计且有测试）；`watch_intent` 回 `existing_watches` 并在指纹已被占用时提醒换长的；
  示例指纹改成 12 位；`min_salary` / `currency` / `require_stated_salary` 的语义和「薪资基本只有美国岗才标」写进工具说明；401 tests。
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
  **2026-09-28 起再加四处插件清单**：`.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json`（plugins[0]）、`.cursor-plugin/plugin.json`、根目录 `plugin.json`（agent-plugins.org 标准）。
  **2026-10-08 起根目录 `.mcp.json` 和 `mcp.json` 也钉版本**（`uvx openhire==X serve`）：Anthropic 目录的检查把 `@latest` 判为阻塞项「Unpinned uvx launcher」。
  **2026-10-15 起 `hosted/Dockerfile` 也钉版本**（`pip install "openhire==X"`，托管端点装的就是它）。
  发版时一条 `sed 's/0\.6\.x/0\.6\.y/g'` 把这**十二个**文件一起换；**第十三处 `uv.lock` 不用 sed，bump 后跑 `uv lock` 重生成**（目录 Verified 徽章要 pyproject + uv.lock；单文件上限 256 KiB，现约 240 KB）；`tests/test_release.py` 全部钉死。插件图标 `.claude-plugin/icon.png`（512px，目录只在首次提交时采用）。
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
  **腾讯云开发者 MCP 广场（056，2026-09-28）：** 页面无入口、文档写「第三方暂不上架」，但真正的提交仓库是 **cnb.cool/codebuddy/mcp-market**（issue 模板，微信登录），
  有第三方提了被收的先例（DemoWay 70 天、有活 2026-06）。**已提：issue #21（2026-09-28）**，邮件同日从领导 Gmail 发到 `cloudcommunity@tencent.com`。
  材料在 `drafts/tencent-mcp-listing.md`。**10-12 前后**用广场搜索接口查一次 `openhire` 有没有出现；issue 下不追问（无人回复）。
  **CNB 镜像：https://cnb.cool/gzchenhao/openhire** （组织 `gzchenhao`，领导实名认证后建的；`openhire` 这个组织名被 CNB 按域名保护）。
  同步靠仓库里的 `.cnb.yml`（CNB 流水线每 6 小时从 GitHub 拉 main + 全部 tag，用流水线自带 `CNB_TOKEN` 强推，GitHub 侧零密钥）
  和 `.cnb/web_trigger.yml`（CNB 分支页 `…` → 执行 → 「从 GitHub 同步」按钮）。**发版后想让镜像立刻跟上就点那个按钮。**
  CNB 的 Monaco 编辑器会把逐字输入和粘贴的 YAML 自动缩进成阶梯，内置浏览器的剪贴板也进不去；要在 CNB 网页上写 `.cnb.yml`，
  用**单行 JSON**（YAML 是 JSON 超集）。GitHub Actions 不读 `.cnb.yml`，`tests/` 也不管它。
- **Release v0.1.0：** https://github.com/gzchenhao/openhire/releases/tag/v0.1.0 （含快照资产 `openhire-index.db.gz`，URL 稳定不变）
- **PyPI：** https://pypi.org/project/openhire/0.5.0/ （`pipx install openhire` / `uvx openhire@latest serve`）
- **官方 MCP Registry：** `io.github.gzchenhao/openhire`（`registry.modelcontextprotocol.io`）。**推 `v*` tag 即由 `.github/workflows/publish-mcp-registry.yml` 用 OIDC 自动发布**（v0.3.1 起每次均如此），本地 `mcp-publisher` 只作备用。
  从 Registry 自动收录的有 mcpservers.org、mcpmarket.com、Glama；**mcp.so 2026-10-16 收录**（主动提交的 #3845、#4473 由维护者关闭，页面 https://mcp.so/servers/openhire ）；**PulseMCP 没有我们**（2026-09-28 核实，此前写「自动同步」是错的）。中文清单 yzfly/Awesome-MCP-ZH PR #602 2026-10-15 合并。
- **上架渠道全景（057，2026-09-28）：** 仓库本身已是 **Claude Code 插件市场**（`.claude-plugin/`，用户 `/plugin marketplace add gzchenhao/openhire` + `/plugin install openhire@openhire`，端到端实测过）、
  **Cursor 插件**（`.cursor-plugin/plugin.json`）和 **Agent Plugins 标准包**（根目录 `plugin.json` + `mcp.json`）。已提：火山引擎 `volcengine/mcp-server` PR #437、mcp.so 目录 `chatmcp/mcpso` issue #4473。
  README 有 TRAE 一键导入链接。**Anthropic 目录已提交（2026-10-08，`reports/058`）**：插件页 https://claude.ai/directory/manage/plugins/1a281d9a-66a9-437d-a666-5635047cc35a （领导 Max 账号登录才能看），等待安全扫描 + 人工审核（三类保留项，答复在 058 第四节）；审核邮件到领导 icloud 邮箱。
  内置浏览器面板打不开 claude.ai，这类操作走 Chrome 扩展。接受目录条款那一勾每次都要领导在对话里明确说「可以」。push webhook 领导已装好（密钥不经我手），推 main 几分钟内目录就读到新版本。
  **仍要领导登录的**：Cursor Marketplace、cursor.directory、Smithery、LobeHub、AIBase；清单在 `drafts/listing-handoff-2026-09-28.md`。
  **SECURITY.md + GitHub 私密漏洞报告（2026-10-08 开启）**：目录条款要求漏洞报告机制；报告落在仓库 Security → Advisories，领导邮箱收通知，承诺 3 天确认、14 天评估。
  **不可**：扣子 / 讯飞星辰 / 元器要公网托管端点（**ChatGPT 连接器 0.8.11 起有托管端点可接**，见上）；百炼、千帆、华为云、豆包、TRAE 市场无第三方入口；Goose 停收，PulseMCP 停收，Continue 没了。
  **本机坑：** `~/.claude/plugins/known_marketplaces.json` 曾损坏成全零字节，任何 `claude plugin marketplace` 命令都报 JSON 错；已重置为 `{}`（备份 `.corrupt-20260928`）。
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
- **分工（领导 2026-10-10 定）：写稿、查数据、改代码、发版全在云端会话做；本机会话只做知乎、即刻、X 的发布**（要领导浏览器的登录态）。
  **2026-10-15 领导补：能让本机会话做的事，不让领导手工做。** 凡是要登录态或本机操作的活（注册账号、取 token、放 GitHub secret、目录提交、知乎回复），云端写好 prompt 交本机会话，领导只负责把 prompt 贴过去。
  **2026-10-20 领导补：GitHub 上所有评论、关注和之后的互动归云端统筹，「千万别怠慢 github 的生态圈」。** SOP 在私库 `github-ecosystem-routine.md`：云端每天读 GitHub 通知邮件、起草回复写进它的「待发回复」，自己仓库的直接回；别人仓库里的评论云端发不了（权限只到 `gzchenhao/openhire`，公开接口对外部仓库也是 403），由本机在每天知乎日检之后用 `gh` 发；真人关注回关，批量号不理，不做互关互赞与挂徽章换收录。
  **桌面版位置（官方文档 10-20 核实）：** 本机会话与定时任务都在桌面版 **Code** 标签页；定时任务在侧栏「Scheduled」→ 点任务 →「Review history」看每次运行（含跳过及原因）；只在桌面版开着、电脑醒着时运行，睡眠错过只补跑一次，设置 → This computer → System →「Keep computer awake」可防跳过（领导 2026-10-23 已打开；此前 10-16、10-17、10-21、10-22 四晚漏跑，之后再漏就不是睡眠的原因）。实时直连要领导在本机 Code 会话里输 `/remote-control` 连上远程控制，云端→本机的消息文档只写了一半，需实测；无人值守的定时运行收不到跨会话消息，所以日常活一律走 `local-inbox.md`。
  **2026-10-20 起云端交本机的日常活写进私库 `local-inbox.md`（本机待办）**：本机每晚定时任务第一步同步私库、做完标「已办」，再做知乎和 GitHub 日检；领导只在要他本人在场的活（输密码、付款、授权第三方应用）才转贴任务书。
  **知乎的一切由云端全权定（领导 2026-10-21：「知乎的一切都交给你定不用问我了」）**：选题、发文、改稿、投稿、自荐券、回复都不再请示，执行仍由本机会话（要领导浏览器的登录态）。
  **领英一律不自动化（领导 2026-10-22：怕封号）**：领英发帖、私信、删帖只由领导本人手动；本机会话任何情况都不碰领英（内置浏览器、Chrome 扩展、脚本都不行），香港岗位改用 OpenHire 读雇主官网。起因：10-22 上午本机隔夜卡在权限确认，领导改成全部接受后它照昨晚的旧稿用领导 Chrome 的登录态发了一条领英帖，云端的更正晚到十几分钟。私库 `local-inbox.md` 规则因此加了四条：领英不碰；每条待办动手前重新同步并重读；付费精抽只在 DeepSeek 半价时段；内置浏览器没登录就标卡住，不自己换到领导的 Chrome。
  **宣传四条（领导 2026-10-29 批，`reports/104`）：** ① 知乎精力从文章挪到回答，每周新发改投高浏览老问题（浏览过万、回答少于 80），自荐券给回答，周表定时任务已改；② 带货回答的唯一链接指向连接向导 `/connect`，本机日检每天记 GitHub 来源（link.zhihu.com）、14 天浏览、stars 和 PyPI 周数；③ X、即刻有事才发，脉脉停；④ 11-12 复盘 stars、PyPI 周下载、知乎近 7 天阅读三个数（已设一次性提醒）。
  **知乎评论与数据自 2026-10-15 起由本机每日定时任务处理**（SOP 私库 `zhihu-daily-routine.md`：分类规则、每日上限、只上报不回的五类、每天记阅读 / 赞同 / 收藏 / 评论进 growth-log）；下方「四个入口」第 3 条云端不再每天看，只在本机日检上报时处理。
  **云端写稿交接：** 云端会话同时选 `openhire` 和 `openhire-private` 两个仓库，稿子写在 `openhire-private` 根目录（它就是本机的 `drafts/`），提交并推它的 main。
  不要写进 `openhire/drafts/`：那里被 gitignore，推不上去，会话结束就丢。本机发布前先跑上面那条同步命令把稿拉下来。
  同步脚本 2026-10-10 起是**双向三方合并**（`drafts/.sync-state.json` 记上次同步时每个文件的内容）：只有一边改了就同步那边，两边都改了报 CONFLICT、不覆盖，人工合并后 `--resolved <文件>`。
  **本机任务队列（2026-10-11 起，`reports/070`）：** 云端跑不了的查证（RDAP / 档案馆 / 雇主官网 / OFAC），云端写进私库根目录 `local-tasks.json`，本机一条命令
  `.venv\Scripts\python.exe scripts\run_local_tasks.py --sync` 拉任务、跑、推回 `drafts/local-results/`；云端读私库的 `local-results/`。要本机先 `git pull` 并重装包。
  **外部事实源的分工（2026-10-12 定）：** 外部事实源（私库 `*-org-events-decisions-*.md`）的生产侧（规格、导出、回填、上传、验收）归对方项目经理；OpenHire 只管消费侧（怎么读、company_key 匹配、展示规矩），要求写成裁定条目经领导转达，**不直接指挥对方的 agent 改对方仓库**（10-12 夜越过一次，对方项目经理来函纠正）。
  `.env` / API key **永不进任何仓库**（含私有），存密码管理器。**唯一例外（领导 2026-10-10 定，`reports/066`）：DeepSeek key 可以存成 Claude Code 云端环境的「网络密钥」（会话看不到明文，只附到 api.deepseek.com），由领导自己粘贴；PyPI 改走 `.github/workflows/release.yml` 可信发布，token 不进云端。**`dist/`、`.tools/`、本地 DB 均可重建，不必备份。
- 再发新版流程（2026-10-10 起，云端和本机一样）：bump 十二处版本（含 `uv lock`）→ 全量测试 → 提交推 main。**到此为止**：Actions 的 Release 看到新版本号会自己测、发 PyPI（可信发布）、打 tag、挂 mcpb、建 Release，然后 Registry 自动跟上。不要手动推 tag（会和 Actions 建的 tag 冲突），不再 twine，README `mcp-name` 保持不变。发完用 `curl -s https://pypi.org/pypi/openhire/json` 核对版本。

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
   - **云端会话写的汇报先到 GitHub**（推到公开仓库 `reports/`），本机在 `C:\openhire` 跑 `git pull` 后才出现在领导电脑上（2026-10-20 领导没看到 084 才发现）；本机每晚定时任务第一步会 `git pull`，云端汇报行之前另附一行 GitHub 链接 https://github.com/gzchenhao/openhire/tree/main/reports 。
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
| 无 | | | 上一期「月报页点名后的雇主反应」（09-19 到 10-03）已于 2026-10-08 汇报：GitHub issue 零条、知乎通知里零雇主投诉或认领、Downloads 无新体验报告、邮箱要领导自己看。要不要继续点名由领导定（见 PROGRESS 10-08 条）。 |

**每次开工要主动查的四个入口**（有动静立刻处理，不等到期）：
1. GitHub issues（`gh issue list --repo gzchenhao/openhire`）—— 雇主认领模板会落在这里
2. 邮箱：**Gmail `globalheadhunter007@gmail.com` 自 2026-10-12 起托管给云端会话**（领导原话：「属于 openhire 的项目，你都全权负责处理」）。
   云端会话有 Gmail 连接器，每天一次例行查过去 24 小时的 OpenHire 相关邮件（GitHub 通知、PyPI、Glama、Registry、目录收录、雇主认领、用户吐槽附件），
   能处理的直接处理（我们自己仓库的 CI 红了就修并推；目录邮件按规矩回；认领走认领流程），处理记录追加到私库 `gmail-log.md`；要密码、密钥、授权码的邮件一律不动只报告。
   已建 Routine「OpenHire 邮箱日检」每天 08:51（香港时间）唤醒本会话。QQ 邮箱 `gdchenhao@qq.com` 仍读不到，**认领若走 QQ 邮箱仍要提醒领导自己看**。
3. 知乎通知与评论（https://www.zhihu.com/notifications）
3.5 **体验报告附件：看 `C:\Users\gdche\Downloads` 里有没有新的 `吐槽-*.md` / `体验报告-*.md`。**
   Gmail 连接器**只给附件 id、不给内容**；`RAW` 能取到整封 MIME，但要把 12KB base64 手抄进文件，有损坏风险。
   **约定（2026-09-22 定）：领导把附件下载到 Downloads 就行，我自己去读，不必再拖进对话。**
   **绝不为此索取邮箱授权码 / 应用专用密码** —— 那是整个邮箱的读取权（银行、验证码、私人往来都在里面），
   为一个 5KB 的附件付这个代价不成比例，而且那串密钥还得长期保管、泄露后果远重于一个 API key。
4. **X 改为「有事才发」（领导 2026-10-08 定，按我的建议）。** 每日一轮停了：三轮下来 0 粉丝、两条帖合计 24 次浏览、Mentions 始终为空，
   零产出的例行动作不值得每天花时间。只在两类事发生时发：发版（含值得说的修复）、被某个目录 / 周刊收录。
   发帖走 Web Intent（记忆 `x-posting-via-web-intent`），回复标准不变（带实测事实、第一条不放链接、不 @ 人）。
   Mentions 不再每天看，发帖当天和次日看一次即可。记账仍在 `drafts/x-engagement-log.md`。

观察期结束后删掉这一行，换成下一个观察项；没有观察项时保留表头写「无」。

## 对外文案的五条硬规矩（体验官 Round 3 定，第 4 条 2026-09-15 补，第 5 条 2026-09-23 补）

1. **数字只准引用 `docs/numbers.json`。** 跑 `ohp numbers` 生成，写文案时照抄，**不准凭记忆写**。
   「139 家」在所有文章里出现过，而表里是 140 行——那不是写错数，是**两个不同的问题共用了一个标签**。
   文件里每个字段名都说清了它数的是什么（`companies_in_index` vs `employers_with_live_postings`）。
   百分比对外一律取整并标注实测日期，索引每周刷新，小数必然漂移。
   **2026-10-23 又犯一次**：云端稿写「155 家雇主」，本机核出有在架岗位的是 152 家（`employers_with_live_postings`），改前就发会违规；带货文案里「雇主」一律用 `employers_with_live_postings` 这个字段（10-26 快照、0.8.31 新口径是 172 家、20,019 条；0.8.31 起「在架」= 雇主系统 30 天内返回过）。同稿还把工具起始写成「去年起」，仓库首次提交是 2026-07-14，**对外一律写「今年 7 月起」**，到 2027 年再改。
2. **人设：主叙事是「deep tech 猎头，覆盖智驾与具身」**（领导 2026-09-14 批准；**2026-10-12 定：「深科技」三个字不再用，中英文文案里一律写英文 deep tech**，行业内人士都看得懂）。
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

6. **称呼与用词（领导 2026-10-08 定）。** 对雇主一律「贵公司」，不写「贵司」（语法错误）；「小公司」带贬义，正文用「中小型公司」或「小型公司」，只有引用问题原文时照抄。
   **对外邮件与回信（领导 2026-10-29 定）：** 称呼对方一律「您」不写「你」，全文不用叹号（中英文都不用）。起草后自查这两条再交领导。

7. **装机文案点名五个助手（领导 2026-10-12 定）。** 凡是说「把 OpenHire 装进 AI 助手」的文案（README、docs 站、知乎、LinkedIn、目录描述），一律写
   **Claude、豆包、DeepSeek、Cursor、腾讯 WorkBuddy**，不能只写 Claude 和 Cursor：中国大陆用户用不了 Claude，只写它们没有代入感。
   准确写法：豆包（豆包工作）的自定义连接器只收 HTTP 地址，所以给它的路径是本机 `ohp serve --transport streamable-http --port 8000` 加 `http://127.0.0.1:8000/mcp`（2026-10-12 领导在豆包工作里实测通过，README 已改成实测口径）；
   DeepSeek 自己的 App 没有 MCP 入口，写法是「DeepSeek 经 Cherry Studio / Chatbox 这类支持 MCP 的客户端」；WorkBuddy 走 `~/.workbuddy/mcp.json`。
   **2026-10-15 领导补三款：** ① 名单加 **ChatGPT**，而且排第一：举例 AI agent 时顶级名字越多，认同感越大，OpenHire 跟在后面出场的权威感越强；不要因为 ChatGPT 是 Claude 的对手就回避（领导原话「你现在不是为 Claude 服务，你是为我服务」）。实情照写：ChatGPT 只接公网地址的连接器（开发者模式，付费档）；**托管地址 2026-10-21 起可用：https://openhire-vlny.onrender.com/mcp** ，文案写「ChatGPT 在 设置 → 连接器 → 高级 → 开发者模式 里新建连接器，地址填这个，不用装任何东西」。
   ② **带货要喂到嘴里，不只送到手里：** 凡是带货段落，把读者要贴给助手的 prompt 原样写进文案，用代码块，一键复制。**2026-10-21 起用「装机加提问」合并版**（领导定，私库 `install-copy-blocks.md` 顶部是定稿，README Quickstart 中英各一份）：装机句和提问合成一段，中间带一道判断「现在能不能调 openhire 的工具？能就直接做；不能就停下说明怎么重启，不许用网页搜索代替」，因为助手装完 MCP 这一轮往往用不上新工具，会拿网页搜索凑结果甚至编岗位；旧写法里「重启你自己」那句是错的。专题文章可把「找工作任务」换成本篇的提问，前两段保留原样。一行 `mcpServers` 配置（给只能聊天的助手）和豆包的 HTTP 路径照旧单独给。提问 prompt 只问工具真能答的（搜索结果不带 JD 全文，别写「JD 里要不要论文」）。
   ③ **文章发完要去投稿：** 每篇知乎文章发出后，云端给本机会话一份投稿 prompt（问题选择标准、每题一条不雷同的 200 到 400 字回答、数字只从文章表里抄、每天最多 5 题、记进 growth-log），本机会话去相关问题下投。原则：我们说的每句话要么对产品打造有贡献，要么对带货有贡献，不发只为刷存在感的内容。

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
    **只在 DeepSeek 低价时段跑（领导 2026-09-23 定；0.8.27 起代码锁死，`pipeline/pricing.py`，没有开关）。** 官方定价页（api-docs.deepseek.com/quick_start/pricing）：
    高价时段 = **工作日 UTC 01:00–04:00 和 06:00–10:00**，即**北京时间 09:00–12:00、14:00–18:00**（2026-08-17 起峰谷定价；08-23 起周六日全天半价）；
    其余时间、周末、中国法定假日全天都是半价。本机时钟是 UTC+7，别拿本机时间当北京时间，先 `date -u`。
    代码锁比价格表多留 30 分钟余量（工作日北京时间 08:30 到 12:30、13:30 到 18:30 拒绝）、节假日按工作日算；命令显示的「花费」按 `config.DEEPSEEK_PRICE_*` 固定单价估算、不分时段，对账以 DeepSeek 后台账单为准。
    抽取脚本可以 detach 跑（PowerShell `Start-Process` + 日志文件），会话不用一直挂着。
  - **GLM —— 已停用（2026-09-20 领导决定不再续订）。** 四个 key 当天实测全死：
    #1/#2 是 `1309`「GLM Coding Plan 套餐已到期」、#3 是 401、#4 是 `1113` 余额不足。
    代码仍保留 GLM 后端可用，但**不要再默认走它**。已把 `1309` 归入死 key 判定并抛 `KeysExhausted`，
    因为它原本被当成限流、还提示「重跑会续上」——**重跑不会续费**。
  - 启发式（免费离线，CI 与 `bootstrap` 用）。
  - **血统不造假：** 每行 `jobs.extraction_source` 如实记录是谁抽的（`glm` / `deepseek` / `heuristic`）；重抽只挑「不属任何 LLM 源」的行，两个 LLM 后端不会互刷。
  - serve / search 阶段不需要任何 key。
- 设计交接文档：`design_handoff_openhire_v01\README.md`（唯一权威规格）；`design_refs\*.html` 仅供交互参考，**不复用其代码**。
- **抓取边界判例（020 复核定档）：** 响应体自带密钥、IV 页面明文可得的传输编码 = 可解（等价多绕几道的 base64，如 Moka 的 AES 信封）；请求签名、验证码、登录墙 = 访问控制，不可破（如飞书 `_signature`）。若某 vendor 把密钥移出响应体（JS 派生/会话挑战/轮换），即视为升级成访问控制——**立即停抓该 vendor 并记录**，不做逆向。
  **领导 2026-10-20 确认继续坚守这条线**（问「红线是什么」后答「我听懂了，继续坚守红线不碰」）：飞书岗位级链接不抓，靠雇主授权、飞书合作、公开公众号补。
  **禁止「特征探测」（2026-09-24 定）：** 被站点拦下（WAF / 反爬 / 567 之类）之后，**不许为了「弄清它是按什么拦的」而改变我们客户端的任何身份特征再试一次**
  （改 User-Agent 伪装浏览器、改 TLS cipher / 指纹、换 IP、带别人的 cookie 都算）。哪怕只试一次、哪怕不放进代码，那也是在试另一把钥匙。
  允许的只有三样：读拦截页本身、读 robots.txt、用**完全相同**的请求再试一次以排除偶发。判定「被拦 = 停」不需要知道它按什么拦。
  出处：蔚来 `www.nio.cn` 的 EdgeOne 567，实现 agent 为验证「按 TLS 指纹拦」发过一次改 cipher list 的诊断请求（拿到 200，未入代码），审查者判越线，领导 2026-09-24 问明后定为禁止。
- **抽取/解析规则变更要影响存量数据：必须先失效 content_hash**，否则重抓一律被判「未变」而空转（020 福瑞泰克「元/天→假月薪」修复的教训）。

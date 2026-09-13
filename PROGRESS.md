# PROGRESS · OpenHire `openhire-mcp` v0.1「哨兵」

> 一页进度台账。新条目置顶。恢复会话请先读 `README.md` 再读本文件，勿重做已完成工作。

## 📌 待办（不急，等有空再做）

- **Discord server-author 标识**：punkpeye(Frank) 的 bot 在 PR #13379 合并时留言，要一个 Discord 用户名就发标识。
  号已注册（`gzchenhao`），但**两次踩到 Discord 新号风控**，第一个号被警告。领导决定暂缓，由本人操作、不自动化。
  加入入口 https://glama.ai/mcp/discord （Model Context Protocol，13,991 成员）。
  **价值判断：标识本身近乎为零收益**，真正有价值的是那个 14k 开发者社区的长期参与（慢活）和与 Frank 的关系（已通邮件，更直接）。不是关键路径。

## 2026-09-13（下午）— 按数据换赛道：知乎文章转向具身/自驾，并量出「自荐券不值钱」

- **先更正两个事实**：① 自荐券**本月剩 2 张不是 3 张**（9/09 那条《为什么招聘网站主动投简历没啥回应？》
  已在「加量中」，用掉一张）；② Cline 的上架 issue 在 `cline/mcp-marketplace#2501`，不是 `cline/cline`。
- **量出了券的价值，很低**：9/09 那条**用了券**，四天 257 阅读（≈2.7/小时）；9/12 22:30 那条**没用券**，
  十小时 165 阅读（≈**16.5/小时**）。问题本身的流量远比券值钱。
- **真正的发现是话题错配**：领导号的历史最好成绩是《现在选择具身智能是否合适？》**1,283 阅读**（无券），
  《自动驾驶人才都在哪里？》393；而招聘类最好只有 257。**读者在具身/自驾，不在招聘**。
  我们此前一直往招聘话题上使劲，是在影响力最弱的地方发力。
- **据此发了新文章**（知乎**文章**不是回答，因为该词的流量走搜索+文章页，存量问题只有 48/128 浏览）：
  https://zhuanlan.zhihu.com/p/2082404476653155237 话题「自动驾驶·具身智能」。
  服务端已核验：2 张表、27 行、正文 2,086 字。
- **内容是我们独有的数据**：30 家具身/自驾公司 2,350 个在架岗位，按**雇主自己 ATS 里的发布日**算在架天数
  （覆盖率 100%）。国内 14 家中位 **171 天**、47% 超半年；海外 14 家中位 **76 天**、21% 超半年。逐家表在文里。
- **两次口径自查，记下来**：① 第一版用 `first_seen_at` 算在架天数，得出国内 29 天/海外 39 天——**错的**，
  那是我们自己的观测窗（最大仅 65 天），分布被截断。改用 `posted_at` 才对。
  ② 亿嘉和（中位 1,551 天）、节卡（793 天）**主动从统计中剔除并在文中写明理由**——这两家几乎必然是
  ATS 把「需求创建日」当发布日，不是它们在挂鬼岗。剔除后国内中位从 216 降到 171，文中用 171。
- **文中不出现「幽灵岗位」四个字**：我们量得到「挂了多久」，量不到「还想不想招」，写成指控站不住。
- **下一步**：24h 后看自然数据 → 决定 2 张券投这篇还是留着；knowledge：往后知乎内容默认走具身/自驾赛道。

## 2026-09-13 — 渠道：知乎高赞回答 + 脉脉首帖；一次可核对的渠道排名纠正

- **知乎**：给 137 万浏览的「boss直聘的工作靠谱吗？」写了回答并发布（2,429 字）→
  https://www.zhihu.com/question/437270560/answer/2082249706634221185 。
  **故意先不用自荐券**，让它自然跑满 24h 拿基线，再决定 3 张券（9/30 清零，还剩 3 张）投哪篇。
- **脉脉**：领导发了首帖（我写稿、他发；我没有脉脉会话，不碰他的号）。标题《下次猎头找你，先查这个日期》。
  受众是他 2,858 个算法工程师好友——**在职、不找工作、但天天被猎头骚扰**，所以行动号召定成
  「被动核验猎头给的岗位」而不是「去找工作」。**帖子里没有任何外链**（脉脉外链规则我核不实，不赌）。
  代价是**这条无法归因**：脉脉带来的流量只会落进 direct/搜索，不会出现在 referrer 里。基线已存
  `drafts/growth-log.md`。
- **渠道真实排名（我之前说错过，这里是实测）**：referrer 14 天累计 —
  `link.zhihu.com` 5 次/**5 uniques** · `chatgpt.com` 3/1 · `lnkd.in` 2/**1** · `news.ycombinator.com` 1/1。
  **知乎是唯一持续产出独立访客的渠道**；领英 474 次曝光只换来 1 个独立点击。
  我此前凭那 1 个点击宣布「领英是主渠道」，是错的，按数据更正。
- **今日计数**：stars 4 · views14d 66（uniq 39）· snapshot_dl 38（注意该计数每周一被快照刷新清零）。
- **下一步**：① 明天看知乎新回答 24h 数据 → 定券投哪篇；② 明天看 `lnkd.in` 是否突破 1 uniq →
  决定领英是否继续当渠道；③ Glama 托管等 Frank 回信。

## 2026-09-11（晚）— 外部体验官报告 → 0.4.2（版本漂移 / 假幂等 / 陈旧文案）

- **智谱 Autoclaw 产品体验官**对 0.3.2 与 0.4.1 做了两轮完整实测（五工具 + 错误路径 + CLI +
  streamable-http），出报告与 17 条吐槽。**这是迄今最有价值的外部输入**，见 reports/026。
- **三条最严重的我逐条复验，全部属实，其中两条是我当天造成的**：① `__init__.py` 硬编码
  `__version__`，0.4.0 与 0.4.1 两次 bump 都漏，`ohp version` 一直报 0.3.2；②
  `authorize_application` 标 `idempotentHint=True` 但连调两次得 `r_8d6d`/`r_d03f`，注解是我当天加的；
  ③ README 仍写 "Moka is on the roadmap" 而 moka=13 家在跑。
- **0.4.2 已发**：版本号改为从 `importlib.metadata` 读取（物理上杜绝第二份副本）+ 回归测试；
  `idempotentHint` 改为 False（**只改注解不改行为**，语义变更是产品决策，等领导定）；删陈旧句。
  干净 venv 装 PyPI 验证通过。256 tests。
- **我的流程失误（记下来）**：0.4.2 是在测试未通过的情况下发的——`pip install -e .` 因 `ohp.exe`
  被占用而失败，pytest 报 23 个 collection error，但 install→test→build→publish 串在一条命令链里，
  `set -e` 捕不到管道尾部为 `tail` 的失败。产物碰巧是好的（wheel 由源码构建），**但那是运气不是把关**。
  今后发布前的测试必须单独成步、单独断言退出码。
- **环境**：`.venv` editable 安装当前是坏的，占用 `ohp.exe` 的是 **Claude Desktop（PID 7260）派生的
  两个 `ohp serve`**——OpenHire 正在领导的 Claude Desktop 里跑着，我没擅自杀。**待领导重启 Claude
  Desktop** 后修复；期间用 `PYTHONPATH=src` 绕开，不影响干活。
- **他的总评**：未发现 S0/S1，S2×3 / S3×9 / S4×5，「修完三个 P0 就可以上 MCP store」。隐私三条红线
  他在代码与运行时都验证属实。零配置 serve 实测 24 秒从空索引到第一条数据。
- **待领导决定**：销售岗噪音（需抽取管线立项）、重复授权是否应当幂等、bootstrap 文档收口。

## 2026-09-11（下午）— 0.4.1 热修：非阻塞启动 → 魔搭从「不可部署」翻成 Hosted

- **0.4.0 有个我自己引入的缺陷**：`serve()` 同步跑那 31 s 的快照下载才进 `mcp.run()`。托管市场探测新服务的方式是「连上 → 调 tools/list」，而 `tools/list` 根本不需要索引。结果魔搭部署检测超时，列表被判 **不可部署**。（我一度误报「检测通过」，那是个短暂状态，重检即失败——教训：托管平台的状态要等稳定再下结论。）
- **0.4.1 修法**：`_start_bootstrap()` 把下载丢到 daemon 线程立即返回；只有五个读数据的工具调 `_await_index()` 等待；无人启动 bootstrap 时 `_await_index()` 直接返回（否则测试/CLI/宿主进程会干等 180 s——这个坑我自己先踩了一次，pytest 挂住）。
- **实测**：`_start_bootstrap` 0.02 s · `list_tools` 0.00 s（5 个工具）· 首次 `search_jobs` 13.5 s 返回真实行。**255 tests**（新增 2 个把这两条性质锁死）。
- **魔搭结果**：徽章 `Local/不可部署` → **`Hosted` / 可部署**，五个工具全部列出，MIT License 被识别。已建免费部署实例（函数计算 FC 共享资源池，Streamable HTTP）。
- **⚠️ 免费部署有效期只有 24 小时**（创建 09-11 14:47 → 到期 09-12 14:47）。所以它是「试用实例」，不是可对外长期宣传的稳定端点。长期要么手动续，要么走「个人专属云资源」（需授权、要钱）。
- **隐私说明已写进魔搭服务描述**：托管模式下匿名指纹与筛选条件会经过魔搭服务器，要纯本地请用 `uvx openhire@latest serve`。不破红线（仍无简历/PII），但信任叙事有变化，给用户选择权。
- **魔搭个人主页**已定制：昵称「陈灏 Howard」、主页链接、个人简介（猎头→自己写代码→OpenHire 的来龙去脉）。
- **Glama 创始人 Frank Fiegel 回信已回**（他问「你想做什么」）：告诉他 Glama 的构建流水线替我们抓到过一个线上 bug（`mcp>=1.2.0` 无上限 + mcp 2.x 改名，只有新用户会崩且不会来提 issue），并问了两件事：Glama 是否托管远程 MCP、以及我们能否提供 server-author 侧的反馈。
- **意外收获**：freemcp.space 的 bot 自动提 PR 收录我们（Appnova-EU-OU/awesome-remote-mcp-servers#554），无需动作。

## 2026-09-11 — 0.4.0 发布（零配置 serve）+ 四个 Agent 平台商店同日提交 + 掘金昵称

- **0.4.0 已上线**：PyPI ✅ · tag v0.4.0 → OIDC 工作流自动发官方 Registry ✅ · GitHub Release 附 `openhire-0.4.0.mcpb`。253 tests green。
- **为什么要 0.4.0**：上架任何「一键装 / 云托管」商店的共同前提是 `uvx openhire serve` **零配置就能出数据**。此前 serve 起来是空库，必须先 `ohp bootstrap`。现在 serve 检测到空索引自动拉公开快照（实测 140 家 / 23,874 岗 / 31 s），`OPENHIRE_NO_AUTO_BOOTSTRAP=1` 可关。同时补齐商店硬性要求：五个工具 `title` + `readOnly/destructive/idempotent/openWorld` 注解、`docs/PRIVACY.md`、品牌图标、`Dockerfile`、`--transport sse|streamable-http`。
- **商店提交（当日）**：Cline Marketplace issue cline/mcp-marketplace#2501 · Docker MCP Registry PR docker/mcp-registry#5055 · GitHub 精选 Registry 申请（github/github-mcp-server discussion #1257 评论）。
- **魔搭 ModelScope MCP 广场已上线**：https://modelscope.cn/mcp/servers/haolu98/openhire ——自动解析 README 取到 `uvx openhire@latest serve`，**部署检测通过、五个工具全部 list 成功**（0.4.0 零配置改造的端到端验证）。遗留：详情页徽章仍显示 Local（疑缓存）、图标待补、「新建部署」会占算力配额未擅自点。
- **Claude Desktop 扩展目录已提交**（09-11，领导本人填表，提交 0.4.1 的 .mcpb）。表单偏好 Node.js 我们是 Python，概率偏低，等回音。步骤存档 `drafts/claude扩展目录-提交步骤.md`。
- **调研定档（reports/025）**：腾讯云 MCP 广场「暂不提供第三方上架」；百度千帆仅企业；扣子/百炼/ChatGPT 插件目录/Claude 远程连接器目录都要公网 HTTP 端点（后者还要 Team/Enterprise 组织）→ 归为「托管期」，等有服务器再做；WorkBuddy 无公开市场，只能靠用户手填。
- **掘金**：作者昵称「用户857732759795」→「陈灏」由领导本人提交，**审核中**（自动化填表被前端校验挡回，已交回人工）。
- **测量口径修正**：`snapshot_dl` 不是累计——每周一工作流覆盖资产会归零计数，只代表「本周 bootstrap 次数」（已写进 growth_metrics.py 注释）。
- **KPI(09-11)**：star **4**（09-09 +1 rei-lena，09-10 +1 sparowjake-troll）· views14d 53/25 · 四渠道归因见 reports/024。
- **下一步**：等 Cline/Docker 审核；领导登录魔搭后 2 分钟完成国内最大入口；LinkedIn 每周一条（主阵地）；知乎以回答为主。

## 2026-09-07 — 🎉 punkpeye(94k★) 已合并！三渠道重炮发射 + 第二北极星立项

- **PR #13379 MERGED**（02:55Z）→ OpenHire 正式进入 awesome-mcp-servers（94k★，全 MCP 生态最大发现入口）。
- **三渠道里程碑重炮已发**（合并即发，star 基线=2）：X changelog 续推 · 知乎想法（同步「开源软件宝藏库」圈子，第171篇）· 即刻动态（AI探索站圈子）。文案见 drafts/punkpeye-merge-posts.md。
- **第二北极星立项**：雇主认领数（employer_claim）——见 reports/019 北极星序列 + memory。推广话术备好（drafts/employer-claim-outreach.md），启动门槛 star≥100 或周活≥50。
- 目录触达面态势：官方 Registry ✅ · Glama 83% ✅ · **punkpeye 94k ✅ 已合并** · mcp.so 待审 · PulseMCP 恢复后自动收录 · wong2/appcypher 维护者限制挡。
- **下一步**：盯 star 曲线（重炮转化）；到门槛启动雇主认领。

## 2026-09-05 — Glama release 拿下 → 评分 83% → punkpeye(94k) 推进；X 进展续推

- **Glama 农场当日恢复** + **逮到 CMD 回退**（Glama 自动填成 `ohp serve`，`ohp` 不在容器 PATH → `spawn ohp ENOENT`；改回 `uv run openhire serve`）→ 构建 **success**（server 正确响应 introspection）。
- **Glama Release v0.3.2 已发布** → 质量评分 **33%→83%**，Server Coherence **A**（工具命名/职责/数量各 5/5）。
- **punkpeye PR #13379**：已发事实性评论附 83% 分数推进合并（labels 已有 has-emoji/valid-name/has-glama，等 bot 复检或人工 merge）。
- **X 进展续推**已发（Glama+Registry+0.3.2+软性 star 邀请，挂原 changelog 线程）。知乎/即刻**按住**，留给 punkpeye 合并/star 里程碑再放（防受众连日轰炸疲劳）。
- 触达面态势：官方 Registry ✅ Glama(83%)✅ punkpeye 待 merge · mcp.so 待审 · wong2/appcypher 被维护者互动限制挡(非我可控) · PulseMCP 未同步。
- KPI(09-05): star 2 · 快照下载 7 · PyPI 限流未取到。

## 2026-09-04（晚）— 0.3.2 已发布（PyPI + tag v0.3.2 → Registry 自动发）

- 内容：一次性价值时刻星标提示 + `ohp star`。解耦于 Glama（其构建农场故障，徽章链接动态无需发版）。发布前门禁：253 tests、twine check、全新环境 wheel 验证（mcp 1.29.1、serve import OK）。
- 版本线：0.3.0（Moka 崩溃修）→ 0.3.1（mcp<2 热修）→ 0.3.2（star 漏斗）。**现在 PyPI 新装用户三个已知洞全堵。**

## 2026-09-04（下午）— 装机→star 漏斗后端：一次性星标提示 + `ohp star`（commit 2eaa5ca）

- 依据 npm「终端广告」被禁→`npm fund` 的教训设计：提示**仅一次**、仅在首次搜出结果/check 命中的价值时刻、永不出现在 `serve`（stdout 属协议）、`OPENHIRE_NO_STAR_HINT=1` 可关；`ohp star` 为 npm-fund 式的用户主动命令。253 tests green（+5）。
- 否决「MCP 返回值里塞推广脚标」：污染 AI 上下文 + 破坏冻结协议契约 + 与定位相悖。
- 待下次发版进 PyPI；社区文案（知乎/即刻）文末加诚恳 star CTA（HN 除外，文化不容）。

## 2026-09-04 — Glama 认领/评分 + 0.3.1 热修（详见 reports/021）

- **0.3.1 已发布**（PyPI + Registry isLatest + tag）：修 `mcp>=1.2.0` 无上限导致新装用户解析到 mcp 2.x、`serve` 崩溃（FastMCP 被 2.x 移除）。锁 `mcp<2`。全新装机验证 mcp=1.29.1、serve import OK。248 tests green。
- **Glama**：加 glama.json + GitHub 认领 → 作者验证通过（蓝勾）、评分 17%→33%；修正 Glama 自动 CMD 漏 `serve`。
- **遗留**：Glama Docker release 未完（mcp 修复后 server 成功启动，但**四次**（trixie/bookworm 两种镜像）均卡在 Glama 拉 docker.io 元数据的第一步 `no active session ... context deadline exceeded`——发生在 git clone 我方代码之前，纯 Glama 构建农场故障（最后一次卡 14 分钟才超时），非我方问题；配置已定稿（bookworm+serve+pinned），**下次会话一键重试 Build 即可，无需再改任何配置**）。通过后 Release → 回 punkpeye PR #13379 推进合并。
- KPI：star 2 · 快照下载 5 · PyPI 72/天。装机>star，漏斗后端（首次运行引导 star）待优化。

## 2026-09-03 — 020 验收通过 + 小鹏入库 + 精抽存量二次清零 + 快照刷新

- **020 验收：过**（248 tests 亲测；Moka 620 岗 posted_at 零造假；AES 信封判定复核维持，边界判例入 CLAUDE.md）。
- **小鹏按新口径入库**（判据=赛道自研第一梯队）：193 社招岗。覆盖 **139 家 / 15,841 活跃岗**。
- **精抽二次清零**：heuristic 活跃岗 0、role_family NULL 0（GLM 3/4 号钥匙，¥0）；coding 套餐 1/2 号钥匙据领导告知已作废，后续靠领导补充新钥匙，**绝不回落 DeepSeek**（领导 9-03 指令）。
- **快照已刷**：139 家 / 22,976 行 / 26.4MB，2026-09-03T06:36Z 上线。
- KPI 基线（9-03）：star 2 · views14d 26（uniq 9）。HN 未回信（含垃圾箱查证），9-08 未回则跟进。

**当前状态：v0.2.0 已上线（PyPI + Registry isLatest）· 248 tests green · 覆盖 137 家 / 在架 15,648 岗 · 国内两个 vendor（北森 + Moka）· 快照周刷自动化**

## 2026-09-02 — 020 楔子覆盖冲刺完成（详见 reports/020）

**当前状态：248 tests green · 137 家 / 在架 15,648 · 国内第二个 vendor（Moka）已打通 · 本单现金 ¥0**

- **A Moka 适配器 ✅**（门槛 ≥3 家，实测 **12 家**目标行业公司可抓，超 4 倍）。新增 `ats/moka.py` + `ats/_aes.py`。
  - `tenant = "<org>/<siteId>"`，`company_id` 仍是裸 org slug —— siteId 漂了也不会让历史职位变孤儿。
  - **入库 620 岗，`posted_at` 真实覆盖 620/620 = 100%**；12 家 apply_channel **12/12** 逐家实测直达该岗（另在浏览器人工打开 3 家核对）。
  - Moka 的 AES 信封**不是访问控制**：端点公开免登录，密钥 `necromancer` 装在它自己加密的响应里，IV 明文在页面上。
    没算任何签名、没解验证码、没绕登录墙 —— 与 014 判飞书不可抓是两回事。AES 自己实现（纯 Python，只解密，FIPS-197 三组向量钉死），
    不为此引入编译依赖。
  - **「200 不等于存在」已代码化**：乱写 slug 和已关停 portal 都返 200，判据是 init-data 里有没有 `org`；两个真实 200 页面做 fixture 锁死。
- **B 11 家未定公司 ✅ 全部结案**：Moka 5 家（元戎启行/驭势/白犀牛/星动纪元/傅利叶，**已入库**）· 飞书 4 家（它石智航/自变量/穹彻智能，
  加上众擎，仍不可抓）· 已关停或破产 2 家（毫末智行、纵目科技）· 仅三方 1 家（松延动力）。
  **纠了 014 三处错**：`tarsai.cn` 是待售停靠页不是它石官网；`engineai.com.cn` 是**众擎机器人**不是松延动力；穹彻借用非夕的飞书租户。
- **C 两个异常北森租户 ✅**：`yijiahe` **已修复入库 134 岗**（014 读数不复现，标准端点正常返回 JSON）；
  `zhito` 查明是北森**旧版 CmsPortal**部署、根本没有那个 JSON 端点，且浏览器实测页面写着**「无任何在招职位」**——
  故意不入种子（否则每周 CI 永远多一个稳定失败的租户），证据留观。
- **D 数据质量**：抓取中发现并修掉一个会造假的坑 —— Moka 的 `实习/兼职` 岗在同一薪资字段里填的是**元/天**（150–250），
  ×1000 会变成「月薪 15 万的实习生」。现在这类岗薪资一律落 NULL（本库没有 daily 周期，折算就是编造）。已加断言。
  **改存量时又踩一层**：`_update_job` 只在 `content_hash`（标题+JD）变化时才重写薪资，规则变了原文没变 → 重抓空转全判「未变」；
  清空这 620 行的 hash 再抓才生效（620 条全部更新，带薪资行 242→232，最高薪回到 55K–100K/月的合理量级）。
  14 条空 JD 逐条回源核实，**确认是雇主自己没填**，不是抓取失败。
- **GLM 精抽本次做不了**：主/备钥匙配额均耗尽（`1310`，**2026-09-03 21:22 重置**），按任务书就地停手、未回落 DeepSeek
  （`deepseek` 行数仍为 16,316，与开工前一致 → **确认零付费调用**）。免费的 `role_family` 启发式已跑（标注 931 条，¥0），
  国内岗不会对 `--role-family` 隐身。库内 `heuristic` 行 1,217 条，配额重置后一条命令清偿。
- **测试：248 passed / 0 failed / 0 skipped**（204 基线 + 44 新增），既有断言未改未删未 skip。
- **待领导拍板**：小鹏（Moka `xiaopeng/67918`，**335 岗**）收不收 —— 主业整车制造，014 曾以同样理由排除追觅/汇川。技术上一行种子即可。

---

## 2026-09-01 — GLM 多钥匙精抽收官（详见 reports/018 终账）

- 多钥匙轮换上线后连修两个 provider 侧突变（thinking 参数契约、1310→1113 变身），204 tests green。
- 存量精抽全部清偿：skills 剩 2、role_family NULL=0，现金 ¥0（全走领导的智谱套餐/资源包，主力为 glm-4.5-air token 包）。
- 新快照 25.0MB 已上传（2026-09-01T14:50Z），公开数据即刻带上精抽质量。
- GitHub：https://github.com/gzchenhao/openhire （main，tag v0.2.0）
- Release v0.1.0（含快照 `openhire-index.db.gz`，URL 稳定）：https://github.com/gzchenhao/openhire/releases/tag/v0.1.0
- PyPI：https://pypi.org/project/openhire/0.1.1/ （`pipx install openhire`）
- **官方 MCP Registry：`io.github.gzchenhao/openhire` v0.1.1**（`registry.modelcontextprotocol.io`；PulseMCP/mcp.so 会自动同步）
- Smithery：v0.1 **放弃**（无本地 stdio 网页入口，见 `reports/010`）。
- **常设仅剩：月度一次本机 LLM 精抽**（`ohp extract-rebuild --backend glm`）——每周快照刷新已自动化，CI 无 key 只能跑启发式，精抽是它唯一做不到的事。

---

## 2026-08-31 — 018 GLM 多钥匙轮换（小改动，详见 reports/018）+ 017 验收通过

- **017 管理者验收：过**（4/5 达成 + 1 项合规断点；pytest 188 亲测、CI run 全绿亲查、.github 零密钥亲扫、三家租户 DB 实据）。
- **018**：`ZHIPU_API_KEY_2…_9` 备用钥匙槽 + 额度尽/无效自动热切换（429/1310、401），全尽才落 DeepSeek；普通限流不烧备用钥匙。**198 tests green**。`.env` 已留空槽待领导填。
- 剩余精抽（3,503 skills + 1,712 role_family）：填入备用钥匙后随时可跑，或等 9-03 21:22 首钥匙配额重置。

## 2026-08-31 — 017 完成（4/5 硬指标达成，详见 reports/017）

**当前状态：188 tests green · 125 家 / 21,568 岗（活跃 14,909）· 快照刷新已自动化 · 本单花费 CNY 0.00**

- **A GLM 后端 ✅：** 把 `DeepSeekExtractor` 抽成可配置基类，新增 `GLMExtractor`（coding 端点 + `thinking:disabled` + `max_tokens≥1024` + 剥 ```json 围栏）。`extraction_source` 如实标 `'glm'`；重抽范围改为「不属任何 LLM 源」，杜绝 glm/deepseek 互刷；429 退避 + 连续 5 次停在断点；`auto` 链优先 GLM（免费）而非 DeepSeek（按次计费）。
- **A 选型 ✅ 取 `glm-5.3-flash`：** 新命令 `ohp extract-compare` 对同一批 100 条（中文 JD 30 条）做三方对比。**中文岗 7.86 技能/岗 vs 库内 deepseek 7.39、清空 0 条、1.17 s/岗**；glm-5.3 更慢（1.65 s/岗）且清空 9 条。对比本身也 ¥0（基准用库内已有结果）。
- **B 存量精抽 ⚠️ 停在断点：** 跑到 1,800 条时 **GLM 周配额耗尽**（HTTP 429 / code **1310**，**2026-09-03 21:22 重置**）。已入库 **glm 1,749** 条；剩 heuristic 活跃岗 **3,503**、role_family NULL **1,712**。按止损条款停下，进度逐批已提交，重跑续上不重抽。**待你定：等 9-03 配额（¥0，推荐）还是今天花约 ¥10 走 DeepSeek 补完。**
- **C 快照周刷新 ✅ 已上线并实跑通过：** `.github/workflows/refresh-snapshot.yml`（周一 06:10 UTC + 手动）。**零密钥**——`permissions: contents:write` 单项、无任何 GitHub Secret、唯一凭据是 `${{ github.token }}`。从已发布快照起步，故 GLM 抽取结果不被覆盖（已复核公开快照里 glm 1,749 条仍在）。新增 `ohp ingest --fail-over N` 让崩掉的抓取以非零退出触发失败邮件。**run 33376083394 全绿**：资产 `06:01:01Z → 09:08:32Z`、新用户 bootstrap「龄 0 天前」、公开快照只含 companies/jobs 两张表。前 3 次失败都是我验证脚本自身的 bug（三个不同原因），核心流程每次都成功。
- **C CN 可达性 ✅ 有日志实证：** 北森 `zhiye.com` 从 GitHub 海外 runner **4/4 HTTP 200**（unitree/galaxea/pudutech/jaka），当次 125 家 0 失败 → **预备的「北森只能本机刷新」降级不需要启用**。探测步骤保留在工作流里（不拦截，只留证据）。
- **D 三家租户 ✅ 全部找到，无一关站：** `aurorainnovation → ashby:aurora-operations-inc`（从 aurora.tech 的 `ashbyOrgSlug` 挖到，UUID 交叉验证）、`temporaltechnologies → ashby:temporal`、`fireworksai → ashby:fireworks`。给 `Candidate` 加 `company_id`：**ATS tenant 可以漂、我们的 slug 钉死**（职位主键是 `{company_id}:{ats_job_id}`，换 slug 会让全部历史变孤儿）。实抓入库 70/57/67 岗，217 条旧岗转「下架」而非删除。
- **测试：188 passed / 0 failed / 0 skipped**（155 + 33：GLM 22 / 迁移 7 / fail-over 4）。
- **顺手发现：** `lever:mistral` 板面在线但返回空数组（本次 seed 唯一被拒租户），不是 slug 漂移；建议观察一周。

---

## 2026-08-31 — 017 开工回执：GLM 接入 + 存量精抽 + 快照自动刷新 + 三家租户（进行中）

- **核验过：** `pytest -q` **155 passed / 0 failed / 0 skipped**（基线）；`.env` 含 `ZHIPU_API_KEY`（未打印、不入 git）。
- **GLM 连通性实测：** base_url `https://open.bigmodel.cn/api/coding/paas/v4`；`glm-5.3` / `glm-5.3-flash` × {plain, json_mode, thinking-disabled} **6 组全 200**，中文 JD 技能抽取正确。
- **新发现（提速关键）：** `thinking:{"type":"disabled"}` 生效——reasoning tokens 242→5、completion 267→29；flash 关思考后输出带 ```json 围栏，解析须剥。
- **库存现状：** 21,413 条（活跃 14,963）；`extraction_source` deepseek 16,316 / heuristic 5,097（5,097 全部活跃）；`role_family` NULL **1,676**（全部活跃）。
- **计划：** A 加 GLM 后端（`extraction_source='glm'`，选取条件改为「不属任何 LLM 源」）+ 三方对比选型 → B 存量精抽（¥0）→ C Actions 周刷新（零密钥）→ D 三家租户。
- **风险：** GLM 配额未知（连续 429×5 即停并记进度）；Actions runner 在海外，北森 zhiye.com 可达性待实证。

---

## 2026-08-31 — 恢复会话：015 验收关单 + 补欠 5 周快照 + 目录提交（详见 reports/016）

- **015 验收：过**（七项硬指标管理者独立复核全过；pytest 155 green 亲测；OIDC 发布工作流审过批准保留）。
- **快照刷新补欠**：ingest 新 5,097/更 3,957/下架 4,484；role_family 启发式补标 3,421（¥0）；快照 **125 家 / 21,413 行（在招 14,963）/ 24.6MB**，资产 updatedAt=2026-08-31T06:01:01Z，零用户态通过。
- **3 家租户持续 404 待查**：aurorainnovation / temporaltechnologies / fireworksai（疑 slug 漂移）。
- **目录**：Glama 已自动收录 ✅；mcp.so 已提交（chatmcp/mcpso#3845，领导批准）；PulseMCP 等其恢复自动拉取；Show HN 定稿在 drafts/（不入 git）。
- **待办候选**：快照刷新自动化（Actions 每周）、1,676 条 role_family NULL 付费补标（需批预算）、Moka 适配器、404 租户调查。

---

## 2026-07-27 — 015 v0.2.0 已发布（✅ 7 项硬指标全达成，详见 reports/015）

**当前状态：v0.2.0 已上线 PyPI + GitHub Release + 新快照 · 155 tests green · 本单花费 ¥11.59**

- **PyPI 0.2.0 ✅** https://pypi.org/project/openhire/0.2.0/ —— 全新隔离 venv 从 PyPI 实装验证：`ohp version`=0.2.0、`all_vendors()` 含 **beisen**、MCP stdio 握手列出 **5 工具**、`search_jobs` 调用无误。（上传前先用同法验过本地 wheel。）
- **GitHub Release v0.2.0 ✅**（变更说明，**0 资产**）；**快照资产仍留在 v0.1.0 稳定 URL**，`ohp bootstrap` 跨版本不断链。
- **新快照 ✅** 公司 **125** · 职位 **16,316** · 18.3MB · 零用户态校验通过；**时序合规**：PyPI `14:19:09Z` → 资产 `14:35:26Z`（资产更晚）。真·新用户端到端（PyPI 0.2.0 + 已发布快照）：「龄 0 天前」，且 `--currency CNY --role-family engineering --min-salary 300000` 能搜到**宇树岗**。
- **ingest 未强制 `--all`：** freshness 未到期、索引本就是当日的；强刷会用 heuristic 覆盖刚花钱买的 DeepSeek 抽取结果。
- **官方 Registry ✅ 0.2.0 · isLatest:true**（`published 2026-07-27T14:47:43Z`）。曲折：011 那枚 JWT 已过期 → `publish` 报 401；按止损条款**不自行找回/重置凭据**，走 device-code 交用户授权但超时作废。**遂改用 GitHub Actions OIDC 根治**——新增 `.github/workflows/publish-mcp-registry.yml`（`id-token: write`），用**仓库自身身份**证明归属 `io.github.gzchenhao/*`，**没有任何令牌需要经手、也没有会过期的东西**。首跑 Verify 步骤误报（search 返回全部历史版本且旧版在前，我取了 `servers[0]`）已修为按 `isLatest` 判定 + 显式 utf-8。
- **副产品：** 以后发版只需 bump `server.json` + 推 `v*` tag（或点 Run workflow），不必再碰 `mcp-publisher` 登录。`BLOCKED.md` 已删除。
- **下一步：** 三方目录（glama/mcp.so/PulseMCP）仍需主动提交（对外动作待批）。

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

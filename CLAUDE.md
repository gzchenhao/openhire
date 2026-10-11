# CLAUDE.md — OpenHire 工作约定（每个会话必读）

## 新会话恢复指引（开工前先做这三步）

1. **先读 `README.md`** — 了解产品定位、五个协议字段、三条隐私红线、安装与工具（公开版 README）。
2. **再读 `PROGRESS.md`** — 了解已完成到哪一步、关键决策与理由、下一步、待用户确认事项。
3. **禁止重做已完成的工作。** M1–M4 已全部完成，**v0.1 已公开发布**（见下方发布状态、PROGRESS.md 验收证据）。除非用户明确要求返工，不要重建已完成的里程碑。

## 发布状态（最新 v0.8.2 · 2026-10-11；v0.1 首发 2026-07-15）

- **GitHub：** https://github.com/gzchenhao/openhire （owner `gzchenhao`，main，最新 tag v0.8.2 由 Actions 建）
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
  发版时一条 `sed 's/0\.6\.x/0\.6\.y/g'` 把这**十一个**文件一起换；**第十二处 `uv.lock` 不用 sed，bump 后跑 `uv lock` 重生成**（目录 Verified 徽章要 pyproject + uv.lock；单文件上限 256 KiB，现约 240 KB）；`tests/test_release.py` 全部钉死。插件图标 `.claude-plugin/icon.png`（512px，目录只在首次提交时采用）。
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
  从 Registry 自动收录的有 mcpservers.org、mcpmarket.com、Glama；**PulseMCP 和 mcp.so 没有我们**（2026-09-28 核实，此前写「自动同步」是错的）。
- **上架渠道全景（057，2026-09-28）：** 仓库本身已是 **Claude Code 插件市场**（`.claude-plugin/`，用户 `/plugin marketplace add gzchenhao/openhire` + `/plugin install openhire@openhire`，端到端实测过）、
  **Cursor 插件**（`.cursor-plugin/plugin.json`）和 **Agent Plugins 标准包**（根目录 `plugin.json` + `mcp.json`）。已提：火山引擎 `volcengine/mcp-server` PR #437、mcp.so 目录 `chatmcp/mcpso` issue #4473。
  README 有 TRAE 一键导入链接。**Anthropic 目录已提交（2026-10-08，`reports/058`）**：插件页 https://claude.ai/directory/manage/plugins/1a281d9a-66a9-437d-a666-5635047cc35a （领导 Max 账号登录才能看），等待安全扫描 + 人工审核（三类保留项，答复在 058 第四节）；审核邮件到领导 icloud 邮箱。
  内置浏览器面板打不开 claude.ai，这类操作走 Chrome 扩展。接受目录条款那一勾每次都要领导在对话里明确说「可以」。push webhook 领导已装好（密钥不经我手），推 main 几分钟内目录就读到新版本。
  **仍要领导登录的**：Cursor Marketplace、cursor.directory、Smithery、LobeHub、AIBase；清单在 `drafts/listing-handoff-2026-09-28.md`。
  **SECURITY.md + GitHub 私密漏洞报告（2026-10-08 开启）**：目录条款要求漏洞报告机制；报告落在仓库 Security → Advisories，领导邮箱收通知，承诺 3 天确认、14 天评估。
  **不可**：扣子 / 讯飞星辰 / ChatGPT Apps / 元器都要公网托管端点；百炼、千帆、华为云、豆包、TRAE 市场无第三方入口；Goose 停收，PulseMCP 停收，Continue 没了。
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
  **云端写稿交接：** 云端会话同时选 `openhire` 和 `openhire-private` 两个仓库，稿子写在 `openhire-private` 根目录（它就是本机的 `drafts/`），提交并推它的 main。
  不要写进 `openhire/drafts/`：那里被 gitignore，推不上去，会话结束就丢。本机发布前先跑上面那条同步命令把稿拉下来。
  同步脚本 2026-10-10 起是**双向三方合并**（`drafts/.sync-state.json` 记上次同步时每个文件的内容）：只有一边改了就同步那边，两边都改了报 CONFLICT、不覆盖，人工合并后 `--resolved <文件>`。
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
2. 邮箱 `gdchenhao@qq.com`（认领的非 GitHub 通道，我读不到，**需要提醒领导自己看**）
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

6. **称呼与用词（领导 2026-10-08 定）。** 对雇主一律「贵公司」，不写「贵司」（语法错误）；「小公司」带贬义，正文用「中小型公司」或「小型公司」，只有引用问题原文时照抄。

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
    **只在 DeepSeek 低价时段跑（领导 2026-09-23 定）。** 官方定价页（api-docs.deepseek.com/quick_start/pricing）：
    高价时段 = **工作日 UTC 01:00–04:00 和 06:00–10:00**，即**北京时间 09:00–12:00、14:00–18:00**；
    其余时间、周末、中国法定假日全天都是半价。本机时钟是 UTC+7，别拿本机时间当北京时间，先 `date -u`。
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
  **禁止「特征探测」（2026-09-24 定）：** 被站点拦下（WAF / 反爬 / 567 之类）之后，**不许为了「弄清它是按什么拦的」而改变我们客户端的任何身份特征再试一次**
  （改 User-Agent 伪装浏览器、改 TLS cipher / 指纹、换 IP、带别人的 cookie 都算）。哪怕只试一次、哪怕不放进代码，那也是在试另一把钥匙。
  允许的只有三样：读拦截页本身、读 robots.txt、用**完全相同**的请求再试一次以排除偶发。判定「被拦 = 停」不需要知道它按什么拦。
  出处：蔚来 `www.nio.cn` 的 EdgeOne 567，实现 agent 为验证「按 TLS 指纹拦」发过一次改 cipher list 的诊断请求（拿到 200，未入代码），审查者判越线，领导 2026-09-24 问明后定为禁止。
- **抽取/解析规则变更要影响存量数据：必须先失效 content_hash**，否则重抓一律被判「未变」而空转（020 福瑞泰克「元/天→假月薪」修复的教训）。

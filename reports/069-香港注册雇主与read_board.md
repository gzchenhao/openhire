# 069 · 求职者视角第二轮：目标改为「香港注册雇主、地点不限」，OpenHire 加 `read_board`（0.8.3）（2026-10-11，云端会话）

领导在 068 之后把目标说清了：雇主是香港注册公司、发港薪即可，上班地点不限，因为 2027 年 12 月要续签高才通；投香港企业不需要中文简历；不受 ATS 限制，站在求职者角度要的是结果；第二个角色（OpenHire 项目经理）要观察求职者要什么，怎样帮到求职者就怎样改造 OpenHire。领导已说明：不要再问，全部放行。

## 一、这个目标暴露的产品缺口

求职者真正的筛选条件是**雇主主体的注册地**（香港公司），不是岗位地点。没有任何招聘网站给这个字段，OpenHire 也没有。索引里「地点含香港」只有 10 条、3 家，而索引只覆盖三个行业；领导的市场比索引大得多。三件事决定了这轮改什么：

1. 索引之外的雇主，只要招聘系统在我们已经会读的五家供应商上（Greenhouse、Lever、Ashby、Moka、北森），适配器现成，缺的只是「按需读、不入库」这一层。这就是 0.8.3 的 `read_board`。
2. 「是不是香港注册公司」目前只能靠公司註冊處免费查名（0.8.2 已把链接放进 `pending_user`）。公司註冊處在 data.gov.hk 有开放接口，但云端容器连不上 gov.hk，规格没法验证，这轮不上。
3. 猜雇主的招聘板地址会猜错（下面 12 家猜错 6 家，全是 404）。下一步要做「给公司官网，自动找到它的招聘板」。

## 二、0.8.3：`read_board`（CLI `ohp read-board`）

- 输入求职者贴的招聘页 URL，`ats/boards.py` 解析成适配器要的 (vendor, tenant)：`job-boards.greenhouse.io/<board>`、`boards.greenhouse.io/embed/job_board?for=`、`jobs.lever.co/<site>`、`jobs.ashbyhq.com/<board>`、`app.mokahr.com/apply/<org>/<siteId>`、`<tenant>.zhiye.com`，以及各家的 API 形式。
- 现读：`pipeline/crawler.py` 新增 `fetch_board`，用周抓取同一套客户端、超时和 User-Agent，一次读一个板；服务层 `service.read_board` 不碰网络（`tests/test_three_nos.py` 钉死 service 不许出现 httpx）。有事件循环时自动换到工作线程跑，CLI 和 MCP 都能用。
- 输出：板上岗位的标题、地点、板自己的发布日与在架天数（没有就 `date_signal: not_reported_by_ats`）、雇主自己租户上的投递链接、JD 摘录；`location` 过滤复用搜索的中英文别名表，`title` 过滤复用 HR 同义词组；按发布日倒序、无日期的排最后；`total_matching` 与 `truncated`。
- 不给什么：skills、ghost_score、重挂记录、watch，这些都要反复观察；**什么都不入库**。雇主已在索引里就提示改用 `search_jobs`。
- 拒绝什么：飞书招聘 / Lark（请求签名）、Workday、SuccessFactors、Taleo、iCIMS、LinkedIn、JobsDB、BOSS 直聘，一律 `ERR_UNSUPPORTED_BOARD` 加原因，告诉用户自己打开，不找别的路进去。
- 礼貌：每个进程每个板 15 分钟内只现读一次，重复请求从内存答（`from_cache: true`）；板不答复就说「板没有答复」，不说成雇主的问题，也不缓存失败。
- 隐私说明 §3 加一条：只把租户名发给供应商的公开接口，和周抓取同一个请求，用户的任何信息不发，读到的不存。
- 测试 622（新增 11 条：URL 解析表、封闭门户拒绝表、现读与过滤与不入库、缓存与失败不缓存、工具注册与说明）。推 main 后由 Actions 自动发版。

### 实测（2026-10-11，云端容器能连五家供应商的接口）

| 招聘板 | 板上 | 地点含香港 | 说明 |
|---|---|---|---|
| UiPath（Ashby） | 107 | 3 | Senior Partner Sales Manager (Agentic AI Automation) 08-27 发布 |
| AIFT / OneDegree（Greenhouse） | 26 | 10 | Head of Partnership 在架 1,620 天未动 |
| Airwallex（Ashby） | 526 | 18 | GTM Partnerships Manager (Partner Acquisition) 06-29 |
| Lalamove（Lever） | 180 | 51 | Data Enablement Lead 07-24、Strategy & Analytics 09-02 |
| OKX（Greenhouse） | 346 | 13 | AI Enablement PMO Director 07-24、VP AI Strategy & Transformation 03-31、Senior Talent Acquisition Partner 07-16、Senior Manager Global Partnerships 07-31 |
| Animoca Brands（Lever） | 15 | 3 | Talent Acquisition Specialist（6 个月合约）09-29、Director Institutional Distribution & Partnerships 09-02 |
| Lynx Analytics（Greenhouse） | 7 | 0 | 全在美国、印度 |
| Klook、Crypto.com、WeLab、Prenetics、HashKey、Hex Trust、Bowtie | 404 | | 租户名是猜的，猜错了；工具如实说「板没有答复」 |

## 三、求职者侧：按新目标的候选清单

高才通续签：入境处要求延长逗留时证明已在香港受聘并有稳定收入，或已在香港开办或参与业务；2025 年报道称受聘者要提交雇佣合约并证明薪酬达市场水平；2026-01-30 起递交延期申请前须先完成指定问卷（KPMG 2026-02 解读）。另有报道称年薪 250 万以上受聘于非本港企业且有纳税也可续签三年，这条只见于媒体，以入境处官网为准：https://www.immd.gov.hk/hkt/services/visas/TTPS.html 。所以「香港公司受聘、港薪、有稳定收入」是硬条件，上班地点确实不是。

**第一梯队（香港注册公司，头衔正是「AI 原生 + 生态 / 人才」方向，都是雇主自己的招聘板现读，投递链接在雇主自己租户上）：**
- OKX：AI Enablement PMO Director（07-24，78 天）、Vice President, AI Strategy & Transformation（03-31，194 天）、Senior Strategy PMO / Project Manager (AI & Org)（03-03）、Senior Talent Acquisition Partner（07-16）、Senior Manager, Global Partnerships（07-31）。加密行业，要看清雇佣主体是哪家香港公司。
- UiPath 香港：Senior Partner Sales Manager (Agentic AI Automation)（08-27，45 天），生态伙伴拓展；Customer Engineering Director（06-18）。UiPath 在港有实体，雇佣主体要在 offer 阶段确认。
- Airwallex：GTM Partnerships Manager (Partner Acquisition)（06-29，104 天）。
- Animoca Brands：Director, Institutional Distribution & Partnerships（09-02）；Talent Acquisition Specialist 6 个月合约（09-29，合约工能否续签要先问入境处）。
- Lalamove：Data Enablement Lead（07-24）。

**第二梯队（索引内，地点含香港）：** 驭势科技「项目经理（海外项目）」（09-08，32 天，香港离岛区在四个地点里，雇佣主体要问清是不是香港公司）；MongoDB 香港 CSM 两条。

**第三梯队（机构，自建站或 SuccessFactors，去官网投，均为摘要未亲自打开）：** HKSTP Senior Manager, Partnerships 与 Assistant Director, InnoHK and University Collaborations（08-21）；ASTRI 策略经理；中科院香港创新院 HR Manager；商汤香港公共事务 / 政府关系经理；华为香港研究所 Technology Cooperation Manager；宏利 AI Adoption Manager, Asia（07-31，可能已关）。

**不用再出中文简历**，英文通用版已交付。

防骗：第一、二梯队全部从雇主自己的招聘系统读出，投递链接只在雇主自己的租户上；公司主体到公司註冊處电子服务网站免费查名核对；任何要你先付费、出境面试、交护照的一律停。

## 四、项目经理侧

从这轮看，求职者要的不是「一个更好的岗位库」，是四个动作一站式：找得到（索引 + 索引外任何会读的板）、看得清（在架时长、板自己的日期）、查得了（企业查证）、投得出（雇主自己的投递页）。0.8.3 把「找得到」从索引扩到了索引外的五家供应商，这是这轮最大的一步。打分从 76 提到约 **82 / 100**：便捷 8、金钱 10、时间 8、高效 7、可信 8。

路线图（按对求职者的价值排序，领导定）：
1. **按官网找板**：给公司域名或官网，GET 一次它的招聘页，找出指向五家供应商的链接，再 `read_board`。这轮猜租户名 12 家错 6 家，这一步能把「给公司名就能读」做实。一次 GET，和首页备案号检查同一类请求。
2. **香港注册核对**：公司註冊處 data.gov.hk 开放接口（按名称或 BRN 查成立日期），先在本机验证接口与条款，再进 `check_employer`；成了就能直接回答「这家是不是香港公司」。
3. `read_board` 结果可加 watch：求职者指定一个板，周快照之外由助手定期重读并报新增与消失（生命周期信号，068 第 1 条的索引外版本）。
4. 支持 Workable 与 SmartRecruiters 两家公开接口的供应商（香港中小型公司常用），覆盖再扩一圈；SuccessFactors / Workday 没有公开接口，不做。
5. 068 的其余项不变：relist 年龄下限、投递难度字段、制裁与 LEI 核对、HR 与 AI-enablement 族。

## 五、证据

- 测试：`.venv/bin/pytest -q` → `622 passed`。
- 实测：`ohp read-board https://jobs.ashbyhq.com/uipath --location "Hong Kong"` 等 12 板，结果见第二节表。
- 提交：`ca69fb0`（0.8.3）在 main。

汇报已写入 C:\openhire\reports\069-香港注册雇主与read_board.md

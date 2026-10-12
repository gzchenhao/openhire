# 075 · Workable 与 SmartRecruiters 适配器：做市商思维的落地，吃长尾雇主（0.8.6）（2026-10-12，云端会话）

073 的结论是：做市商靠覆盖更多标的赚钱，对 OpenHire 标的是雇主，一个 ATS 供应商的适配器写一次，之后该供应商上每一家雇主边际成本为零。领导批了「这个可以做了」，本版加两家供应商。

## 一、加了什么

| 供应商 | 公开接口（无 key） | 一次读到什么 | 板地址形态 |
|---|---|---|---|
| Workable | `apply.workable.com/api/v1/widget/accounts/<subdomain>?details=true`（供应商文档里的 Widget API） | 全部在架岗位，含描述、要求、福利 HTML；`published_on` 是裸日期，存成当天 00:00 UTC；无薪资、无最后改动时间 | `apply.workable.com/<subdomain>`、`<subdomain>.workable.com` |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/<company>/postings?limit=100&offset=N` 分页；每条再读 `/postings/<id>` 取描述与投递链接 | 名称、发布时间、地点在列表里；描述在详情里；详情调用限 6 并发，单条失败不影响整批 | `jobs.smartrecruiters.com/<company>`、`careers.smartrecruiters.com/<company>` |

两家都接进 `read_board`、`watch_intent(board_url=...)` 和将来的 `ohp seed`；投递链接只信各自的雇主租户主机（`apply.workable.com`、`jobs.smartrecruiters.com`）且必须带岗位 id，否则退回我们按规则拼的租户页。`ats/base.py` 的 `ATS_APPLY_HOSTS` 和 `canonical_apply_url` 各加两行，`tests/test_three_nos.py` 的边界不变。

## 二、老实话：云端没法实测，先靠文档和测试，再靠本机现读

云端容器的出网白名单不含 `apply.workable.com` 和 `api.smartrecruiters.com`，两家文档站也打不开。两个适配器按供应商公开文档的字段写，解析对字段名做了容错（`shortcode` 或 `id`、`locations[0]` 或 `city/state/country`、`fullLocation` 或拼接），19 条测试在固定载荷和 mock 传输上钉住解析与分页逻辑。**第一次真实读取放在本机任务队列**：私库 `local-tasks.json` 排了 `read-board https://apply.workable.com/robotec-ai/`（Robotec.ai，机器人仿真，搜索引擎里唯一能确认的 Workable 租户）和 `read-board https://jobs.smartrecruiters.com/BoschGroup`（博世，租户标识是猜的，404 就如实报）。结果回来若与文档不符，按载荷改，再发一版。

## 三、索引里还没有这两家的雇主

本版只让「读板」和「盯板」认识这两家供应商；公开索引的来源说明仍是「Greenhouse、Lever、Ashby、北森、Moka 加首方站」，没有改，因为种子表里还没有 Workable 或 SmartRecruiters 的雇主。下一步是找目标行业（AI 基础设施、智驾、具身）里用这两家的雇主进种子表，每加一家都要先本机实测再入库，和 `ohp seed` 的规矩一样。

## 四、证据

- 测试：`654 passed`（0.8.5 是 636，新增 18 条：两家解析、Workable 取数校验、SmartRecruiters 分页与详情合并、无公开 feed 的租户、八种板地址、四种非租户地址、`read_board` 端到端）。
- 十二处版本号到 0.8.6（含 `uv lock`），推 main 自动发版。

今日请备份 `C:\openhire` 到 U 盘。

汇报已写入 C:\openhire\reports\075-Workable与SmartRecruiters适配器-长尾雇主-0.8.6.md

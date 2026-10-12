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

## 五、本机实测补记（10-12 夜，`local-results/` 21:53 那轮）

第一轮（21:08）8 个任务里 6 个「失败」，原因不在雇主：本机 `ohp --json` 在 PowerShell 管道里按 GBK 输出中文，`run_local_tasks.py` 按 UTF-8 读，解码报错后结果记成「退出码 0、无输出」。脚本已修（main `60055b5`：子进程强制 `PYTHONIOENCODING=utf-8`，解不出的字节替换不报错，失败摘要写明原因；脚本不随包发版），重跑 8 个全过。

| 板 | 结果 | 和文档的出入 |
|---|---|---|
| Workable `apply.workable.com/robotec-ai/` | 200，6 条在架：AI Engineer（09-30，12 天）、Marketing Automation Engineer（06-30，104 天）、Ecosystem Evangelist（03-17，209 天）、IT Recruiter（02-10，244 天）等；地点 `Warsaw, Masovian Voivodeship, Poland`；描述齐；`published_on` 全部有，`date_signal = ats_reported` | 投递链接是供应商自己给的 `apply.workable.com/j/<shortcode>/apply`（主机在白名单里，照用），不是我们按规则拼的 `/<tenant>/j/<id>/`；六条 `remote_policy` 全是 `unknown`，因为 widget 只给 `telecommuting: false`、没有 `workplace` 字段，「不是远程」不等于「现场」，如实报 unknown |
| SmartRecruiters `jobs.smartrecruiters.com/BoschGroup` | 200，板上 4,947 条（分页读到底，没碰 50 页上限），`--location Germany` 匹配 738 条，返回 30 条（默认 limit）；30 条全部带描述、投递链接全部是详情里的 `jobs.smartrecruiters.com/BoschGroup/<id>-<slug>?oga=true`，没有一条退回拼接链接，说明详情调用没有被限流；`releasedDate` 到日，当天发布的 `days_open = 0` | `location.hybrid` 字段文档里没写但载荷里有，解析已经认；`location.remote = true` 的「Servicetechniker Gebäudeautomation」是外勤岗，这是博世自己的标记，按「ATS 原生字段优先」原样报，不替雇主改 |

结论：两个适配器在真实载荷上不用改。两条待办进路线图：① 大租户每次现读要打和岗位数一样多的详情调用（博世 4,947 次），`read_board` 和盯板应先按地点、标题过滤再取详情；② Workable `workplace` 值若写成 `on-site`（带连字符）现在会落到 unknown，下次发版顺手放宽。

今日请备份 `C:\openhire` 到 U 盘。

汇报已写入 C:\openhire\reports\075-Workable与SmartRecruiters适配器-长尾雇主-0.8.6.md

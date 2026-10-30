# 雇主发现：自动驾驶与具身智能（2026-10-30）

云端会话按任务单逐家查官网招聘页，确认招聘系统（ATS）与租户名；OpenHire 能读的系统用 `ohp read-board <板> --limit 3 --json` 现读一次。逐家明细在同目录 `discovery-2026-10-30.json`。

**读法规矩：** 默认 httpx 客户端与 Playwright 默认设置，不改 User-Agent、不带 cookie、不登录、不做签名；遵守 robots.txt；遇 403 / 429 / WAF 记被拦跳过、不换办法重试；每家之间停 3 到 5 秒。不改代码，只写这两个文件。

## 各状态家数

共 99 家（任务单里已在 `candidates.py` 或 `not_indexed.py` 的跳过，含驭势 UISEE，它已在 Moka 种子表里）。

| 状态 | 家数 |
|---|---|
| readable（OpenHire 现有读法读得到） | 31 |
| unsupported_ats（系统不支持，或自建页） | 29 |
| blocked（官网 403 / 429 / WAF 或 robots 不许） | 21 |
| no_jobs_page（没有在招页面） | 10 |
| not_found（没找到可用的板或官网连不上） | 8 |

readable 的 31 家现读合计 **6,023 条**在架（2026-10-30 现读；追觅 2,000 条可能是读法上限）。

## 不支持的系统，按出现次数

这一节决定下一步先写哪个系统的读法。

| 系统 | 家数 | 雇主 |
|---|---|---|
| 自建页 / 自建站（无第三方 ATS） | 9 | Mobileye、Verdant Robotics、Tensor Auto、Zipline、Aptiv、Oxa、Foretellix、iMotion 知行科技、Exyn |
| Rippling | 4 | Forterra、Foundation Robotics、Mytra、Bonsai Robotics |
| Comeet | 3 | Mentee Robotics、Innoviz、Imagry |
| Personio | 2 | Wandelbots、Franka Robotics |
| Dover | 2 | Weave Robotics、Scythe Robotics |
| JazzHR | 1 | Ouster |
| Teamtailor | 1 | Starship Technologies |
| BambooHR | 1 | Plus One Robotics |
| Breezy | 1 | RightHand Robotics |
| Kula | 1 | Sanctuary AI |
| TalentsConnect（job-shop） | 1 | Neura Robotics |
| SuccessFactors | 1 | Universal Robots |
| Feishu 飞书 | 1 | Neolix 新石器 |
| Dayee 大易 | 1 | 高仙 Gausium |

第三方系统里 **Rippling（4 家）** 最多，其次 **Comeet（3 家，以色列系：Innoviz、Imagry、Mentee）**、Personio 与 Dover 各 2 家。自建页 9 家没有统一读法。飞书（新石器）按 020 判例不读；大易（高仙）和地平线同一系统，读法未评估。

## readable 的雇主（按现读条数）

| 雇主 | 行业 | 系统 | 租户 | 条数 |
|---|---|---|---|---|
| Anduril | autonomous_driving | Greenhouse | `andurilindustries` | 2,555 |
| 追觅 Dreame | embodied_ai | Beisen 北森 | `dreame` | 2,000 |
| Applied Intuition | autonomous_driving | Ashby | `applied` | 327 |
| Skydio | autonomous_driving | Ashby | `skydio` | 185 |
| Humanoid | embodied_ai | Ashby | `humanoid` | 96 |
| Mujin | embodied_ai | Lever | `mujininc` | 88 |
| Boston Dynamics | embodied_ai | Workday | `bostondynamics.wd1/Boston_Dynamics` | 87 |
| Tutor Intelligence | embodied_ai | Lever | `tutorintelligence` | 59 |
| Bedrock Robotics | embodied_ai | Ashby | `bedrock-robotics` | 58 |
| Wing | autonomous_driving | Greenhouse | `wing` | 56 |
| Avride | autonomous_driving | Greenhouse | `avride` | 46 |
| PlusAI | autonomous_driving | Lever | `plus-2` | 45 |
| Aeva | autonomous_driving | Lever | `aeva` | 45 |
| Formic | embodied_ai | Greenhouse | `formic` | 41 |
| Nimble Robotics | embodied_ai | Greenhouse | `nimblerobotics` | 40 |
| May Mobility | autonomous_driving | Greenhouse | `maymobility` | 38 |
| AutoStore | embodied_ai | Workday | `autostore.wd3/autostore` | 33 |
| RobCo | embodied_ai | Ashby | `robco` | 32 |
| Machina Labs | embodied_ai | Lever | `MachinaLabs` | 28 |
| Serve Robotics | embodied_ai | Ashby | `serverobotics` | 27 |
| Persona AI | embodied_ai | Ashby | `persona.ai` | 27 |
| Gecko Robotics | embodied_ai | Ashby | `gecko-robotics` | 21 |
| Simbe Robotics | embodied_ai | Lever | `SimbeRobotics` | 17 |
| Stack AV | autonomous_driving | Greenhouse | `stackav` | 13 |
| Diligent Robotics | embodied_ai | Greenhouse | `diligentrobotics` | 10 |
| Brain Corp | embodied_ai | Greenhouse | `braincorporation` | 10 |
| Pickle Robot | embodied_ai | Lever | `picklerobot` | 9 |
| Viam | embodied_ai | Greenhouse | `viamrobotics` | 8 |
| Reflex Robotics | embodied_ai | Ashby | `ReflexRobotics` | 8 |
| The Bot Company | embodied_ai | Ashby | `thebotcompany` | 7 |
| Coco Robotics | embodied_ai | Ashby | `cocodelivery` | 7 |

## 要留意的几家

- **Aeva：** 官网用 WordPress 的 Lever 插件在服务端取岗位，页面不露租户；按公司名试读 `aeva` 得 45 条激光雷达岗，判定是本人。
- **Mobileye：** 官网仍有 `jobs.lever.co/mobileye` 旧链接，板子 404；在用的是自建站 careers.mobileye.com。
- **Dusty Robotics：** 官网链 Greenhouse `dustyrobotics`，板子 404，记 not_found。
- **Luminar：** luminartech.com/careers 404，官网链到 MicroVision 的招聘页（Lever `microvision`，2 条），不算 Luminar 的板。
- **Zipline：** 第三方说后端是 Greenhouse，官网渲染后没露 ATS 地址，按规矩没猜租户试读。
- **被拦 21 家**多是 Cloudflare 一类对默认客户端回 403（Locus、Symbotic、Berkshire Grey、Exotec、ANYbotics 等）；Cognata、Kargobot 是 robots.txt 不许抓招聘页；优艾智合是宝塔 WAF。
- **连不上 4 家**（K-Scale、Glacier、Electric Sheep、达闼）是本会话出网代理拒绝或对方不通，不说明对方有问题，本机可再查一次。

## 下一步建议

1. readable 的 31 家可直接进种子表（进之前照惯例由 `ohp seed` 再核一次）；Anduril（2,555 条）、追觅（2,000）体量大、非目标岗多，进不进由领导定。
2. 新读法先评估 Rippling（4 家，有公开的 `ats.rippling.com/<租户>/jobs` 页），再看 Comeet。
3. 被拦与连不上的 25 家交本机按同样规矩复查一次（只许同样请求再试）。

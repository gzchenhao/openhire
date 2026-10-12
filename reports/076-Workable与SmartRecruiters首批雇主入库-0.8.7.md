# 076 · Workable 与 SmartRecruiters 首批六家雇主入库（v0.8.7，2026-10-12 夜）

## 背景

075 把两个适配器按供应商文档写出来，第一次真实读取排在本机任务队列。10-12 夜本机跑了三轮：第一轮 8 个任务 6 个「失败」，原因是编码（本机 `ohp --json` 在 PowerShell 管道里按 GBK 输出，脚本按 UTF-8 读；脚本已修，main `60055b5`），重跑全过，Robotec.ai 与博世两块板证明适配器在真实载荷上不用改（075 第五节）；接着用搜索引擎在两家系统上找目标行业的雇主，排了 5 家候选板，本机 22:19 一次读通。本版把读通的六家入种子表，顺手修了真实载荷教的一件事。

## 一、真实载荷教的两件事

1. **Workable 的 widget 接口把一个岗位按开放城市重复给出**，同一个 shortcode 出现两次：Flexion 的「AI Research Engineer」苏黎世一条、旧金山一条；Agile Robots 的技工 Palo Alto 一条、Petaluma 一条。入库主键是 `company:ats_job_id`，两条同主键在一次抓取里会撞；读板的 `count_on_board` 也会把「岗位 × 城市」当岗位数。修在解析层：同 shortcode 合成一行，`location` 用分号连起每个城市（`Zürich, Zurich, Switzerland; San Francisco, California, United States`），`location` 过滤照样按子串命中，一岗一主键。一条测试钉住。
2. Workable 的 `workplace` 值若写成 `on-site`（带连字符）原来落到 unknown，现在连字符和空格都剥掉再比。六条 Robotec 岗位仍报 unknown，因为 widget 只给 `telecommuting: false`、没有 `workplace` 字段，「不是远程」不等于「现场」。

## 二、入库六家（每家都是本机真实读通后才进种子表，和 `ohp seed` 的规矩一样）

| 供应商 | 租户 | 名称 | 10-12 本机现读 | 是谁 |
|---|---|---|---|---|
| Workable | `robotec-ai` | Robotec.ai | 6 条，在架 12 到 1,620 天，发布日齐 | 机器人仿真与 physical AI 工具，华沙 |
| Workable | `flexion-robotics` | Flexion Robotics | 14 行（含同岗双城），最新一条 10-12 当天发布 | 人形机器人智能层，苏黎世 + 旧金山 |
| Workable | `andromeda-robotics` | Andromeda Robotics | 16 行 | 陪伴型人形机器人，旧金山 + 墨尔本 |
| Workable | `agile-robots` | Agile Robots | 4 行（3 岗） | 工业与人形机器人，这块板只有美国岗 |
| SmartRecruiters | `AeroVect` | AeroVect | 6 条，全部 2020 到 2022 年发布，在架 1,729 到 2,140 天 | 机场自动驾驶牵引车，旧金山 |
| SmartRecruiters | `PalRobotics` | PAL Robotics | 3 条，含一条常年岗「Talented Team Player」699 天 | 人形服务机器人，巴塞罗那 |

SmartRecruiters 的租户名保留供应商的大小写（它是 URL 的一部分），公司 slug 用我们自己的小写（`aerovect`、`palrobotics`），和其他雇主一致。

没入库的：博世（SmartRecruiters，板上 4,947 条，绝大多数是客服与技工，不属索引的三个行业；`read_board` 照样能读）。

AeroVect 六条全是三四年前发布的岗位。这正是索引要如实报的事：板的日期是雇主自己的，在架天数照算，不替雇主解释，也不下判断。

## 三、文案

索引来源说明三处加上 Workable 与 SmartRecruiters：README「Where the data comes from」、MCP `instructions`、`docs/employers.html`。雇主数（143）不动：数字只准引用 `docs/numbers.json`，周一快照把六家带进公开库之后 `ohp numbers` 重生成再改。

## 四、证据

- 测试：`656 passed`（0.8.6 是 654；新增 Workable 同岗多城合并、本机任务脚本编码两条）。
- 十二处版本号到 0.8.7（`uv lock` 重生成，241 KB）。推 main 自动发版，发完核对 PyPI、Release、Registry。
- 本机结果：私库 `local-results/` 22:19 那轮六个 json 与 summary；21:53 那轮 Robotec.ai 与博世（075 第五节）。

## 五、下一步

- 周一 06:10 UTC 的快照工作流跑 `ohp seed` 时把六家带进公开库；之后 `ohp numbers` 更新 `numbers.json` 与 README 里的雇主数。
- 路线图：大租户（博世 4,947 条）每次现读要打和岗位数一样多的详情调用，`read_board` 和盯板应先按地点、标题过滤再取详情。
- 继续找两家系统上的目标行业雇主：搜索引擎按 `apply.workable.com` / `jobs.smartrecruiters.com` 域名筛，每家本机读通再入。

今日请备份 `C:\openhire` 到 U 盘。

汇报已写入 C:\openhire\reports\076-Workable与SmartRecruiters首批雇主入库-0.8.7.md

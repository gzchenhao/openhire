# 121 · Rippling 与 Personio 读取器，6 家进种子表（0.8.41，2026-10-30，云端会话）

## 背景

119 号大扫描里还读不了的系统，按家数排：自建 9、Rippling 4、Comeet 3、Personio 2、Dover 2。领导批「按家数从 career-ops（MIT 许可，注明出处）移植读取器，直接做」。这一版做了第二、第四名：Rippling 和 Personio。

## 做了什么

* `ats/rippling.py`：读 `ats.rippling.com/api/v2/board/<slug>/jobs`，一次最多 1,000 条。这个接口不给发布日期，所以每条都标 `date_signal: not_reported_by_ats`，在架天数从本索引第一次看到它那天算，和理想汽车的处理一样。投递链接是雇主在 Rippling 上的岗位页。
* `ats/personio.py`：读 `<slug>.jobs.personio.de/xml` 公开 XML，`createdAt` 是雇主系统给的发布日（`ats_reported`）。投递链接是雇主在 Personio 上的岗位页。
* `read_board`、`add_employer`、盯岗都认这两种网址；各处「支持哪些系统」的说明（README、雇主页、门户目录、服务器指令、命令行帮助）都加上了两家。
* 种子表加 6 家，各标一个行业：

| 雇主 | 系统 | 行业 | 10-30 现读在架 | 发布日 |
|---|---|---|---|---|
| Forterra | Rippling | 自动驾驶（地面无人车） | 55 | 无 |
| Foundation Robotics | Rippling | 具身智能 | 26 | 无 |
| Mytra | Rippling | 具身智能（仓储机器人） | 43 | 无 |
| Bonsai Robotics | Rippling | 具身智能（农业机器人） | 8 | 无 |
| Wandelbots | Personio | 具身智能（工业机器人软件） | 11 | 有 |
| Franka Robotics | Personio | 具身智能（机械臂） | 3 | 有 |

合计 146 条，下周一快照自动进公开索引。

## 证据

* 现读：Default 环境的子会话用我们默认的客户端读六个板，全部第一次就返回 200，没有被拦，没有重试，没有改任何身份特征。
* 全量测试 1079 passed（适配器 3 条测试在 0.8.40 之后加的）。
* 版本号十二处加 `uv lock`，推 main 由 Actions 发版。

## 下一步

* Comeet（Innoviz、Imagry、Mentee，要从招聘页取 uid 和 token）与 Dover（Weave、Scythe）。
* 自建的 9 家只能逐家看有没有机器可读页，读不了的进门户目录。
* 薪资：每条岗位带同类分位（缓存）、Levels.fyi / 对标网链接、国内公开来源（先核地址与口径）。

## 待领导

无。

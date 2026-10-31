# 122 · Comeet 读取器，Dover 不读（0.8.42，2026-10-31，云端会话）

## 背景

领导 10-30：「Comeet 和 Dover 接着做，结果出来直接发版」。119 号大扫描里 Comeet 3 家（Innoviz、Imagry、Mentee）、Dover 2 家（Weave、Scythe）。读法从 career-ops（MIT 许可，注明出处）移植。

## 现读结果（Default 环境子会话，默认客户端，没改任何身份特征）

| 雇主 | 系统 | 结果 |
|---|---|---|
| Imagry | Comeet | 读通：7 条，带完整职位描述 |
| Mentee Robotics | Comeet | 它在 Comeet 上的页面 404，找不到读取所需的编号，没收录 |
| Innoviz | 自家官网 | 整个站点（连 robots.txt）都回人机验证页，按规矩视为访问控制，停下 |
| Weave Robotics | Dover | 不读：Dover 的 robots.txt 禁止抓取 `/api/`，岗位列表正是从那里加载 |
| Scythe Robotics | Dover | 同上 |

## 做了什么

* `ats/comeet.py`：读 `www.comeet.co/careers-api/2.0/company/<uid>/positions?token=<token>&details=true`。uid 和 token 是雇主自己招聘页里明文写着的（Comeet 的网页插件），按 020 判例属于页面明文可得，不是访问控制。种子表的键是 `<slug>/<uid>/<token>`，所以 `read_board` 不能从贴来的网址直接读 Comeet，只走种子表。
  * Comeet 只给 `time_updated`（雇主最后改动时间），不给发布日。按「血统不造假」，它存成更新时间，发布日留空（`not_reported_by_ats`），在架天数从索引第一次看到算。
  * 投递链接用 Comeet 给的岗位页；不可信时退回雇主的 Comeet 招聘板，不编链接，token 不进链接。
  * 远程 / 驻场按 Comeet 自己的 `workplace_type` 填。
* Imagry 进种子表（自动驾驶），候选 214 家。
* 门户目录加 3 家：Weave、Scythe（Dover，robots 禁止）、Innoviz（人机验证），各写明原因与核对日期，公开页已重生成。
* 索引来源说明加上 Comeet。

## 证据

* 子会话现读 Imagry：返回 200，7 条；前三条为 CO-143 Algo and Control Engineer、CO-144 Hardware Practical Engineer、Deep learning team leader - Perception，地点 San Jose, CA，描述 1,734 到 3,360 字。
* 全量测试 1081 passed（新增 `tests/test_comeet.py` 2 条，门户目录测试加 3 家）。

## 下一步

* 119 号排名里剩下的是自建页 9 家，没有统一读法，逐家看有没有机器可读页，读不了的进门户目录。
* 薪资：每条岗位带同类分位、Levels.fyi / 对标网链接、国内公开来源。
* 10-30 夜的模拟求职者报告（62 条发现，1 条 high：年限把管理年限当成总年限）交每日 10:37 的定时任务处理。

## 待领导

无。

# 136 · Mentee Robotics 核过，进种子表（v0.8.57）

日期：2026-11-03（云端会话）

## 背景

135 号评估 Mobileye 时，子会话发现 Mobileye 招聘页链到 Mentee Robotics 的 Comeet 新地址；10-31（122 号）我们试过的 Mentee 地址是 404。领导：「Mentee Robotics 也核一下，能读就进种子表。」

## 怎么核的

同一个全网环境的子会话，只读：
- 先读 www.comeet.com 与 www.comeet.co 的 robots.txt，没有条目禁止 `/careers-api/` 或 `/jobs/`。
- 用我们默认的客户端标识打开公开招聘页 `https://www.comeet.com/jobs/mentee_robotics/6A.002` 一次，HTTP 200；公司编号 `6A.002` 和令牌都在页面内嵌 JSON 的明文里（和 Imagry 一样的取法，122 号定的规矩）。
- 用 `read_board` 同一条路径 `pipeline.crawler.fetch_board("comeet", key)` 读，stock 设置，200，没被拦。
- 没改任何身份特征，没提交任何代码。

## 结果

| 项 | 值 |
|---|---|
| 租户键 | `mentee_robotics/6A.002/<页面明文令牌>` |
| 在架 | 11 条，全部在 Herzliya |
| 发布日期 | 没有；只有 `time_updated`（2026-07-28 到 2026-11-02），索引里标 `not_reported_by_ats` |
| 算法类标题 | 2 / 11（AI Engineer、AI Researcher），其余是后端、DevOps、嵌入式、BSP、硬件、测试台架、机械技师、C/C++ |

## 改了什么

- `seed/candidates.py` 的 `_COMEET` 加一行，company_id `mentee-robotics`；`seed/sectors.py` 归具身智能。
- `tests/test_big_employers_1103.py` 加断言。1121 tests 全绿。
- 122 号里「Mentee 的 Comeet 页 404」这一条作废：当时的地址是死的，正确地址经 Mobileye 招聘页找到。

## 下一步

- 推 main 自动发 0.8.57。PyPI 上线后再跑一次快照刷新，Mentee 和 135 号的三家一起进公开索引。

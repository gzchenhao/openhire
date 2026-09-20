# 041 · 体验官 Round 6（MCP 真调用闭环）与两条 P3 处理

日期：2026-09-20 ｜ 测试：338 passed

## 一、体验官补上了唯一没被独立验证的路径

领导点了「信任」之后，`mcp__openhire__*` 六个工具在 WorkBuddy 侧真正加载。
体验官跑了 **8 次调用，覆盖全部 6 个工具 + 2 条边缘路径，全过**，MCP 维度独立定级 **9/10**。

| 验证点 | 结果 |
|---|---|
| `search_jobs` 过滤 | `required_skills=["rust"]` 硬生效，5 条全真 rust 岗，协议字段齐全 |
| 空结果机制 | `cobol` 返回带 `hint`/`unknown_skills`/`suggestions` 的结构化对象，不是空 `[]` |
| `get_company_info` | 只返匿名聚合信号，零候选人 PII |
| `watch_intent` + `check_watches` | pull 模型有效，拉回 20 条真实匹配 |
| **`authorize_application` 隐私红线** | **`resume_transmitted=false`**；反向 `authorized=false` 返回干净的 `ERR_NOT_AUTHORIZED`，无堆栈 |

**最硬的一条**：隐私契约在 MCP 层实锤了。这是我们唯一无法用文档证明、只能用运行结果证明的承诺。

他还**主动没调 `refresh_index`**（工具文档自己写了「别投机调用」，真调会去爬雇主的公开 ATS），
并在报告里标注这是遵守规则而非漏测。这个分寸值得记一笔。

**他同时修正了自己上一轮的判断**：P2「匹配透明度」只存在于 **CLI**（CLI 不打印 skills），
MCP 返回结构里 `skills` 是内联的。我上一轮修的正是 CLI 侧（`matched_skills` + 打印「命中 rust」），方向一致。

## 二、P3-1 薪资噪声：他报了一个，实际是三个

他举的例子是「某岗 `salary_min=50`」。我去查，**是三类不同的缺陷**，全部实测于今日索引：

| 缺陷 | 实例 | 规模 |
|---|---|---|
| **0 被当成真实下限** | Cloudflare `Senior Customer Engineer` = `0 – 292,000 USD annual` | **90 条在架** |
| **时薪被标成年薪** | Dexterity `Materials Handler` = `22 – 27 USD annual` | 数十条 |
| **min/max 单位不一致** | Fivetran `BDR` = `15 – 103,259` | 若干 |

第二类最难看：**我们在告诉 agent「这个岗位年薪 22 到 27 美元」。**

### 我自己在路上判断错了一次

我一开始跟领导说「min=0 会让 `--min-salary 200000` 把那个 29 万的岗位筛掉」。
**实测是不会** —— 过滤是 `max OR min`，max 救了它。
**缺陷不在筛选，在我们发布的内容。** 已当场更正。

### 处理

新增读时可用性判定 `usable_salary()`，判不出的就不发：

- `annual` 且 `max < 5000` → 整对都不是年薪，两个数都不发，`salary_note=ats_range_below_plausible_floor`
- `monthly` 同理，阈值 500
- `min == 0` → 只丢 min 保留 max，`salary_note=ats_reported_zero_minimum`
- `max/min > 200` → 两半不同单位，丢 min 保留 max，`salary_note=ats_min_and_max_in_different_units`

**存储一个字节都不改**，这是读时判断，将来解析器变好可以直接改结论，不需要迁移。
`require_stated_salary` 与 currency 过滤共用同一个判定 ——
**给「只看有薪资的」返回一条我们随后又抹掉薪资的行，比两种行为单独存在都糟。**

思路和 `update_signal` 一致：**宁可说「不知道」，也不发一个明显是假的数字。**

## 三、P3-2 watch 首拉返回全量

行为本身是对的（这个 watch 从没报过，全部内容对用户都是新的），代码注释也写了。
**但字段叫 `new_matches`，调用方只能从 `since: null` 去猜自己拿到的是哪一种。**

已补 `is_first_pull` 与一句 `baseline` 说明，并在 MCP 工具 docstring 里写明
**不要把首拉当成「上次之后新出现的岗位」展示给用户**。

顺带修掉这里同样的 scored-skills bug（只传 `skills` 不传 `required_skills`），
和 `search_jobs` 上一轮那个是同一个。

## 四、总评

体验官维持 **8.0/10**，MCP 维度 9/10。剩余扣分在 CLI 侧，上一轮已处理。

## 下一步

- 10/03 月报页观察期到期自动汇报
- 本月剩 1 张知乎自荐（我定）
- 雇主认领人选仍等领导

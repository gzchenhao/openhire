# 033 · 体验官 Round 2：复验、四条修复、一次差点说错的解释（2026-09-14）

## 一、先查的：快照工作流「停摆」——**是我判断错了，它没坏**

昨天我说「9/07 起停摆」。查完记录，**这个说法不成立**：

```
cron: "10 6 * * 1"        每周一 06:10 UTC
最近一次: 2026-09-07T12:20 schedule → success（22 分钟跑完）
今天:     2026-09-14 06:43 UTC，周一
已发布快照资产: updated_at 2026-09-07T12:35
```

- **它是周更，不是日更**——体验官的本地索引「9/7 静止到 9/14」是设计如此，不是故障。
- 9/07 那次排定 06:10、实际 12:20 才跑，**GitHub 的 cron 延迟了 6 小时 10 分**。
  今天延迟 33 分钟还在正常范围，不能据此判定停摆。
- 并发保护存在（`concurrency: refresh-snapshot`），手动 dispatch 会排队而非冲突。

**留下的真问题**：如果 cron 某周被 GitHub 整个跳过，**没有任何告警**——
现有机制只在「运行且失败」时发邮件，「根本没运行」是静默的。已记为待办。

## 二、复验体验官的六条新账

| # | 等级 | 复验结论 |
|---|---|---|
| N1 公司维度死路 | S1 | **成立**。`search_jobs` 12 个参数无一是公司；CLI `No such option: --company` |
| N2 雷达不扫 | S2 | **成立**（三小条，已修其一） |
| N3 启动税 7–8s | S3 | 未独立复现（本机无 uvx），**采信** |
| N4 ghost 与 verified_at 打架 | S3 | **成立，且比他说的严重**：全库 2,557/15,963（**16%**）ghost≥0.99 |
| N5 20% 重复摊给下游 | S3 | **成立** |
| N6 文档超频 | S4 | 采信，无从复验 |
| 徽章 139≠140 | — | **他半对**：`companies` 表 140 行，**有在架岗位的公司 139 家**。口径歧义，非错值 |

## 三、已修（本次，284 tests 全绿）

### N1 · `company` 过滤 —— 最贵的那条

```python
search_jobs(company="宇树")   # id / 中文名 / 英文名 / 大小写 任意片段
ohp search --company 宇树 --role-family engineering
```

设计上的两个决定：

1. **精确命中优先于子串**。否则一家名字本身是别人子串的公司（"Way" vs "Waymo"）会被淹掉。
2. **查不到的公司返回诊断对象，绝不退化成无过滤搜索**。
   后者会给出一个「看起来合理、但回答的是另一个问题」的答案——这是最坏的失败形态，
   有测试专门钉死（`test_unknown_company_returns_nothing_not_everything`）。

### N5 · `collapse_role_group` / `--distinct`

服务端折叠同岗多城市，返回 `role_group_size`。**默认关闭**——
每个城市行有独立 `job_id` 与 `apply_channel`，在地点/签证约束下是真实差异（027 已论证）。

### N2(c) · bootstrap 不再静默

`ingest` 早就有 `on_progress` 并逐家打印，**`bootstrap` 调同一个函数却没传**，
于是首次安装 20 多分钟零输出。此前我们选择「改文档说明它会静默」——
体验官说那是权宜不是修复，**他是对的**。两条抓取路径现在都传回调，并有测试禁止任一条再变哑。

### S4-02 · `--version` / `-V`

`version` 子命令一直有，但所有人第一反应敲的 `--version` 报 `No such option`。已补，带回归测试。

### S3-04 · 徽章口径

`employers` → **`employers hiring`**。139 指「有在架岗位的雇主」，表里 140 行。
不是错值，是两个人读出两个意思——那就把口径写进标签。

## 四、一次差点发出去的错误解释（本单最该记住的）

做 N4 的 `ghost_reason` 时，我按 docstring 里的公式用 `first_seen_at` 算天数，跑出来：

```
ghost=1.0   verified=2026-09-02   -> "age only: open 48d, never relisted"
```

**48 天算不出 1.0。** 查 `ingest.py:143` 才发现：
**流水线实际是按雇主自己的 `posted_at` 计龄，`first_seen_at` 只是兜底**。
按错误锚点生成的解释会在每一行上写一个自信的错话——**比不解释更糟**。

改为镜像流水线的同一锚点后：

```
宇树科技    ghost=1.0     -> age only: open 367d, never relisted
Waymo      ghost=0.7298  -> age only: open 188d, never relisted
傅利叶      ghost=0.0     -> fresh: 14d old, never relisted
```

并加测试把「解释的锚点」和「打分的锚点」钉在一起，防止将来漂移。

**教训**：docstring 写的是契约，`ingest.py` 写的是事实。两者不一致时，**代码赢**——
这和体验官自己认账的那条（「注释是别人的记忆，运行时才是事实」）是同一个教训，
一天之内我们俩各踩一次。

## 五、开发环境事故（CLAUDE.md 那个坑，第四次）

`pip install -e .` 撞上 `ohp.exe` 被占用，**包被卸载且没装回去**，
`importlib.metadata` 直接 `PackageNotFoundError`，两个测试红。

- 占用者：PID 7992 / 15072，两个 `ohp.exe serve` —— 领导 Claude Desktop 的 MCP 进程（026 记过「两个」这件事）。
- **我没有杀它们**：那是他正在用的应用，CLAUDE.md 写明正解是先退出 Claude Desktop。
- 按 CLAUDE.md 的恢复步骤重跑 `pip install -e . --no-deps`：包装回去了（0.5.1），只有 exe 替换那步失败。
- **重跑全量 pytest 确认，不靠推断**：275 → 全绿，两个失败确系安装残缺。

## 六、未做，及理由

| 项 | 状态 |
|---|---|
| N2(a) `refresh_index` MCP 工具 | **未做**。要动数据生命周期与节流策略，不是顺手能加的，单独立项 |
| N4 `last_seen_change` 字段 | **未做**。需要加列 + 迁移（`db/migrate.py` 支持），但已发布快照是旧 schema，要设计回填路径 |
| `response_sla_days` | 自 0.1 空到现在，长期项 |
| N3 启动税文档 | 待写：并列 uvx / pipx 的真实代价 + pin 版本写法 |
| N6 文档超频 | 采信。本单产出是**代码 4 项 + 文档 1 篇**，比例已经反过来了 |

## 七、下一步

1. 快照 cron 被跳过时的告警（现在是静默的）
2. `refresh_index` 立项
3. 发 0.6.0（company + distinct + ghost_reason + --version 值得一个版本号）

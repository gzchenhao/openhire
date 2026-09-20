# 044 · DeepSeek 全量抽取清偿、GLM 套餐到期、以及两次我自己的错误假设

日期：2026-09-20 ｜ 测试：370 passed

## 一、GLM 四个 key 全死了，而我们把它报成了「限流」

跑 Round 7 挖出的抽取欠账时，GLM 全部失败，输出是：

```
其中 20 条因限流（HTTP 429）未完成，重跑会从断点续上。
```

**不是限流。** 逐个 key 直接打接口：

| key | 结果 |
|---|---|
| #1 / #2 | HTTP 429 code **1309** 「您的 GLM Coding Plan 套餐已到期」 |
| #3 | HTTP 401 身份验证失败 |
| #4 | HTTP 429 code **1113** 余额不足或无可用资源包 |

**`1309` 不在死 key 判定里**（只有 1310/1113），于是「套餐到期」被当成瞬时限流，
**我们还建议操作者重跑** —— 而重跑一万次也不会续费。

### 处理

- `1309` 归入死 key；全部 key 死光时抛 `KeysExhausted`（`RateLimited` 子类，
  原有 `except RateLimited` 路径照常停机），错误信息**带上智谱自己那句话**
- `_retry_call` 对它**立刻抛出不退避** —— 否则 3,045 个岗位会把退避序列各空跑一遍
- CLI 改口：`ERR_LLM_KEYS_DEAD` +「这不是限流，重跑不会有任何改变。请先续订/更换 key」

## 二、改用 DeepSeek 跑完全量

领导决定换 DeepSeek。实测发现 `.env` 里现有的 `DEEPSEEK_API_KEY` **本来就是好的**，
不需要换 token，只需 `--backend deepseek`。

先跑 10 条实测报价（¥0.02），据此报「全量约 ¥6.7」，领导批准后全量：

```
完成 · 更新 3035/3035 · 失败 0 · 总花费 CNY 6.57
  input 2,618,565 tok / output …
在架行 extraction_source: deepseek 10,798 · glm 5,463 · heuristic 0
```

**模型选 `deepseek-flash`（默认 `deepseek-chat` 指向它），不选 `deepseek-v4-pro`** ——
理由是 flash 是唯一实测过的（10/10 成功），抽技能是结构化提取不是强推理任务，
**不为省事去赌一个没量过的模型**。

### 验收（唯一检验标准）

小鹏那个引出整件事的岗位：

```
修复前: heuristic + ['c++']
现在  : deepseek + ['c++','trajectory planning','control algorithms',
                    'autonomous driving','robotics']
```

搜 `autonomous driving` 现在能在小鹏下命中它。

（`perception` 对小鹏仍是 0 —— **印证了体验官那部分是对的**：
这个 ATS 租户里确实没有主线感知岗，只能靠扩源解决。）

## 三、两次我自己的错误假设，都是查出来的不是想出来的

### 假设一：「skills 为空只降了 89 条 ⇒ 抽取失败了」

实际 2,087 条无标签行里：

| role_family | 条数 |
|---|---|
| sales | 634 |
| ops | 529 |
| (未分类) | 375 |
| **engineering** | **298** |
| marketing | 114 |

**61% 是销售/市场/运营岗。Account Executive 本来就没有技术技能标签，返回空是正确答案。**
我差点把正确行为报成缺陷。

### 假设二：「engineering 那 298 条是被 4000 字符截断害的」

JD 长度五六千字，截断嫌疑很大。抽 52 条长 JD 实测：

```
前 4000 字符里就有技术关键词:  1
前 4000 没有、4000 之后有:     4
整篇都没有技术关键词:         47
```

**47/52 整篇 JD 都不提任何技术** —— 它们是 Engineering Manager、Senior Manager R&D、
Manufacturing Engineering Manager，**管理岗和制造岗的 JD 本来就只写职责不写技术栈**。

放宽截断只能救 4 条（8%），是个小优化，**不是我假设的那个缺陷**。

## 四、已推进公开快照

CI **做不了**这一步（工作流零密钥，没有 LLM key），所以不手动上传的话，
这 ¥6.57 的成果一个新用户都拿不到。

```
ohp snapshot-build → 140 公司 · 26,021 职位 · 零用户态校验通过
gh release upload v0.1.0 --clobber → updated 2026-09-20T12:19:28Z · 30.6 MB
```

`numbers.json` 与月报页已按新索引重新生成并推送。

## 下一步

- 扩源调研：小鹏主线智驾、鹏行（具身）是否有独立 ATS
- 可选小优化：对「前 4000 字符无技术关键词」的长 JD 放宽截断重抽（约影响 8%）
- 10/03 月报页观察期到期自动汇报
- GLM 套餐是否续订由领导定；不续订则月度精抽改走 DeepSeek（约 ¥7/次）

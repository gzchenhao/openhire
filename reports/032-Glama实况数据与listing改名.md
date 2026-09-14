# 032 · Glama 后台实况：四个零，和一处被找到的硬伤（2026-09-14）

## 背景

Frank Fiegel（Glama 创始人）9/11 回信说托管要「connect GitHub repo through glama.ai/mcp/servers」。
我据此判断需要去认领 + 配 Docker build。**这个判断链条上我连续错了三次**，直到领导问了一句
「你之前管理过我的 glama 吧？」才去查记录。

## 我的三次误判（记下来，是同一个毛病）

| # | 我看到的 | 我的判断 | 事实 |
|---|---|---|---|
| 1 | 「Login with GitHub to claim」 | 还没认领 | **早在 9/04 就认领过**（reports/021），提示只是因为**我的自动化浏览器没登录** |
| 2 | 徽章是 `Local` | 构建没成功、不可部署 | **Auto-Release 一直开着**，每次 GitHub release 自动构建，0.5.1 镜像 9/13 刚发 |
| 3 | 「下一步去配 Docker build」 | 有活要干 | **不需要配**，左侧导航里 Dockerfile / Releases 全是现成的 |

**根因**：我拿一个未登录浏览器里的残缺页面，去推断服务端真实状态。
正确顺序应该是**先查 `reports/` 和 git log**（021 白纸黑字写着认领与构建配置都做过），或者直接要截图。
另外我一度用「页面上找不到 Sign Up 字样」判断已登录——**文本匹配判断登录态本身就是错的**，
正确做法是请求一个需要鉴权的地址看是否被重定向（后来这么做，立刻拿到
`/sign-up?returnPath=...` 的确凿证据）。

## 拿到的实况数据（领导截图，近 30 天）

```
Inspection    5 tools（2026-09-12 探测）
Deployments   0 live   —— "Nobody has deployed this server on Glama"
Directory rank  Unranked
Callers 0 · Tool calls 0 · 1d/7d/30d 全 0
Search Impressions  48
Search Clicks       0     (CTR 0.0%)
Profile Views       2,110
Score 83% · Auto-Release ON
```

**四个零是干净的外部数据**：零部署、零工具调用、零搜索点击、未排名。
我们没有遥测（隐私红线），GitHub star 只有 5，snapshot 下载数被自己发版污染过——
**这是目前唯一一份没被污染的外部使用数据**。

**Profile Views 2,110 不可当真人看**：大概率混了爬虫、README 徽章、awesome-mcp-servers 的流量。

## 找到的硬伤

**Listing 的 Name 栏填的是 `io.github.gzchenhao/openhire`**——一个机器 ID。

同目录竞品叫「LogoKit Brand & Company Data」「Kyrodata — Brazil Trade, Crop & Commodity Data」
「Books & Papers MCP Server」。**48 次曝光 0 次点击**，因为搜 job 的人扫过列表看到一串
`io.github.xxx/yyy` 不会停。

## 已改（领导操作，我给文案）

| 字段 | 改前 | 改后 |
|---|---|---|
| Name | `io.github.gzchenhao/openhire` | **OpenHire — Real Job Postings, Ghost Jobs Scored** |
| Categories | Search, Open Data（3 格用了 2 格） | Search, Open Data, **Workplace & Productivity** |
| Description | 开头是「An MCP server that turns your AI assistant into a private radar...」全是行话 | 384 字符版，差异化（139 家 ATS / 真实发布日 / ghost_score）前置 |

外部已核验：`h1` 与 `<title>` 均已变为新名，机器 ID 不再出现。

**Description 限 400 字符**（领导实测报错后得知），最终版 384 字符。

## 一个值得记下的生态观察

Glama 有 **85 个分类**，我拉了全集：**没有 jobs / careers / recruiting / HR 中的任何一个**。
20,888 个 connector、86,821 个 server，这个格子是空的。

- **好消息**：我们不是在拥挤赛道里排第 300 名，而是在一个还没被命名的赛道里。
- **坏消息**：靠「分类浏览」带不来流量，**只能靠搜索词命中**——所以 Name 里带 "Job" 这个改动，
  比选哪个分类重要得多。

## 下一步（只看一个数）

24 小时后回看 Analytics，**只看 Search Clicks 是否离开 0**。
期间不做任何其他 Glama 改动，保证因果干净。若仍为 0，说明问题不在名字，换方向。

基线已存 `drafts/growth-log.md`。

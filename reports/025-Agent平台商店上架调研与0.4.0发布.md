# 025 · Agent 平台商店上架调研 + 0.4.0 发布 + 当日四项提交

日期：2026-09-11
背景：领导问「能否在腾讯 WorkBuddy 等中美 AI Agent 平台的连接器 / skill / MCP store 里出现我们的身影」，并要求继续筹划下一步发力方向。本报告先给结论，再给证据、已做的事、待领导动手的两步、下一步。

## 结论先给

1. **能，而且比推文章划算得多。** 商店是「用户主动来找」的入口，一次上架长期有效；文章是「我们推给别人」，24 小时衰减。四渠道齐发（024）证明单靠内容触达量太小，商店是补分母的正道。
2. **但所有「一键装 / 云托管」商店有一个共同前提：`uvx openhire serve` 必须零配置就能出数据。** 此前 serve 起来是空库，用户得先手动 `ohp bootstrap`，任何商店的自动检测都会把我们判成「装上没东西」。所以今天先发了 **0.4.0**（空索引自动拉快照），再去提交。
3. **中美各有一个最值得做的入口**，都已到位或只差领导登录：
   - 国外：**Docker MCP Registry**（PR 已提）+ **Cline Marketplace**（issue 已提）+ 官方 Registry 0.4.0（已自动发）；
   - 国内：**魔搭 ModelScope MCP 广场**（国内最大、免费托管、支持从 GitHub 仓库一键收录 + 自动部署检测）——只差领导登录一次，两分钟。
4. **腾讯这条线目前走不通**：腾讯云开发者 MCP 广场官方文档明写「针对第三方 MCP 产品，目前暂不提供上架与更新服务」；WorkBuddy 没有公开市场，只有内置连接器 + 用户手填自定义 MCP。我们能做的只是让用户容易手填（README 首块配置已按此优化）。
5. **一批入口要公网 HTTP 端点**（扣子插件商店、百炼、ChatGPT 插件目录、Claude 远程连接器目录），0.4.0 已支持 `--transport streamable-http`，但要有一台服务器长期跑。这是「托管期」的事，等 star / 认领数据证明值得花这笔钱再做。

## 一、平台逐个核实（全部亲自查过官方文档或提交入口，不是印象）

| 平台 | 类型 | 第三方能否提交 | 硬性要求 | 我们的状态 |
|---|---|---|---|---|
| 官方 MCP Registry | 全球索引 | ✅ | server.json + 所有权校验 | **0.4.0 已上（tag 推送触发 OIDC 工作流）** |
| Docker MCP Registry | 目录 + Docker Desktop 工具箱 | ✅ PR | 仓库根目录 Dockerfile；MIT/Apache；Docker 方构建签名 | **PR #5055 已提**（新增 `servers/openhire/server.yaml`） |
| Cline Marketplace | IDE 内市场 | ✅ issue | 400×400 PNG 图标；README 能让 Cline 自动装 | **issue #2501 已提** |
| GitHub 精选 Registry (github.com/mcp, VS Code @mcp 画廊) | 人工精选 ~250 | ⚠️ 排队 | 先上官方 Registry，再在 discussion #1257 留言申请；无明确标准与时限 | **已留言申请**（概率低，成本零） |
| Claude Desktop 扩展目录 (MCPB) | 一键安装 | ✅ Google 表单 | .mcpb 文件；隐私政策；工具注解；**明示偏好 Node.js** | .mcpb 已打包并挂 Release；**表单要上传文件，需领导操作** |
| Claude 远程连接器目录 | 云端 | ⚠️ | HTTPS 端点 + **Team/Enterprise 组织**才能进提交门户 | 个人版无入口 → 托管期 |
| ChatGPT 插件目录 (Apps SDK) | 云端 | ✅ | 远程 MCP + 审核 | 需服务器 → 托管期 |
| 魔搭 ModelScope MCP 广场 | 国内最大（1400+）| ✅ | 从 GitHub 仓库快速创建；README 首个配置块须是 `npx`/`uvx`；包在 PyPI；自动部署检测调 list_tools | **万事俱备，只差登录** |
| 腾讯云开发者 MCP 广场 | 官方+精选 | ❌ | 文档：「第三方 MCP 产品暂不提供上架」 | 不可做 |
| 腾讯 WorkBuddy | 桌面 Agent | ❌ 无市场 | 内置连接器 + 用户自填 JSON | 只能靠 README 配置块 |
| 阿里云百炼 | 云端 | ⚠️ | 支持 `uvx` 脚本托管（函数计算，按次计费）；文档未见社区发布入口 | 自用可，上架路径不明 |
| 扣子 Coze 插件商店 | 云端 | ✅ | 必须公网 HTTPS URL | 需服务器 → 托管期 |
| 百度千帆 MCP 广场 | 云端 | ❌ 个人 | 「仅面向企业级 MCP」 | 不可做 |
| 火山引擎 MCP 市场 | 云端 | ？ | 新闻稿称支持上传共享，未找到提交表单 | 待查，低优先 |

## 二、今天做了什么

### 0.4.0（commit 7b5ee37 · PyPI · Release v0.4.0 · 官方 Registry）

- `serve()`：SQLite 索引为空时自动安装公开快照（实测 140 家 / 23,874 岗 / 31 s），只走 stderr，不污染 stdio；`OPENHIRE_NO_AUTO_BOOTSTRAP=1` 可关；Postgres 跳过。
- `ohp serve --transport stdio|sse|streamable-http --host --port`（mcp SDK 1.28.1 原生支持，改动一行）。
- 五个工具加 `title` + `readOnlyHint / destructiveHint / idempotentHint / openWorldHint`（Claude 目录硬性要求；如实标注：`check_watches` 会推进游标所以不是只读）。
- `Dockerfile`（python:3.11-slim，`pip install .`，`ENTRYPOINT ohp serve`）。
- `mcpb/`：manifest 0.4、`uv` 运行时（依赖从 PyPI 解析，不打包 venv）、`privacy_policies`；`npx @anthropic-ai/mcpb validate` 通过；打包产物挂在 Release。
- `docs/PRIVACY.md` + README「Privacy Policy」节；README「Works with」首块改为 `uvx openhire@latest serve`（魔搭解析器只读第一块）。
- `docs/brand/icon.svg` → 512 / 400 PNG（雷达图案，与「求职雷达」定位一致）。
- 253 tests green。

### 提交

- Cline：https://github.com/cline/mcp-marketplace/issues/2501
- Docker：https://github.com/docker/mcp-registry/pull/5055
- GitHub 精选：https://github.com/github/github-mcp-server/discussions/1257#discussioncomment-18394819

### 其他

- 掘金作者昵称：**领导本人已提交，审核中**。（我这边自动化填表能启用保存按钮，但提交被掘金前端判「保存失败，请检查提交内容」——个人资料表单有多个联动必填项，不值得继续钻，已交回人工。）
- `.tools/mcp-publisher.exe`（v1.8.1）已下载备用；本地令牌已过期，但实际不需要它——`v*` tag 推送即由 OIDC 工作流自动发布。
- CLAUDE.md 发布状态、PROGRESS.md 已更新。

## 三、魔搭已上线（领导登录后当场完成）

**https://modelscope.cn/mcp/servers/haolu98/openhire**

- 从 GitHub 仓库快速创建，托管类型「可托管部署」，标签 招聘/求职/jobs。
- 魔搭自动解析 README 抽到了三组服务配置，**第一组正是 `uvx openhire@latest serve`**（平台默认用第一组做部署检测——这正是 0.4.0 把 README 首块改成它的原因）。
- **部署检测通过**：工具测试页显示「可部署」，五个工具全部 list 出来（Search_jobs / Get_company_info / Watch_intent / Check_watches / Authorize_application）。
- AI 自动摘的服务描述带了 markdown 残片（`](https://glama.` 之类），已手工改写成中文版。
- 遗留两点：① 详情页头部徽章仍显示 `Local / 不可部署`，与工具页的「可部署」矛盾，疑为缓存或标签延迟，观察一天；② 图标未上传（内置浏览器无文件选择器），可后补；③ 工具页有「新建部署」按钮可开一个托管 SSE 端点，**会占用魔搭账号的算力配额，未擅自点，等领导决定**。

## 四、还差一步：Claude 扩展目录表单

内置浏览器里你的 Google 账号已登录，只差上传 `dist/openhire-0.4.0.mcpb`。表单明示偏好 Node.js，我们是 Python，概率偏低，但成本两分钟。字段答案见 `drafts/marketplace-手工两步.md`。

## 五、下一步发力方向（筹划）

按「触达量」这个瓶颈排，投入产出从高到低：

1. **商店审核跟进**（零成本，等结果）：Cline 通常几天；Docker 要过 CI 构建 + 人工 review；魔搭登录后当天出结果。
2. **LinkedIn 每周一条，主阵地**（024 定档）：受众 74% 技术岗、28% 湾区。下一条形态：一个具体发现 + 一张图，不再堆特性。
3. **知乎以回答为主**（回答分发是专栏的 2.25 倍）。
4. **托管期决策点**：当 Cline/Docker/魔搭任一上架后一周内 clone 或 bootstrap 明显抬升，再评估租一台服务器跑 `streamable-http`，打开扣子 / ChatGPT / Claude 远程目录三个入口。在那之前不花这笔钱。
5. **X 不追加**。
6. **雇主认领**门槛不变（star ≥ 100 或周活 ≥ 50）。

## 六、验收证据

- `curl https://registry.modelcontextprotocol.io/v0.1/servers/io.github.gzchenhao%2Fopenhire/versions/0.4.0` → 200
- `pip download openhire==0.4.0` → 取到 wheel
- `gh release view v0.4.0` → assets: `openhire-0.4.0.mcpb`
- `pytest` → 253 passed
- 自动快照实测：`_ensure_index()` 在空库上 31.4 s 装入 140 家 / 23,874 岗，二次调用 0.00 s
- 魔搭部署检测通过：工具测试页「可部署」+ 五个工具全部列出（即平台成功从 PyPI 装包、起服务、调通 `list_tools`）——这是 0.4.0 零配置改造的端到端验证

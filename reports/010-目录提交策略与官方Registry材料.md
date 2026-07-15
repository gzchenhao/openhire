# 010 · MCP 目录提交策略（Smithery 查证 + 转投官方 Registry）

- **日期：** 2026-07-15
- **状态：** 查证完成，材料就绪。**等你过目再动**（尚未做任何提交、未改任何包）。
- **一句话结论：** Smithery 对"本地 stdio + pip 包"没有网页提交入口（只有 URL 或 MCPB 包两条 CLI 路径，均不划算）→ **v0.1 放弃 Smithery，改投官方 MCP Registry**（原生支持 PyPI 包 + stdio），PulseMCP/mcp.so 会自动从官方 Registry 抓取、无需主动提交。

---

## ① Smithery 查证结论：v0.1 放弃（有据）

- 你截图的 **Publish 表单只接受远程 MCP Server URL（HTTPS Streamable-HTTP）** —— 属实，那是"远程托管服务"的登记入口。
- Smithery **确实支持本地 stdio**，但只有两条 CLI 路径（`smithery mcp publish --help` 实测）：
  ```
  smithery mcp publish https://my-server.com -n org/name    # 远程 URL
  smithery mcp publish ./server.mcpb        -n org/name    # 本地 MCPB 包
  ```
- 也就是说要上 Smithery，要么①把服务部署成一个公网 HTTPS 服务（与"数据在你本机、简历不出户"的定位冲突），要么②把我们打成一个 **MCPB 包**（`.mcpb` 是 Anthropic 的 MCP Bundle 格式，需把 Python 服务及依赖打进 bundle，额外工程量，且对 pip 分发的包不是自然产物）。
- **判断：** 两条路对 v0.1 都不划算。**放弃 Smithery**，等以后若做了公网 HTTP 变体或 MCPB 再回来。

---

## ② 转投官方 MCP Registry（推荐主渠道）

`registry.modelcontextprotocol.io` —— MCP 官方注册中心，**原生支持 PyPI 包 + 本地 stdio**，用 `server.json` 描述、`mcp-publisher` CLI 发布，命名空间 `io.github.<你的用户名>` 绑定 GitHub 账号验证归属。**下游的 PulseMCP / mcp.so / Glama 都从它同步**，所以这是"一处发布、多处可见"的正确入口。

### 需要先做的一次小改版（0.1.1）
官方 Registry 通过"PyPI 包 README 里含一行归属标记"验证所有权；而 PyPI 同一版本的 README 不可改，所以要发一个 **0.1.1**：
1. 在 `README.md` 顶部加一行（可用 HTML 注释隐藏，不影响渲染）：
   ```
   <!-- mcp-name: io.github.gzchenhao/openhire -->
   ```
2. `pyproject.toml` 版本 `0.1.0 → 0.1.1`。
3. 重新 `python -m build` + `twine upload`（token 仍走 `.pypirc`）。
> 这步**我可代劳**（改文件 + 构建 + 上传），无新密钥。

### server.json（拟用，发布时以 `mcp-publisher init` 生成后微调为准）
```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.gzchenhao/openhire",
  "title": "OpenHire · 哨兵",
  "description": "Private radar for remote AI/Infra jobs — direct from employer ATS; your résumé never transits the server.",
  "repository": { "url": "https://github.com/gzchenhao/openhire", "source": "github" },
  "version": "0.1.1",
  "packages": [
    {
      "registryType": "pypi",
      "registryBaseUrl": "https://pypi.org",
      "identifier": "openhire",
      "version": "0.1.1",
      "runtimeHint": "uvx",
      "transport": { "type": "stdio" },
      "packageArguments": [
        { "type": "positional", "value": "serve" }
      ],
      "environmentVariables": [
        {
          "name": "OPENHIRE_DATABASE_URL",
          "description": "Optional. Postgres URL; omit to use the local SQLite index.",
          "isRequired": false
        }
      ]
    }
  ]
}
```
> 说明：客户端据此以 `uvx openhire serve` 启动我们的 stdio 服务（`serve` 参数经 `packageArguments` 传入）。`packageArguments` 字段名/格式发布时按最新 schema 校准。**无必填、无密钥环境变量**。

### 发布步骤（逐条 + 谁做）
| 步 | 命令 / 动作 | 谁做 |
|---|---|---|
| 1 | 0.1.1 小改版（README 加 mcp-name 注释 + 版本 bump + 构建 + `twine upload`） | **我可代劳** |
| 2 | 装 `mcp-publisher` CLI（Windows：从 `github.com/modelcontextprotocol/registry/releases/latest` 下 windows 版；官方 curl 一行是 unix 版） | **我可代劳** |
| 3 | `mcp-publisher init` 生成 `server.json` → 按上文微调 | **我可代劳** |
| 4 | `mcp-publisher login github` —— 浏览器授权，把 `io.github.gzchenhao` 命名空间绑到你 GitHub | **你**（浏览器，同 gh 登录，一次性；我在旁边带你走 device code） |
| 5 | `mcp-publisher publish` | **我可代劳**（授权后） |
| 6 | 验证：`curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.gzchenhao/openhire"` | **我可代劳** |

> 红线不变：不新增任何进代码/git 的密钥；`mcp-publisher` 的 GitHub 授权走它自己的本地凭据（同 gh）。

---

## ③ PulseMCP / mcp.so：无需主动提交（确认）

- **PulseMCP**（pulsemcp.com，日更 2 万+ 服务）：**自动爬 GitHub + 同步官方 Registry**。发布到官方 Registry 后会被自动收录；可选去 `pulsemcp.com/submit` "认领"列表以自定义描述/链接（非必须）。
- **mcp.so**：自动爬取 + 可选手动（导航栏 Submit 或提 GitHub issue）。低优先，非必须。
- **结论：** 这两处**不需要为发布做任何强制动作**；先把官方 Registry 搞定，它们会陆续自动收录。日后想优化展示再去认领即可。

---

## 结论与下一步（等你拍板）
1. **放弃 Smithery（v0.1）** —— 无合适的本地 stdio 网页入口，MCPB/远程两条路都不划算。
2. **主渠道 = 官方 MCP Registry**：需一次 **0.1.1 小改版**（加 mcp-name 注释 + bump），然后 `mcp-publisher` 发布；仅第 4 步 `login github` 要你在浏览器点一下，其余我代劳。
3. **PulseMCP / mcp.so**：无需主动提交，官方 Registry 发布后自动收录。

**你回一句「按官方 Registry 走」（或指示别的），我就开始做 0.1.1 小改版 + 装 mcp-publisher，到 `login github` 那步再喊你点授权。** 在此之前不动。

---
### 来源
- Smithery CLI 实测 `smithery mcp publish --help`（v4.11.1）
- 官方 Registry 发布指引（PyPI 流程、mcp-name、mcp-publisher init/login/publish）：registry.modelcontextprotocol.io 文档
- server.json PyPI 示例：modelcontextprotocol/registry `docs/reference/server-json`
- PulseMCP 提交/爬取说明：pulsemcp.com/api、pulsemcp.com/submit；mcp.so 提交说明

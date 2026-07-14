# 009 · Smithery（MCP 目录）提交确认单 —— 待你过目

- **日期：** 2026-07-14
- **约定：** 这是提交前的**最终确认单**，列出目录页要填的每个字段 + 我拟填的值。你过目后回我「**提交**」二字，我才提交；在此之前不动。
- **前提已就绪：** 仓库已含 `smithery.yaml`；GitHub/PyPI 均已上线。

---

## 一、逐字段确认（拟填值）

| # | 字段 | 拟填值 | 说明 |
|---|---|---|---|
| 1 | Repository（仓库） | `https://github.com/gzchenhao/openhire` | Smithery 会读仓库里的 `smithery.yaml` |
| 2 | Qualified name（唯一标识） | `gzchenhao/openhire` | 通常取 `owner/repo` |
| 3 | Display name（显示名） | `OpenHire · openhire-mcp` | |
| 4 | 一句话描述 | Private radar for remote AI/Infra jobs — direct from employer ATS; your résumé never transits the server. | ≤120 字符 |
| 5 | 详细描述 | 取自 README 首段（"An MCP server that turns your AI assistant … No account. No signup. No résumé upload. Ever."） | 目录支持 Markdown 长描述 |
| 6 | Homepage / Website | `https://github.com/gzchenhao/openhire` | 无独立站，用仓库 |
| 7 | 分类 / Tags | `jobs`, `recruiting`, `ats`, `greenhouse`, `lever`, `ashby`, `privacy`, `local-first` | |
| 8 | License | MIT | |
| 9 | 图标 / Logo | **无**（Smithery 会用仓库 owner 头像兜底） | 见下方决策点 B |
| 10 | 连接方式 | **stdio（本地）** | 非远程托管 |
| 11 | 运行命令 | `ohp serve` | 来自 `smithery.yaml` 的 commandFunction |
| 12 | 安装前置 | `pipx install openhire`（Python ≥ 3.11）→ 首次 `ohp bootstrap` | 见决策点 A |
| 13 | 配置 schema | `OPENHIRE_DATABASE_URL`（可选，字符串，Postgres URL；留空用本地 SQLite） | 来自 `smithery.yaml` configSchema；**无必填项、无密钥** |
| 14 | 工具清单（5） | `search_jobs` / `get_company_info` / `watch_intent` / `check_watches` / `authorize_application` | 描述取自各工具 docstring |
| 15 | 安全 / 隐私说明 | 简历/PII 绝不过服务端；只读公开 ATS；只存一枚匿名指纹；无账号无计费 | |

### `smithery.yaml`（已在仓库，Smithery 实际读取的内容）
```yaml
startCommand:
  type: stdio
  configSchema:
    type: object
    properties:
      OPENHIRE_DATABASE_URL:
        type: string
        description: Optional. Postgres URL (postgresql+psycopg://…); omit to use the local SQLite index.
    required: []
  commandFunction: |
    (config) => ({
      command: "ohp",
      args: ["serve"],
      env: config.OPENHIRE_DATABASE_URL
        ? { OPENHIRE_DATABASE_URL: config.OPENHIRE_DATABASE_URL, PYTHONIOENCODING: "utf-8" }
        : { PYTHONIOENCODING: "utf-8" }
    })
build: null
```

---

## 二、两个需要你拍板的决策点

**A. 安装方式（重要）。** Smithery 生态以 npm/Docker 为主；我们是 **Python(pip) + stdio 本地**包。两条路：
- **A1（推荐，简单诚实）：** 作为「本地 stdio 服务」上架，前置说明写清 `pipx install openhire`。用户在自己机器装好后，Smithery 配置块 `command: ohp serve` 即生效。**无需 Docker，最省事，符合 v0.1 定位。**
- **A2（可选，后续）：** 为 Smithery 托管加一个 `Dockerfile`（`pip install openhire` + `ohp serve`），支持一键远程试用。工作量更大，且远程托管与"数据在本机"的定位略有张力。**建议 v0.1 先走 A1，A2 留到以后。**

**B. 图标。** 现无 logo。可（B1）先不放，用兜底头像；（B2）你给一张 512×512 PNG 我一并提交。**建议 B1，先上架。**

> 我的默认建议：**A1 + B1**（最快上架、零额外工作）。你若同意，回「提交」即可；若选 A2 或 B2，请一并说明。

---

## 三、提交动作（你回「提交」后我会做的）
1. 在 `https://smithery.ai` 用你的 GitHub 授权登录（**这步需要你在浏览器点授权**，同 gh 登录逻辑；我会带你走）。
2. Add server → 填入本单第一节的字段 → Smithery 自动读取 `smithery.yaml`。
3. 保存后把目录页链接发你复核。

> 说明：Smithery 的账号授权只有你能在浏览器完成；字段内容按本单填。**在你回「提交」前，我不进行任何提交动作。**

---

## 四、其他 MCP 目录（可选，供参考）
- **MCP 官方 registry**（modelcontextprotocol 生态）：也可提交，形式类似（仓库 + 元数据）。
- **PulseMCP / mcp.so 等聚合站**：多为自动抓取 GitHub，通常无需主动提交。

需要的话，上架 Smithery 后我再整理这些的提交材料。

---

**结论：** 材料齐备，`smithery.yaml` 已在库。等你一句「提交」（并确认 A/B 选项，默认 A1+B1），我即带你走浏览器授权并填表；在此之前不提交。

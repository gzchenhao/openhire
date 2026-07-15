# 011 · 官方 MCP Registry 发布执行记录

- **日期：** 2026-07-15
- **状态：** ✅ **已上架官方 MCP Registry**。`io.github.gzchenhao/openhire` v0.1.1 已收录并验证。
- **背景：** Smithery 无本地 stdio 网页入口（见 `reports/010`），改投官方 Registry。

---

## 成果
- **官方 Registry：** `io.github.gzchenhao/openhire` v0.1.1
  - 查询：`curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.gzchenhao/openhire"`
  - 收录内容：pypi 包 `openhire` 0.1.1 · stdio · 启动参数 `serve` · 环境变量 `OPENHIRE_DATABASE_URL`（可选、非密钥）
- **PyPI：** 升级到 https://pypi.org/project/openhire/0.1.1/
- **GitHub：** main 已推 commit `8e4a8bf`，打标签 **v0.1.1**（快照资产仍在 v0.1.0 Release，URL 不变）

---

## 逐步执行

| 步 | 操作 | 结果 |
|---|---|---|
| 1 | 0.1.1 小改版：README 加 `<!-- mcp-name: io.github.gzchenhao/openhire -->`；版本 0.1.0→0.1.1（`pyproject` + `__init__`） | ✅ |
| 2 | `python -m build` + `twine upload`（token 仍走 `.pypirc`） | ✅ PyPI 0.1.1 上线，PKG-INFO 含 mcp-name（轮询确认 description 含归属行） |
| 3 | 下载 `mcp-publisher` v1.8.0（windows_amd64）到本地临时目录 | ✅ |
| 4 | `mcp-publisher init` 生成 server.json → 改为真值 | ✅ |
| 5 | `mcp-publisher validate` | ✅（首次报 description>100 字符，缩短后通过 `✅ server.json is valid`） |
| 6 | `mcp-publisher login github`（**用户浏览器**授权 device code `0259-6F74`） | ✅ Successfully logged in |
| 7 | `mcp-publisher publish` | ✅ Successfully published · v0.1.1 |
| 8 | Registry API 验证 | ✅ 1 条结果，metadata 正确（pypi openhire 0.1.1 · args `serve`） |
| 9 | 提交 server.json + 0.1.1 改动 + 打 tag v0.1.1 推送 | ✅ commit `8e4a8bf` |

## server.json（已入库、已发布）
命名空间 `io.github.gzchenhao/openhire`（GitHub 账号验证归属）；包 `pypi:openhire@0.1.1`；`runtimeHint: uvx`；`transport: stdio`；`packageArguments: [{positional, "serve"}]` → 客户端以 `uvx openhire serve` 启动；`OPENHIRE_DATABASE_URL` 可选。

---

## 下游目录（无需主动提交）
- **PulseMCP / mcp.so / Glama** 从官方 Registry 同步 + 自动爬 GitHub，会陆续自动收录。日后可选去 `pulsemcp.com/submit` 认领以自定义展示（非必须）。

---

## 隐私/安全红线执行
- 代码库仍零密钥；`server.json` 无任何密钥。
- PyPI token 仅 `.pypirc`；`mcp-publisher` 的 GitHub 授权走它本地凭据（device flow，用户浏览器完成），均未入代码/git。

---

## 结论
OpenHire v0.1 现已：**GitHub 源码 + Release 快照 + PyPI 包（0.1.1）+ 官方 MCP Registry 收录**四位一体，端到端可用。Smithery 按 010 结论 v0.1 放弃。**目录提交目标达成。** 后续仅剩每周快照刷新（`docs/maintainer-snapshot-refresh.md`）这一常设维护职责。

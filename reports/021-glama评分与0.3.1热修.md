# 021 · Glama 认领/评分 + 0.3.1 热修（mcp<2 生产 bug）

**日期：** 2026-09-04　**执行人：** Claude（PM 会话）　**花费：** ¥0

## 背景
按定位主线做「转化就绪」+ 分发。目标：解锁 punkpeye/awesome-mcp-servers（9.4 万 star）榜单 PR #13379 —— 其自动 bot 要求 server 在 Glama 有 quality score。

## 做了什么

### 1. Glama 认领与验证（用户 GitHub 登录，Claude 代操作）
- 加 `glama.json`（maintainers: gzchenhao）→ 提交 GitHub。
- 用户 GitHub 授权登录 Glama → 认领 server → 作者验证通过（页面蓝勾 ✓）。
- 质量评分 17% → 33%（资料完整度 + 作者验证）。

### 2. 借 Glama 构建逮到并热修一个生产 bug（本单最大价值）
- **现象**：Glama Docker 构建跑 `openhire serve` 崩 `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`。
- **根因**：官方 `mcp` 出了 2.x（FastMCP 改名 MCPServer、import 路径变），而 `pyproject` 依赖写 `mcp>=1.2.0`（**无上限**）→ 任何全新 `pipx install openhire` / `uvx openhire serve` 解析到 mcp 2.x 时，MCP server 直接起不来。本地锁在 1.28.1 才一直没暴露。
- **修复**：依赖锁 `mcp>=1.2.0,<2`。248 tests green。
- **发布 0.3.1 止血**：PyPI https://pypi.org/project/openhire/0.3.1/ · 官方 Registry 0.3.1 isLatest=True（OIDC 工作流自动发）· tag v0.3.1。
- **全新环境验证**：PyPI 装 0.3.1 → mcp 解析到 **1.29.1**、`from mcp.server.fastmcp import FastMCP` 与 `import openhire.mcp_server` 均 OK。

### 3. Glama Dockerfile 配置修正
- Glama 自动生成的 CMD `uv run openhire` **漏了 `serve` 子命令** → 改为 `[..., "openhire", "serve"]`（服务端保存）。
- pinned commit 同步到含修复的 7fc2022。

## 遗留（下次继续）
- **Glama 构建 release 未完成**：mcp<2 修复后 server 已能成功启动（构建从秒崩变为跑满 10 分钟），但两次构建分别遇 Glama 侧基础设施超时（拉 debian:trixie-slim 基础镜像 `context deadline exceeded`）——**非我方问题**。此后又两次（分别用 trixie 与 bookworm 两种基础镜像）均在 Docker 第一步 `load metadata for docker.io/library/debian:*` 处 `no active session … context deadline exceeded`——三连败全发生在我方代码被克隆之前，判定为 **Glama 构建农场当日故障**。配置已定稿（bookworm-slim + `serve` + pinned 96bfcc8），择日重试即可。构建通过后点「Build & Release」→ 评分跳升 → 回 PR #13379 回复 bot 推进合并。
- 重试若持续遇 Glama infra 超时，改日再试即可（配置与代码均已就位，无需再改）。

## KPI（2026-09-04）
star 2 · 快照下载 5 · PyPI 72/天·182/月（有真实装机流量；star 滞后于装机，转化漏斗后端待优化）。

---
**今日请备份 `C:\openhire` 到 U 盘。**

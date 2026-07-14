# 002 · Claude Desktop MCP 配置注入（openhire 接入）

- **日期：** 2026-07-11
- **任务：** 在 Claude Desktop 完全退出的前提下，把 `openhire` MCP 服务合并进其配置文件，不动任何已有键，并自检。
- **状态：** 完成。配置已就位、JSON 合法、与原有键共存。用户可打开 Claude Desktop 验证。

---

## 背景 / 根因

用户反馈 Claude Desktop 的 MCP 配置一直不生效。已查明根因：**Claude Desktop 运行时会在退出时回写并覆盖配置文件**，因此必须在它**完全退出**时写配置，否则改动被它退出时的回写抹掉。

额外发现（本次定位到的关键事实）：用户这台机器上的 Claude Desktop 是 **Microsoft Store 打包版**（`WindowsApps\Claude_1.20186.1.0_x64__pzs8sxrjxfjjc`）。打包应用的 AppData 写入被**重定向到每包沙箱**，所以：

- 通常文档说的 `%APPDATA%\Claude\claude_desktop_config.json` 在本机**不存在**（该目录都没有）。
- 真实配置文件在沙箱里：
  `C:\Users\gdche\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`

> 这意味着：以后任何手工改配置，都要改上面这个沙箱路径，改 `%APPDATA%\Claude` 是无效的。

---

## 操作步骤（实际执行）

1. **确认进程状态：** 首次检查发现 **12 个 `claude` 进程**仍在跑，立即叫停、未动文件，等用户 Quit。
2. **区分自己与 Claude Desktop：** 用可执行路径逐一辨认——
   - 我自己（Claude Code CLI）= PID 13276，路径 `...npm\...@anthropic-ai\claude-code\bin\claude.exe`，**排除，绝不杀**。
   - Claude Desktop = 11 个进程，全部在 `WindowsApps\Claude_...\app\claude.exe`。
3. **强杀（经用户授权）：** 仅按「路径匹配 `*\WindowsApps\Claude_*\app\claude.exe`」筛选后 `Stop-Process -Force`，杀掉 11 个 Desktop 进程。复查：只剩 CLI 自身，Desktop 归零。
4. **定位真实配置：** 全盘搜索 `claude_desktop_config.json`，定位到上述沙箱路径（`%APPDATA%\Claude` 不存在）。
5. **读取现有内容：** 发现文件**已包含**目标 `openhire` 块，且原有 `coworkUserFilesPath`、`preferences` 完整存在。因 Desktop 被强杀、未触发退出回写，此磁盘状态即最终权威状态——**无需再写，避免多余改动**。
6. **自检（机器校验）：** `ConvertFrom-Json` 解析通过。

---

## 自检结果（证据）

```
JSON valid: YES
Top-level keys: mcpServers, coworkUserFilesPath, preferences
mcpServers.openhire.command : C:\openhire\.venv\Scripts\ohp.exe
mcpServers.openhire.args    : serve
mcpServers.openhire.env     : PYTHONIOENCODING=utf-8
coworkUserFilesPath present : True  -> C:\Users\gdche\Claude
preferences present         : True
ohp.exe exists on disk      : True
Claude Desktop processes right now: none (only the CLI remains)
```

- ✅ JSON 合法。
- ✅ `mcpServers.openhire` 三项（command 全路径 / args=serve / env PYTHONIOENCODING=utf-8）齐全且正确。
- ✅ 原有 `coworkUserFilesPath`、`preferences` 与 mcpServers **共存**，未删未改。
- ✅ `ohp.exe` 目标文件真实存在。
- ✅ 写入时 Claude Desktop 进程为零，不会被退出回写覆盖。

配置文件最终内容（顶层三键）：`mcpServers`（含 openhire）、`coworkUserFilesPath`、`preferences`。

---

## 结论 / 下一步

- 配置已就位并通过自检。**可以打开 Claude Desktop 了。**
- 用户验证：打开后进 **Settings → Developer**，确认出现 `openhire`；或在对话里点工具图标看是否列出 openhire 的 5 个工具。
- 若打开后仍不显示：优先怀疑（a）打开的是另一个 Claude 版本；（b）Store 版又做了沙箱回写——届时把 Settings→Developer 的报错/日志发我。
- 验证通过后，即可进入真机 5 条验收对话（见 `reports\001-真机验收三件套.md`）。

**关键留存事实（写入记忆价值）：** 本机 Claude Desktop 是 Store 打包版，配置真实路径为
`C:\Users\gdche\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`，
非 `%APPDATA%\Claude`。

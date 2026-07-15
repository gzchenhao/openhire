# CLAUDE.md — OpenHire 工作约定（每个会话必读）

## 新会话恢复指引（开工前先做这三步）

1. **先读 `README.md`** — 了解产品定位、五个协议字段、三条隐私红线、安装与工具（公开版 README）。
2. **再读 `PROGRESS.md`** — 了解已完成到哪一步、关键决策与理由、下一步、待用户确认事项。
3. **禁止重做已完成的工作。** M1–M4 已全部完成，**v0.1 已公开发布**（见下方发布状态、PROGRESS.md 验收证据）。除非用户明确要求返工，不要重建已完成的里程碑。

## 发布状态（v0.1 已上线 + 上架官方 Registry · 2026-07-15）

- **GitHub：** https://github.com/gzchenhao/openhire （owner `gzchenhao`，main，tag v0.1.1）
- **Release v0.1.0：** https://github.com/gzchenhao/openhire/releases/tag/v0.1.0 （含快照资产 `openhire-index.db.gz`，URL 稳定不变）
- **PyPI：** https://pypi.org/project/openhire/0.1.1/ （`pipx install openhire`）
- **官方 MCP Registry：** `io.github.gzchenhao/openhire` v0.1.1（`registry.modelcontextprotocol.io`，用 `server.json` + `mcp-publisher` 发布；PulseMCP/mcp.so 自动同步）。
- **Smithery：** v0.1 放弃（无本地 stdio 网页入口，见 `reports/010`）。
- 推送用 `gh`（keyring）；PyPI token 仅 `%USERPROFILE%\.pypirc`；`mcp-publisher` 用其本地 GitHub 凭据。三者均**不进代码/git**。
- 再发新版流程：改 README `mcp-name` 保持不变 → bump 版本 → `twine upload` → 改 `server.json` 版本 → `mcp-publisher publish`。

## 常设工作制度（持续遵守）

1. **进度记录：** 每完成一个里程碑、或每个工作日结束时，更新 `PROGRESS.md`：
   - 日期
   - 已完成（含验收证据：测试数、实测输出、花费等可核对的事实）
   - 关键决策及理由
   - 下一步
   - 待用户确认事项
   控制在一页以内；新进展追加在顶部（倒序），旧条目保留。
2. **恢复指引常驻：** 本文件顶部的「新会话恢复指引」始终保留并保持最新。
3. **每次会话结束前主动提醒用户：** 「今日请备份 `C:\openhire` 到 U 盘。」
4. **里程碑节奏：** 每完成一个里程碑停下，对照验收标准向用户汇报后再继续。
5. **汇报归档：** 每次完成任务后的完整汇报，除在终端显示外，**同时写入 `C:\openhire\reports\`**。
   - 文件名 = 递增编号 + 主题，如 `001-真机验收三件套.md`、`002-M4打包.md`。
   - Markdown 格式，**自足完整**：不依赖终端上下文，单独打开也能看懂（含背景、做了什么、证据、结论、下一步）。
   - 每次干完活的**最后一行**告诉用户：「汇报已写入 C:\openhire\reports\xxx.md」。
   - 编号取 `reports\` 里现有最大编号 +1（补零三位）。
6. **每周快照刷新（维护者职责）：** 发布用的快照是 GitHub Release 资产，会随时间过时。每周按 `docs/maintainer-snapshot-refresh.md` 跑一次 `ohp snapshot-build` 并替换 Release 里的 `openhire-index.db.gz`（文件名保持不变，否则 `ohp bootstrap` 找不到）。构建自带「零用户态」红线校验。

## 三条隐私红线（CI 强制，永不可破）

1. 简历或任何 PII **绝不**经过服务端 —— 只有匿名指纹过网。
2. 排序**绝不**是付费参数 —— 只是 f(匹配度, 新鲜度) 的纯函数，签名锁死。
3. 雇主只为已授权、已交付的结果付费 —— 绝不为曝光付费（v0.1 无任何计费代码）。

对应自动化测试见 `tests/test_privacy.py`、`tests/test_ranking.py`。改动排序/服务层/apply 后必须跑 `pytest` 确认全绿。

## 关键路径与事实

- 代码根：`C:\openhire\src\openhire`
- 数据库（默认，绝对路径）：`C:\Users\gdche\.openhire\openhire.db`（11,825 职位 / 96 公司 / 全量 DeepSeek 抽取）
- CLI 可执行文件：`C:\openhire\.venv\Scripts\ohp.exe`（**未在系统 PATH 上** —— 接入 Claude Desktop 时须写全路径）
- 抽取后端：DeepSeek（`deepseek-chat`，key 从 `.env` 的 `DEEPSEEK_API_KEY` 读；serve 阶段不需要 key）
- 设计交接文档：`design_handoff_openhire_v01\README.md`（唯一权威规格）；`design_refs\*.html` 仅供交互参考，**不复用其代码**。

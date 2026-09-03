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
6. **每周快照刷新：已自动化（017）。** `.github/workflows/refresh-snapshot.yml` 每周一 06:10 UTC 自动跑（也可在 Actions 手动 Run workflow）：下载已发布快照 → 重新 seed → 免费启发式全量刷新 → `ohp snapshot-build` → 覆盖上传同名资产。**工作流零密钥**（只用 GitHub 自动下发的 per-run token，权限仅 `contents: write`），失败靠 GitHub 默认邮件通知仓库主。
   人工只剩**月度一条命令**的 LLM 精抽（CI 无 key，只能跑启发式）：
   ```
   ohp extract-rebuild --backend glm       # 补 skills（套餐内，现金 ¥0）
   ohp extract-role-family --backend glm   # 补 role_family
   ```
   跑完按 `docs/maintainer-snapshot-refresh.md` 手动 build + upload 一次，让精抽结果进到公开快照。

## 三条隐私红线（CI 强制，永不可破）

1. 简历或任何 PII **绝不**经过服务端 —— 只有匿名指纹过网。
2. 排序**绝不**是付费参数 —— 只是 f(匹配度, 新鲜度) 的纯函数，签名锁死。
3. 雇主只为已授权、已交付的结果付费 —— 绝不为曝光付费（v0.1 无任何计费代码）。

对应自动化测试见 `tests/test_privacy.py`、`tests/test_ranking.py`。改动排序/服务层/apply 后必须跑 `pytest` 确认全绿。

## 关键路径与事实

- 代码根：`C:\openhire\src\openhire`
- 数据库（默认，绝对路径）：`C:\Users\gdche\.openhire\openhire.db`（2026-09-01：21,568 职位 / 活跃 14,909 / 125 公司；抽取来源 deepseek 16,316 · glm 5,250 · heuristic 2——精抽存量已全部清偿，role_family 空值 = 0）
- CLI 可执行文件：`C:\openhire\.venv\Scripts\ohp.exe`（**未在系统 PATH 上** —— 接入 Claude Desktop 时须写全路径）
- 抽取后端（可插拔，`--backend` 选）：
  - **GLM（默认首选，017 起）** —— `glm-5.3-flash`，走领导的 coding 套餐，**现金 ¥0**。key 从 `.env` 的 `ZHIPU_API_KEY` 读。base_url 必须是 `https://open.bigmodel.cn/api/coding/paas/v4`（标准 `/api/paas/v4` 对套餐 key 报 1113）。两个坑已在代码里处理并有测试锁死：① 必须发 `thinking:{"type":"disabled"}` 且 `max_tokens ≥ 1024`（reasoning token 先于 content 从额度里扣，额度小会返回空串）；② flash 输出带 ```json 围栏，解析须剥。
  - DeepSeek（`deepseek-chat`，`DEEPSEEK_API_KEY`）—— 按次计费，017 起不再默认使用。
  - 启发式（免费离线，CI 与 `bootstrap` 用）。
  - **血统不造假：** 每行 `jobs.extraction_source` 如实记录是谁抽的（`glm` / `deepseek` / `heuristic`）；重抽只挑「不属任何 LLM 源」的行，两个 LLM 后端不会互刷。
  - serve / search 阶段不需要任何 key。
- 设计交接文档：`design_handoff_openhire_v01\README.md`（唯一权威规格）；`design_refs\*.html` 仅供交互参考，**不复用其代码**。
- **抓取边界判例（020 复核定档）：** 响应体自带密钥、IV 页面明文可得的传输编码 = 可解（等价多绕几道的 base64，如 Moka 的 AES 信封）；请求签名、验证码、登录墙 = 访问控制，不可破（如飞书 `_signature`）。若某 vendor 把密钥移出响应体（JS 派生/会话挑战/轮换），即视为升级成访问控制——**立即停抓该 vendor 并记录**，不做逆向。
- **抽取/解析规则变更要影响存量数据：必须先失效 content_hash**，否则重抓一律被判「未变」而空转（020 福瑞泰克「元/天→假月薪」修复的教训）。

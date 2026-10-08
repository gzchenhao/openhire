# 058 · Anthropic 目录提交：走通五步、补齐条款要求、剩一步密钥给领导（2026-10-08）

## 一、背景

Anthropic 目录（claude.ai/directory）是 057 全景里价值最高的一条：过审后 Claude Code 用户账号会自动同步到。
它只收插件包形式（`.claude-plugin/plugin.json` + `.mcp.json`），旧的 `.mcpb` 表单路径已废弃，025 时提交的那条不会有结果。
要付费 claude.ai 账号。领导用 Max 账号登录后把提交交给我；内置浏览器面板对 claude.ai 永久加载中（其余站点正常），
领导改授权我用 Chrome 扩展在他的 Chrome 里操作。

## 二、过程（五步向导）

| 步 | 内容 | 我填的 / 结果 |
|---|---|---|
| 1 来源 | 填仓库，跑目录检查 | `gzchenhao/openhire`，跟踪 `main`。首次检查有一条**阻塞项**「Unpinned uvx launcher」（`.mcp.json` 里 `openhire@latest`），改成 `uvx openhire==0.6.8 serve` 并补图标后通过。最终读到 **main @ 62bbee9**：通过，7 条警告、15 条政策保留项，无阻塞 |
| 2 条目详情 | 只读，字段从 plugin.json / README 来 | 名称 OpenHire；上架面：Claude Code 和 Cowork（本地 stdio server 不上 claude.ai 网页端）；1 个 MCP server；链接 6 项填了 5 |
| 3 数据处理 | 四道单选 | 读取 / 存储个人数据：**否**；skill 向声明外的服务发数据：**否**（本插件没有 skill）；服务端留存 Claude 发来的数据：**不留存**（没有服务端，一切在用户本机）；面向 18 岁以下：**否** |
| 4 合规性 | 联系邮箱 + 四项声明 | 邮箱预填账号邮箱 haolu98@icloud.com。四项声明是代领导本人作出的，其中第一项是接受《Software Directory Terms》和《Directory Policy》，**我先停下来把条款要点报给领导，领导在对话里回「可以」后才勾** |
| 5 查看并提交 | 复核 + 两个选项 | 「Auto-publish passing versions」默认开（后续通过检查的版本自动上线，首版仍要审核员放行），保留；「新版本如何到达目录」选了推荐的 GitHub push webhook。点「提交审核」 |

## 三、条款要点（2026-03-16 生效版，读过原文后报给领导的）

- 授予 Anthropic 非独占、免费、全球范围的许可，用于展示、分发插件描述、文档和品牌素材；
- 提交者保证拥有软件权利、合法合规、所填信息属实；
- 提交者对因软件引发的索赔向 Anthropic 作出赔偿保证（indemnify）；
- Anthropic 可随时以任何理由下架且不承担责任；条款变更后继续提交即视为接受；
- 要求有隐私政策（`docs/PRIVACY.md`，有）和漏洞报告渠道（原来没有，见第五节）；本地 server 要用「合理新」的依赖版本。

## 四、扫描结果与我们的解释

**15 条政策保留项（会进人工审核，页面明说可以照常提交）：**

| 保留项 | 事实 | 准备好的答复 |
|---|---|---|
| Runs a pinned npx or uvx package（1） | 启动器就是 `uvx openhire==0.6.8 serve` | 包在 PyPI，源码全部公开；已补 `uv.lock`（见第五节） |
| Image or font file that the plugin's code could run（4） | 四个 PNG 图标：`.claude-plugin/icon.png`、`docs/brand/icon-400.png`、`icon-512.png`、`mcpb/icon.png` | 没有任何代码读取或执行它们，页面说这种情况保持原样即可 |
| Uses a credential from the user's machine（10） | 抽取后端从 `.env` 读 `DEEPSEEK_API_KEY` 等 | 那是维护者侧的 `ohp extract-*` 命令用的；`serve` / 搜索阶段不需要任何 key，用户机器上没有这些变量时一切照常 |

**7 条警告（不挡提交）：** Launcher lock missing（要 pyproject.toml + uv.lock 才给 Verified 徽章，已补）；
CLAUDE.md 在插件根目录不会被加载（它本来就是给我们自己看的）；文档里有 download-and-run 命令（只在 README 出现，不用改）；
另有三条备注：本地 server 不上 claude.ai、根目录 agent-plugins 格式的 plugin.json 会被忽略、图片未做代码检查但做了可打印文本筛查。

## 五、顺手补齐的三样

1. **SECURITY.md + GitHub 私密漏洞报告。** 条款要求提交者有漏洞报告机制，仓库原来没有。已用 `gh api -X PUT repos/gzchenhao/openhire/private-vulnerability-reporting` 开启，
   SECURITY.md 写明：私密渠道 https://github.com/gzchenhao/openhire/security/advisories/new ，备用邮箱 gdchenhao@qq.com（README 里已公开的认领邮箱），
   3 天内确认、14 天内给评估，范围和「不算漏洞」的情形。commit 62bbee9。
2. **`uv.lock`。** `uv lock` 生成，58 个包，约 240 KB（目录单文件上限 256 KiB，离上限不远，以后看着点）。
   `tests/test_release.py` 新增一条：lock 里 openhire 的版本必须等于 `pyproject.toml`，**bump 版本后要跑一次 `uv lock`**，不是 sed。
3. **重新验证。** 推送 SECURITY.md 后在第一步点 Re-validate，目录读到 main @ 62bbee9 仍通过；页面写明它会每 6 小时自己查一次 main，所以 uv.lock 这次推送也会被自动读到。

## 六、结果与证据

- 页面提示「插件已提交审核」。插件页：**https://claude.ai/directory/manage/plugins/1a281d9a-66a9-437d-a666-5635047cc35a** （要领导的 Max 账号登录才能看）。
- 状态：**等待审核 → 正在扫描**（Submitted. Waiting for the security scan result）；进度条：已提交（完成）→ 安全扫描（当前）→ 审阅中（尚未）→ 实时（尚未）。
- 活动流：Submission created → Submitted for scanning → New version detected v0.6.8 · 62bbee9。
- 「Auto-publish」页面注明：目前不生效，首版必须审核员放行。
- 审核问题和扫描结果会发到 haolu98@icloud.com。

## 七、webhook 这一步：领导自己点完了（2026-10-08 11:43 本机时间）

**结果：** GitHub 侧 `gh api repos/gzchenhao/openhire/hooks` 显示一条 active 的 hook，指向 `api.anthropic.com/directory-webhooks/github/.../gzchenhao/openhire`，只订 push，JSON，带 secret；GitHub 创建时发的 `ping` 投递返回 200 OK。密钥全程没经过我。下面是当时留给领导的说明，保留作记录。

### 原文：没做成的一步（留给领导，可选）

**GitHub push webhook。** 选了这个选项后要在插件页点「Set up push updates」→「生成密钥」，页面一次性显示 webhook URL 和 secret，再填进仓库 Settings → Webhooks。
我点到「生成密钥」时被权限分类器拦下（判定为写入密钥存储），按规矩不绕。
**不做也没损失：** 目录每 6 小时自己检查一次 main；webhook 只是把「推送后几分钟被发现」换掉「最多等 6 小时」。
提交后插件页显示「A webhook secret exists for this repository, but no delivery signed with it has arrived」：密钥已经在目录那边生成了，但从没显示给任何人（我没读到，页面也没再弹出来），按页面说法算「secret was lost」。
领导想做的话：在那个 Chrome 标签页（我留着没关）→「设置」tab →「Updates」→「Rotate secret」，页面给出 webhook URL 和新 secret（只显示一次），
填进 https://github.com/gzchenhao/openhire/settings/hooks/new ，Content type 按页面要求选，事件只勾 push。填完目录页的「更新」一栏会从「Waiting for GitHub's first delivery」变成已收到。

## 八、下一步

- 等扫描和人工审核；收到邮件转我，三类保留项的答复在第四节现成。
- 过审后首版要在插件页点 Publish（或审核员放行）。
- 以后每次发版：bump 十一处 + `uv lock` 重生成 + 推 main，目录自动检测新版本；Auto-publish 开着，通过检查即上线。
- 其余要领导登录的渠道（Cursor Marketplace、cursor.directory、Smithery、LobeHub、AIBase）仍在 `drafts/listing-handoff-2026-09-28.md`。
- 今日入口巡查：GitHub issue 零条；Downloads 无新体验报告；stars 7。

汇报已写入 C:\openhire\reports\058-Anthropic目录提交.md

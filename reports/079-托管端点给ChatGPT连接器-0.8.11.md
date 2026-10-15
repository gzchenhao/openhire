# 079 · 托管端点：让 ChatGPT 这类「只收网址」的客户端也能用 OpenHire（0.8.11）

日期：2026-10-15（云端会话）。起因：领导看完知乎文章修订稿里那句「ChatGPT 走它的连接器，要先把服务挂到公网地址」，裁定「那我们就挂吧，你来操作」。

## 一、这是什么，为什么要做

OpenHire 到今天为止是一个跑在用户自己电脑上的 MCP 服务：`uvx openhire serve`，一行配置接进 Claude、豆包、DeepSeek（经 Cherry Studio）、Cursor、腾讯 WorkBuddy。这条路的好处是隐私：搜索条件、指纹、盯岗记录都在用户自己的盘上，我们的服务器什么都看不见。

ChatGPT 不走这条路。它的自定义连接器（开发者模式，付费档）只收一个公网 https 地址，不能启动本机进程；本机服务要先经一条隧道挂到公网，普通用户不会做。所以要让 ChatGPT 用户用上 OpenHire，就得有人在公网跑一份。领导点名 ChatGPT 排第一（文案规矩第 7 条 2026-10-15 补款），那这一份只能我们来跑。

## 二、做了什么

**代码（0.8.11，714 tests）**

1. **托管模式** `src/openhire/hosted.py`，`OPENHIRE_HOSTED=1` 时随 `ohp serve --transport streamable-http` 启动，本机模式一行都不跑：
   - 首页 `/`（说明这是什么、怎么接、这台主机看得见什么、本机安装仍是推荐路径）和 `/healthz`（版本、索引是否装好、雇主数、岗位行数、数据日期；索引空则 503）；
   - MCP `instructions` 末尾加一句「这是托管端点，请求到了维护者的主机，只有工具参数，没有简历，盯岗记录存在这台主机的索引里，要放自己盘上就本机跑」，让助手能如实告诉用户；
   - 限流：每个来源地址每分钟 300 次、全站每分钟 3,000 次，超了回 429 和 `Retry-After`（ChatGPT 很多用户共用少数出口地址，所以每地址给得宽）；
   - 无状态的 streamable HTTP（进程重启不会让客户端卡在「会话不存在」）；uvicorn 关掉访问日志，主机不留查询记录；
   - **快照刷新工作线程**：每 6 小时对公开快照资产做一次 HEAD（ETag、长度、修改时间）；变了就把新快照下载、校验到 `openhire.db.staged`，然后给自己发 SIGTERM 平稳退出；`hosted/entrypoint.sh` 的循环再把它拉起来，`serve()` 启动时在任何连接打开索引之前把 staged 换成正式文件。**绝不在别的线程读着的时候覆盖 SQLite 文件**，那是索引损坏的来路。
2. **换快照不丢盯岗记录**（`pipeline/snapshot.py` 的 `stage_snapshot` / `activate_staged` / `carry_over_user_state`）：旧文件先 checkpoint 再改名为 `.previous`，新文件就位后把 `watches` 和 `applications` 两张表按共有列 `INSERT OR IGNORE` 搬过去，表不存在就照旧文件的 DDL 建。这顺手修掉了 0.8.4 路线图上那条「`ohp bootstrap --force` 整文件覆盖会清 watches」：现在 `--force` 保留盯岗和投递记录。
3. **SSRF 防线**（`verify/checks.py`）：`check_employer` 会按用户给的域名去取首页、按用户给的页面地址去找电话。在用户自己的电脑上这是他自己的网络；在托管主机上就是我们的网络。所以现在取之前先解析地址，127.0.0.1、10.x、192.168.x、169.254.169.254（云元数据）、`localhost` / `.internal` / `.local` 这类名字、非 80 / 443 端口一律不发请求；重定向改为手动跟（最多 5 跳），每一跳同样检查。本机模式一样生效，无害。`read_board` 本来就只拼已知 ATS 域名、租户名有正则，不需要改。
4. `hosted/`：`Dockerfile`（装 PyPI 上的 `openhire==0.8.11`，非 root 用户，`/data` 放索引，7860 端口）、`entrypoint.sh`（重启循环）、`README.md`（Hugging Face Space 的 front matter）。`tests/test_release.py` 把 Dockerfile 的版本钉死到 pyproject，**版本号现在是十二处 sed 加一处 `uv lock`**。
5. `.github/workflows/deploy-hosted.yml`：Release 成功后（或手动）把 `hosted/` 推到 Space（没有就建），先等 PyPI 上有这个版本，再等 `/healthz` 报出这个版本号，20 分钟不出来就红；每天 03:17 UTC 一次健康检查，不答或版本不对就红（GitHub 会给领导发邮件），顺带让免费 Space 不因没流量而睡着。**仓库里没有 `HF_TOKEN` 这个 secret 时，部署步骤只打一条 notice 就停，别的什么都不影响。**

**文档**：README「Hosted endpoint」一段（ChatGPT 开发者模式的点法、这台主机看得见什么、本机仍是推荐）；`docs/PRIVACY.md` §3 加托管端点一条；`hosted/README.md` 是 Space 页面。

## 三、为什么选 Hugging Face Space

要求：免费、不绑卡、公网 https、能跑 Docker、Python 加一个 30 MB 的 SQLite 文件、ChatGPT（美国）能到、我能从云端会话部署（经 GitHub Actions 的 secret，token 不经我手）。

- Hugging Face Space（Docker SDK，免费 CPU）：都满足；48 小时没流量会睡，第一个请求唤醒要几十秒，每天的健康检查顺带挡住这一点。大陆访问不了 hf.co，但 ChatGPT 用户本来就不在大陆。
- Render 免费档：15 分钟没流量就睡，冷启动几十秒，ChatGPT 的连接器容易超时。
- Fly.io / Google Cloud Run / 阿里云函数：要绑卡或要账号配置，先不碰。
- Smithery 托管：每个用户还要一把 Smithery 的 key，和「喂到嘴里」背道而驰。
- 魔搭托管：要国内手机号登录，不是给 ChatGPT 用户的。
- 领导的 Mac 或 Windows 本机加隧道：不稳定，也把家里网络暴露出去，不做。

## 四、隐私姿态怎么变了，怎么写进了文案

本机模式三条红线不动。托管模式新增一条如实披露：这台主机看得见工具参数（搜索条件、公司名或域名、板地址、匿名指纹），看不见别的；不记查询日志；盯岗和投递记录存在它的索引里，按指纹存，换快照时搬过去，主机重建会丢；`check_employer` 和 `read_board` 的外联请求从它发出；Hugging Face 作为平台能看见连接。写在 README、PRIVACY §3、首页和 MCP instructions 四处，措辞一致。

## 五、还差一步，只有领导能做

云端会话没有 Hugging Face 账号，token 也不能经我手。要做的只有三件：

1. 在 https://huggingface.co 注册（或登录）账号，用户名建议就用 `gzchenhao`（Space 地址会是 `https://gzchenhao-openhire.hf.space`；用别的名字也行，告诉我一声，我改两处默认值）；
2. Settings → Access Tokens → New token，类型选 **Write**，名字随意（比如 `openhire-deploy`）；
3. 到 GitHub 仓库 Settings → Secrets and variables → Actions → New repository secret，名字 `HF_TOKEN`，值就是那串 token。

然后告诉我「secret 放好了」，我用 GitHub MCP 手动触发「Deploy hosted endpoint」工作流，十来分钟后 `/healthz` 报 0.8.11 就算上线。往后每次发版自动跟。token 只在 GitHub secret 里，不进任何仓库、不进云端会话。

## 六、上线之后要做的

- 知乎文章里那句「ChatGPT 走它的连接器，要先把服务挂到一个公网地址」改成具体做法：开发者模式新建连接器，地址填 `https://gzchenhao-openhire.hf.space/mcp`（私库稿的「发布备注」里会写成第三步）；
- 实测：领导或本机会话用 ChatGPT 开发者模式接一次，问一句「具身智能公司在招的感知岗」，截图或把答复贴回来；
- 观察一周 `/healthz` 和 Space 的日志，看限流有没有误伤、睡眠唤醒要多久；
- 等第一次周一快照刷新后，看工作线程有没有如期换文件、盯岗记录有没有搬过去（`/healthz` 的 `data_as_of` 会跳到新日期）。

## 七、口径限制

- 托管端点没有真机实测：云端连不上 huggingface.co，Space 也还没建。代码靠 20 条新测试钉住（路由、限流、刷新判断、换文件搬记录、SSRF 防线），真实链路要等领导放好 token 后由工作流验证。
- ChatGPT 开发者模式的入口位置 2026 年内挪过几次，README 写的是「Settings → Connectors → Advanced → Developer mode」，以 ChatGPT 当天界面为准。

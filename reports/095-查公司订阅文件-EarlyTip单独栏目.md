# 095 · 「查公司」订阅文件，EarlyTip 单独栏目自动同步（0.8.28，2026-10-27）

日期：2026-10-27（云端会话）

## 背景

- 10-21（`reports/088`）给 earlytip.com 做了「查公司」独立页，EarlyTip 原计划在页脚放一个外链。
- 领导 10-27 提出：EarlyTip 上的「查公司」应该像「顶会归档」那样单独开一个栏目，内容跟我们这边实时同步，我们改了它自己更新，不用再另外通知 EarlyTip。

## 判断

- **同步「查公司」页，不同步求职清单。** 清单里有七步求职流程、安装引导和产品名，正是 EarlyTip 10-21 提出不能出现在入口目标页的内容。「查公司」页就是按那次条件做的。
- **用订阅文件，不用 iframe 或外链。** iframe 会让 EarlyTip 的读者直接连 github.io（国内不稳）或 Render 免费主机（休眠后首次要等）。订阅文件由 EarlyTip 自己的定时任务在服务端拉，读者看到的是 EarlyTip 自己站点上的内容，我们这边哪个地址一时打不开都不影响读者。
- **「实时」的实际含义：** 我们推 main 后几分钟 github.io 上的文件就更新；EarlyTip 按建议每 6 小时拉一次，所以最多晚 6 小时左右。对一页官方网址清单，这个延迟够用，也不需要任何一方发通知。

## 做了什么

1. `src/openhire/check_company_feed.py`：从页面生成订阅文件 `check-company.json`（schema 1）。字段：`title`、`updated`、`sha256`、`html`、`feedback_url`、`page_url` / `page_url_cn`、`sources`、`allowed_tags`。
   - `html` 是按白名单重新生成的正文片段：只有 h2、p、ul、li、table、tr、th、td、a 九种标签；`<a>` 只留 https 的 `href`，其他标签不带属性；文字全部转义；script、style、图片、iframe 连内容一起去掉；不含 `<h1>` 和页脚。
2. 三个发布地址，内容相同：
   - github.io 的 `docs/check-company.json`：推 main 后几分钟内更新；
   - 托管端点 `/check-company.json`：随发版更新，带 `Access-Control-Allow-Origin: *`；
   - CNB 代码镜像：每 6 小时同步。原始文件的地址格式云端核不了，排进本机待办第 24 条。
3. `scripts/build_check_company_feed.py`：改页面后跑一次，重新生成订阅文件。
4. `tests/test_check_company_feed.py`，10 条：
   - 订阅文件必须等于从当前页面重新生成的结果，忘了跑脚本测试就红；
   - EarlyTip 的条件对订阅文件同样成立：不出现「求职」「招聘」「岗位」、uvx、/mcp、安装、checklist、产品名；
   - 白名单与 https 链接；
   - 四种恶意输入（script、javascript: 链接、onclick 加 img、http 链接加 iframe）都被清掉，且没有孤立的 `</a>`；
   - 内容一变 `sha256` 就变；
   - **「查公司」页里的每个官方网址都必须也出现在求职清单里**：清单改了网址，「查公司」页不跟着改测试就红，所以两页（连同 EarlyTip 的栏目）不会各说各的；
   - 托管端点输出的订阅文件与 docs 那份一字不差。
5. 部署工作流与每日体检都多一步：`/check-company.json` 能解析，`schema` 为 1，标题是「查公司」。
6. 给 EarlyTip 项目经理的任务书在私库 `earlytip-check-company-column-brief-2026-10-27.md`，由领导转达。我们不直接指挥 EarlyTip 的会话，也不改 EarlyTip 的仓库。任务书写明：
   - 单独栏目「查公司」，与「顶会归档」同级；
   - 每 6 小时拉一次（至少每天一次），三个地址按顺序试；
   - 校验 schema、title、sha256 和白名单，EarlyTip 自己再清洗一遍；
   - `sha256` 变了才重新渲染；拉不到就显示上一份好的，绝不显示空白；
   - 栏目底部只放反馈链接；
   - 做完回报栏目网址、拉取频率和第一次显示的 `sha256`。

   我们的承诺：
   - 内容条件一条不变，现在对页面和订阅文件同时有测试钉住；
   - 订阅文件要换地址或换格式时，schema 升到 2，提前告知，旧的再保留 30 天；
   - 托管主机不记访问日志。

## 证据

- 全量测试 892 passed（原 882，加 10）。
- 订阅文件当前 `sha256` 是 084651172198f756c6c494a4e215b7848e318a4ae36f70cbc72d0cb4ab1210fb，`updated` 是 2026-10-21。
- 发版核对见文末补记。

## 以后改「查公司」页的流程

1. 改 `docs/check-company.html`，复制到 `src/openhire/pages/`；
2. 跑 `python scripts/build_check_company_feed.py`；
3. 测试全绿后推 main。

EarlyTip 下一次拉取时会自动换上新内容，不用发通知。求职清单里「查公司」和「反诈骗」两步的网址改了，「查公司」页也要一起改，测试会提醒。

## 下一步

- 领导：把私库那份任务书转给 EarlyTip 项目经理。
- 本机：第 24 条，核三个地址能拉到且 `sha256` 一致；第 15 条改为看 EarlyTip 导航里有没有「查公司」栏目。
- 云端：EarlyTip 回报栏目网址后，排本机核对栏目内容与订阅文件一致。

## 补记：发版与部署核对（03:07 UTC）

- PyPI 0.8.28 在 03:05 UTC 上线（推 main 后由 Release 工作流自动发布）。
- 托管端点部署 run 40442070719 成功，03:07 UTC 完成。这次运行的检查项包括 `/healthz` 报 0.8.28、`/mcp` 能答 initialize 和 tools/list、`/check-company.json` 能解析且 schema 为 1、标题为「查公司」。
- github.io 和 CNB 两个地址云端连不上，排在本机待办第 24 条核对。

# 098 · 桌面版 openhire 断开的原因（2026-10-28，本机会话）

## 背景
领导贴了 Claude 桌面版的 `mcp-server-openhire.log`，最后一段是 2026-10-28 01:08:37 UTC「Server transport closed unexpectedly」，之后没有重连。领导问：是 OpenHire 本身的问题，还是电脑的问题。

## 查了什么
1. **包本身是好的。** `ohp version` 显示 0.8.28。用和桌面版同一条命令 `C:\openhire\.venv\Scripts\ohp.exe serve` 在本机跑了一次完整握手：initialize 7.5 秒返回，tools/list 返回 11 个工具，`search_jobs(location="Hong Kong")` 正常返回岗位。
2. **断开的时间点正好是我们自己重装包的时候。** `.venv\Lib\site-packages\openhire-0.8.28.dist-info` 和 `ohp.exe` 的修改时间是本机 08:09:09（01:09:09 UTC），比断开晚 30 秒。这一步是本机每晚定时任务做的：本机待办第 1 条写着 `git pull` 后 `pip install -e . --no-deps` 装 0.8.28。这次运行在 10-28 01:07 UTC 开工（growth-log 有记），01:08 开始装包，桌面版跑着的服务器随之退出。
3. **以前也是这样。** 日志里 09-12 那次断开带着 `ModuleNotFoundError: No module named 'openhire'`，就是 CLAUDE.md 记过三次的「改 venv 时桌面版占着 ohp.exe」。10-22 02:16 UTC 那次断开，也落在本机当天上午补跑装 0.8.25 / 0.8.26 的时段。
4. **电脑这边没有相关故障。** 08:00 前后的系统日志只有一条「电源切换」和一条 08:07:54 的 `Harddisk1` 控制器错误。后者是外接盘（大概率是 U 盘），和服务器进程无关。
5. **桌面版不会自己重连。** 进程意外退出后，日志里再没有「Initializing server」，要人手重启它。

## 结论
不是 OpenHire 的缺陷，也不是电脑的毛病，是我们自己的维护步骤：本机定时任务在桌面版开着 openhire 的时候重装了包，把它踢掉了，而桌面版不会自动重连。

## 修复
- **现在：** 领导在 Claude 桌面版的 设置 → 开发者（Developer）里把 openhire 重启一下，或者退出桌面版再打开。本机已验证同一条启动命令能正常握手。
- **以后：** 已发给云端会话，请它改本机待办的规则。编辑安装（`-e`）下，`git pull` 之后服务器跑的就是新代码，平时不用重装。只有依赖、入口或版本号变了才装；要装就放在报告最后，并提醒领导重启桌面版的 openhire。

## 顺带发现（不影响连接）
昨天 18:49 那两次北森读板，`ubtech.zhiye.com`、`geely.zhiye.com`，北森都回 302 跳到 `/404`，说明这两个租户名不存在。`read_board` 却报成 `non-json body`，看起来像我们解析出错。`magiclab.zhiye.com` 现读正常（73 条）。已请云端把「北森跳 /404」报成「这个招聘页不存在」。

# BLOCKED — 015 任务 D4：官方 MCP Registry 发布 0.2.0

**日期：** 2026-07-27　**范围：** 只有这一步被卡；015 的其余全部完成（见 `reports/015-v0.2.0发布.md`）。

## 现象

`mcp-publisher publish` 返回 401：

```
Publishing to https://registry.modelcontextprotocol.io...
Error: publish failed: server returned status 401:
{"title":"Unauthorized","status":401,
 "detail":"Invalid or expired Registry JWT token",
 "errors":[{"message":"failed to parse token: token has invalid claims: token is expired"}]}
```

即 `~/.config/mcp-publisher/token.json` 里那枚 011（2026-07-15）留下的 Registry JWT 已过期。

## 已试

1. **重装二进制** —— 任务书说 `mcp-publisher` 已从 PATH 丢失，属实。按官方 Release 重装
   `mcp-publisher_windows_amd64` **v1.8.0**（`modelcontextprotocol/registry`，与 011 同版本），
   `mcp-publisher 1.8.0 (commit d813d2b…)` 可正常运行。
2. **校验发布物** —— `mcp-publisher validate` → `✅ server.json is valid`；`server.json` 两处版本
   均已是 **0.2.0**；PyPI 上的 `openhire 0.2.0` 长描述里保留着
   `<!-- mcp-name: io.github.gzchenhao/openhire -->` 归属行（Registry 校验所有权要用）。
3. **publish** → 上面的 401。
4. **按官方文档重新登录** —— `mcp-publisher login github` 走 device-code 流程，已拿到
   授权码（`36CA-9789`）并交给用户在其**自己的浏览器**完成授权。用户当时不在场，
   该码**已超时作废**：

   ```
   Error: login failed: error polling for token: device code authorization timed out
   ```

   → 解除时必须**重新执行 `login` 取新码**（旧码不能再用）。这是预期行为，不是故障。

## 怀疑什么

不是配置或版本问题，就是**登录态过期**这一件事：Registry 的 JWT 是短期令牌，011 那次登录到现在
已 12 天，过期是预期行为而非故障。发布链条上其它环节都已验证可用。

## 为什么不自行解决

本单止损条款明确：「twine/mcp-publisher 凭据失效 → 停写 BLOCKED.md（**不许自行找回/重置任何凭据**）」。
device-code 授权必须由账号本人在浏览器点确认，我只能发起、不能代办，也不会去动任何凭据文件。

## 解除办法（一步）

在 `C:\openhire` 执行（二进制在临时目录，可复制到任意位置）：

```powershell
& "<mcp-publisher.exe 路径>" login github     # 浏览器打开 https://github.com/login/device 输入所示 code
& "<mcp-publisher.exe 路径>" publish
curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=io.github.gzchenhao/openhire"
# 期望：version 0.2.0 且 isLatest:true
```

`server.json` 无需再改。

## 影响面（小）

**不影响用户安装**：`pipx install openhire` / `uvx openhire serve` 拿到的已经是 **0.2.0**
（PyPI 已上线并经全新环境验证）。Registry 条目滞后只影响目录页展示的版本号，
`io.github.gzchenhao/openhire` 条目本身仍在（0.1.1，status active）。

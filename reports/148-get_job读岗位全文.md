# 148 · 第 15 个工具 get_job：读一条岗位的职位描述全文（0.8.68）

日期：2026-11-17（云端会话）

## 背景

`reports/147` 记下的待定功能之一：模拟求职者 11-16 夜，产品经理人设想知道理想汽车一条岗位是不是真做产品。`check_employer` 显示这条的职位描述已在索引里，但 `search_jobs` 不返回描述、`read_board` 又读不了理想的自建官网，助手只好对用户说「职位描述读不到全文」。领导 11-17：「get_job 那个功能直接做吧」。

## 做了什么

- **新工具 `get_job(job_id, max_chars=8000, offset=0)`**（`service.get_job`，`mcp_server.get_job`）：
  - 返回和 search_jobs 一行相同的字段（日期、在架天数、dates_in_words、requirements、签证、check_before_apply、投递链接等），去掉 rank_score / match_quality（没有查询条件，0 分会被读成「不匹配」）。
  - 加 `description`：雇主自己的原文，按索引最后一次读到的版本；长文按 `max_chars`（1 到 20,000）分段，`description_next_offset` 为 null 时读完。全库在架描述平均约 4,900 字，最长约 4.4 万字。
  - 加 `status`：live / closed（已下架，仍给原文让用户看自己投过什么，但不得当作在招推荐）/ not_verified_recently（30 天没核到，先 refresh_index），后两种带 `status_in_words` 中英文。
  - 描述为空时 `description_note` 说明「雇主系统没给描述，照实说，不要代写」。
  - 只读、不联网、不写库；job_id 过匿名检查，带简历、邮箱等未声明参数一律拒收（与 authorize_application 同一道防线）。
- **说明同步**：服务器指令加一句；`evaluate_fit`、`tailor_cv` 两个提示词改为用 get_job 读全文；README 工具表、本机求职技能 `skills/openhire-job-search` 同步。
- **协议变化**：服务器现在 15 个工具、12 个提示词；验收测试的工具集合已加 get_job。

## 证据

- 新增 `tests/test_get_job.py` 6 条（正常返回、分段、下架与过期、空描述、错 id 与错页、个人信息当 id 被拒）；验收测试加一次真实 MCP 调用和一次夹带 resume 参数被拒。
- 全量 1,194 通过。版本 0.8.68，十二处版本号与 `uv.lock` 同步，推 main 由 Actions 发版。

## 下一步

- 下一晚模拟求职者测试会用到它；日读时看助手有没有照原文引用、有没有把下架岗当在招。

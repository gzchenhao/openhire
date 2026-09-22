# Acceptance log · 验收日志

Every session on this project ends with a report written into this folder. They are not
release notes. They are the working record: what was attempted, what the evidence was, and
**what turned out to be wrong**. Nothing here has been cleaned up after the fact.

本目录是这个项目的验收日志，不是发布说明。每次开工结束都写一份，含背景、做了什么、
可核对的证据、结论。**包括做错的部分，事后不修改。**

The project is built by a deep-tech headhunter who does not write code, pair-programming with
Claude Code. That makes the failure record more interesting than the success record, so it is
kept in the open.

---

## Start here · 先读这几篇

These are the entries where a public claim of ours turned out to be wrong, and what we did about it.
**这几篇是我们对外说错了话、然后收回的记录。**

| | |
|---|---|
| [031](031-增长报告落地与CVPR结论收回.md) | A published conclusion retracted. 公开结论的收回。 |
| [035](035-Round3软文吐槽处理.md) | A number with no provenance, and a house style rule we broke ourselves. 一条无出处的数字。 |
| [043](043-Round7-技能词表与静默截断.md) | Two real defects, found by a tester whose stated mechanism was backwards in both cases. |
| [044](044-DeepSeek全量抽取与GLM套餐到期.md) | Two of my own assumptions, measured and falsified. 两次我自己的错误假设。 |
| [046](046-Round5与0.6.1发布.md) | Fixed for a week, shipped to nobody. 修了一周，用户一个都没拿到。 |
| [036](036-Pages上线与北森失联.md) | A page published by accident, and a refresh failure that reported success. |

## By theme

**External testers · 外部体验官**
[026](026-外部体验官报告与0.4.2修复.md) ·
[033](033-体验官Round2复验与N1N2N4N5修复.md) ·
[035](035-Round3软文吐槽处理.md) ·
[037](037-Round4雇主视角处理.md) ·
[041](041-Round6-MCP真调用与薪资噪声.md) ·
[043](043-Round7-技能词表与静默截断.md) ·
[046](046-Round5与0.6.1发布.md)

**Releases · 发布**
[006](006-M4打包与发布准备.md) ·
[008](008-发布执行记录.md) ·
[011](011-官方Registry发布执行记录.md) ·
[015](015-v0.2.0发布.md) ·
[021](021-glama评分与0.3.1热修.md) ·
[025](025-Agent平台商店上架调研与0.4.0发布.md) ·
[027](027-agent视角的重复岗位-role_group与分页.md) ·
[046](046-Round5与0.6.1发布.md)

**Coverage and crawling · 数据覆盖与抓取边界**
[014](014-自动驾驶具身智能覆盖扩张.md) ·
[020](020-楔子覆盖冲刺-Moka适配器与11家复查.md) ·
[022](022-第三个国内vendor调研.md) ·
[017](017-GLM接入与快照自动刷新.md) ·
[044](044-DeepSeek全量抽取与GLM套餐到期.md)

**Employer claim · 雇主认领**
[034](034-雇主认领落地能力.md) ·
[037](037-Round4雇主视角处理.md)

**Distribution · 分发与渠道**
[010](010-目录提交策略与官方Registry材料.md) ·
[024](024-四渠道齐发首日归因.md) ·
[029](029-渠道实测与脉脉首帖.md) ·
[030](030-知乎转向具身赛道与文章发布.md) ·
[032](032-Glama实况数据与listing改名.md) ·
[039](039-知乎数据后台摸底.md) ·
[040](040-X线程发布与催促.md) ·
[045](045-知乎走深与X日常.md)

**Product definition · 定位与规格**
[019](019-产品定位锤炼.md) ·
[028](028-立项-技能标签精度与销售岗噪音.md) ·
[038](038-doctor与知乎回答发布.md) ·
[042](042-apply链接信任校验.md)

---

The rules these reports are written against are in [`CLAUDE.md`](../CLAUDE.md) — including the
four hard rules for anything we publish, of which rule 4 exists because we broke it:
*a verb describing an employer's behaviour must have a field behind it.*

"""docs/portals.html: the link directory for the blind spots, as a page a person can click.

Generated from seed/not_indexed.py by `ohp portals --html docs/portals.html`; the test
suite regenerates it and fails when the committed page and the registry disagree, so the
page can never drift from what the tools answer. The page's date is the newest
last_checked in the registry, not the build time, for the same reason.
"""

from __future__ import annotations

import html

from .seed import not_indexed

_STYLE = """:root{--bg:#fff;--fg:#1a1d1a;--dim:#5e6b62;--line:#e3e7e3;--accent:#1f7a4d}
@media(prefers-color-scheme:dark){:root{--bg:#0f1211;--fg:#e9eee9;--dim:#9aa69d;--line:#252b27;--accent:#4ade87}}
body{background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,"Segoe UI",system-ui,sans-serif;
     margin:0 auto;max-width:52rem;padding:16px;padding-block:3rem}
a{color:var(--accent);overflow-wrap:anywhere}
h1{font-size:1.5rem;margin:0 0 .4rem}
h2{font-size:1.15rem;margin:2rem 0 .6rem}
.dim{color:var(--dim)}
table{border-collapse:collapse;width:100%;font-size:.93em}
td,th{border-bottom:1px solid var(--line);padding:.5rem .4rem;text-align:left;vertical-align:top}
th{font-weight:600}
code{font-size:.92em}
@media(max-width:640px){thead{display:none}tr{display:block;border-bottom:1px solid var(--line);padding:.4rem 0}
  td{display:block;border:0;padding:.15rem 0}td:first-child{font-weight:600}}"""


def _e(text: str | None) -> str:
    return html.escape(text or "", quote=True)


def render() -> str:
    entries = not_indexed.portals()
    as_of = max([e.last_checked for e in entries] + [p.last_checked for p in not_indexed.second_portals()])
    parts = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>OpenHire · 读不到的招聘门户</title>",
        '<meta name="description" content="自动驾驶、具身智能、大模型方向在招、但岗位放在 OpenHire 读不了的地方的公司：'
        '它们自己的招聘页链接，点开直接看。">',
        f"<style>\n{_STYLE}\n</style>",
        "</head>",
        "<body>",
        "<h1>读不到的招聘门户</h1>",
        f'<p class="dim">{len(entries)} 家公司 · 最近核对 {_e(as_of)} · 由 '
        '<a href="https://github.com/gzchenhao/openhire/blob/main/src/openhire/seed/not_indexed.py">登记表</a> 生成</p>',
        "<p>这些公司在自动驾驶、具身智能、大模型方向招人，岗位却放在 OpenHire 读不了的地方："
        "飞书招聘的列表接口要请求签名（我们视为访问控制，不绕过），有的只在 BOSS 直聘上发，"
        "有的官网没有可读的岗位列表。岗位是真的，人用浏览器就能看。下面是它们自己的招聘页，点开直接看。</p>",
        "<p>OpenHire 不读、不存、不标日期、不盯这些页面。在 AI 助手里，"
        "<code>list_portals</code> 工具给的是同一份清单；带浏览器的助手可以替你打开。</p>",
    ]
    for sector in not_indexed.SECTORS:
        rows = [e for e in entries if e.sector == sector]
        if not rows:
            continue
        parts.append(f"<h2>{_e(not_indexed.SECTOR_NAMES_ZH[sector])}（{len(rows)}）</h2>")
        parts.append("<table>")
        parts.append("<thead><tr><th>公司</th><th>招聘页</th><th>不登录能看到什么</th><th>为什么不在索引里</th><th>核对</th></tr></thead>")
        parts.append("<tbody>")
        for e in rows:
            url = _e(e.careers_url)
            parts.append(
                f"<tr><td>{_e(e.name)}</td>"
                f'<td><a href="{url}" rel="nofollow noopener">{url}</a></td>'
                f"<td>{_e(e.visible_without_login_zh)}</td>"
                f"<td>{_e(e.reason_zh)}</td>"
                f"<td>{_e(e.last_checked)}</td></tr>"
            )
        parts.append("</tbody></table>")
    seconds = not_indexed.second_portals()
    if seconds:
        parts.append(f"<h2>已收录、但另有一个读不到的门户（{len(seconds)}）</h2>")
        parts.append("<p>索引读得到这些公司的一个招聘页，但它们在另一个门户上还挂着岗位，只在那里的岗位搜不到。</p>")
        parts.append("<table>")
        parts.append("<thead><tr><th>公司</th><th>读不到的门户</th><th>不登录能看到什么</th><th>说明</th><th>核对</th></tr></thead>")
        parts.append("<tbody>")
        for p in seconds:
            url = _e(p.careers_url)
            parts.append(
                f"<tr><td>{_e(p.name)}</td>"
                f'<td><a href="{url}" rel="nofollow noopener">{url}</a></td>'
                f"<td>{_e(p.visible_without_login_zh)}</td>"
                f"<td>{_e(p.note_zh)}</td>"
                f"<td>{_e(p.last_checked)}</td></tr>"
            )
        parts.append("</tbody></table>")
    parts += [
        "<h2>不在这张表上的公司</h2>",
        "<p>它的招聘页如果在 Greenhouse、Lever、Ashby、Moka、北森、Workable、SmartRecruiters 或 Workday 上，"
        "对助手说「读一下这家公司的招聘页」并贴上网址，OpenHire 现读给你；想以后一直盯着，"
        "再说「把它加进我的索引」。</p>",
        '<p>是这些公司的招聘负责人？想让贵公司的岗位在这里可读，见 <a href="employers.html">给雇主的一页说明</a>：'
        "免费、只读，排序谁也买不到。</p>",
        '<p class="dim"><a href="./">OpenHire 首页</a> · <a href="https://github.com/gzchenhao/openhire">GitHub</a></p>',
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)

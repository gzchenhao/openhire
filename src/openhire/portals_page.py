"""docs/portals.html: the link directory for the blind spots, as a page a person can click.

Generated from seed/not_indexed.py by `ohp portals --html docs/portals.html`; the test
suite regenerates it and fails when the committed page and the registry disagree, so the
page can never drift from what the tools answer. The page's date is the newest
last_checked in the registry, not the build time, for the same reason.
"""

from __future__ import annotations

import html

from . import house_style
from .seed import not_indexed

_STYLE = house_style.CSS


def _e(text: str | None) -> str:
    return html.escape(text or "", quote=True)


SECTOR_NAMES_EN = {"autonomous_driving": "Autonomous driving", "embodied_ai": "Embodied AI",
                   "ai_infra": "AI infrastructure and foundation models"}

# The page in two languages behind one 中文 / English switch (house_style.SWITCH); every row
# comes from the registry, which already carries each sentence in both.
_TEXT = {
    "zh": {
        "h1": "读不到的招聘门户",
        "meta": "{n} 家公司 · 最近核对 {d} · 由 <a href=\"{src}\">登记表</a> 生成",
        "intro": [
            "<p>这些公司在自动驾驶、具身智能、大模型方向招人。岗位放在 OpenHire 读不到的地方：飞书招聘、BOSS 直聘，或没有岗位列表的官网。</p>",
            "<p>岗位是真的。用浏览器打开公司自己的招聘页，就能看到。</p>",
            "<p class=\"dim\">飞书的列表接口要请求签名。我们把它当作访问控制，不绕过。OpenHire 不读、不存、不标日期、不盯这些页面。助手里的 <code>list_portals</code> 给同一份清单。</p>",
            "<p>要助手替你看，把这句话和招聘页链接发给它：</p>",
            "<pre>用浏览器打开这个招聘页，把在招岗位的名称、城市和链接列给我；不用登录，打不开就告诉我：（贴上招聘页链接）</pre>",
            "<p class=\"if\">如果：</p>",
            "<p class=\"c\">1. 助手只能读网页文字</p>",
            "<p class=\"c\">2. 它说页面上没有岗位</p>",
            "<p class=\"stop\">自己点开招聘页看。</p>",
        ],
        "link": "打开招聘页",
        "see": "看得到：",
        "why": "不在索引里：",
        "note": "说明：",
        "checked": "核对：",
        "second_h2": "已收录、但另有一个读不到的门户（{n}）",
        "second_p": "<p>索引读得到这些公司的一个招聘页。它们在另一个门户上也有岗位，那里的岗位搜不到。</p>",
        "count": "{name}（{n}）",
        "outro": [
            "<h2>不在这张表上的公司</h2>",
            "<p>招聘页在 Greenhouse、Lever、Ashby、Moka、北森、Workable、SmartRecruiters、Workday、Rippling 或 Personio 上时：</p>",
            "<ol><li>对助手说「读一下这家公司的招聘页」，贴上网址。OpenHire 现读。</li>"
            "<li>要一直盯着，说「把它加进我的索引」。</li></ol>",
            '<p>是这些公司的招聘负责人？看<a href="employers.html">给雇主</a>。免费，只读，排序谁也买不到。</p>',
            '<p class="dim"><a href="./">OpenHire 首页</a> · <a href="https://github.com/gzchenhao/openhire">GitHub</a></p>',
        ],
    },
    "en": {
        "h1": "Hiring portals we cannot read",
        "meta": "{n} companies · last checked {d} · generated from <a href=\"{src}\">the registry</a>",
        "intro": [
            "<p>These companies hire in autonomous driving, embodied AI and foundation models. Their postings are where OpenHire cannot read them: Feishu Hire, BOSS Zhipin, or a site with no list.</p>",
            "<p>The jobs are real. Open the company's own careers page in a browser to see them.</p>",
            "<p class=\"dim\">Feishu's list API needs signed requests. We treat that as access control and do not work around it. OpenHire does not read, store, date or watch these pages. In an assistant, <code>list_portals</code> gives the same list.</p>",
            "<p>To have an assistant look for you, send it this sentence with the careers page link:</p>",
            "<pre>Open this careers page in a browser and list the open jobs with title, city and link; no login needed, and tell me if it will not open: (paste the careers page link)</pre>",
            "<p class=\"if\">If:</p>",
            "<p class=\"c\">1. The assistant reads only page text</p>",
            "<p class=\"c\">2. It says the page has no jobs</p>",
            "<p class=\"stop\">Open the careers page yourself.</p>",
        ],
        "link": "Open the careers page",
        "see": "You see: ",
        "why": "Not in the index: ",
        "note": "Note: ",
        "checked": "Checked: ",
        "second_h2": "In the index, but with a second portal we cannot read ({n})",
        "second_p": "<p>The index reads one careers page for these companies. They also post on another portal. The jobs there are not in search.</p>",
        "count": "{name} ({n})",
        "outro": [
            "<h2>A company not on this list</h2>",
            "<p>If its careers page is on Greenhouse, Lever, Ashby, Moka, Beisen, Workable, SmartRecruiters, Workday, Rippling or Personio:</p>",
            "<ol><li>Tell the assistant \"read this company's careers page\" and paste the address. OpenHire reads it live.</li>"
            "<li>To keep watching it, say \"add it to my index\".</li></ol>",
            '<p>Hiring at one of these companies? Read <a href="employers.html">For employers</a>. Free. Read-only. Nobody can buy ranking.</p>',
            '<p class="dim"><a href="./">OpenHire home</a> · <a href="https://github.com/gzchenhao/openhire">GitHub</a></p>',
        ],
    },
}
_SRC = "https://github.com/gzchenhao/openhire/blob/main/src/openhire/seed/not_indexed.py"


def _entry(t: dict, name: str, url: str, see: str, why_label: str, why: str, checked: str) -> str:
    """One company, laid out like a step on the 查公司 page: name, link, then grey notes."""
    return (f'<li><p class="lead">{_e(name)}</p>'
            f'<p><a href="{_e(url)}" rel="nofollow noopener">{t["link"]}</a></p>'
            f'<p class="dim">{t["see"]}{_e(see)}</p>'
            f'<p class="dim">{why_label}{_e(why)}</p>'
            f'<p class="dim">{t["checked"]}{_e(checked)}</p></li>')


def _block(lang: str, entries, seconds, as_of: str) -> list[str]:
    t = _TEXT[lang]
    zh = lang == "zh"
    out = [f"<h1>{t['h1']}</h1>",
           '<p class="dim">' + t["meta"].format(n=len(entries), d=_e(as_of), src=_SRC) + "</p>",
           *t["intro"]]
    for sector in not_indexed.SECTORS:
        rows = [e for e in entries if e.sector == sector]
        if not rows:
            continue
        name = not_indexed.SECTOR_NAMES_ZH[sector] if zh else SECTOR_NAMES_EN[sector]
        out.append(f"<h2>{_e(t['count'].format(name=name, n=len(rows)))}</h2>")
        out.append("<ul>")
        for e in rows:
            out.append(_entry(t, e.name, e.careers_url,
                              e.visible_without_login_zh if zh else e.visible_without_login,
                              t["why"], e.reason_zh if zh else e.reason, e.last_checked))
        out.append("</ul>")
    if seconds:
        out.append(f"<h2>{_e(t['second_h2'].format(n=len(seconds)))}</h2>")
        out.append(t["second_p"])
        out.append("<ul>")
        for p in seconds:
            out.append(_entry(t, p.name, p.careers_url,
                              p.visible_without_login_zh if zh else p.visible_without_login,
                              t["note"], p.note_zh if zh else p.note, p.last_checked))
        out.append("</ul>")
    out += t["outro"]
    return out


def render() -> str:
    entries = not_indexed.portals()
    seconds = not_indexed.second_portals()
    as_of = max([e.last_checked for e in entries] + [p.last_checked for p in seconds])
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
        house_style.NOSCRIPT,
        "</head>",
        "<body>",
        house_style.nav("portals"),
        "<main>",
        house_style.SWITCH,
        '<div class="lang-zh">',
        *_block("zh", entries, seconds, as_of),
        "</div>",
        '<div class="lang-en">',
        *_block("en", entries, seconds, as_of),
        "</div>",
        "</main>",
        house_style.lang_script("OpenHire · 读不到的招聘门户", "OpenHire · Hiring portals we cannot read"),
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)

"""One look for every OpenHire page, taken from EarlyTip's layout spec (2026-11-01).

The 查公司 page was restyled first, to match EarlyTip's daily brief; the maintainer then asked
for every page to carry the same look ("they are the same gene"). This module is the single
copy: scripts/apply_house_style.py writes it into the static pages under docs/ (and their
packaged twins), portals_page.py and hosted.landing_html() embed it when they render, and
tests/test_house_style.py fails when any page drifts from it.

What it is: the spec's colours as variables, system Chinese fonts at 15px / 1.75, an 860px
column, a sticky top bar with the current page as a brick-red pill, section headings with a
3px red bar, thin #e0e0d8 rules, #1a6496 links without underline, white cards with one shade
of shadow for code and tables. Brick red is for the brand, the bar, the pill and headings,
never for body text. No dark mode (EarlyTip has none). On a phone, table rows stack so no
column is squeezed to one character per line.
"""

from __future__ import annotations

import html

CSS = """/* house style: EarlyTip layout spec (2026-11-01); edit src/openhire/house_style.py, then run scripts/apply_house_style.py */
:root{--bg:#f6f6f0;--bg2:#ffffff;--fg:#1a1a1a;--fg-dim:#888;--accent:#c0392b;--link:#1a6496;--border:#e0e0d8;--max-w:860px}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font-family:"PingFang SC","Microsoft YaHei",-apple-system,BlinkMacSystemFont,sans-serif;font-size:15px;line-height:1.75}
nav.house{position:sticky;top:0;z-index:100;background:var(--bg);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
nav.house .brand{font-size:14px;font-weight:700;color:var(--fg);letter-spacing:.05em;text-decoration:none}
nav.house .brand span{color:var(--accent)}
nav.house .links{display:flex;flex-wrap:wrap;gap:14px;align-items:center;font-size:11px}
nav.house .links a{color:var(--accent);text-decoration:none}
nav.house .links .here{color:var(--accent);border:1px solid var(--accent);border-radius:12px;padding:3px 11px;background:var(--bg2)}
main{max-width:var(--max-w);margin:0 auto;padding:48px 24px 80px}
h1{font-size:26px;font-weight:700;line-height:1.3;margin:0 0 8px}
h2{font-size:15px;font-weight:700;margin:40px 0 14px;padding-left:10px;border-left:3px solid var(--accent);line-height:1.6}
h3{font-size:13px;font-weight:700;color:var(--accent);margin:18px 0 8px}
p{margin:0 0 12px}
ul,ol{margin:0 0 16px;padding-left:1.3em}
li{font-size:14px;line-height:1.7;margin:4px 0}
a{color:var(--link);text-decoration:none;overflow-wrap:anywhere}
a:hover{text-decoration:underline}
b,strong{font-weight:700}
.dim{color:var(--fg-dim)}
hr{border:0;border-top:1px solid var(--border);margin:32px 0}
code{font-size:13px;background:var(--bg2);border:1px solid var(--border);border-radius:4px;padding:0 4px}
pre{background:var(--bg2);border-left:3px solid var(--accent);border-radius:0 4px 4px 0;box-shadow:0 1px 3px rgba(0,0,0,.06);padding:14px 18px;margin:0 0 16px;font-size:13px;line-height:1.7;white-space:pre-wrap;overflow:auto;position:relative}
pre code{background:none;border:0;padding:0;font-size:inherit}
table{width:100%;border-collapse:collapse;margin:0 0 20px;background:var(--bg2);font-size:14px;line-height:1.6;box-shadow:0 1px 3px rgba(0,0,0,.06)}
th{text-align:left;font-size:12px;font-weight:600;color:var(--fg-dim);padding:10px 12px;border-bottom:2px solid var(--border);background:var(--bg)}
td{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:top}
tr:last-child td{border-bottom:none}
button{font:inherit;font-size:12px;color:var(--accent);background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:3px 11px;cursor:pointer}
button[aria-pressed="true"]{border-color:var(--accent);font-weight:600}
.switch{display:flex;justify-content:flex-end;gap:8px;margin:0 0 16px}
.lang-en{display:none}
html[data-lang="en"] .lang-zh{display:none}
html[data-lang="en"] .lang-en{display:block}
footer.house{border-top:1px solid var(--border);padding:24px;text-align:center;font-size:11px;color:var(--fg-dim);line-height:2}
@media (max-width:600px){
  nav.house{padding:10px 16px}
  main{padding:28px 16px 60px}
  h1{font-size:20px}
  thead{display:none}
  table,tbody,tr,td{display:block;width:100%}
  tr{border-bottom:1px solid var(--border);padding:6px 0}
  td{border:0;padding:4px 12px}
  td:first-child{font-weight:700}
}"""

# The top bar: (label, link, page key). Relative links resolve on github.io (/openhire/...) and
# on the hosted endpoint (which serves /connect.html, /checklist.html, ... and / for the home
# page); the employer page lives on github.io only, so it is linked absolutely.
NAV = (
    ("首页", "./", "index"),
    ("连接向导", "connect.html", "connect"),
    ("求职清单", "checklist.html", "checklist"),
    ("查公司", "check-company.html", "check-company"),
    ("读不到的门户", "portals.html", "portals"),
    ("给雇主", "https://gzchenhao.github.io/openhire/employers.html", "employers"),
)


def nav(current: str, home: str = "./") -> str:
    """The top bar, with `current` shown as the pill. `home` is where the brand links."""
    items = []
    for label, href, key in NAV:
        if key == "index":
            href = home
        if key == current:
            items.append(f'<span class="here">{html.escape(label)}</span>')
        else:
            items.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>')
    return (f'<nav class="house"><a class="brand" href="{html.escape(home, quote=True)}">Open<span>Hire</span></a>'
            f'<span class="links">{"".join(items)}</span></nav>')


# The 中文 / English switch every bilingual page carries (reports/131: the maintainer found
# the portal directory, the employer page and the home pages had none). The choice is kept
# under the same localStorage key as the checklist and the connect guide, so picking English
# once carries across every page. Without JavaScript both blocks show and the switch hides.
SWITCH = ('<div class="switch" role="group" aria-label="语言 · Language">\n'
          '<button type="button" data-set="zh" aria-pressed="true">中文</button>\n'
          '<button type="button" data-set="en" aria-pressed="false">English</button>\n'
          '</div>')
NOSCRIPT = '<noscript><style>.lang-en{display:block}.switch{display:none}</style></noscript>'


def lang_script(title_zh: str, title_en: str) -> str:
    """?lang= first, then the reader's last choice, then the browser language."""
    titles = '{zh:"%s",en:"%s"}' % (title_zh.replace('"', ""), title_en.replace('"', ""))
    return """<script>
(function(){
  var html=document.documentElement;
  var titles=%s;
  function apply(l,save){
    html.setAttribute("data-lang",l);
    html.setAttribute("lang",l==="en"?"en":"zh-CN");
    document.title=titles[l];
    var bs=document.querySelectorAll(".switch button");
    for(var i=0;i<bs.length;i++){bs[i].setAttribute("aria-pressed",bs[i].getAttribute("data-set")===l?"true":"false");}
    if(save){try{localStorage.setItem("openhire-lang",l);}catch(e){}}
  }
  var q=null;
  try{q=new URLSearchParams(location.search).get("lang");}catch(e){}
  var saved=null;
  try{saved=localStorage.getItem("openhire-lang");}catch(e){}
  var nav=(navigator.language||"").toLowerCase();
  var l=(q==="en"||q==="zh")?q:(saved==="en"||saved==="zh")?saved:(/^(zh|yue)/.test(nav)?"zh":"en");
  apply(l,false);
  var sw=document.querySelector(".switch");
  if(sw){sw.addEventListener("click",function(ev){
    var b=ev.target.closest?ev.target.closest("button"):null;
    if(b&&b.getAttribute("data-set")){apply(b.getAttribute("data-set"),true);}
  });}
})();
</script>""" % titles

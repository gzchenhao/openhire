# -*- coding: utf-8 -*-
"""Render the monthly ghost-jobs report page from report-data.json."""
import io, json, html

d = json.load(io.open(r"C:\openhire\docs\report-data.json", encoding="utf-8"))

def rows(items, extra_class=""):
    out = []
    for t in items:
        cn = " cn" if t["vendor"] in ("beisen", "moka") else ""
        flag = ' <span class="tag warnflag">口径存疑</span>' if t["median"] > 730 else ""
        out.append(
            f'<tr class="{extra_class}"><td>{html.escape(t["name"])}'
            f'{"<span class=tag>国内</span>" if cn else ""}{flag}</td>'
            f'<td class=num>{t["n"]}</td><td class=num><b>{t["median"]}</b></td>'
            f'<td class=num>{t["stale"]}%</td><td class=num>{t["touched"]}%</td></tr>'
        )
    return "\n".join(out)

HTML = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>岗位在架时长月报 · {d['generated']} · OpenHire</title>
<meta name="description" content="{d['employers']} 家公司、{d['live']:,} 个在架岗位，按雇主自己招聘系统里的真实发布日统计在架时长。每月更新，数据可复核。">
<link rel="canonical" href="https://gzchenhao.github.io/openhire/report/">
<style>
:root{{--bg:#fff;--fg:#1a1d1a;--dim:#5e6b62;--line:#e3e7e3;--accent:#1f7a4d;--warn:#a8501e;--card:#f7f9f7}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1211;--fg:#e9eee9;--dim:#9aa69d;--line:#252b27;--accent:#4ade87;--warn:#e3b341;--card:#161a18}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:820px;margin:0 auto;padding:48px 20px 80px}}
h1{{font-size:30px;line-height:1.3;margin:0 0 8px}}
h2{{font-size:20px;margin:48px 0 12px;padding-top:24px;border-top:1px solid var(--line)}}
.sub{{color:var(--dim);margin:0 0 36px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:28px 0}}
.stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}}
.stat b{{display:block;font-size:27px;line-height:1.2;color:var(--accent)}}
.stat span{{color:var(--dim);font-size:13px}}
.tblwrap{{overflow-x:auto;margin:16px 0}}
table{{border-collapse:collapse;width:100%;font-size:14.5px;min-width:520px}}
th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line)}}
th{{color:var(--dim);font-weight:600;font-size:13px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.tag{{font-size:11px;color:var(--dim);border:1px solid var(--line);border-radius:4px;padding:1px 5px;margin-left:6px}}
.warnflag{{color:var(--warn);border-color:var(--warn)}}
.note{{background:var(--card);border-left:3px solid var(--warn);padding:14px 18px;border-radius:0 8px 8px 0;margin:24px 0}}
.note b{{color:var(--warn)}}
code{{background:var(--card);padding:2px 6px;border-radius:4px;font-size:14px}}
a{{color:var(--accent)}}
footer{{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);color:var(--dim);font-size:14px}}
</style>
</head>
<body><div class="wrap">

<h1>岗位在架时长月报</h1>
<p class="sub">{d['generated']} · {d['employers']} 家公司 · {d['live']:,} 个在架岗位<br>
数据来自各公司<b>自己的招聘系统（ATS）公开接口</b>，不是招聘平台。每月更新。</p>

<div class="grid">
<div class="stat"><b>{d['median']} 天</b><span>在架时长中位数</span></div>
<div class="stat"><b>{d['p90']}%</b><span>挂了超过 90 天</span></div>
<div class="stat"><b>{d['p180']}%</b><span>挂了超过 180 天</span></div>
<div class="stat"><b>{d['p365']}%</b><span>挂了超过一年</span></div>
</div>

<div class="note">
<b>先说这份数据不能证明什么。</b><br>
我们量得到「这个岗位挂了多久」，量不到「雇主还想不想招」。挂得久可能是没打算招，
也可能是真的招不到人（技术岗尤其常见），还可能是常青岗——公司为高频岗位常年挂一个入口，随到随收。
这三种从在架天数上分不开。<b>所以下面的数字是「值得你去问」的依据，不是「这些是幽灵岗位」的结论。</b>
</div>

<h2>国内和海外差多少</h2>
<div class="tblwrap"><table>
<tr><th>来源</th><th class=num>在架岗位</th><th class=num>中位在架</th><th class=num>超过半年</th></tr>
<tr><td>国内（北森 / Moka）</td><td class=num>{d['cn']['n']:,}</td><td class=num><b>{d['cn']['median']} 天</b></td><td class=num>{d['cn']['p180']}%</td></tr>
<tr><td>海外（Greenhouse / Lever / Ashby）</td><td class=num>{d['ov']['n']:,}</td><td class=num><b>{d['ov']['median']} 天</b></td><td class=num>{d['ov']['p180']}%</td></tr>
</table></div>
<p>差距是真实的，但别急着下价值判断：两边的招聘系统对「发布日」这个字段的语义并不统一，
国内有少数公司记的可能是「需求创建日」而不是「上线日」，这会把它们的天数整体抬高。
下面那张「挂得最久」的表里，排前两位的就属于这种情况，我们标出来了。</p>

<h2>摘牌最快的公司</h2>
<p>这张表比「谁挂得久」有用得多。<b>岗位会被摘下来，通常只有一个原因：招到人了。</b>
中位数三四十天，说明这家公司的招聘流程是真的转得动的。（只统计在架岗位 ≥10 个的公司。）</p>
<div class="tblwrap"><table>
<tr><th>公司</th><th class=num>在架岗位</th><th class=num>中位在架</th><th class=num>超半年占比</th><th class=num>近 30 天被雇主动过</th></tr>
{rows(d['freshest'])}
</table></div>

<h2>在架时间最长的公司</h2>
<p><b>这张表不是一份指控名单，请连着最后一列一起读。</b>在架时间长本身不说明任何意图，
它只说明「值得在面试时问一句」。标了<span class="tag warnflag">口径存疑</span>的公司，
中位数超过两年，这在真实招聘里几乎不可能——最合理的解释不是它们在挂鬼岗，
而是<b>它们的招聘系统把「需求创建日」当成了发布日</b>，国内 ATS 对这个字段的语义本来就不统一。
我们把它们留在表里而不是删掉，是因为删掉等于替你做判断；标出来，你自己判断。</p>
<div class="tblwrap"><table>
<tr><th>公司</th><th class=num>在架岗位</th><th class=num>中位在架</th><th class=num>超半年占比</th><th class=num>近 30 天被雇主动过</th></tr>
{rows(d['stalest'])}
</table></div>

<h2>为什么最后一列最重要</h2>
<p>「挂了多久」单独看会误判。我们还记录了雇主自己在他们招聘系统里
<b>最后一次改动这个岗位</b>的时间，这个字段他们改不掉，也刷不了。两个数放一起才有意义：</p>
<ul>
<li>挂了 367 天、<b>367 天没人碰过</b> → 大概率是弃坑；</li>
<li>挂了 327 天、<b>13 天前刚被动过</b> → 大概率是有人维护的常青岗，不是死岗。</li>
</ul>
<p>全库里在架时长评分最高（<code>ghost_score ≥ 0.99</code>）的 {d['ghost_hi']:,} 个岗位中，
<b>{d['ghost_hi_touched']}% 在最近 30 天被雇主动过</b>。
也就是说，光看「挂得久」这一个指标，会把其中约三分之一判错。</p>

<h2>你可以怎么用</h2>
<ul>
<li><b>投之前查原始发布日。</b>多数公司官网的招聘页会给，招聘平台上的日期不要信，那是平台刷新过的；</li>
<li><b>看公司整体的中位数，别只看单个岗位。</b>一家中位三四十天的公司，流程是转得动的；</li>
<li><b>中位数长不等于别投</b>，但值得在一面直接问：这个岗位挂多久了？之前面过几个人？卡在哪一环？对方的反应本身就是信息。</li>
</ul>

<h2>自己跑一遍</h2>
<p>这页上每个数字都可以复核，工具是开源的（MIT，不用注册，简历不上传）：</p>
<p><code>uvx openhire@latest serve</code>（需先装 <a href="https://docs.astral.sh/uv/">uv</a>），
或者去 <a href="https://github.com/gzchenhao/openhire/releases/latest">Releases</a> 下载 <code>.mcpb</code> 双击装进 Claude 桌面版，不用碰命令行。</p>
<p>然后问你的 AI 助手：<b>「帮我查一下小鹏现在在招哪些智驾岗，每个挂了多久了？」</b></p>

<footer>
<p><b>方法</b>：直接读各公司官网招聘页背后的公开 ATS 接口（Greenhouse / Lever / Ashby / 北森 / Moka），
取雇主自己系统里记的发布日与最后改动时间。不抓招聘平台，不使用任何需要登录的数据。
索引每周自动刷新，本页每月重算，数字会有小幅变动。</p>
<p><b>口径</b>：百分比四舍五入到整数，「0%」表示不足 0.5%。公司表只列在架岗位 ≥10 个的公司。</p>
<p>数据与代码：<a href="https://github.com/gzchenhao/openhire">github.com/gzchenhao/openhire</a> ·
是雇主本人且想更正自己的岗位状态？<a href="https://github.com/gzchenhao/openhire/issues/new?template=employer_claim.yml">免费认领</a>，按企业身份验证，不收费，也不影响排序。</p>
</footer>

</div></body></html>
"""
io.open(r"C:\openhire\docs\report\index.html", "w", encoding="utf-8").write(HTML)
print("wrote docs/report/index.html", len(HTML), "bytes")

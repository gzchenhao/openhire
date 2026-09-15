# -*- coding: utf-8 -*-
"""Compute the monthly ghost-jobs report payload from the live index."""
import io, sys, json, datetime as dt, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from sqlalchemy import select, func
from openhire.db import init_db, session_scope, Job
from openhire.db.models import Company

CN_VENDORS = {"beisen", "moka"}
init_db()
now = dt.datetime.now(dt.timezone.utc)

with session_scope() as s:
    companies = {c.id: c for c in s.execute(select(Company)).scalars()}
    rows = s.execute(
        select(Job.company_id, Job.title, Job.posted_at, Job.updated_at,
               Job.ghost_score, Job.relist_count, Job.role_family)
        .where(Job.delisted_at.is_(None))
    ).all()

def days(x):
    if not x: return None
    x = x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)
    return (now - x).days

recs = []
for cid, title, posted, updated, ghost, relist, rf in rows:
    c = companies.get(cid)
    # An ATS that echoes posted_at back as updated_at is not telling us the employer has
    # gone quiet; it is telling us nothing. Ashby and Lever never differ, Beisen differs on
    # 3% of rows. Counting those as "untouched" would publish a column about the vendor's
    # API while it reads as an accusation about the employer.
    real_upd = bool(posted and updated and posted != updated)
    recs.append(dict(cid=cid, name=c.name if c else cid,
                     vendor=c.ats_vendor if c else "?", title=title,
                     d_open=days(posted), d_upd=days(updated) if real_upd else None,
                     ghost=ghost or 0.0, relist=relist or 0, rf=rf))

live = [r for r in recs if r["d_open"] is not None]
n = len(live)
def pct(f): return round(100 * sum(1 for r in live if f(r)) / n, 1)

cn = [r for r in live if r["vendor"] in CN_VENDORS]
ov = [r for r in live if r["vendor"] not in CN_VENDORS]
def med(v):
    v = sorted(x["d_open"] for x in v)
    return v[len(v)//2] if v else None

# per-company: median days open, and how many are still being touched
per = collections.defaultdict(list)
for r in live: per[r["cid"]].append(r)
tbl = []
for cid, v in per.items():
    if len(v) < 10: continue
    ds = sorted(x["d_open"] for x in v)
    known = [x for x in v if x["d_upd"] is not None]
    touched = sum(1 for x in known if x["d_upd"] <= 30)
    tbl.append(dict(name=v[0]["name"], vendor=v[0]["vendor"], n=len(v),
                    median=ds[len(ds)//2],
                    stale=round(100*sum(1 for d in ds if d > 180)/len(ds)),
                    # None means this employer's ATS does not report it at all.
                    touched=(round(100*touched/len(known)) if known else None)))
tbl.sort(key=lambda x: x["median"])

hi = [r for r in live if r["ghost"] >= 0.99]
hi_known = [r for r in hi if r["d_upd"] is not None]
hi_touched = sum(1 for r in hi_known if r["d_upd"] <= 30)

out = dict(
    generated=now.date().isoformat(),
    employers=len({r["cid"] for r in live}), live=n,
    median=med(live), p90=pct(lambda r: r["d_open"] > 90),
    p180=pct(lambda r: r["d_open"] > 180), p365=pct(lambda r: r["d_open"] > 365),
    cn=dict(n=len(cn), median=med(cn), p180=round(100*sum(1 for r in cn if r["d_open"]>180)/max(1,len(cn)))),
    ov=dict(n=len(ov), median=med(ov), p180=round(100*sum(1 for r in ov if r["d_open"]>180)/max(1,len(ov)))),
    ghost_hi=len(hi), ghost_hi_known=len(hi_known),
    ghost_hi_touched=round(100*hi_touched/max(1,len(hi_known))),
    freshest=tbl[:12], stalest=sorted(tbl, key=lambda x:-x["median"])[:12],
)
io.open(r"C:\openhire\docs\report-data.json","w",encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in ("freshest","stalest")}, ensure_ascii=False, indent=1))
print("\n最快摘牌 6 家:"); [print(f"  {t['name'][:22]:24} n={t['n']:4} 中位{t['median']:4}天 超半年{t['stale']:3}% 近30天被动过{('  —' if t['touched'] is None else str(t['touched'])+'%'):>4}") for t in tbl[:6]]
print("\n最久未摘 6 家:"); [print(f"  {t['name'][:22]:24} n={t['n']:4} 中位{t['median']:4}天 超半年{t['stale']:3}% 近30天被动过{('  —' if t['touched'] is None else str(t['touched'])+'%'):>4}") for t in sorted(tbl,key=lambda x:-x['median'])[:6]]

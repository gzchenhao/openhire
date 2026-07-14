"""`ohp` — the OpenHire command-line interface.

v0.1 「哨兵」. Data pipeline (`seed`, `ingest`, `extract-*`), MCP server (`serve`), and
the agent-facing journey (`init`, `search`, `watch`, `check`, `apply`, `status`).
Output follows the 哨兵 symbol system — see console.py.
"""

from __future__ import annotations

import datetime as dt
import re
import webbrowser

import typer
from sqlalchemy import func, select

from . import __version__, client, console, service
from .console import console as c
from .db import Company, Job, Watch, init_db, session_scope
from .errors import OpenHireError

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="OpenHire 「哨兵」— agent-native job protocol. Your résumé never passes through our servers, and we never store it.",
)


def _banner() -> None:
    c.print(f"[accent]OPENHIRE[/] [risk]v{__version__} 哨兵 SENTINEL[/]  [muted]· 仅公开 ATS · 简历不经过我们服务器[/]")


# --- seed ---------------------------------------------------------------------
@app.command()
def seed() -> None:
    """Validate the seed roster against live public ATS APIs and register companies."""
    from .pipeline import seed_companies

    init_db()
    _banner()
    console.cmd("ohp seed")
    console.out("验证种子公司 tenant（要求 HTTP 200 + jobs 数组）…")

    done = {"n": 0}

    def on_result(company, result):
        done["n"] += 1
        mark = "ok" if (result.ok and result.count > 0) else "err"
        glyph = "✓" if mark == "ok" else "×"
        c.print(
            f"  [{'ok' if mark=='ok' else 'errmsg'}]{glyph}[/] "
            f"[muted]{company.ats_vendor:10}[/] {company.name:26} "
            f"[out]jobs={result.count}[/]"
        )

    stats = seed_companies(on_result=on_result)
    console.ok(
        f"已验证 {stats.verified} 家公司 · 共 {stats.total_jobs} 条在架 · "
        f"新增 {stats.inserted} · 拒绝 {stats.rejected}"
    )
    console.note("入库的只是公司与其公开 ATS 端点——没有任何候选人数据")


# --- ingest -------------------------------------------------------------------
@app.command()
def ingest(
    all_companies: bool = typer.Option(
        False, "--all", "-a", help="Crawl every company now, ignoring freshness tiers."
    ),
    company: list[str] = typer.Option(
        None, "--company", "-c", help="Crawl only these company ids (repeatable)."
    ),
    with_seed: bool = typer.Option(
        False, "--seed", help="Run `seed` first, then ingest."
    ),
    daemon: bool = typer.Option(
        False, "--daemon", help="Run the freshness loop forever (APScheduler)."
    ),
) -> None:
    """Fetch due companies from their public ATS and update the local index."""
    from .pipeline import run_ingest

    init_db()
    _banner()

    if with_seed:
        seed()

    if daemon:
        _run_daemon()
        return

    console.cmd("ohp ingest" + (" --all" if all_companies else ""))
    company_ids = list(company) if company else None
    respect = not all_companies and not company_ids

    def on_progress(phase, company_ref, result):
        if phase == "fetch" and company_ref is not None:
            mark = "ok" if result.ok else "errmsg"
            glyph = "✓" if result.ok else "×"
            c.print(
                f"  [{mark}]{glyph}[/] [muted]{company_ref.name}[/] "
                f"[out]{'jobs='+str(result.count) if result.ok else result.error}[/]"
            )

    stats = run_ingest(company_ids=company_ids, respect_interval=respect, on_progress=on_progress)
    _print_ingest_stats(stats)


def _print_ingest_stats(stats) -> None:
    if stats.companies_crawled == 0 and stats.companies_failed == 0:
        console.out("没有到期需要抓取的公司（freshness 未到）。用 --all 强制全量。")
        return
    console.ok(
        f"抓取 {stats.companies_crawled} 家 · 新 {stats.jobs_new} · 更新 {stats.jobs_updated} · "
        f"未变 {stats.jobs_unchanged} · 下架 {stats.jobs_delisted} · 重挂 {stats.jobs_relisted}"
    )
    console.out(f"LLM/启发式抽取调用：{stats.extractions}（仅 content_hash 变化时）")
    if stats.companies_failed:
        console.out(f"{stats.companies_failed} 家抓取失败：{', '.join(stats.failed_tenants[:8])}")


def _run_daemon() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    from . import config
    from .pipeline import run_ingest

    console.ok(
        f"freshness 循环启动 · hot={config.FRESHNESS_HOT_INTERVAL_HOURS}h "
        f"cold={config.FRESHNESS_COLD_INTERVAL_HOURS}h · 每 tenant ≥ "
        f"{config.MIN_TENANT_INTERVAL_MINUTES}min · 并发 ≤ {config.MAX_GLOBAL_CONCURRENCY}"
    )
    console.note("Ctrl-C 退出。只发出对公开 ATS 的 GET 请求，绝不上传任何数据。")

    def tick():
        ts = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
        stats = run_ingest(respect_interval=True)
        if stats.jobs_seen or stats.companies_crawled:
            console.out(
                f"[{ts}] 抓取 {stats.companies_crawled} 家 · 新 {stats.jobs_new} · "
                f"下架 {stats.jobs_delisted}"
            )

    scheduler = BlockingScheduler(timezone="UTC")
    # Check for due companies every 10 minutes; per-tenant floor still applies.
    scheduler.add_job(tick, "interval", minutes=10, next_run_time=dt.datetime.now())
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.out("freshness 循环已停止。")


# --- serve --------------------------------------------------------------------
@app.command()
def serve() -> None:
    """Start the stdio MCP server (for Claude Desktop / Cursor / CLI clients)."""
    from .mcp_server import serve as _serve

    # NOTE: no banner/stdout chatter — stdio transport owns stdout for the MCP protocol.
    _serve()


# --- search -------------------------------------------------------------------
@app.command()
def search(
    skills: str = typer.Option(None, "--skills", help="Comma-separated skills (ANY overlap), or 'auto'."),
    required_skills: str = typer.Option(None, "--required-skills", help="Comma-separated skills that must ALL be present (AND)."),
    remote: bool = typer.Option(False, "--remote", help="Only fully-remote roles."),
    remote_scope: str = typer.Option(None, "--remote-scope", help="worldwide | region_locked | country_locked."),
    min_salary: str = typer.Option(None, "--min-salary", help="Salary floor, e.g. 600000 / 60w / 600k."),
    currency: str = typer.Option(None, "--currency", help="Restrict to a stated-pay currency, e.g. USD."),
    require_stated_salary: bool = typer.Option(False, "--require-stated-salary", help="Drop roles with no published pay."),
    role_family: str = typer.Option(None, "--role-family", help="Coarse family (v0.1: unpopulated → no-op)."),
    limit: int = typer.Option(10, "--limit", help="Max results."),
) -> None:
    """Search the local index (same hard filter + ranking as the MCP tool)."""
    init_db()
    _banner()
    skill_list = _parse_skills(skills)
    req_list = [s.strip().lower() for s in required_skills.split(",")] if required_skills else None
    floor = _parse_salary_arg(min_salary)
    console.cmd(
        "ohp search"
        + (f" --skills {skills}" if skills else "")
        + (f" --required-skills {required_skills}" if required_skills else "")
        + (" --remote" if remote else "")
        + (f" --remote-scope {remote_scope}" if remote_scope else "")
        + (f" --min-salary {min_salary}" if min_salary else "")
        + (f" --currency {currency}" if currency else "")
        + (" --require-stated-salary" if require_stated_salary else "")
        + (f" --role-family {role_family}" if role_family else "")
        + (f" --limit {limit}" if limit != 10 else "")
    )
    with session_scope() as s:
        results = service.search_jobs(
            s, skill_list, remote or None, floor, limit,
            required_skills=req_list, currency=currency,
            require_stated_salary=require_stated_salary, remote_scope=remote_scope,
            role_family=role_family,
        )
    if not results:
        console.out("无匹配结果。")
        return
    console.ok(f"{len(results)} 条结果 · 服务端只做硬过滤 + 固定排序，精排交给客户端 Agent")
    for r in results:
        _print_job(r)


def _parse_skills(skills: str | None) -> list[str] | None:
    if not skills:
        return None
    if skills.strip().lower() == "auto":
        # 'auto' → use the locally-derived skills from `ohp init --scan`.
        fp = client.load_fingerprint()
        return list(fp.skills) if fp and fp.skills else None
    return [s.strip().lower() for s in skills.split(",") if s.strip()]


def _parse_salary_arg(value: str | None) -> int | None:
    """Parse salary like '600000', '60w'/'60万' (万), '600k'."""
    if value is None:
        return None
    s = str(value).strip().lower().replace(",", "").replace("，", "")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(w|万|k|m)?$", s)
    if not m:
        raise typer.BadParameter(f"无法解析薪资：{value!r}（示例：600000 / 60w / 600k）")
    num = float(m.group(1))
    mult = {"w": 10000, "万": 10000, "k": 1000, "m": 1_000_000, None: 1}[m.group(2)]
    return int(num * mult)


def _print_job(r: dict) -> None:
    sal = ""
    if r.get("salary_min") or r.get("salary_max"):
        cur = r.get("salary_currency") or ""
        sal = f" · {cur} {r.get('salary_min')}–{r.get('salary_max')}"
    scope = r.get("remote_scope")
    regions = r.get("eligible_regions") or []
    scope_str = ""
    if scope:
        scope_str = f" · {scope}" + (f" [{', '.join(regions)}]" if regions else "")
    c.print(
        f"  [accent]⬥[/] [text]{r['company']}[/] · {r['title']} "
        f"[out]({r.get('remote_policy')}{scope_str}{sal})[/]"
    )
    c.print(
        f"     [muted]id={r['job_id']} · datePosted={r.get('datePosted')} · "
        f"days_open={r.get('days_open')} · ghost_score={r['ghost_score']} · "
        f"match={r['match_quality']}[/]"
    )
    c.print(f"     [out]▸ {r['apply_channel']}[/]")
    c.print(f"     [muted]# 投递：ohp apply {r['job_id']}[/]")


# --- init (fingerprint) -------------------------------------------------------
@app.command()
def init(
    scan: str = typer.Option(None, "--scan", help="Local repo directory to derive skills from."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Generate a local skill fingerprint from your own repos. Code never leaves the machine."""
    from pathlib import Path

    _banner()
    if not scan:
        console.error("ERR_SCAN_DIR_REQUIRED", "请用 --scan <目录> 指定要扫描的个人项目目录。")
        raise typer.Exit(1)
    path = Path(scan).expanduser()
    if not path.exists() or not path.is_dir():
        console.error("ERR_DIR_NOT_FOUND", f"目录不存在：{scan}")
        raise typer.Exit(1)

    console.cmd(f"ohp init --scan {scan}")
    # Design STEP 2 — explicit consent before scanning; data never leaves the machine.
    if not console.confirm(
        "扫描仅限个人项目、数据不出本机 · 只提取技能标签、代码永不上传 → 确认",
        assume_yes=yes,
    ):
        console.out("已取消。")
        raise typer.Exit(0)

    console.out(f"分析 {path} …（本地进行）")
    skills, lang_pct, repos = client.scan_repos(path)
    fp = client.load_fingerprint() or client.Fingerprint(
        id=client.new_fingerprint_id(),
        created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
    fp.skills, fp.language_pct, fp.repos_scanned = skills, lang_pct, repos
    if not fp.created_at:
        fp.created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    client.save_fingerprint(fp)

    langs = " · ".join(f"{l.title()} {p}%" for l, p in list(lang_pct.items())[:4])
    extra = " · ".join(s for s in skills if s not in lang_pct)
    console.ok(f"技能指纹已生成（本地）：{langs}" + (f" · {extra}" if extra else ""))
    console.note("无姓名 · 无邮箱 · 无雇主代码 —— 简历？从头到尾没写过")
    console.out(f"指纹 {fp.id} · 扫描 {repos} 个仓库 · 写入 {client.fingerprint_path()}")


# --- watch (register standing intent) ----------------------------------------
@app.command()
def watch(
    skills: str = typer.Option("auto", "--skills", help="Comma-separated (ANY overlap), or 'auto' (fingerprint)."),
    required_skills: str = typer.Option(None, "--required-skills", help="Comma-separated skills that must ALL be present (AND)."),
    remote: bool = typer.Option(False, "--remote", help="Only fully-remote roles."),
    role_family: str = typer.Option(None, "--role-family", help="Only this family, e.g. engineering (keeps sales/SA out)."),
    min_salary: str = typer.Option(None, "--min-salary", help="e.g. 600000 / 60w / 600k."),
    daemon: bool = typer.Option(False, "--daemon", help="Poll every 30 min and notify."),
) -> None:
    """Register a standing intent — jobs come knocking, even with the terminal closed."""
    init_db()
    _banner()
    fp = client.load_or_create_fingerprint()

    if daemon:
        _watch_daemon(fp)
        return

    console.cmd("ohp watch --skills " + skills
                + (f" --required-skills {required_skills}" if required_skills else "")
                + (" --remote" if remote else "")
                + (f" --role-family {role_family}" if role_family else "")
                + (f" --min-salary {min_salary}" if min_salary else ""))
    skill_list = _parse_skills(skills)
    filters: dict = {}
    if skill_list:
        filters["skills"] = skill_list
    if required_skills:
        filters["required_skills"] = [s.strip().lower() for s in required_skills.split(",") if s.strip()]
    if remote:
        filters["remote"] = True
    if role_family:
        filters["role_family"] = role_family
    sal = _parse_salary_arg(min_salary)
    if sal is not None:
        filters["min_salary"] = sal

    with session_scope() as s:
        try:
            out = service.watch_intent(s, fp.id, filters)
        except OpenHireError as e:
            console.error(e.code, e.message)
            raise typer.Exit(1)

    console.ok(f"常驻意向已注册 · {out['watch_id']} · 指纹 {fp.id} · 出户内容仅一枚匿名指纹")
    console.out("过滤：" + (", ".join(f"{k}={v}" for k, v in filters.items()) or "（全部）"))
    console.note("关掉终端也在生效 —— 有匹配它自己会响（ohp check 拉取新命中）")


def _watch_daemon(fp) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    console.ok("watch 守护进程启动 · 每 30 分钟拉取一次新命中 · Ctrl-C 退出")
    console.note("stdio 无服务端推送，采用客户端拉取（check_watches）")

    def tick():
        ts = dt.datetime.now().strftime("%H:%M:%S")
        with session_scope() as s:
            res = service.check_watches(s, fp.id)
        if res["new_matches"]:
            console.notif(f"[{ts}] {res['new_matches']} 个新命中！")
            _print_check_results(res)
        else:
            console.out(f"[{ts}] 暂无新命中。")

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(tick, "interval", minutes=30, next_run_time=dt.datetime.now())
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        console.out("watch 守护进程已停止。")


# --- check (pull new hits) ----------------------------------------------------
@app.command()
def check() -> None:
    """Pull new matches since your last check (client-pull; stdio has no server push)."""
    init_db()
    _banner()
    fp = client.load_or_create_fingerprint()
    console.cmd("ohp check")
    with session_scope() as s:
        res = service.check_watches(s, fp.id)
    if res["watches"] == 0:
        console.out("尚未注册常驻意向。先运行 ohp watch。")
        return
    if res["new_matches"] == 0:
        console.out(f"{res['watches']} 个常驻意向 · 暂无新命中。")
        return
    console.notif(f"{res['new_matches']} 个新命中")
    _print_check_results(res)


def _print_check_results(res: dict) -> None:
    for r in res["results"]:
        for m in r["new_matches"]:
            _print_job(m)


# --- apply --------------------------------------------------------------------
@app.command()
def apply(
    job_id: str = typer.Argument(..., help="Job id from search / check."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the authorization prompt."),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open the browser."),
) -> None:
    """Apply to a job: summary → authorize → open the employer's own form → record receipt."""
    init_db()
    _banner()
    fp = client.load_or_create_fingerprint()

    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None:
            console.error("ERR_JOB_NOT_FOUND", f"没有找到职位：{job_id}")
            raise typer.Exit(1)
        company = s.get(Company, job.company_id)
        summary = {
            "company": company.name if company else job.company_id,
            "title": job.title,
            "remote_policy": job.remote_policy,
            "salary_min": job.salary_min, "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "skills": list(job.skills or []),
            "ghost_score": round(job.ghost_score, 4) if job.ghost_score is not None else None,
            "apply_channel": job.apply_channel,
            "description": job.description_raw or "",
        }

    console.cmd(f"ohp apply {job_id}")
    _print_apply_summary(summary)

    # The apply form (esp. Greenhouse embed) shows NO JD — the summary above restores it.
    if not console.confirm(
        "以你本人身份、走雇主官方通道投递 · 简历不经过服务器 → 授权",
        assume_yes=yes,
    ):
        console.out("已取消，未投递。")
        raise typer.Exit(0)

    with session_scope() as s:
        try:
            res = service.apply(s, job_id, fp.id, True)
        except OpenHireError as e:
            console.error(e.code, e.message)
            raise typer.Exit(1)

    client.append_receipt({
        "receipt_id": res["receipt_id"],
        "job_id": job_id,
        "company": summary["company"],
        "title": summary["title"],
        "apply_channel": res["apply_channel"],
        "fingerprint": fp.id,
        "resume_transmitted": res["resume_transmitted"],
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })

    opened = False
    if not no_open:
        try:
            opened = bool(webbrowser.open(res["apply_channel"]))
        except Exception:
            opened = False

    # v0.1: response_sla_days is NULL, so omit the SLA segment (per README).
    console.ok("已直达雇主 ATS · 来源 = 你自己")
    console.out(f"receipt {res['receipt_id']} · 简历未经服务器（resume_transmitted=false）")
    if opened:
        console.out(f"申请页（已在浏览器打开）：{res['apply_channel']}")
    else:
        console.out(f"申请页（请手动打开）：{res['apply_channel']}")


def _print_apply_summary(s: dict) -> None:
    sal = "薪资未公开"
    if s.get("salary_min") or s.get("salary_max"):
        cur = s.get("salary_currency") or ""
        sal = f"{cur} {s.get('salary_min')}–{s.get('salary_max')}"
    ghost = s.get("ghost_score")
    c.print()
    c.print(f"  [accent]⬥ {s['company']} · {s['title']}[/]")
    c.print(f"     [out]{s.get('remote_policy')} · {sal} · ghost_score={ghost}[/]")
    if s.get("skills"):
        c.print(f"     [muted]技能：{', '.join(s['skills'][:12])}[/]")
    points = _jd_points(s.get("description", ""))
    if points:
        c.print("     [muted]JD 要点：[/]")
        for p in points:
            c.print(f"       [out]· {p}[/]")
    c.print()


def _jd_points(desc: str, n: int = 3, width: int = 100) -> list[str]:
    """A few readable lines from the JD (the apply form itself shows none)."""
    lines = [ln.strip(" •-\t") for ln in (desc or "").splitlines() if ln.strip()]
    out = []
    for ln in lines:
        if len(ln) < 25:  # skip headers/short fragments
            continue
        out.append(ln[:width] + ("…" if len(ln) > width else ""))
        if len(out) >= n:
            break
    return out


# --- status -------------------------------------------------------------------
@app.command()
def status() -> None:
    """Show your local identity — fingerprint, standing watches, application receipts."""
    init_db()
    _banner()
    fp = client.load_fingerprint()
    if fp is None:
        console.out("尚无技能指纹。运行 ohp init --scan <目录> 生成（或 apply/watch 会自动创建匿名指纹）。")
    else:
        langs = " · ".join(f"{l.title()} {p}%" for l, p in list(fp.language_pct.items())[:4])
        console.out(f"指纹 {fp.id}" + (f" · {langs}" if langs else ""))
        if fp.skills:
            console.out(f"技能：{', '.join(fp.skills)}")

    with session_scope() as s:
        fid = fp.id if fp else None
        watches = list(
            s.execute(select(Watch).where(Watch.fingerprint == fid, Watch.active.is_(True))).scalars()
        ) if fid else []
        n_live = s.scalar(
            select(func.count()).select_from(Job).where(Job.delisted_at.is_(None))
        ) or 0
        n_companies = s.scalar(select(func.count()).select_from(Company)) or 0

    c.print()
    c.print(f"  [muted]常驻意向（{len(watches)}）[/]")
    for w in watches:
        console.out(f"{w.watch_id} · {w.filters}")
    receipts = client.load_receipts()
    c.print(f"  [muted]投递回执（{len(receipts)}）[/]")
    for r in receipts[-10:]:
        console.out(f"{r['receipt_id']} · {r['company']} · {r['title'][:44]} · {r['created_at'][:10]}")
    c.print()
    console.note(f"索引：{n_companies} 家公司 · {n_live} 条在架（ohp index-status 看协议字段覆盖）")


# --- index-status -------------------------------------------------------------
@app.command(name="index-status")
def index_status() -> None:
    """Show the local index — companies, live jobs, protocol-field coverage."""
    init_db()
    _banner()
    now = dt.datetime.now(dt.timezone.utc)
    with session_scope() as session:
        n_companies = session.scalar(select(func.count()).select_from(Company)) or 0
        n_jobs = session.scalar(select(func.count()).select_from(Job)) or 0
        n_live = session.scalar(
            select(func.count()).select_from(Job).where(Job.delisted_at.is_(None))
        ) or 0
        n_delisted = n_jobs - n_live

        # Protocol-field coverage on live jobs (五协议字段全部有值; sla NULL is legal).
        live = select(func.count()).select_from(Job).where(Job.delisted_at.is_(None))
        cov_verified = session.scalar(live.where(Job.verified_at.isnot(None))) or 0
        cov_source = session.scalar(live.where(Job.source.isnot(None))) or 0
        cov_apply = session.scalar(
            live.where(Job.apply_channel.isnot(None), Job.apply_channel != "")
        ) or 0
        cov_ghost = session.scalar(live.where(Job.ghost_score.isnot(None))) or 0

        remote = session.scalar(
            live.where(Job.remote_policy == "remote")
        ) or 0

        by_vendor = session.execute(
            select(Company.ats_vendor, func.count()).group_by(Company.ats_vendor)
        ).all()

    console.out(f"公司 {n_companies} · 在架职位 {n_live} · 已下架 {n_delisted} · 总计 {n_jobs}")
    console.out("按 ATS：" + " · ".join(f"{v}={n}" for v, n in by_vendor))
    console.out(f"远程职位（remote_policy=remote）：{remote}")
    c.print()
    c.print("  [muted]五协议字段覆盖（在架）[/]")
    _cov("① verified_at", cov_verified, n_live)
    _cov("② source     ", cov_source, n_live)
    _cov("③ ghost_score", cov_ghost, n_live)
    c.print(f"  [ok]✓[/] ④ response_sla_days  [out]NULL（v0.1 合法：雇主认领后才有）[/]")
    _cov("⑤ apply_channel", cov_apply, n_live)


def _cov(label: str, have: int, total: int) -> None:
    full = have == total and total > 0
    glyph = "[ok]✓[/]" if full else "[risk]![/]"
    pct = (have / total * 100) if total else 0
    c.print(f"  {glyph} {label}  [out]{have}/{total} ({pct:.1f}%)[/]")


# --- fix-apply-channels -------------------------------------------------------
@app.command(name="fix-apply-channels")
def fix_apply_channels() -> None:
    """Regenerate every apply_channel so it deep-links to the specific job.

    Employer-embedded ATS pages (on the company's own domain) often fail to direct-link;
    those are replaced with a canonical, guaranteed-deep-linking ATS apply URL.
    """
    from .pipeline import regenerate_apply_channels

    init_db()
    _banner()
    console.cmd("ohp fix-apply-channels")
    stats = regenerate_apply_channels()
    console.ok(
        f"检查 {stats.jobs_total} 条 · 重写 {stats.jobs_rewritten} · "
        f"回退到 ATS 官方托管页 {stats.jobs_fallback}"
    )
    console.out(
        f"嵌入式（雇主自建页）公司 {len(stats.embed_companies)} 家 · "
        f"涉及 {stats.embed_jobs} 条职位"
    )
    if stats.embed_companies:
        console.note("嵌入式公司：" + ", ".join(stats.embed_companies))


# --- extract-sample -----------------------------------------------------------
@app.command(name="extract-sample")
def extract_sample(
    n: int = typer.Option(100, "--n", help="How many jobs to sample."),
    workers: int = typer.Option(8, "--workers", help="Concurrent API calls."),
) -> None:
    """Run DeepSeek on N jobs and compare against the heuristic (no DB writes)."""
    from .pipeline import run_sample_comparison
    from .pipeline.rebuild import cost_cny  # noqa
    from sqlalchemy import func as _f

    init_db()
    _banner()
    console.cmd(f"ohp extract-sample --n {n}")
    console.out(f"用 DeepSeek deepseek-chat 抽取 {n} 条并与启发式对比…")
    try:
        rep = run_sample_comparison(n, workers)
    except RuntimeError as e:
        console.error("ERR_DEEPSEEK_KEY_MISSING", str(e))
        raise typer.Exit(1)

    with session_scope() as s:
        total_jobs = s.scalar(_f.count(Job.id)) or 0

    c.print()
    c.print("  [muted]样本对比（启发式 → DeepSeek）[/]")
    console.out(f"成功 {rep.ok}/{rep.n} · 失败 {rep.failed}")
    console.out(f"平均技能数：启发式 {rep.heur_skill_avg:.2f} → DeepSeek {rep.llm_skill_avg:.2f}")
    console.out(f"新增/更细技能：{rep.llm_broader} 条 · 收窄（去掉疑似误标）：{rep.llm_narrower} 条 "
                f"· 其中清空非技术岗误标：{rep.llm_emptied} 条")
    console.out(f"remote_policy 改变（仅填补 unknown，不覆盖 ATS 权威值）：{rep.remote_changed} 条")
    console.out(f"薪资：新增 {rep.salary_added} · 丢失 {rep.salary_removed}（合并策略下应为 0）")
    c.print()
    c.print("  [muted]示例（title · 启发式 skills → DeepSeek skills · remote）[/]")
    for ex in rep.examples[:8]:
        c.print(f"  [accent]⬥[/] [text]{ex['company']}[/] {ex['title']}")
        c.print(f"     [out]{ex['heur_skills']} → {ex['llm_skills']}"
                f"  · remote {ex['heur_remote']}→{ex['llm_remote']}[/]")

    c.print()
    c.print("  [risk]预算[/]")
    console.out(f"本次样本 {rep.ok} 条实际用量：input {rep.prompt_tokens} · output {rep.completion_tokens} tokens")
    console.out(f"本次样本成本：¥{rep.cost:.4f}")
    full = rep.extrapolate(total_jobs)
    ceiling = _cfg_ceiling()
    console.out(f"外推全量 {total_jobs} 条预计成本：¥{full:.2f}（上限 ¥{ceiling:.0f}）")
    if full >= ceiling:
        console.error("ERR_BUDGET_OVER_CEILING",
                      f"预计 ¥{full:.2f} ≥ ¥{ceiling:.0f}——已停下，请确认后再跑全量。")
    else:
        console.note(f"预计低于上限。确认质量后运行 `ohp extract-rebuild` 跑全量（¥{ceiling:.0f} 硬停）。")


def _cfg_ceiling() -> float:
    from . import config
    return config.EXTRACTION_COST_CEILING_CNY


# --- extract-rebuild ----------------------------------------------------------
@app.command(name="extract-rebuild")
def extract_rebuild(
    batch: int = typer.Option(50, "--batch", help="Jobs committed per batch (resumable)."),
    workers: int = typer.Option(8, "--workers", help="Concurrent API calls."),
    limit: int = typer.Option(None, "--limit", help="Cap jobs this run (for testing)."),
    ceiling: float = typer.Option(None, "--ceiling", help="CNY hard stop (default from config)."),
) -> None:
    """Rebuild extraction with DeepSeek in resumable batches; hard-stops at the ¥ ceiling."""
    from .pipeline import rebuild_extraction

    init_db()
    _banner()
    console.cmd("ohp extract-rebuild")
    try:
        def on_batch(stx):
            console.out(
                f"进度 {stx.processed}/{stx.total_target} · 更新 {stx.updated} · "
                f"失败 {stx.failed} · 花费 ¥{stx.cost:.2f}"
            )

        stats = rebuild_extraction(batch, workers, limit, ceiling, on_batch)
    except RuntimeError as e:
        console.error("ERR_DEEPSEEK_KEY_MISSING", str(e))
        raise typer.Exit(1)

    if stats.halted:
        console.error("ERR_BUDGET_OVER_CEILING",
                      f"{stats.halt_reason}——已在断点停下。再次运行会从未完成处续跑。")
    console.ok(
        f"完成 · 更新 {stats.updated}/{stats.total_target} · 失败 {stats.failed} · "
        f"总花费 ¥{stats.cost:.2f}（input {stats.prompt_tokens} / output {stats.completion_tokens} tok）"
    )
    console.note("原启发式值已存入 *_fallback 列，可 `ohp extract-rollback` 回滚对比。")


# --- extract-rollback ---------------------------------------------------------
@app.command(name="extract-rollback")
def extract_rollback() -> None:
    """Restore heuristic extraction values from the fallback columns."""
    from .pipeline import rollback_extraction

    init_db()
    _banner()
    console.cmd("ohp extract-rollback")
    n = rollback_extraction()
    console.ok(f"已回滚 {n} 条至启发式抽取值。")


# --- bootstrap (first-run data) -----------------------------------------------
def _sqlite_db_path() -> str | None:
    from . import config
    url = config.DATABASE_URL
    if not url.startswith("sqlite"):
        return None
    return url.split(":///", 1)[-1]


@app.command()
def bootstrap(
    fresh: bool = typer.Option(False, "--fresh", help="Skip the snapshot; crawl the public ATS live (heuristic, free)."),
    deepseek: bool = typer.Option(False, "--deepseek", help="Use DeepSeek extraction (needs your own DEEPSEEK_API_KEY)."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing local index."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    snapshot_url: str = typer.Option(None, "--snapshot-url", help="Override the snapshot URL."),
) -> None:
    """First-run setup: get a job index so search/watch/apply work.

    Default: download the public snapshot, then refresh it live. `--fresh` skips the
    snapshot and crawls the public ATS from scratch. No account, no signup, no PII.
    """
    from . import config
    from .db import Company, session_scope
    from .pipeline import run_ingest
    from .pipeline.seed_runner import seed_companies
    from .pipeline.snapshot import SnapshotError, install_snapshot

    _banner()
    console.cmd("ohp bootstrap" + (" --fresh" if fresh else "") + (" --deepseek" if deepseek else ""))
    init_db()

    db_path = _sqlite_db_path()
    with session_scope() as s:
        existing = s.query(Company).count() if hasattr(s, "query") else \
            s.execute(select(func.count()).select_from(Company)).scalar()
    if existing and not force:
        console.note(f"本地已有 {existing} 家公司的索引。要重建请加 --force，或直接 `ohp ingest` 刷新。")
        raise typer.Exit(0)

    # Choose the extractor for any live crawl in this run.
    config.EXTRACTOR = "deepseek" if deepseek else "heuristic"
    if deepseek and not config.DEEPSEEK_API_KEY:
        console.error("ERR_DEEPSEEK_KEY_MISSING",
                      "--deepseek 需要你自己的 DEEPSEEK_API_KEY（写进 .env）。不加则用免费启发式。")
        raise typer.Exit(1)

    # --- Pre-flight: say exactly what will happen (no account, no PII) ---
    if fresh:
        console.out("将执行（现抓模式）：")
        console.out("  · 抓取 ~96 家雇主的公开 ATS（Greenhouse/Lever/Ashby）建立本地索引")
        console.out(f"  · 抽取后端：{'DeepSeek（你的 key）' if deepseek else '启发式（本地·免费）'}")
        console.out("  · 无账号 · 无登录 · 简历/任何 PII 不参与")
    else:
        console.out("将执行（快照模式）：")
        console.out("  · 下载一份公开职位数据快照（约 20MB · 仅 jobs/companies · 无任何用户数据）")
        console.out("  · 随后就地增量抓取一次，把 verified_at / 下线状态刷新到最新")
        console.out("  · 无账号 · 无登录 · 简历/任何 PII 不参与")
    if not console.confirm("开始", assume_yes=yes):
        console.out("已取消。")
        raise typer.Exit(0)

    if fresh:
        console.out("① 校验并注册公开 ATS 种子…")
        seed_companies()
        console.out("② 抓取入库…")
        stats = run_ingest(respect_interval=False)
        console.ok(f"现抓完成 · 新增 {stats.jobs_new} · 公司 {stats.companies_crawled}")
        return

    # Snapshot path
    url = snapshot_url or config.SNAPSHOT_URL
    if db_path is None:
        console.error("ERR_SNAPSHOT_NEEDS_SQLITE",
                      "快照安装仅支持 SQLite。用 Postgres 请改用 `ohp bootstrap --fresh`。")
        raise typer.Exit(1)
    console.out(f"① 下载快照：{url}")
    from .db.session import dispose_engine
    dispose_engine()  # release the SQLite file handle before overwriting it
    try:
        res = install_snapshot(url, db_path)
    except SnapshotError as e:
        console.error("ERR_SNAPSHOT_INVALID", str(e))
        raise typer.Exit(1)
    except Exception as e:  # network etc.
        console.error("ERR_SNAPSHOT_UNREACHABLE",
                      f"下载失败（{type(e).__name__}）。可改用 `ohp bootstrap --fresh` 现抓。")
        raise typer.Exit(1)
    age = f"{res.age_days} 天前" if res.age_days is not None else "未知"
    console.ok(f"快照就绪 · 公司 {res.companies} · 职位 {res.jobs} · 数据截至 {res.data_as_of}（龄 {age}）")
    console.out("② 增量刷新（现抓一次，更新 verified_at / 下线）…")
    stats = run_ingest(respect_interval=False)
    console.ok(f"刷新完成 · 新增 {stats.jobs_new} · 更新 {stats.jobs_updated} · 下线 {stats.jobs_delisted} · 公司 {stats.companies_crawled}")
    console.note("接着可 `ohp serve` 接入 Claude Desktop，或 `ohp search …` 直接用。")


# --- snapshot-build (maintainer) ----------------------------------------------
@app.command(name="snapshot-build")
def snapshot_build(
    out: str = typer.Option("dist/openhire-index.db.gz", "--out", help="Output .db.gz path."),
) -> None:
    """(Maintainer) Build the public jobs/companies-only snapshot for a GitHub Release.

    Refuses to build if any user-state (watches/applications) would leak in — a privacy
    red line enforced in the build itself.
    """
    from .pipeline.snapshot import SnapshotError, build_snapshot

    _banner()
    console.cmd("ohp snapshot-build")
    src = _sqlite_db_path()
    if src is None:
        console.error("ERR_SNAPSHOT_NEEDS_SQLITE", "snapshot-build 需要源库为 SQLite。")
        raise typer.Exit(1)
    try:
        r = build_snapshot(src, out)
    except SnapshotError as e:
        console.error("ERR_SNAPSHOT_REDLINE", str(e))
        raise typer.Exit(1)
    mb = r.gz_bytes / 1_000_000
    console.ok(f"快照已构建 · {r.path} · {mb:.1f} MB")
    console.out(f"公司 {r.companies} · 职位 {r.jobs} · 数据截至 {r.data_as_of}")
    console.note("零用户态校验通过（watches/applications=0）。上传为 GitHub Release 资产即可。")


# --- extract-role-family ------------------------------------------------------
@app.command(name="extract-role-family")
def extract_role_family(
    batch: int = typer.Option(100, "--batch", help="Jobs committed per batch (resumable)."),
    workers: int = typer.Option(12, "--workers", help="Concurrent API calls."),
    limit: int = typer.Option(None, "--limit", help="Cap jobs this run (for testing)."),
    ceiling: float = typer.Option(None, "--ceiling", help="CNY hard stop (default from config)."),
) -> None:
    """Classify each job's role_family with DeepSeek; resumable, hard-stops at the ¥ ceiling."""
    from .pipeline import rebuild_role_family

    init_db()
    _banner()
    console.cmd("ohp extract-role-family")
    try:
        def on_batch(stx):
            console.out(
                f"进度 {stx.processed}/{stx.total_target} · 标注 {stx.updated} · "
                f"失败 {stx.failed} · 花费 ¥{stx.cost:.2f}"
            )

        stats = rebuild_role_family(batch, workers, limit, ceiling, on_batch)
    except RuntimeError as e:
        console.error("ERR_DEEPSEEK_KEY_MISSING", str(e))
        raise typer.Exit(1)

    if stats.halted:
        console.error("ERR_BUDGET_OVER_CEILING",
                      f"{stats.halt_reason}——已在断点停下。再次运行会从未完成处续跑。")
    console.ok(
        f"完成 · 标注 {stats.updated}/{stats.total_target} · 失败 {stats.failed} · "
        f"总花费 ¥{stats.cost:.2f}（input {stats.prompt_tokens} / output {stats.completion_tokens} tok）"
    )


# --- backfill-dates -----------------------------------------------------------
@app.command(name="backfill-dates")
def backfill_dates() -> None:
    """Re-fetch public ATS to fill real posting dates (datePosted) + recompute ghost_score.

    Free (no LLM). Never re-extracts or touches skills/salary/remote.
    """
    from .db.migrate import ensure_schema
    from .pipeline import backfill_posting_dates

    _banner()
    console.cmd("ohp backfill-dates")
    added = ensure_schema()
    if added:
        console.note(f"已补列：{', '.join(added)}")
    done = {"n": 0}

    def on_progress(phase, cid, result):
        if phase == "fetch":
            done["n"] += 1
            console.out(f"抓取 {done['n']} · {cid} · {result.count if result.ok else 'ERR'}")

    stats = backfill_posting_dates(on_progress=on_progress)
    console.ok(
        f"完成 · 公司 {stats.companies_fetched} 抓取/{stats.companies_failed} 失败 · "
        f"真实发布日 {stats.jobs_dated} · ATS 无日期 {stats.jobs_no_ats_date} · "
        f"未匹配 {stats.jobs_unmatched} · ghost 重算 {stats.ghost_recomputed}"
    )


# --- version ------------------------------------------------------------------
@app.command()
def version() -> None:
    """Print version."""
    c.print(f"openhire {__version__}")


def main() -> None:  # console-script entry
    app()


if __name__ == "__main__":
    main()

"""Fixes from the two runs the maintainer did himself on 2026-09-28 (reports/055).

An HR persona — "a recruiting role in autonomous driving / embodied AI, base Hong Kong" —
was put to OpenHire through Kimi's web agent (a sandbox in mainland China) and through
Tencent WorkBuddy on the maintainer's own machine. Neither agent got an answer the index
could actually have given. These tests pin the parts that were code:

* role_family="recruiting" silently returned the whole index (Waymo engineers);
* "Hong Kong" and "香港" were two different places;
* no filter could isolate recruiting roles at all, so an agent paged one employer at
  limit 10, saw none, and reported "Chinese embodied companies post no HR roles" while
  Dobot's HRBP sat on page 4;
* one read timeout on the ~30 MB snapshot threw the download away with no retry, and the
  resulting empty index looked like "no matches".
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import mcp_server, service
from openhire.db.models import Base, Company, Job, Watch
from openhire.errors import OpenHireError

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 28, tzinfo=UTC)


def mkjob(jid, company_id, title, skills, *, posted_days_ago=10, role_family=None,
          location="深圳"):
    posted = NOW - dt.timedelta(days=posted_days_ago)
    return Job(
        id=f"{company_id}:{jid}", company_id=company_id, title=title,
        description_raw=title, skills=skills, remote_policy="onsite",
        salary_min=None, salary_max=None, salary_currency=None, salary_inferred=False,
        location=location, posted_at=posted, updated_at=None,
        first_seen_at=posted, verified_at=NOW, source="ats_public_api",
        apply_channel=f"https://app.mokahr.com/apply/{company_id}/1#/job/{jid}",
        content_hash=f"h{jid}", ghost_score=0.0, role_family=role_family,
    )


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="dobot", name="越疆 Dobot", ats_vendor="moka", ats_tenant="dobot",
                      careers_url="x", verified=False, last_crawled_at=NOW))
        s.add(Company(id="uisee", name="驭势科技 UISEE", ats_vendor="beisen", ats_tenant="uisee",
                      careers_url="y", verified=False, last_crawled_at=NOW))
        s.add(Company(id="mongodb", name="MongoDB", ats_vendor="greenhouse", ats_tenant="mongodb",
                      careers_url="z", verified=False, last_crawled_at=NOW))
        # The exact rows the two agents were looking at.
        s.add(mkjob("hrbp", "dobot", "HRBP(J10343)", [], role_family="ops"))
        s.add(mkjob("zp", "dobot", "招聘经理(J11800)", [], role_family=None))
        s.add(mkjob("rec", "mongodb", "Senior Technical Recruiter", [], role_family="ops",
                    location="Hong Kong"))
        s.add(mkjob("chrome", "mongodb", "Chrome Extension Engineer", ["javascript"],
                    role_family="engineering", location="Hong Kong"))
        s.add(mkjob("pm", "uisee", "项目经理", [], role_family="ops", location="香港·九龙区"))
        s.add(mkjob("perc", "dobot", "感知算法工程师", ["perception"], role_family="engineering"))
        s.commit()
        yield s


# --- 1. an unknown role_family is refused, not ignored -------------------------------
def test_unknown_role_family_is_refused_with_the_valid_list(session):
    with pytest.raises(OpenHireError) as ei:
        service.search_jobs(session, role_family="recruiting", now=NOW)
    assert ei.value.code == "ERR_UNKNOWN_ROLE_FAMILY"
    assert "engineering" in ei.value.message and "ops" in ei.value.message
    assert "title" in ei.value.message, "the message must say what to use instead"
    # The valid values still work, case-insensitively.
    ids = {r["job_id"] for r in service.search_jobs(session, role_family="OPS", now=NOW)}
    assert "dobot:hrbp" in ids and "mongodb:chrome" not in ids
    assert "dobot:zp" in ids, "an unclassified row is still included, never hidden"


def test_a_watch_refuses_an_unknown_role_family_too(session):
    with pytest.raises(OpenHireError) as ei:
        service.watch_intent(session, "#hr-k2p7-x8q1-a1", {"role_family": "recruiting"}, now=NOW)
    assert ei.value.code == "ERR_UNKNOWN_ROLE_FAMILY"


def test_mcp_search_returns_the_refusal_as_a_structured_error():
    out = mcp_server.search_jobs(role_family="recruiting")
    assert out["error"] == "ERR_UNKNOWN_ROLE_FAMILY"


# --- 2. the title filter: the roles no skill tag or family can isolate ----------------
def test_title_filter_reaches_hr_roles_in_both_languages_and_skips_chrome(session):
    def ids(*terms):
        return {r["job_id"] for r in service.search_jobs(session, title=list(terms), now=NOW)}

    hr = {"dobot:hrbp", "dobot:zp", "mongodb:rec"}
    assert ids("hr") == hr, "hr expands to HRBP / 招聘 / Recruiter, and never to Chrome"
    assert ids("招聘") == hr
    assert ids("recruit") == hr
    assert ids("感知") == {"dobot:perc"}
    # ANY-of across terms; a plain string is accepted as one term.
    assert ids("感知", "项目") == {"dobot:perc", "uisee:pm"}
    assert {r["job_id"] for r in service.search_jobs(session, title="项目经理", now=NOW)} == {"uisee:pm"}
    # An ASCII term anchors to the start of a word, so it never reaches the inside of one.
    assert service.title_matches("Chrome Extension Engineer", ["hr"]) is False
    assert service.title_matches("HR Business Partner", ["hr"]) is True
    assert service.title_matches("Senior HRBP", ["hr"]) is True


def test_title_combines_with_company_so_one_employer_can_be_asked_for_hr(session):
    rows = service.search_jobs(session, company="dobot", title=["hr"], now=NOW)
    assert {r["job_id"] for r in rows} == {"dobot:hrbp", "dobot:zp"}


def test_a_watch_can_be_scoped_to_a_title(session):
    w = service.watch_intent(session, "#hr-k2p7-x8q1-b2", {"title": ["招聘"], "company": "dobot"}, now=NOW)
    assert w["status"] == "active"
    res = service.check_watches(session, "#hr-k2p7-x8q1-b2", now=NOW)["results"][0]
    assert {m["job_id"] for m in res["new_matches"]} == {"dobot:hrbp", "dobot:zp"}
    stored = session.execute(select(Watch).where(Watch.watch_id == w["watch_id"])).scalar_one()
    assert stored.filters["title"] == ["招聘"], "stored as typed; expansion happens at match time"


def test_cli_search_accepts_and_echoes_title_and_refuses_bad_role_family():
    from typer.testing import CliRunner

    from openhire.cli import app

    res = CliRunner().invoke(app, ["search", "--title", "招聘,hrbp", "--company", "dobot"])
    assert "--title招聘,hrbp" in "".join(res.stdout.split())

    res = CliRunner().invoke(app, ["search", "--role-family", "recruiting"])
    assert res.exit_code == 2
    assert "ERR_UNKNOWN_ROLE_FAMILY" in res.output and "engineering" in res.output


# --- 3. Hong Kong is one place in two languages --------------------------------------
def test_hong_kong_in_either_language_reaches_both_spellings(session):
    def ids(loc):
        return {r["job_id"] for r in service.search_jobs(session, location=loc, now=NOW)}

    both = {"mongodb:rec", "mongodb:chrome", "uisee:pm"}
    assert ids("Hong Kong") == both
    assert ids("香港") == both
    assert ids("HK") == both, "an abbreviation resolves to the group"
    assert "hk" not in service.location_aliases("hk"), "but is never itself a match pattern"


def test_the_other_single_spelling_cities_reach_their_pinyin(session):
    session.add(mkjob("cz", "dobot", "结构工程师", [], location="江苏省·常州市"))
    session.add(mkjob("hf", "dobot", "测试工程师", [], location="安徽·包河区"))
    session.add(mkjob("sg", "mongodb", "Account Executive", [], location="Singapore"))
    session.commit()

    def ids(loc):
        return {r["job_id"] for r in service.search_jobs(session, location=loc, now=NOW)}

    assert ids("changzhou") == {"dobot:cz"} and ids("常州") == {"dobot:cz"}
    assert ids("hefei") == {"dobot:hf"}, "合肥 reaches a district-only 包河区 row"
    assert ids("新加坡") == {"mongodb:sg"} and ids("sg") == {"mongodb:sg"}


# --- 4. the snapshot download survives one bad read ----------------------------------
def test_snapshot_download_resumes_after_a_mid_stream_failure(tmp_path, monkeypatch):
    import httpx

    from openhire.pipeline import snapshot as snap

    payload = bytes(range(256)) * 400  # 102,400 bytes
    stall_at = 40_000
    calls: list[str | None] = []

    class FakeStream:
        def __init__(self, headers):
            self.range = (headers or {}).get("Range")

        def __enter__(self):
            calls.append(self.range)
            if self.range is None:
                self.status_code = 200
                self.headers = {"content-length": str(len(payload))}
                self._body, self._stall = payload, stall_at
            else:
                start = int(self.range[len("bytes="):-1])
                self.status_code = 206
                self.headers = {"content-range": f"bytes {start}-{len(payload) - 1}/{len(payload)}"}
                self._body, self._stall = payload[start:], None
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self):
            sent = 0
            for i in range(0, len(self._body), 8192):
                chunk = self._body[i:i + 8192]
                if self._stall is not None and sent + len(chunk) > self._stall:
                    yield chunk[: self._stall - sent]
                    raise httpx.ReadTimeout("simulated stall")
                sent += len(chunk)
                yield chunk

    monkeypatch.setattr(httpx, "stream", lambda method, url, **kw: FakeStream(kw.get("headers")))
    monkeypatch.setattr("time.sleep", lambda s: None)
    dest = tmp_path / "openhire-index.db.gz"
    snap._fetch_to("https://example.invalid/openhire-index.db.gz", dest)
    assert dest.read_bytes() == payload
    assert calls == [None, f"bytes={stall_at}-"], "second request asked only for the rest"


def test_snapshot_download_does_not_retry_a_404(tmp_path, monkeypatch):
    import httpx

    from openhire.pipeline import snapshot as snap

    calls = []

    class Gone:
        status_code = 404
        headers: dict = {}

        def __init__(self, headers):
            calls.append(1)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            raise httpx.HTTPStatusError("404", request=None, response=None)

    monkeypatch.setattr(httpx, "stream", lambda method, url, **kw: Gone(kw.get("headers")))
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(httpx.HTTPStatusError):
        snap._fetch_to("https://example.invalid/missing.gz", tmp_path / "x.gz")
    assert calls == [1], "a missing asset is reported at once, not four times"


# --- 5. an empty index we failed to fill says so, with the way out ---------------------
def test_empty_index_diagnosis_names_the_failed_download(monkeypatch):
    monkeypatch.setattr(mcp_server, "_BOOTSTRAP_ERROR",
                        "ConnectTimeout: timed out (url: https://github.com/…/openhire-index.db.gz)")
    diag = mcp_server._explain_bootstrap_failure({"results": [], "index_empty": True, "hint": "old"})
    assert diag["bootstrap_error"].startswith("ConnectTimeout")
    assert "OPENHIRE_SNAPSHOT_URL" in diag["hint"] and "--fresh" in diag["hint"]
    assert "not a market answer" in diag["hint"]
    # A genuine miss on a populated index is left alone.
    plain = mcp_server._explain_bootstrap_failure({"results": [], "matched": 0, "hint": "old"})
    assert "bootstrap_error" not in plain and plain["hint"] == "old"


# --- 6. ghost_score is documented as a measurement, never a verdict --------------------
def test_ghost_score_is_documented_as_time_not_a_fake_job_verdict():
    doc = mcp_server.search_jobs.__doc__
    assert "never a verdict" in doc and "僵尸岗" in doc
    assert "never a verdict" in mcp_server.mcp.instructions
    assert "recruiting" in doc and "ERR_UNKNOWN_ROLE_FAMILY" in doc
    assert "title" in mcp_server.watch_intent.__doc__

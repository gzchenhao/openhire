"""Persona night 2026-11-19 (reports/155): three high findings and two medium ones, each pinned."""
from __future__ import annotations

from openhire import service
from openhire.ats.base import JobRecord
from openhire.pipeline.extract import _resolve_remote, requirements_from_text


def _years(text: str):
    return requirements_from_text("产品经理", text)["min_years"]


def test_project_or_product_management_years_are_job_years():
    # 驭势「车辆产品经理（物流车）」: read as no requirement.
    assert _years("任职要求\n• 本科及以上学历\n• 5年以上商用车/特种车辆/自动驾驶领域产品或项目管理经验") == 5
    assert _years("2年以上智驾行业相关工作经验，1年以上团队管理经验") == 2      # people management still skipped
    assert requirements_from_text("PM", "5+ years of project management experience")["min_years"] == 5


def test_a_long_clause_listing_fields_still_reads():
    # 驭势「高级产品经理（物流车）」: 52 characters between 年以上 and 经验.
    text = ("岗位要求：\n1. 全日制本科以上学历。\n2. 3年以上自动驾驶、人工智能、机器人、智能网联或相关科技行业产品经理、"
            "解决方案架构师、战略规划或售前技术支持经验；熟悉L4自动驾驶系统架构")
    assert _years(text) == 3


def test_a_list_number_before_the_years_is_not_a_decimal():
    # 理想「海外座舱产品」: "1.5年以上" is item 1, five years; and both counts are asked for.
    text = ("6.参与海外软件团队0-1搭建\n\n1.5年以上智能座舱/车载信息娱乐系统端到端产品交付经验，3年以上海外市场经验"
            "\n\n2.主导过至少1个海外车型座舱产品从0到1的完整交付")
    assert _years(text) == 5
    assert _years("1.5年以上产品经验") == 1                       # no list around it: one and a half years
    assert _years("本科5年以上相关工作经验或硕士3年以上相关工作经验") == 3   # a choice: the smaller one


def test_employer_hybrid_text_beats_an_on_site_field():
    job = JobRecord(ats_job_id="1", title="Policy Lead", description_raw="x", apply_channel="https://x",
                    remote_hint="onsite")
    anthropic = ("Location-based hybrid policy: Currently, we expect all staff to be in one of our offices "
                 "at least 25% of the time. However, some roles may require more time in our offices.")
    assert _resolve_remote(job, anthropic) == "hybrid"
    assert _resolve_remote(job, "This role is on-site in San Francisco.") == "onsite"


def test_campus_text_under_social_link_needs_no_question():
    req = {"hire_track": "campus"}
    url = "https://pudu.zhiye.com/social/detail?jobAdId=1"
    common = dict(date_source="ats_reported", days_open=10, salary_stated=False, remote_scope=None,
                  apply_ok=True, correction=None, requirements=req, apply_url=url, title="嵌入式工程师")
    codes = lambda d: {c["code"] for c in service.check_before_apply(**common, description=d)}
    assert "campus_posting_in_social_channel" not in codes("本岗位接受优秀校招生。")
    assert "campus_posting_in_social_channel" in codes("负责嵌入式开发。")


def test_read_time_workplace_follows_the_employer_words():
    # Persona night 2026-11-21: "Remote-Friendly (Travel-Required) | San Francisco, CA" stored as onsite.
    assert service.effective_remote("onsite", "Remote-Friendly (Travel-Required) | San Francisco, CA", "") == "remote"
    assert service.effective_remote("onsite", "San Francisco, CA",
                                    "Location-based hybrid policy: at least 25% of the time in one of our offices.") == "hybrid"
    assert service.effective_remote("onsite", "上海", "到岗办公") == "onsite"
    assert service.effective_remote("remote", "Remote, US", "") == "remote"


def test_read_board_rows_use_the_same_reading():
    import datetime as dt
    rec = JobRecord(ats_job_id="9", title="Policy Lead", description_raw="We expect all staff to be in one of our "
                    "offices at least 25% of the time.", apply_channel="https://job-boards.greenhouse.io/anthropic/jobs/9",
                    location="San Francisco, CA", remote_hint="onsite")
    out = service._board_posting(rec, dt.datetime(2026, 11, 21, tzinfo=dt.timezone.utc))
    assert out["remote_policy"] == "hybrid"

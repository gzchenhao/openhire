"""The identity ladder behind a self-reported roster (reports/064): hermetic, no network.

A corporate email proves control of a domain, which costs ten dollars. The checks here
are the ones an applicant cannot supply for themselves: the 统一社会信用代码 check digit,
the sender domain, the company's own domain for apply addresses and phone pages, and the
posting red flags that recruitment scams cannot hide.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ve = _load("verify_employer")
imp = _load("import_employer_roster")


# --- 统一社会信用代码 -----------------------------------------------------------------------
def test_uscc_check_digit_is_consistent_and_a_typo_is_caught():
    prefix = "91110000MA01ABCD2"
    code = prefix + ve.uscc_check_digit(prefix)
    ok, _ = ve.uscc_valid(code)
    assert ok
    wrong = code[:-1] + ("0" if code[-1] != "0" else "1")
    ok, note = ve.uscc_valid(wrong)
    assert not ok and "校验位" in note


@pytest.mark.parametrize("code,word", [
    ("", "18 位"), ("9111", "18 位"), ("91110000MA01ABCD2I", "非法字符"), ("91110000MA01ABCDOO", "非法字符"),
])
def test_uscc_shape_errors_are_named(code, word):
    ok, note = ve.uscc_valid(code)
    assert not ok and word in note


# --- domains -------------------------------------------------------------------------------
def test_sender_domain_must_be_the_company_domain_not_a_look_alike():
    assert ve.sender_matches("hr@example-robotics.cn".split("@")[1], "example-robotics.cn")[0]
    assert ve.sender_matches("mail.example-robotics.cn", "example-robotics.cn")[0]
    assert not ve.sender_matches("example-robotics.co", "example-robotics.cn")[0]
    assert not ve.sender_matches("example-robotics.cn.evil.com", "example-robotics.cn")[0]
    assert not ve.sender_matches("", "example-robotics.cn")[0]


def test_normalise_domain_strips_scheme_path_and_www():
    assert ve.normalise_domain("https://www.Example-Robotics.cn/careers") == "example-robotics.cn"
    assert ve.normalise_domain("example-robotics.cn") == "example-robotics.cn"


def test_phone_page_off_domain_fails_without_network():
    r = ve.phone_on_page("010-12345678", "https://pastebin.com/abc", "example-robotics.cn")
    assert r["status"] == "FAIL" and "域名下" in r["note"]
    r = ve.phone_on_page(None, None, "example-robotics.cn")
    assert r["status"] == "FAIL"


# --- the importer's own gates ---------------------------------------------------------------
def test_red_flags_reject_the_scam_shapes_and_leave_real_roles_alone():
    assert imp.red_flags_in("海外高薪客服，包机票包吃住，无需经验") == ["海外高薪", "包机票", "包吃住", "无需经验"]
    assert imp.red_flags_in("感知算法工程师", "负责多传感器融合与 BEV 感知模型开发。要求：3 年以上经验。") == []
    assert "no experience" in imp.red_flags_in("Robotics Engineer", "No experience needed, visa provided")


def test_row_with_red_flags_is_dropped_and_email_must_be_on_domain(capsys):
    bad = {"职位名称": "境外客服", "工作城市": "柬埔寨", "发布日期": "2026-10-01", "投递链接或投递邮箱": "hr@example-robotics.cn", "岗位描述": "包机票"}
    assert imp.row_to_posting(bad, "example", "example-robotics.cn") is None
    assert "拒绝" in capsys.readouterr().err
    foreign_mail = {"职位名称": "感知算法工程师", "工作城市": "上海", "发布日期": "2026-10-01",
                    "投递链接或投递邮箱": "someone@gmail.com", "岗位描述": "负责感知。"}
    p = imp.row_to_posting(foreign_mail, "example", "example-robotics.cn")
    assert p is not None and "apply_email" not in p and "apply_url" not in p
    own_mail = dict(foreign_mail, **{"投递链接或投递邮箱": "hr@example-robotics.cn"})
    assert imp.row_to_posting(own_mail, "example", "example-robotics.cn")["apply_email"] == "hr@example-robotics.cn"


def test_build_roster_refuses_without_a_verification_sentence():
    rows = [{"职位名称": "感知算法工程师", "工作城市": "上海", "发布日期": "2026-10-01", "投递链接或投递邮箱": "", "岗位描述": "x"}]
    with pytest.raises(SystemExit):
        imp.build_roster(rows, slug="example", name="示例", domain="example-robotics.cn",
                         careers_url="https://www.example-robotics.cn/careers", verified_on="2026-10-08")
    roster = imp.build_roster(rows, slug="example", name="示例", domain="example-robotics.cn",
                              careers_url="https://www.example-robotics.cn/careers", verified_on="2026-10-08",
                              verification="gsxt record checked 2026-10-08; callback done")
    assert roster["verification"].startswith("gsxt") and len(roster["postings"]) == 1


# --- the sheet the applicant fills -------------------------------------------------------------
def test_template_carries_the_company_sheet_with_the_fields_the_verifier_reads():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(ROOT / "docs" / "openhire-岗位表.xlsx", read_only=True)
    assert wb.sheetnames == ["岗位", "公司信息", "说明"]
    keys = [row[0] for row in wb["公司信息"].iter_rows(values_only=True) if row and row[0]]
    for field in ve.COMPANY_FIELDS:
        assert field in keys, field

"""DeepSeek's price bands, and the lock that keeps every paid call in the cheap one.

DeepSeek has billed by time of day since 2026-08-17: full price on weekdays 09:00-12:00
and 14:00-18:00 Beijing time, half price at every other hour, and since 2026-08-23 half
price all day on Saturdays and Sundays (api-docs.deepseek.com/quick_start/pricing and the
two announcements). The lead's rule since 2026-09-23 has been to run paid extraction only
at half price, but a rule a session has to remember is a rule a session can forget: on
2026-10-22 the local session ran the role-family pass at 11:11 on a weekday and paid
full price, ¥12.50, for work that costs half that off-peak. So the check now sits in front
of every DeepSeek call (`DeepSeekExtractor._call`), and no flag, option or environment
variable turns it off. If DeepSeek changes its bands, change the constants below in a
release.

Two choices only ever err towards waiting:
  * Chinese public holidays count as weekdays. DeepSeek bills them at half price, but
    keeping a holiday calendar right every year is not worth the risk of a wrong entry.
  * Each full-price window is padded by 30 minutes on both sides, because the clock this
    reads is the machine's, and the lead's PC has been seen running ten-odd minutes slow.
"""

from __future__ import annotations

import datetime as dt

BEIJING = dt.timezone(dt.timedelta(hours=8), "Beijing")

# Full-price windows, Beijing time, Monday to Friday: (start, end) in minutes after midnight.
FULL_PRICE_WINDOWS = ((9 * 60, 12 * 60), (14 * 60, 18 * 60))
GUARD_MINUTES = 30


class PeakHours(RuntimeError):
    """A paid DeepSeek call was refused because DeepSeek bills full price right now."""


def _now() -> dt.datetime:
    # The one clock read in this module; conftest pins it to a half-price hour.
    return dt.datetime.now(dt.timezone.utc)


def blocked_until(now: dt.datetime | None = None) -> dt.datetime | None:
    """None when a paid DeepSeek call may go out now; otherwise the Beijing time it may."""
    t = (now or _now()).astimezone(BEIJING)
    if t.weekday() >= 5:
        return None
    minute = t.hour * 60 + t.minute
    midnight = t.replace(hour=0, minute=0, second=0, microsecond=0)
    for start, end in FULL_PRICE_WINDOWS:
        if start - GUARD_MINUTES <= minute < end + GUARD_MINUTES:
            return midnight + dt.timedelta(minutes=end + GUARD_MINUTES)
    return None


def explain(now: dt.datetime | None = None) -> str | None:
    """The refusal in words (Chinese, for the console), or None at half price."""
    now = now or _now()
    until = blocked_until(now)
    if until is None:
        return None
    here = now.astimezone(BEIJING)
    return (
        f"现在是北京时间 {here:%H:%M}，DeepSeek 全价时段（工作日 9 点到 12 点、14 点到 18 点，"
        f"前后各留 30 分钟余量）。付费抽取只在半价时段跑，北京时间 {until:%H:%M} 以后再运行"
    )


def check(now: dt.datetime | None = None) -> None:
    """Raise PeakHours unless DeepSeek bills half price right now."""
    reason = explain(now)
    if reason is not None:
        raise PeakHours(reason)

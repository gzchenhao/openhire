"""The hosted endpoint wipes watches and application records at every redeploy (Render's free plan
has no disk). Howard 2026-11-17: say so in the tool results rather than let a user find out."""
from openhire import hosted, mcp_server


def test_note_only_in_hosted_mode(monkeypatch):
    monkeypatch.delenv(hosted.ENV_FLAG, raising=False)
    assert "hosted_reset_note" not in mcp_server._with_reset_note({"a": 1})
    monkeypatch.setenv(hosted.ENV_FLAG, "1")
    out = mcp_server._with_reset_note({"a": 1})
    assert "清空" in out["hosted_reset_note"]["zh"] and "deleted" in out["hosted_reset_note"]["en"]
    assert mcp_server._with_reset_note([1]) == [1]


def test_instructions_and_home_page_say_it():
    assert "EVERY REDEPLOY OF THIS HOST DELETES THEM" in hosted.NOTICE
    assert "most likely reset by an update" in hosted.NOTICE


def test_the_four_tools_attach_it():
    import inspect
    src = inspect.getsource(mcp_server)
    for call in ("service.check_watches(", "service.manage_watch(", "service.check_applications("):
        assert f"_with_reset_note({call}" in src, call
    assert "return _with_reset_note(out)" in src

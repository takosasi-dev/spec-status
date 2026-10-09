# 仕様書の写しと差分(snapshots)のテスト: 写しの置き方・ensure_baseline の条件・差分・指示文の切り詰め。
from __future__ import annotations

from specstatus import snapshots as S

from test_guilogic import ps, rec


def _ps(tmp_path, name="A", text="一\n二\n", **kw):
    p = ps(name, f"W/{name}", "実装完了", **kw)
    f = tmp_path / f"{name}.md"
    f.write_text(text, encoding="utf-8")
    p.project.docs[0].abs_path = str(f)
    return p, f


def test_save_and_diff(tmp_path):
    snap = str(tmp_path / "snap")
    p, f = _ps(tmp_path)
    assert S.diff(p, snap) is None and S.diff_prompt(p, snap) == ""        # 写しが無い
    S.save(p, snap)
    assert S.diff(p, snap) == [] and S.diff_prompt(p, snap) == ""          # 違いが無い
    f.write_text("一\n三\n", encoding="utf-8")
    [(path, lines)] = S.diff(p, snap)
    assert path == p.project.docs[0].path
    assert lines[:2] == ["--- 記録した時点", "+++ 今"] and "-二" in lines and "+三" in lines
    text = S.diff_prompt(p, snap)
    assert str(f) in text and "```diff" in text and "+三" in text and "切りました" not in text


def test_ensure_baseline(tmp_path):
    snap = str(tmp_path / "snap")
    norec, _ = _ps(tmp_path, "N")
    changed, _ = _ps(tmp_path, "C", history=[rec("2026-10-01T00:00:00+09:00")])
    changed.spec_changed = "2026-10-05"
    ok, f = _ps(tmp_path, "K", history=[rec("2026-10-01T00:00:00+09:00")])
    assert S.ensure_baseline([norec, changed, ok], snap) == 1
    assert S.diff(norec, snap) is None and S.diff(changed, snap) is None and S.diff(ok, snap) == []
    f.write_text("別\n", encoding="utf-8")
    assert S.ensure_baseline([ok], snap) == 0                               # 写しがあれば上書きしない
    assert S.diff(ok, snap) != []


def test_prompt_truncates(tmp_path):
    snap = str(tmp_path / "snap")
    p, f = _ps(tmp_path, text="")
    S.save(p, snap)
    f.write_text("".join(f"{i}\n" for i in range(500)), encoding="utf-8")
    text = S.diff_prompt(p, snap)
    assert "切りました" in text and f"+{S.PROMPT_MAX_LINES}" not in text

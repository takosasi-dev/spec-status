# 時間の流れ(history: ある日の状態・推移・止まっている物)・週のまとめ(render.weekly_markdown)・GitHub(github: 結び方と取り直し)。
# ネットワークと git には触れない(取りに行く関数を差し替える)。
from __future__ import annotations

import json
from datetime import date

from specstatus import github, history, render
from specstatus.model import Board, Evidence, ImplPath

from test_guilogic import ps, rec

DAY = date(2026, 10, 9)


def board(statuses, **cfg) -> Board:
    return Board(vault="C:/v", pc_name="pc", config=cfg, docs=[], statuses=statuses, unreadable=[],
                 skipped_evidence=[], record_problems=[], orphans=[], folders_without_specs=[], registry_issues=[],
                 record_count=0, os_dirs=[])


def test_state_at_and_series():
    # 10/01 に着手済、10/08 に実装完了。記録より前は記録以外の証拠(説明書の 着手済)
    a = ps("A", "W/A", "実装完了", source=("events", "実装完了"),
           history=[rec("2026-10-01T10:00:00+09:00", state="着手済"), rec("2026-10-08T10:00:00+09:00", state="実装完了")])
    a.evidence = [Evidence("setsumei", "着手済", "着手済", "")]
    b = ps("B", "W/B", "実装完了", source=("tooldeck", "実装完了"))       # 記録なし = いつでも実装完了とみなす
    c = ps("C", "W/C", "証拠なし")
    assert history.state_at(a, "2026-09-30") == "着手済"
    assert history.state_at(a, "2026-10-07") == "着手済"
    assert history.state_at(a, "2026-10-08") == "実装完了"
    assert history.state_at(c, "2026-10-08") is None
    assert history.series([a, b, c], DAY, 3) == [("2026-09-25", 1, 1), ("2026-10-02", 1, 1), ("2026-10-09", 2, 0)]


def test_mark_stale():
    old = ps("old", "W/old", "着手済", source=("events", "着手済"), history=[rec("2026-08-01T10:00:00+09:00")])
    old.folded.impl = [ImplPath("C:/impl/old", "pc", True), ImplPath("C:/gone", "pc", False)]
    fresh = ps("fresh", "W/fresh", "一部未実装", history=[rec("2026-08-01T10:00:00+09:00")])
    fresh.folded.impl = [ImplPath("C:/impl/fresh", "pc", True)]
    done = ps("done", "W/done", "実装完了", history=[rec("2026-01-01T10:00:00+09:00")])
    asked = []
    git = {"C:/impl/old": "2026-08-20", "C:/impl/fresh": "2026-10-01"}

    def fake_git(path):
        asked.append(path)
        return git.get(path)
    history.mark_stale([old, fresh, done], DAY, 30, fake_git)
    assert (old.last_activity, old.stale_days) == ("2026-08-20", 50)
    assert (fresh.last_activity, fresh.stale_days) == ("2026-10-01", None)
    assert done.last_activity is None
    assert sorted(asked) == ["C:/impl/fresh", "C:/impl/old"]  # この PC に無いフォルダと、途中でない物は見ない(並列なので順は不定)


def test_weekly_markdown():
    a = ps("A", "W/A", "実装完了", source=("events", "実装完了"), waiting="確認待ち",
           history=[rec("2026-09-20T10:00:00+09:00", state="着手済"),
                    rec("2026-10-07T10:00:00+09:00", by="claude-code", state="実装完了", waiting="確認待ち")])
    b = ps("B", "W/B", "着手済", source=("events", "着手済"), history=[rec("2026-09-01T10:00:00+09:00", state="着手済")])
    b.last_activity, b.stale_days = "2026-09-01", 38
    a.github = {"repo": "o/a", "url": "https://github.com/o/a", "pushed_at": "2026-10-06", "release": "v1.0.0",
                "release_at": "2026-10-06", "ci": "成功"}
    md = render.weekly_markdown(board([a, b]), DAY, DAY, set())
    assert "# 実装状況の週まとめ(10/5〜10/11)" in md
    assert "| 実装完了 | 0 | 1 | +1 |" in md and "| 着手済 | 2 | 1 | -1 |" in md
    assert "| [[A_仕様書\\|A]] | 着手済 | 実装完了 | 2026-10-07 | Claude Code |" in md
    assert "## あなたの番になった物(1)" in md
    assert "| [[B_仕様書\\|B]] | 着手済 | 2026-09-01 | 38 |" in md
    assert "[o/a](https://github.com/o/a) | v1.0.0" in md


class Headers(dict):
    def get(self, k, d=None):
        return next((v for kk, v in self.items() if kk.lower() == k.lower()), d)


def test_github_match_and_refresh(tmp_path):
    spec = ps("SpecStatus", "W/SpecStatus", "実装完了")
    lens = ps("RepoLens", "W/RepoLens", "実装完了")
    other = ps("Other", "W/Other", "未着手")
    repos = [{"name": "spec-status", "html_url": "https://github.com/o/spec-status", "pushed_at": "2026-10-09T12:00:00Z",
              "default_branch": "main", "open_issues_count": 3},
             {"name": "github-repo-lens", "html_url": "u", "pushed_at": "2026-10-08T01:00:00Z", "default_branch": "main"}]
    calls = []

    def fetch(url, etag):
        calls.append((url, etag))
        if url.endswith("/repos?per_page=100"):
            return (304, Headers(), b"") if etag else (200, Headers(ETag="e1", **{"X-RateLimit-Remaining": "50"}),
                                                       json.dumps(repos).encode())
        if "releases" in url:
            return 200, Headers(), json.dumps([{"tag_name": "v0.1.0", "published_at": "2026-10-09T12:00:00Z"}]).encode()
        if "spec-status/actions" in url:
            return 200, Headers(), json.dumps({"workflow_runs": [{"status": "completed", "conclusion": "failure"}]}).encode()
        return 200, Headers(), json.dumps({"workflow_runs": []}).encode()

    cfg = {"github": {"owner": "o", "repos": {"RepoLens": "github-repo-lens"}}}
    path = str(tmp_path / "c.json")
    assert github.attach([spec, lens, other], cfg, now=1000.0, fetch=fetch, path=path) == ""
    assert spec.github == {"repo": "o/spec-status", "url": "https://github.com/o/spec-status", "pushed_at": "2026-10-09",
                           "release": "v0.1.0", "release_at": "2026-10-09", "ci": "失敗", "issues": 3, "branch": "main",
                           "stars": None, "forks": None, "downloads": 0}
    assert lens.github["ci"] is None and other.github is None
    assert render.github_text(spec.github) == "v0.1.0 CI 失敗 Issue 3"
    assert "checks-status/o/spec-status/main" in render.badges(spec.github)
    assert len(calls) == 5

    # 新しいうちは取りに行かない。古くなったら ETag 付きで聞き直す
    calls.clear()
    github.attach([spec], cfg, now=2000.0, fetch=fetch, path=path)
    assert calls == []
    github.attach([spec], cfg, now=1000.0 + 7 * 3600, fetch=fetch, path=path)
    assert calls[0][1] == "e1"

    # 回数の上限・繋がらないときは前の結果を使い、一言だけ返す
    lim = ps("SpecStatus", "W/SpecStatus", "実装完了")
    note = github.attach([lim], cfg, now=1e9, fetch=lambda u, e: (403, Headers(), b""), path=path)
    assert "上限" in note and lim.github["release"] == "v0.1.0"

    def down(u, e):
        raise OSError("no network")
    assert "繋がりません" in github.attach([lim], cfg, now=2e9, fetch=down, path=path)
    assert github.attach([lim], {"github": {"owner": ""}}, fetch=down) == ""

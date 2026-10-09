# GitHub の反響(星・フォーク・ダウンロード数)と offline。通信は差し替える(本物の GitHub は呼ばない)。
from __future__ import annotations

import json

from specstatus import github

from test_guilogic import ps


class Headers(dict):
    def get(self, k, d=None):
        return super().get(k, d)


REPOS = [{"name": "spec-status", "html_url": "u", "pushed_at": "2026-10-09T12:00:00Z", "default_branch": "main",
          "open_issues_count": 1, "stargazers_count": 12, "forks_count": 3, "private": False}]
RELEASE = [{"tag_name": "v0.6.0", "published_at": "2026-10-09T12:00:00Z",
            "assets": [{"download_count": 40}, {"download_count": 2}, {}]}]


def fetch_ok(calls):
    def fetch(url, etag):
        calls.append(url)
        if url.endswith("/repos?per_page=100"):
            return 200, Headers(), json.dumps(REPOS).encode()
        if "releases" in url:
            return 200, Headers(), json.dumps(RELEASE).encode()
        return 200, Headers(), json.dumps({"workflow_runs": []}).encode()
    return fetch


CFG = {"github": {"owner": "o"}}


def test_stars_forks_downloads(tmp_path):
    a = ps("SpecStatus", "W/SpecStatus", "実装完了")
    calls = []
    assert github.attach([a], CFG, now=1000.0, fetch=fetch_ok(calls), path=str(tmp_path / "c.json")) == ""
    assert (a.github["stars"], a.github["forks"], a.github["downloads"]) == (12, 3, 42)
    assert len(calls) == 3                     # 一覧・版・CI の3つだけ(呼び出しは増やさない)
    saved = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    repo = next(e for u, e in saved["urls"].items() if u.endswith("per_page=100"))["data"][0]
    assert "private" not in repo and repo["stargazers_count"] == 12


def test_no_release_downloads_none(tmp_path):
    a = ps("SpecStatus", "W/SpecStatus", "実装完了")

    def fetch(url, etag):
        if url.endswith("/repos?per_page=100"):
            return 200, Headers(), json.dumps(REPOS).encode()
        return 200, Headers(), json.dumps([] if "releases" in url else {"workflow_runs": []}).encode()
    github.attach([a], CFG, now=1000.0, fetch=fetch, path=str(tmp_path / "c.json"))
    assert a.github["downloads"] is None and a.github["release"] is None


def test_old_cache_gives_none_and_drops_etag(tmp_path):
    path = tmp_path / "c.json"
    old_repo = {k: REPOS[0][k] for k in ("name", "html_url", "pushed_at", "default_branch", "open_issues_count")}
    base = "https://api.github.com"
    path.write_text(json.dumps({"version": 2, "urls": {
        f"{base}/users/o/repos?per_page=100": {"etag": "e1", "fetched": 1000.0, "data": [old_repo]},
        f"{base}/repos/o/spec-status/releases?per_page=1": {"etag": "e2", "fetched": 1000.0,
                                                             "data": {"tag": "v0.5.0", "at": "2026-10-01"}},
    }}), encoding="utf-8")
    a = ps("SpecStatus", "W/SpecStatus", "実装完了")
    github.attach([a], CFG, now=1000.0, fetch=fetch_ok([]), path=str(path), offline=True)
    assert a.github["release"] == "v0.5.0"
    assert (a.github["stars"], a.github["forks"], a.github["downloads"]) == (None, None, None)

    # 古くなって取り直すときは ETag を付けない(304 で古い形が残らないように)
    etags = []

    def fetch(url, etag):
        etags.append(etag)
        return fetch_ok([])(url, etag)
    github.attach([a], CFG, now=1000.0 + 7 * 3600, fetch=fetch, path=str(path))
    assert etags[:2] == ["", ""] and a.github["stars"] == 12 and a.github["downloads"] == 42


def test_offline_uses_cache_only(tmp_path):
    path = str(tmp_path / "c.json")
    a = ps("SpecStatus", "W/SpecStatus", "実装完了")
    github.attach([a], CFG, now=1000.0, fetch=fetch_ok([]), path=path)

    def boom(url, etag):
        raise AssertionError("offline なのに取りに行った")
    b = ps("SpecStatus", "W/SpecStatus", "実装完了")
    assert github.attach([b], CFG, now=1e9, fetch=boom, path=path, offline=True) == ""
    assert b.github["stars"] == 12
    c = ps("SpecStatus", "W/SpecStatus", "実装完了")
    github.attach([c], CFG, fetch=boom, path=str(tmp_path / "none.json"), offline=True)
    assert c.github is None

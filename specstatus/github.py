# GitHub の公開 API(登録不要・1時間60回まで)から、持ち主のリポジトリの最後の push・最新の版・CI の結果を取り、プロジェクトに付ける。
# 結果はこの PC の %LOCALAPPDATA%\SpecStatus\ に保存し(vault には書かない)、refresh_hours より古い物だけ ETag 付きで取り直す。
# 取れなくても前の結果で続ける。終了コードには響かせず、Board.github_note に一言だけ残す。
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Callable

from .model import ProjectStatus
from .textutil import fold

API = "https://api.github.com"
TIMEOUT_S = 5
BUDGET_S = 20           # 1回の読み込みで GitHub に使う時間の上限
RESERVE = 5             # 残りの回数がこれ以下になったら、続きは次の読み込みに回す
REFRESH_HOURS = 6
CACHE_VERSION = 2       # 2: 一覧に open_issues_count を足した
CI_LABEL = {"success": "成功", "failure": "失敗", "cancelled": "取消", "timed_out": "失敗"}

Fetch = Callable[[str, str], tuple[int, object, bytes]]


def http_get(url: str, etag: str) -> tuple[int, object, bytes]:
    """(状態コード, ヘッダ(大文字小文字を区別しない .get), 本文)。繋がらなければ OSError。"""
    headers = {"User-Agent": "SpecStatus", "Accept": "application/vnd.github+json"}
    if etag:
        headers["If-None-Match"] = etag
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT_S) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, b""


def cache_path(owner: str) -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus", f"github-{owner}.json")


def _local_day(iso: str | None) -> str:
    """GitHub の UTC の時刻(…Z)を、この PC の日付 YYYY-MM-DD にする。"""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().date().isoformat()
    except ValueError:
        return iso[:10]


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", fold(s))


# 取った物は使う所だけ残して保存する
def _trim_repos(data) -> list[dict]:
    return [{k: r.get(k) for k in ("name", "html_url", "pushed_at", "default_branch", "open_issues_count")} for r in data]


def _trim_release(data) -> dict | None:
    return {"tag": data[0]["tag_name"], "at": _local_day(data[0].get("published_at"))} if data else None


def _trim_runs(data) -> dict | None:
    runs = data.get("workflow_runs") or []
    return {"status": runs[0].get("status"), "conclusion": runs[0].get("conclusion")} if runs else None


def _refresh(cache: dict, jobs: list[tuple[str, Callable]], now: float, hours: float, fetch: Fetch) -> str:
    """古い URL を取り直す。止めた理由(無ければ "")を返す。"""
    start = time.monotonic()
    for url, trim in jobs:
        ent = cache.get(url)
        if ent and now - ent["fetched"] < hours * 3600:
            continue
        if time.monotonic() - start > BUDGET_S:
            return "GitHub: 時間切れ。続きは次の読み込みで取ります"
        try:
            status, headers, body = fetch(url, ent["etag"] if ent else "")
        except (OSError, ValueError) as e:
            return f"GitHub に繋がりません(前の結果を使います): {e}"
        if status == 304 and ent:
            ent["fetched"] = now
        elif status == 200:
            try:
                data = trim(json.loads(body))
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                return f"GitHub の返事を読めません(前の結果を使います): {e}"
            cache[url] = {"etag": headers.get("ETag") or "", "fetched": now, "data": data}
        elif status == 404:
            cache[url] = {"etag": "", "fetched": now, "data": None}
        elif status in (403, 429):
            return "GitHub の回数の上限です。前の結果を使い、続きは1時間後に取ります"
        else:
            return f"GitHub が {status} を返しました(前の結果を使います)"
        left = headers.get("X-RateLimit-Remaining")
        if status != 304 and str(left).isdecimal() and int(left) <= RESERVE:
            return "GitHub の回数の上限が近いので、続きは1時間後に取ります"
    return ""


def match(statuses: list[ProjectStatus], repos: list[dict], explicit: dict) -> dict[str, dict]:
    """project.key -> リポジトリ。設定の repos(プロジェクト名か仕様書フォルダ -> リポジトリ名。"" は結ばない)が先、
    無ければ名前と別名を英数字だけにして比べる(SpecStatus と spec-status が当たる)。"""
    by_name = {r["name"].casefold(): r for r in repos}
    by_norm: dict[str, dict] = {}
    for r in repos:
        by_norm.setdefault(_norm(r["name"]), r)
    out = {}
    for ps in statuses:
        p = ps.project
        want = next((explicit[k] for k in (p.name, p.spec_dir) if k in explicit), None)
        if want is not None:
            r = by_name.get(want.casefold()) if want else None
        else:
            r = next((by_norm[k] for k in map(_norm, [p.name, *p.aliases]) if k and k in by_norm), None)
        if r:
            out[p.key] = r
    return out


def _urls(owner: str, repo: dict) -> tuple[str, str]:
    base = f"{API}/repos/{owner}/{repo['name']}"
    branch = urllib.parse.quote(repo.get("default_branch") or "main")
    return f"{base}/releases?per_page=1", f"{base}/actions/runs?per_page=1&branch={branch}"


def info(cache: dict, owner: str, repo: dict) -> dict:
    rel_url, runs_url = _urls(owner, repo)
    rel = (cache.get(rel_url) or {}).get("data")
    run = (cache.get(runs_url) or {}).get("data")
    ci = None
    if run:
        ci = "実行中" if run["status"] != "completed" else CI_LABEL.get(run["conclusion"], run["conclusion"])
    return {"repo": f"{owner}/{repo['name']}", "url": repo.get("html_url") or "",
            "pushed_at": _local_day(repo.get("pushed_at")), "release": rel["tag"] if rel else None,
            "release_at": rel["at"] if rel else None, "ci": ci,
            "issues": repo.get("open_issues_count"), "branch": repo.get("default_branch") or "main"}


def _load(path: str) -> dict:
    """保存の形(CACHE_VERSION)が違えば捨てる(304 では残した形のまま使い続けてしまうため)。"""
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        return c.get("urls", {}) if c.get("version") == CACHE_VERSION else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _save(path: str, cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": CACHE_VERSION, "urls": cache}, f, ensure_ascii=False)
    except OSError:
        pass        # 保存できなくても次に取り直すだけ


def attach(statuses: list[ProjectStatus], cfg: dict, now: float | None = None,
           fetch: Fetch = http_get, path: str | None = None) -> str:
    """設定 [github] owner が空なら何もしない。結べたプロジェクトに ps.github を付け、止めた理由を返す。"""
    sec = cfg.get("github", {})
    owner = (sec.get("owner") or "").strip()
    if not owner:
        return ""
    path = path or cache_path(owner)
    cache = _load(path)
    now = time.time() if now is None else now
    hours = sec.get("refresh_hours", REFRESH_HOURS)
    list_url = f"{API}/users/{owner}/repos?per_page=100"
    note = _refresh(cache, [(list_url, _trim_repos)], now, hours, fetch)
    repos = (cache.get(list_url) or {}).get("data") or []
    matched = match(statuses, repos, sec.get("repos", {}))
    if not note:
        jobs = []
        for r in {r["name"]: r for r in matched.values()}.values():
            rel_url, runs_url = _urls(owner, r)
            jobs += [(rel_url, _trim_release), (runs_url, _trim_runs)]
        note = _refresh(cache, jobs, now, hours, fetch)
    _save(path, cache)
    for ps in statuses:
        r = matched.get(ps.project.key)
        if r:
            ps.github = info(cache, owner, r)
    return note

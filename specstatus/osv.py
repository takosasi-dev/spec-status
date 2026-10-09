# 実装フォルダの依存の一覧(ロックファイル)を読み、OSV.dev(Google の脆弱性データベース。登録不要・無料)で既知の脆弱性を数える。
# 読むのは package-lock.json・requirements.txt(== で固定した行)・poetry.lock・uv.lock・Cargo.lock。実装フォルダとその2段下まで。
# 結果は %LOCALAPPDATA%\SpecStatus\osv.json に依存ごとに残し、refresh_hours より古い物だけ聞き直す。取れなくても前の結果で続ける。
# 脆弱性ごとの深刻度と直る版は /v1/vulns/{id} から取り、隣の osv_vulns.json に ID ごとに7日残す。
from __future__ import annotations

import json
import os
import re
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .history import impl_dirs
from .model import ProjectStatus

API = "https://api.osv.dev/v1/querybatch"
VULN_API = "https://api.osv.dev/v1/vulns/"
DETAIL_DAYS = 7              # 脆弱性の詳細を残す日数(契約の固定値)
SEVERITY = {"CRITICAL": "重大", "HIGH": "高", "MODERATE": "中", "MEDIUM": "中", "LOW": "低"}
SEVERITY_ORDER = ("重大", "高", "中", "低", "不明")       # 重い順
CVSS_STEPS = ((9.0, "重大"), (7.0, "高"), (4.0, "中"), (0.1, "低"))
CHUNK = 1000                 # querybatch の1回の上限
TIMEOUT_S = 20
BUDGET_S = 30
REFRESH_HOURS = 24
DEPTH = 2
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "env", "dist", "build", "target", "__pycache__",
             ".worktrees", ".tox", "site-packages", "_internal"}
LOCKFILES = {"package-lock.json": "npm", "requirements.txt": "PyPI", "poetry.lock": "PyPI", "uv.lock": "PyPI",
             "Cargo.lock": "crates.io"}
SHOW = 5
CACHE_VERSION = 1
REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*==\s*([A-Za-z0-9.!+_-]+)\s*(?:[;#].*)?$")

Pkg = tuple[str, str, str]          # (ecosystem, name, version)
Post = Callable[[list[dict]], list[dict]]
Get = Callable[[str], dict]         # 脆弱性 ID -> OSV の JSON(無い ID は {})


def find_lockfiles(root: str, depth: int = DEPTH) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")) if level < depth else []
        out += [os.path.join(dirpath, f) for f in sorted(filenames) if f in LOCKFILES]
    return out


def parse(path: str) -> list[Pkg]:
    """ロックファイル1つの (ecosystem, name, version)。読めなければ空。"""
    name = os.path.basename(path)
    eco = LOCKFILES[name]
    try:
        if name == "package-lock.json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            pkgs = []
            for key, v in (data.get("packages") or {}).items():          # lockfileVersion 2・3
                if key and "node_modules/" in key and isinstance(v, dict) and v.get("version") and not v.get("link"):
                    pkgs.append((eco, key.rsplit("node_modules/", 1)[1], v["version"]))
            if not data.get("packages"):                                   # lockfileVersion 1
                stack = list((data.get("dependencies") or {}).items())
                while stack:
                    n, v = stack.pop()
                    if isinstance(v, dict) and v.get("version"):
                        pkgs.append((eco, n, v["version"]))
                        stack += list((v.get("dependencies") or {}).items())
            return pkgs
        if name == "requirements.txt":
            with open(path, encoding="utf-8", errors="replace") as f:
                return [(eco, m[1], m[2]) for m in map(REQ_RE.match, f) if m]
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return [(eco, p["name"], p["version"]) for p in data.get("package", [])
                if isinstance(p, dict) and p.get("name") and p.get("version")]
    except (OSError, ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
        return []


def http_post(queries: list[dict]) -> list[dict]:
    body = json.dumps({"queries": queries}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json", "User-Agent": "SpecStatus"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r).get("results", [])


def http_get_json(vid: str) -> dict:
    req = urllib.request.Request(VULN_API + urllib.parse.quote(vid), headers={"User-Agent": "SpecStatus"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:            # 消えた ID。詳細なしとして残す
            return {}
        raise


def _pkg_key(eco: str, name: str) -> str:
    if eco == "PyPI":                # PEP 503 の名前の正規化
        name = re.sub(r"[-_.]+", "-", name)
    return f"{eco}|{name.casefold()}"


def _severity(v: dict) -> str:
    """database_specific.severity(GHSA)を優先、無ければ数値の CVSS、どちらも無ければ不明。"""
    s = SEVERITY.get(str((v.get("database_specific") or {}).get("severity") or "").upper())
    if s:
        return s
    for e in v.get("severity") or []:
        try:
            score = float(e.get("score"))
        except (TypeError, ValueError):
            continue                 # ponytail: CVSS のベクトル文字列は計算しない(不明にする)。要るなら CVSS 3.1 の式を足す
        return next((label for low, label in CVSS_STEPS if score >= low), "不明")
    return "不明"


def _detail(v: dict, now: float) -> dict:
    """1つの脆弱性の残す形: {t, sev, fixed: {pkg_key: [直る版]}}。"""
    fixed: dict[str, list[str]] = {}
    for a in v.get("affected") or []:
        p = a.get("package") or {}
        if not p.get("name"):
            continue
        vs = [e["fixed"] for r in a.get("ranges") or [] if r.get("type") != "GIT"
              for e in r.get("events") or [] if e.get("fixed")]
        fixed.setdefault(_pkg_key(p.get("ecosystem", ""), p["name"]), []).extend(vs)
    return {"t": now, "sev": _severity(v), "fixed": fixed}


def _vkey(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)), v


def _fixed_for(cur: str, versions: list[str]) -> str | None:
    """今の版より新しい直る版のうち、先頭の数字が同じ物を優先して一番小さい物。"""
    newer = [v for v in versions if _vkey(v) > _vkey(cur)]
    head = _vkey(cur)[0][:1]
    same = [v for v in newer if _vkey(v)[0][:1] == head]
    return min(same or newer, key=_vkey, default=None)


def _fetch_details(cache: dict, ids: set[str], now: float, get: Get, start: float) -> str:
    stale = sorted(i for i in ids if i not in cache or now - cache[i]["t"] >= DETAIL_DAYS * 86400)
    for vid in stale:
        if time.monotonic() - start > BUDGET_S:
            return "OSV: 時間切れ。続きは次の読み込みで聞きます"
        try:
            cache[vid] = _detail(get(vid) or {}, now)
        except (OSError, ValueError) as e:
            return f"OSV.dev の詳細が取れません(前の結果を使います): {e}"
    return ""


def _details(hits: list[tuple[Pkg, list[str]]], dcache: dict) -> list[dict]:
    out = []
    for (eco, name, ver), ids in hits:
        known = [dcache[i] for i in ids if i in dcache]
        sev = min((d["sev"] for d in known), key=SEVERITY_ORDER.index, default="不明")
        fixes = [f for d in known if (f := _fixed_for(ver, d["fixed"].get(_pkg_key(eco, name), [])))]
        out.append({"package": name, "version": ver, "ids": ids, "severity": sev,
                    "fixed": max(fixes, key=_vkey, default=None)})
    out.sort(key=lambda d: (SEVERITY_ORDER.index(d["severity"]), d["package"].casefold(), d["version"]))
    return out


def cache_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus", "osv.json")


def _key(p: Pkg) -> str:
    return "|".join(p)


def _refresh(cache: dict, pkgs: set[Pkg], now: float, hours: float, post: Post) -> str:
    stale = sorted(p for p in pkgs if _key(p) not in cache or now - cache[_key(p)]["t"] >= hours * 3600)
    start = time.monotonic()
    for i in range(0, len(stale), CHUNK):
        if time.monotonic() - start > BUDGET_S:
            return "OSV: 時間切れ。続きは次の読み込みで聞きます"
        part = stale[i:i + CHUNK]
        try:
            res = post([{"package": {"ecosystem": e, "name": n}, "version": v} for e, n, v in part])
        except (OSError, ValueError) as e:
            return f"OSV.dev に繋がりません(前の結果を使います): {e}"
        for p, r in zip(part, res):
            cache[_key(p)] = {"t": now, "ids": sorted(v["id"] for v in (r or {}).get("vulns", []) if v.get("id"))}
    return ""


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        return c if c.get("_version") == CACHE_VERSION else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _save(path: str, cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**cache, "_version": CACHE_VERSION}, f, ensure_ascii=False)
    except OSError:
        pass


def attach(statuses: list[ProjectStatus], cfg: dict, now: float | None = None, post: Post = http_post,
           path: str | None = None, get: Get | None = None) -> str:
    """設定 [osv] enabled が true のときだけ。この PC にある実装フォルダのロックファイルを読み、ps.vulns を付ける。
    get を省くと、post も本物のときだけ詳細を聞く(post を差し替えたテストで通信しない)。"""
    if get is None and post is http_post:
        get = http_get_json
    sec = cfg.get("osv", {})
    if not sec.get("enabled"):
        return ""
    found: dict[str, tuple[list[str], set[Pkg]]] = {}
    for ps in statuses:
        files, pkgs = [], set()
        for d in impl_dirs(ps):
            if os.path.isdir(d):
                for lf in find_lockfiles(d):
                    files.append(lf.replace("\\", "/"))
                    pkgs.update(parse(lf))
        if files:
            found[ps.project.key] = (files, pkgs)
    if not found:
        return ""
    path = path or cache_path()
    cache = _load(path)
    cache.pop("_version", None)
    now = time.time() if now is None else now
    start = time.monotonic()
    note = _refresh(cache, set().union(*(p for _, p in found.values())), now, sec.get("refresh_hours", REFRESH_HOURS), post)
    _save(path, cache)
    dpath = os.path.join(os.path.dirname(path), "osv_vulns.json")
    dcache = _load(dpath)
    dcache.pop("_version", None)
    hits_by = {}
    for key, (files, pkgs) in found.items():
        hits_by[key] = sorted((p, cache[_key(p)]["ids"]) for p in pkgs if cache.get(_key(p), {}).get("ids"))
    if get is not None and not note:
        note = _fetch_details(dcache, {i for hs in hits_by.values() for _, ids in hs for i in ids}, now, get, start)
        _save(dpath, dcache)
    for ps in statuses:
        if ps.project.key not in found:
            continue
        files, pkgs = found[ps.project.key]
        hits = hits_by[ps.project.key]
        details = _details(hits, dcache)
        ps.vulns = {"count": len(hits), "total": len(pkgs), "lockfiles": files,
                    "packages": [f"{n}@{v}({', '.join(ids[:3])})" for (_e, n, v), ids in hits[:SHOW]],
                    "ids": sorted({i for _, ids in hits for i in ids}),
                    "details": details, "worst": details[0]["severity"] if details else None}
    return note

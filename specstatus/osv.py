# 実装フォルダの依存の一覧(ロックファイル)を読み、OSV.dev(Google の脆弱性データベース。登録不要・無料)で既知の脆弱性を数える。
# 読むのは package-lock.json・requirements.txt(== で固定した行)・poetry.lock・uv.lock・Cargo.lock。実装フォルダとその2段下まで。
# 結果は %LOCALAPPDATA%\SpecStatus\osv.json に依存ごとに残し、refresh_hours より古い物だけ聞き直す。取れなくても前の結果で続ける。
from __future__ import annotations

import json
import os
import re
import time
import tomllib
import urllib.request
from typing import Callable

from .history import impl_dirs
from .model import ProjectStatus

API = "https://api.osv.dev/v1/querybatch"
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
           path: str | None = None) -> str:
    """設定 [osv] enabled が true のときだけ。この PC にある実装フォルダのロックファイルを読み、ps.vulns を付ける。"""
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
    note = _refresh(cache, set().union(*(p for _, p in found.values())), now, sec.get("refresh_hours", REFRESH_HOURS), post)
    _save(path, cache)
    for ps in statuses:
        if ps.project.key not in found:
            continue
        files, pkgs = found[ps.project.key]
        hits = sorted((p, cache[_key(p)]["ids"]) for p in pkgs if cache.get(_key(p), {}).get("ids"))
        ps.vulns = {"count": len(hits), "total": len(pkgs), "lockfiles": files,
                    "packages": [f"{n}@{v}({', '.join(ids[:3])})" for (_e, n, v), ids in hits[:SHOW]],
                    "ids": sorted({i for _, ids in hits for i in ids})}
    return note

# 依存の古さ: 実装フォルダの package.json・pyproject.toml・requirements.txt・.python-version・.nvmrc から、ランタイムの版の
# サポート期限(endoflife.date)と、依存の最新の版(PyPI・npm)を調べる。どれも登録不要。依存は先頭の数字(major)だけ比べる。
# 結果は %LOCALAPPDATA%\SpecStatus\eol.json に名前ごとに refresh_hours 残す。取れなくても前の結果で続ける(osv.py と同じ作り)。
from __future__ import annotations

import json
import os
import re
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Callable

from .history import impl_dirs
from .model import ProjectStatus
from .osv import DEPTH, SKIP_DIRS, _pkg_key

EOL_API = "https://endoflife.date/api/{}.json"
PYPI_API = "https://pypi.org/pypi/{}/json"
NPM_API = "https://registry.npmjs.org/{}/latest"
TIMEOUT_S = 10
BUDGET_S = 30
REFRESH_HOURS = 24
MAX_QUERIES = 60             # 1回の読み込みで聞く数の上限(残りは次の読み込みで)
WARN_DAYS = 90               # サポート切れがこの日数以内なら「もうすぐ切れる」として出す
CACHE_VERSION = 1
MANIFESTS = ("package.json", "pyproject.toml", "requirements.txt", ".python-version", ".nvmrc")
RUNTIMES = {"python": ("Python", 2), "nodejs": ("Node.js", 1)}   # endoflife.date の製品 -> (表示名, cycle の数字の数)
REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*\(?\s*(===|==|~=|>=|>)\s*(v?\d[\w.*+!-]*)")

Fetch = Callable[[str], object]     # URL -> JSON(無い物は None)。繋がらなければ OSError
Dep = tuple[str, str, str]          # (ecosystem "pypi"|"npm", name, 書いてある版)


def http_get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "SpecStatus", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:            # 無い製品・パッケージ。無いとして残す
            return None
        raise


def _major(spec: str) -> int | None:
    """"^1.2"・">=18"・"v20.1.0"・"~5" の先頭の数字。"*"・"latest"・git や file: の指定は None。"""
    spec = spec.strip()
    if ":" in spec or "/" in spec:
        return None
    m = re.match(r"^[\^~>=<v\s]*(\d+)", spec)
    return int(m[1]) if m else None


def _cycle(product: str, spec: str) -> str | None:
    """ランタイムの版の書き方 -> endoflife.date の cycle(Python は "3.11"、Node は "20")。"""
    if _major(spec) is None:
        return None
    nums = re.findall(r"\d+", spec)
    n = RUNTIMES[product][1]
    return ".".join(nums[:n]) if len(nums) >= n else None


def find_manifests(root: str, depth: int = DEPTH) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")) if level < depth else []
        out += [os.path.join(dirpath, f) for f in sorted(filenames) if f in MANIFESTS]
    return out


def parse(path: str) -> tuple[list[tuple[str, str]], list[Dep]]:
    """ファイル1つの ([(製品, cycle)], [依存])。読めなければ空。"""
    name = os.path.basename(path)
    rts: list[tuple[str, str]] = []
    deps: list[Dep] = []
    try:
        if name in (".python-version", ".nvmrc"):
            with open(path, encoding="utf-8", errors="replace") as f:
                first = f.readline().strip()
            product = "python" if name == ".python-version" else "nodejs"
            if c := _cycle(product, first):
                rts.append((product, c))
        elif name == "package.json":
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if c := _cycle("nodejs", str((data.get("engines") or {}).get("node") or "")):
                rts.append(("nodejs", c))
            for sec in ("dependencies", "devDependencies"):
                for n, v in (data.get(sec) or {}).items():
                    if isinstance(v, str) and _major(v) is not None:
                        deps.append(("npm", n, v))
        elif name == "requirements.txt":
            with open(path, encoding="utf-8", errors="replace") as f:
                deps += [("pypi", m[1], m[2] + m[3]) for m in map(REQ_RE.match, f) if m]
        else:
            with open(path, "rb") as f:
                proj = tomllib.load(f).get("project") or {}
            if c := _cycle("python", str(proj.get("requires-python") or "")):
                rts.append(("python", c))
            deps += [("pypi", m[1], m[2] + m[3]) for m in map(REQ_RE.match, proj.get("dependencies") or []) if m]
    except (OSError, ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
        return [], []
    return rts, deps


def cache_path(folder: str | None = None) -> str:
    if folder is None:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
        folder = os.path.join(base, "SpecStatus")
    return os.path.join(folder, "eol.json")


def _url(key: str) -> str:
    kind, name = key.split("|", 1)
    if kind == "eol":
        return EOL_API.format(urllib.parse.quote(name))
    if kind == "PyPI":
        return PYPI_API.format(urllib.parse.quote(name))
    return NPM_API.format(urllib.parse.quote(name, safe="@"))      # @types/node -> @types%2Fnode


def _trim(key: str, data) -> object:
    """残す形: ランタイムは {cycle: eol(日付の文字か True/False)}、依存は最新の版の文字。無ければ None。"""
    if data is None:
        return None
    if key.startswith("eol|"):
        return {str(c["cycle"]): c.get("eol") for c in data if isinstance(c, dict) and "cycle" in c}
    if key.startswith("PyPI|"):
        return (data.get("info") or {}).get("version")
    return data.get("version")


def _refresh(cache: dict, keys: list[str], now: float, hours: float, limit: int, fetch: Fetch) -> str:
    stale = [k for k in keys if k not in cache or now - cache[k]["t"] >= hours * 3600]
    start = time.monotonic()
    for i, key in enumerate(stale):
        if i >= limit:
            return f"サポート期限: 聞く数の上限({limit})に来たので、続きは次の読み込みで聞きます"
        if time.monotonic() - start > BUDGET_S:
            return "サポート期限: 時間切れ。続きは次の読み込みで聞きます"
        try:
            cache[key] = {"t": now, "data": _trim(key, fetch(_url(key)))}
        except (OSError, ValueError, AttributeError, TypeError, KeyError) as e:
            return f"endoflife.date・PyPI・npm に繋がりません(前の結果を使います): {e}"
    return ""


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        return c.get("names", {}) if c.get("version") == CACHE_VERSION else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _save(path: str, cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": CACHE_VERSION, "names": cache}, f, ensure_ascii=False)
    except OSError:
        pass


def _eol_day(v) -> date | None:
    """endoflife.date の eol: 日付の文字・true(もう切れた。日付不明)・false(期限なし)。"""
    if v is True:
        return date.min
    try:
        return date.fromisoformat(v) if isinstance(v, str) else None
    except ValueError:
        return None


def _judge(rts: set[tuple[str, str]], deps: set[Dep], cache: dict, today: date, warn_days: int) -> dict | None:
    runtimes = []
    for product, cycle in sorted(rts):
        cycles = (cache.get(f"eol|{product}") or {}).get("data") or {}
        day = _eol_day(cycles.get(cycle))
        if day is not None and day <= today + timedelta(days=warn_days):
            runtimes.append({"name": RUNTIMES[product][0], "version": cycle,
                             "eol": "" if day == date.min else day.isoformat(), "ended": day <= today})
    outdated = []
    for eco, name, spec in sorted(deps, key=lambda d: (d[0], d[1].casefold(), d[2])):
        latest = (cache.get(_dep_key(eco, name)) or {}).get("data")
        cur, new = _major(spec), _major(latest) if isinstance(latest, str) else None
        if cur is not None and new is not None and new > cur:
            outdated.append({"package": name, "version": spec, "latest": latest, "behind": new - cur})
    outdated.sort(key=lambda d: (-d["behind"], d["package"].casefold()))
    return {"runtimes": runtimes, "outdated": outdated} if runtimes or outdated else None


def _dep_key(eco: str, name: str) -> str:
    return _pkg_key("PyPI" if eco == "pypi" else "npm", name)


def attach(statuses: list[ProjectStatus], cfg: dict, fetch: Fetch | None = None, now: float | None = None,
           folder: str | None = None, offline: bool = False) -> str:
    """設定 [eol] enabled が true のときだけ。この PC にある実装フォルダを読み、遅れている物があれば ps.eol を付ける。
    offline なら聞きに行かず、残してある結果だけ使う。戻り値は取れなかった等の一言(無ければ "")。"""
    sec = cfg.get("eol", {})
    if not sec.get("enabled"):
        return ""
    fetch = fetch or http_get_json
    found: dict[str, tuple[set, set]] = {}
    for ps in statuses:
        rts, deps = set(), set()
        for d in impl_dirs(ps):
            if os.path.isdir(d):
                for mf in find_manifests(d):
                    r, p = parse(mf)
                    rts.update(r)
                    deps.update(p)
        if rts or deps:
            found[ps.project.key] = (rts, deps)
    if not found:
        return ""
    path = cache_path(folder)
    cache = _load(path)
    now = time.time() if now is None else now
    keys = sorted({f"eol|{p}" for rts, _ in found.values() for p, _c in rts})
    keys += sorted({_dep_key(e, n) for _, deps in found.values() for e, n, _v in deps})
    note = ""
    if not offline:
        note = _refresh(cache, keys, now, sec.get("refresh_hours", REFRESH_HOURS),
                        sec.get("max_queries", MAX_QUERIES), fetch)
        _save(path, cache)
    today = date.fromtimestamp(now)
    for ps in statuses:
        if ps.project.key in found:
            ps.eol = _judge(*found[ps.project.key], cache, today, sec.get("warn_days", WARN_DAYS))
    return note

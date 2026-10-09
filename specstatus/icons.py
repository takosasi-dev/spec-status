# プロジェクトのアイコンを探して、一覧の行と詳細の大きさの PNG にする。
# まずこの PC の実装フォルダ(Chrome 拡張の manifest・統合版の pack_icon・Android の ic_launcher・icon.png 等)、
# 無ければ公開中の GitHub リポジトリのファイルの一覧(API 1回/7日)から探して raw で落とす。
# 縮めた PNG は %LOCALAPPDATA%\SpecStatus\icons\ に置き、元のファイルが変わるまで使い回す。vault には書かない。
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Callable

from . import pngutil
from .history import impl_dirs
from .model import ProjectStatus

DEPTH = 5
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "env", "dist", "build", "target", "__pycache__", ".worktrees",
             ".tox", "site-packages", "_internal", ".godot", ".gradle", "bin", "obj", "out", "tests", "test", "fixtures"}
GENERIC_RE = re.compile(r"^(app[_-]?icon|appicon|icon|logo|favicon)([_-]?\d+(x\d+)?)?\.(png|ico)$", re.I)
GITHUB_DAYS = 7
TREE_TIMEOUT_S = 10
RAW_TIMEOUT_S = 15
MAX_BYTES = 2_000_000

Get = Callable[[str], bytes]


def _png_size(path: str) -> int:
    try:
        with open(path, "rb") as f:
            s = pngutil.size_of(f.read(24))
        return s[0] if s else 0
    except OSError:
        return 0


def _manifest_icons(path: str) -> list[str]:
    """Chrome 拡張の manifest.json の icons(大きい順)。"""
    try:
        with open(path, encoding="utf-8-sig") as f:
            m = json.load(f)
        icons = m.get("icons") if isinstance(m, dict) and "manifest_version" in m else None
        if not isinstance(icons, dict):
            return []
        items = sorted(((int(k), v) for k, v in icons.items() if str(k).isdecimal() and isinstance(v, str)), reverse=True)
        return [os.path.join(os.path.dirname(path), *v.split("/")) for _, v in items]
    except (OSError, ValueError, TypeError):
        return []


def rank(rel: str) -> int | None:
    """アイコンらしさの順位(小さいほど良い)。rel は '/' 区切り。アイコンでなければ None。"""
    name = rel.rsplit("/", 1)[-1]
    low = name.lower()
    if low == "pack_icon.png":
        return 1
    if low == "ic_launcher.png" and "/mipmap-" in rel.lower():
        return 1
    if GENERIC_RE.match(name):
        return 2 if low.endswith(".png") else 3
    return None


def local_candidates(root: str) -> list[str]:
    """実装フォルダの中のアイコンの候補(良い順)。"""
    found: list[tuple[int, int, int, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")) if level < DEPTH else []
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            if fn == "manifest.json" and level <= 2:
                found += [(0, level, i, p) for i, p in enumerate(_manifest_icons(full)) if os.path.isfile(p)]
                continue
            r = rank(os.path.relpath(full, root).replace(os.sep, "/"))
            if r is not None:
                size = _png_size(full) if fn.lower().endswith(".png") else 256
                found.append((r, level, -min(size, 256), full))   # 同じ順位なら浅い方、大きい方(256 まで)
    return [p for *_k, p in sorted(found)]


def cache_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus", "icons")


def _thumbs(data: bytes, key: str, sizes: tuple[int, ...], folder: str) -> dict[int, str] | None:
    """縮めた PNG を大きさごとに置く(あれば作らない)。扱えない画像なら None。"""
    out = {}
    for s in sizes:
        path = os.path.join(folder, f"{key}-{s}.png")
        if not os.path.isfile(path):
            try:
                png = pngutil.thumbnail(data, s)
            except Exception:                               # 壊れた・扱えない形の画像は飛ばす
                return None
            os.makedirs(folder, exist_ok=True)
            with open(path, "wb") as f:
                f.write(png)
        out[s] = path
    return out


def _from_local(path: str, sizes: tuple[int, ...], folder: str) -> dict[int, str] | None:
    try:
        st = os.stat(path)
        if st.st_size > MAX_BYTES:
            return None
        key = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:16]
        if all(os.path.isfile(os.path.join(folder, f"{key}-{s}.png")) for s in sizes):
            return {s: os.path.join(folder, f"{key}-{s}.png") for s in sizes}
        with open(path, "rb") as f:
            return _thumbs(f.read(), key, sizes, folder)
    except OSError:
        return None


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SpecStatus", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=TREE_TIMEOUT_S if "api.github.com" in url else RAW_TIMEOUT_S) as r:
        return r.read(MAX_BYTES + 1)


def github_pick(tree: dict) -> str | None:
    """リポジトリのファイルの一覧(git/trees の返事)から、一番アイコンらしい画像のパス。"""
    best = None
    for t in tree.get("tree", []):
        p = t.get("path", "")
        if t.get("type") != "blob" or any(part in SKIP_DIRS or part.startswith(".") for part in p.split("/")[:-1]):
            continue
        r = rank(p) if not p.endswith("manifest.json") else None
        if r is not None and p.count("/") < DEPTH:
            k = (r, p.count("/"), -(t.get("size") or 0) if p.lower().endswith(".ico") else 0, p)
            best = min(best, k) if best else k
    return best[-1] if best else None


def _from_github(gh: dict, sizes: tuple[int, ...], folder: str, index: dict, now: float, get: Get) -> dict[int, str] | None:
    repo, branch = gh["repo"], gh.get("branch") or "main"
    ent = index.get(repo)
    if not ent or now - ent["t"] > GITHUB_DAYS * 86400:
        tree = json.loads(get(f"https://api.github.com/repos/{repo}/git/trees/{urllib.parse.quote(branch)}?recursive=1"))
        ent = index[repo] = {"t": now, "path": github_pick(tree)}
    if not ent["path"]:
        return None
    key = hashlib.sha1(f"{repo}|{branch}|{ent['path']}|{ent['t']}".encode()).hexdigest()[:16]
    if all(os.path.isfile(os.path.join(folder, f"{key}-{s}.png")) for s in sizes):
        return {s: os.path.join(folder, f"{key}-{s}.png") for s in sizes}
    url = f"https://raw.githubusercontent.com/{repo}/{urllib.parse.quote(branch)}/{urllib.parse.quote(ent['path'])}"
    data = get(url)
    return _thumbs(data, key, sizes, folder) if len(data) <= MAX_BYTES else None


def find_all(statuses: list[ProjectStatus], sizes: tuple[int, ...], folder: str | None = None,
             get: Get = http_get, now: float | None = None) -> dict[str, dict[int, str]]:
    """project.key -> {大きさ: PNG のパス}。見つからない物は入れない。GitHub に繋がらなくても、手元の分は返す。"""
    folder = folder or cache_dir()
    now = time.time() if now is None else now
    index_path = os.path.join(folder, "github.json")
    try:
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError):
        index = {}
    out: dict[str, dict[int, str]] = {}
    net_ok = True
    for ps in statuses:
        got = None
        for d in impl_dirs(ps):
            if os.path.isdir(d):
                for cand in local_candidates(d):
                    got = _from_local(cand, sizes, folder)
                    if got:
                        break
            if got:
                break
        if not got and ps.github and net_ok:
            try:
                got = _from_github(ps.github, sizes, folder, index, now, get)
            except (OSError, ValueError):
                net_ok = False                  # 繋がらない・回数の上限なら、残りは次の読み込みで
        if got:
            out[ps.project.key] = got
    try:
        os.makedirs(folder, exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
    except OSError:
        pass
    return out

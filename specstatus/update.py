# GitHub の Release から新しい版を確かめ、vault の spec-status\ と(exe で動いていれば)exe を入れ替える。
# vault 側は data\ に触らず、specstatus.py などの実行物とパッケージだけを入れ替える(deploy.py と同じ範囲)。
# exe 側は Release の zip を隣に広げ、窓を閉じた後に PowerShell で入れ替えて開き直す(動いている exe は消せないため)。
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime

from . import __version__

REPO = "takosasi-dev/spec-status"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECK_HOURS = 24                 # 起動時の確認は1日1回まで
ASSET_SUFFIX = "-windows.zip"    # Release に付ける exe の zip の名前の終わり
FILES = ("specstatus.py", "start_gui.cmd", "README.md", "config.example.toml")
PACKAGE = "specstatus"
STAGE = ".update"                # vault の spec-status\ の中の作業場所(点で始まるので Obsidian は同期しない)
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class UpdateError(Exception):
    """利用者に見せる理由。"""


def parse_version(s: str | None) -> tuple[int, int, int] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (s or "").strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def is_newer(tag: str, current: str | None) -> bool:
    new, cur = parse_version(tag), parse_version(current)
    return new is not None and (cur is None or new > cur)


def vault_version(vault: str) -> str | None:
    """vault に置いてある spec-status の版(パッケージの __version__)。無ければ None。"""
    try:
        with open(os.path.join(vault, "spec-status", PACKAGE, "__init__.py"), encoding="utf-8") as f:
            m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
    except OSError:
        return None
    return m[1] if m else None


def _get(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SpecStatus", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except OSError as e:          # URLError・HTTPError・時間切れ
        raise UpdateError(f"GitHub から取れません: {e}") from e


def _cache_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus", "update.json")


def latest(force: bool = False, now: float | None = None, fetch=_get, path: str | None = None) -> dict:
    """最新の Release: {tag, url, notes, exe_zip}。force でなければ CHECK_HOURS 以内の前の結果を使う。"""
    path = path or _cache_path()
    now = time.time() if now is None else now
    if not force:
        try:
            with open(path, encoding="utf-8") as f:
                c = json.load(f)
            if now - c["checked"] < CHECK_HOURS * 3600:
                return c["release"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        d = json.loads(fetch(API_LATEST))
        rel = {"tag": d["tag_name"], "url": d.get("html_url") or "", "notes": (d.get("body") or "")[:1500],
               "exe_zip": next((a["browser_download_url"] for a in d.get("assets") or []
                                if a.get("name", "").endswith(ASSET_SUFFIX)), None)}
    except (ValueError, KeyError, TypeError) as e:
        raise UpdateError(f"GitHub の返事を読めません: {e}") from e
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"checked": now, "release": rel}, f, ensure_ascii=False)
    except OSError:
        pass
    return rel


def _safe_members(z: zipfile.ZipFile, prefix: str) -> list[str]:
    """prefix の下の名前だけ。.. や絶対パスで外に出る物があれば止める。"""
    out = []
    for n in z.namelist():
        if not n.startswith(prefix):
            continue
        rel = n[len(prefix):]
        if rel.startswith(("/", "\\")) or ".." in rel.replace("\\", "/").split("/") or ":" in rel:
            raise UpdateError(f"zip の中に置き場所の怪しいファイルがあります: {n}")
        out.append(n)
    return out


def _extract(z: zipfile.ZipFile, prefix: str, names: list[str], dest: str) -> None:
    for n in names:
        target = os.path.join(dest, *n[len(prefix):].split("/"))
        if n.endswith("/"):
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with z.open(n) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def update_vault(vault: str, tag: str, fetch=_get) -> str:
    """vault の spec-status\\ の実行物を tag の版に入れ替える。data\\ には触らない。戻り値は報告の1行。"""
    dest = os.path.join(vault, "spec-status")
    if not os.path.isfile(os.path.join(dest, "specstatus.py")):
        raise UpdateError(f"vault に SpecStatus が置かれていません: {dest}")
    data = fetch(f"https://github.com/{REPO}/archive/refs/tags/{tag}.zip", timeout=120)
    stage = os.path.join(dest, STAGE)
    shutil.rmtree(stage, ignore_errors=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            root = names[0].split("/")[0] + "/" if names else ""
            members = _safe_members(z, root)
            have = set(members)
            missing = [f for f in (*FILES, f"{PACKAGE}/__init__.py") if root + f not in have]
            if missing:
                raise UpdateError(f"{tag} の zip に必要なファイルがありません: {', '.join(missing)}")
            keep = [n for n in members if n[len(root):] in FILES or n[len(root):].startswith(PACKAGE + "/")]
            _extract(z, root, keep, stage)
    except zipfile.BadZipFile as e:
        raise UpdateError(f"{tag} の zip が壊れています: {e}") from e
    # パッケージはフォルダごと入れ替える(消えたファイルを残さない)。古い方は名前を変えてから消す
    pkg, old = os.path.join(dest, PACKAGE), os.path.join(stage, PACKAGE + ".old")
    os.replace(pkg, old)
    try:
        os.replace(os.path.join(stage, PACKAGE), pkg)
    except OSError:
        os.replace(old, pkg)
        raise
    for f in FILES:
        os.replace(os.path.join(stage, f), os.path.join(dest, f))
    with open(os.path.join(dest, "VERSION.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{tag} GitHub {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
    shutil.rmtree(stage, ignore_errors=True)
    return f"vault の SpecStatus を {tag} にしました: {dest}"


# ---- exe -------------------------------------------------------------------

def exe_dir() -> str | None:
    """exe で動いていれば、その exe のフォルダ。"""
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None


def stage_exe(exe_zip: str | None, folder: str, fetch=_get) -> str:
    """Release の exe の zip を <folder>.new に広げ、vault.txt を写す。戻り値は広げたフォルダ。"""
    if not exe_zip:
        raise UpdateError("この版の Release には exe の zip が付いていません")
    exe = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "SpecStatus.exe"
    data = fetch(exe_zip, timeout=300)
    staged = folder.rstrip("\\/") + ".new"
    shutil.rmtree(staged, ignore_errors=True)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            top = next((n[: -len(exe)] for n in z.namelist() if n.endswith("/" + exe) and n.count("/") == 1), None)
            if top is None:
                raise UpdateError(f"zip の中に {exe} がありません")
            _extract(z, top, _safe_members(z, top), staged)
    except zipfile.BadZipFile as e:
        raise UpdateError(f"exe の zip が壊れています: {e}") from e
    for f in ("vault.txt",):
        if os.path.isfile(os.path.join(folder, f)):
            shutil.copy2(os.path.join(folder, f), os.path.join(staged, f))
    return staged


def _ps(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def swap_script(pid: int, folder: str, staged: str, exe: str, launch: bool = True) -> str:
    """pid の終了を待って folder を staged に入れ替え、exe を開き直す PowerShell。失敗したら元に戻す。"""
    folder = folder.rstrip("\\/")
    old = folder + ".old"
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"Wait-Process -Id {int(pid)} -Timeout 60 -ErrorAction SilentlyContinue",
        "Start-Sleep -Milliseconds 500",
        f"$dir = {_ps(folder)}; $old = {_ps(old)}; $new = {_ps(staged)}",
        "if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }",
        "Rename-Item -LiteralPath $dir -NewName (Split-Path $old -Leaf)",
        "try { Rename-Item -LiteralPath $new -NewName (Split-Path $dir -Leaf) }",
        "catch { Rename-Item -LiteralPath $old -NewName (Split-Path $dir -Leaf) }",
        f"Start-Process -FilePath (Join-Path $dir {_ps(exe)})" if launch else "",
        "Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue",
    ])


def start_swap(folder: str, staged: str) -> None:
    """この窓を閉じた後に入れ替えるよう、PowerShell を切り離して起動する。呼んだら窓を閉じること。"""
    exe = os.path.basename(sys.executable)
    script = swap_script(os.getpid(), folder, staged, exe)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                      "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                     creationflags=_NO_WINDOW | 0x00000008, close_fds=True,   # DETACHED_PROCESS
                     cwd=os.path.dirname(folder.rstrip("\\/")))           # 入れ替えるフォルダの中に居座らない


def status(vault: str) -> dict:
    """{current, vault, exe}: 今動いている版、vault の版、exe で動いていれば exe のフォルダ。"""
    return {"current": __version__, "vault": vault_version(vault), "exe": exe_dir()}


def needs(rel: dict, st: dict) -> tuple[bool, bool]:
    """(vault を入れ替えるか, exe を入れ替えるか)。"""
    return is_newer(rel["tag"], st["vault"]), bool(st["exe"]) and is_newer(rel["tag"], st["current"])

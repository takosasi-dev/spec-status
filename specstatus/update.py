# GitHub の Release から新しい版を確かめ、vault の spec-status\ と(exe で動いていれば)exe を入れ替える。
# vault 側は data\ に触らず、specstatus.py などの実行物とパッケージだけを入れ替える(deploy.py と同じ範囲)。
# exe 側は Release の zip を隣に広げ、窓を閉じた後に PowerShell で入れ替えて開き直す。zip は SHA256SUMS.txt があれば照合する。
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
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
VAULT_SUFFIX = "-vault.zip"      # Release に付ける vault 用の zip(タグの git archive)の名前の終わり
SUMS_NAME = "SHA256SUMS.txt"     # Release に付ける照合用の一覧(<sha256>  <ファイル名>)
WAIT_SECONDS = 60                # 入れ替えの前に窓が閉じるのを待つ長さ
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


def _folder() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus")


def _cache_path() -> str:
    return os.path.join(_folder(), "update.json")


def log_path(folder: str | None = None) -> str:
    return os.path.join(folder or _folder(), "update.log")


def log(msg: str, folder: str | None = None) -> None:
    """update.log に1行足す。書けなくても止めない。"""
    try:
        os.makedirs(folder or _folder(), exist_ok=True)
        with open(log_path(folder), "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


# ---- 照合 ------------------------------------------------------------------

def sums_text(paths: list[str]) -> str:
    """SHA256SUMS.txt の中身(release.py が使う)。"""
    lines = []
    for p in paths:
        with open(p, "rb") as f:
            lines.append(f"{hashlib.file_digest(f, 'sha256').hexdigest()}  {os.path.basename(p)}\n")
    return "".join(lines)


def parse_sums(text: str) -> dict[str, str]:
    """{ファイル名: sha256}。sha256sum の「 *名前」(バイナリの印)も読む。"""
    out = {}
    for ln in text.splitlines():
        h, _, name = ln.strip().partition(" ")
        if name.strip():
            out[name.strip().lstrip("*")] = h.lower()
    return out


def verify(data: bytes, url: str, sums: str | None, fetch=_get) -> bool:
    """url の名前で SHA256SUMS.txt と照合する。合えば True、一覧が無い古い Release は False(照合なし)。合わなければ UpdateError。"""
    if not sums:
        return False
    name = url.rsplit("/", 1)[-1]
    want = parse_sums(fetch(sums).decode("utf-8", errors="replace")).get(name)
    if want is None:
        raise UpdateError(f"{SUMS_NAME} に {name} がありません")
    if hashlib.sha256(data).hexdigest() != want:
        raise UpdateError(f"{name} が {SUMS_NAME} と合いません(壊れているか、書き換えられています)")
    return True


def _checked_word(ok: bool) -> str:
    return "照合済み" if ok else "照合なし"


def latest(force: bool = False, now: float | None = None, fetch=_get, path: str | None = None) -> dict:
    """最新の Release: {tag, url, notes, exe_zip, vault_zip, sums}。force でなければ CHECK_HOURS 以内の前の結果を使う。
    前の版のキャッシュには vault_zip・sums が無いことがあるので、呼び手は .get で読む。"""
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
        assets = d.get("assets") or []

        def asset(match) -> str | None:
            return next((a["browser_download_url"] for a in assets if match(a.get("name", ""))), None)
        rel = {"tag": d["tag_name"], "url": d.get("html_url") or "", "notes": (d.get("body") or "")[:1500],
               "exe_zip": asset(lambda n: n.endswith(ASSET_SUFFIX)),
               "vault_zip": asset(lambda n: n.endswith(VAULT_SUFFIX)),
               "sums": asset(lambda n: n == SUMS_NAME)}
    except (ValueError, KeyError, TypeError) as e:
        raise UpdateError(f"GitHub の返事を読めません: {e}") from e
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"checked": now, "release": rel}, f, ensure_ascii=False)
    except OSError:
        pass
    return rel


def _rmtree(path: str) -> None:
    """読み取り専用の印が付いたフォルダ・ファイルも消す(vault の中のフォルダには付いていることがある)。消せなければ残す。"""
    def clear_and_retry(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    if os.path.exists(path):
        shutil.rmtree(path, onerror=clear_and_retry)


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


def _swap_in(dest: str, stage: str, names: tuple[str, ...]) -> None:
    """names を stage から dest へ入れ替える。先に今の物を全部 stage に <名前>.old で退避し、途中で失敗したら全部元に戻す。"""
    moved, placed = [], []
    try:
        for n in names:
            if os.path.lexists(os.path.join(dest, n)):
                os.replace(os.path.join(dest, n), os.path.join(stage, n + ".old"))
                moved.append(n)
        for n in names:
            os.replace(os.path.join(stage, n), os.path.join(dest, n))
            placed.append(n)
    except OSError as e:
        stuck = []
        for n in placed:
            p = os.path.join(dest, n)
            with contextlib.suppress(OSError):
                _rmtree(p) if os.path.isdir(p) else os.remove(p)
        for n in moved:
            try:
                os.replace(os.path.join(stage, n + ".old"), os.path.join(dest, n))
            except OSError:
                stuck.append(n)
        if stuck:
            raise UpdateError(f"入れ替えに失敗し、元に戻せない物があります({', '.join(stuck)})。"
                              f"前の版は {stage} に <名前>.old で残っています: {e}") from e
        raise


def update_vault(vault: str, tag: str, fetch=_get, zip_url: str | None = None, sums: str | None = None) -> str:
    """vault の spec-status\\ の実行物を tag の版に入れ替える。data\\ には触らない。戻り値は報告の1行。
    zip_url(Release の vault 用 zip)と sums があれば照合する。無い古い Release はタグの zip を照合せずに使う。"""
    dest = os.path.join(vault, "spec-status")
    if not os.path.isfile(os.path.join(dest, "specstatus.py")):
        raise UpdateError(f"vault に SpecStatus が置かれていません: {dest}")
    url = zip_url or f"https://github.com/{REPO}/archive/refs/tags/{tag}.zip"
    data = fetch(url, timeout=120)
    checked = verify(data, url, sums if zip_url else None, fetch)
    stage = os.path.join(dest, STAGE)
    _rmtree(stage)
    if os.path.exists(stage):
        raise UpdateError(f"前の更新の作業フォルダを消せません(ほかのアプリが開いていないか確かめてください): {stage}")
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
    # パッケージはフォルダごと入れ替える(消えたファイルを残さない)
    _swap_in(dest, stage, (PACKAGE, *FILES))
    with open(os.path.join(dest, "VERSION.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{tag} GitHub {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
    _rmtree(stage)
    log(f"vault を {tag} にしました({_checked_word(checked)}): {dest}")
    return f"vault の SpecStatus を {tag} にしました({_checked_word(checked)}): {dest}"


# ---- exe -------------------------------------------------------------------

def exe_dir() -> str | None:
    """exe で動いていれば、その exe のフォルダ。"""
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None


def stage_exe(exe_zip: str | None, folder: str, fetch=_get, sums: str | None = None) -> str:
    """Release の exe の zip を(sums があれば照合して)<folder>.new に広げ、vault.txt を写す。戻り値は広げたフォルダ。
    照合したかどうかは update.log に書く。"""
    if not exe_zip:
        raise UpdateError("この版の Release には exe の zip が付いていません")
    exe = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "SpecStatus.exe"
    data = fetch(exe_zip, timeout=300)
    log(f"exe の zip を取りました({_checked_word(verify(data, exe_zip, sums, fetch))}): {exe_zip}")
    staged = folder.rstrip("\\/") + ".new"
    _rmtree(staged)
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


def swap_script(pid: int, folder: str, staged: str, exe: str, launch: bool = True,
                log_file: str | None = None, wait: int = WAIT_SECONDS) -> str:
    """pid の終了を待って folder を staged に入れ替え、exe を開き直す PowerShell。失敗したら元に戻す。
    成功でも失敗でも finally で何かの exe(成功なら新、失敗なら元)を起動し、結果を update.log に1行ずつ足す。
    pid が wait 秒で終わらなければ入れ替えずに元を起動する。.old はここでは消さない(次に起動した exe が cleanup_old で消す)。
    launch=False は起動せずに「起動: <パス>」の行だけ書く(テスト用)。"""
    folder = folder.rstrip("\\/")
    old = folder + ".old"
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"$dir = {_ps(folder)}; $old = {_ps(old)}; $new = {_ps(staged)}; $log = {_ps(log_file or log_path())}",
        "function Log($m) { try { [IO.Directory]::CreateDirectory((Split-Path $log)) | Out-Null",
        "  [IO.File]::AppendAllText($log, (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' ' + $m + \"`n\", [Text.UTF8Encoding]::new($false)) } catch {} }",
        "try {",
        f"  Wait-Process -Id {int(pid)} -Timeout {int(wait)} -ErrorAction SilentlyContinue",
        f"  if (Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue) {{ Log '窓が閉じるのを待ちきれませんでした。入れ替えずに元の版を開きます'; return }}",
        "  Start-Sleep -Milliseconds 500",
        "  if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }",
        "  Rename-Item -LiteralPath $dir -NewName (Split-Path $old -Leaf)",
        "  try { Rename-Item -LiteralPath $new -NewName (Split-Path $dir -Leaf); Log ('入れ替えました: ' + $dir) }",
        "  catch { Log ('入れ替えに失敗したので元に戻します: ' + $_); Rename-Item -LiteralPath $old -NewName (Split-Path $dir -Leaf) }",
        "} catch { Log ('入れ替えに失敗しました: ' + $_) }",
        "finally {",
        # 元に戻すのにも失敗して $dir が無ければ、退避した元の版を開く
        f"  $exe = Join-Path $dir {_ps(exe)}; if (-not (Test-Path -LiteralPath $dir)) {{ $exe = Join-Path $old {_ps(exe)} }}",
        "  Log ('起動: ' + $exe)",
        "  try { Start-Process -FilePath $exe } catch { Log ('起動できませんでした: ' + $_) }" if launch else "",
        "}",
    ])


def cleanup_old(folder: str | None) -> bool:
    """前の更新で残した <folder>.old を消す。無事に起動した後に呼ぶ。消したら True。"""
    if not folder:
        return False
    old = folder.rstrip("\\/") + ".old"
    if not os.path.isdir(old):
        return False
    _rmtree(old)
    if os.path.exists(old):
        return False
    log(f"前の版を消しました: {old}")
    return True


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

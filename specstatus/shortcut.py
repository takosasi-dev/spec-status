# デスクトップとスタートメニューに、SpecStatus のアイコンつきのショートカットを作る(Windows だけ)。
# exe を渡せば exe を、無ければ pythonw で vault の specstatus.py gui を開く。.lnk は PowerShell の WScript.Shell で書く。
from __future__ import annotations

import base64
import os
import subprocess
import sys

NAME = "SpecStatus.lnk"
DESCRIPTION = "仕様書の実装状況"
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _ps(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def target(vault: str, exe: str | None) -> tuple[str, str, str, str]:
    """(開く物, 引数, 作業フォルダ, アイコン)。"""
    if exe:
        exe = os.path.abspath(exe)
        return exe, "", os.path.dirname(exe), exe + ",0"
    here = os.path.join(vault, "spec-status")
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    args = f'"{os.path.join(here, "specstatus.py")}" gui --vault "{vault}"'
    return pyw, args, here, os.path.join(here, "specstatus", "assets", "icon.ico") + ",0"


def script(tgt: str, args: str, workdir: str, icon: str, places: list[str]) -> str:
    """places は Environment.SpecialFolder の名前(Desktop・Programs)。作ったパスを1行ずつ出す。"""
    lines = ["$ErrorActionPreference = 'Stop'", "[Console]::OutputEncoding = [Text.Encoding]::UTF8",
             "$ws = New-Object -ComObject WScript.Shell"]
    for place in places:
        lines += [f"$p = Join-Path ([Environment]::GetFolderPath({_ps(place)})) {_ps(NAME)}",
                  "$s = $ws.CreateShortcut($p)",
                  f"$s.TargetPath = {_ps(tgt)}", f"$s.Arguments = {_ps(args)}", f"$s.WorkingDirectory = {_ps(workdir)}",
                  f"$s.IconLocation = {_ps(icon)}", f"$s.Description = {_ps(DESCRIPTION)}", "$s.Save()", "Write-Output $p"]
    return "\n".join(lines)


def create(vault: str, exe: str | None = None, places: tuple[str, ...] = ("Desktop", "Programs")) -> list[str]:
    """ショートカットを作り(同じ名前は上書き)、作ったパスを返す。失敗したら OSError。"""
    if os.name != "nt":
        raise OSError("ショートカットは Windows だけで作れます")
    if exe and not os.path.isfile(exe):
        raise OSError(f"exe がありません: {exe}")
    enc = base64.b64encode(script(*target(vault, exe), list(places)).encode("utf-16-le")).decode("ascii")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc],
                       capture_output=True, timeout=60, creationflags=_NO_WINDOW)
    if r.returncode != 0:
        raise OSError(r.stderr.decode("cp932", errors="replace").strip()[:500] or f"PowerShell が {r.returncode} で終わりました")
    return [ln.strip() for ln in r.stdout.decode("utf-8", errors="replace").splitlines() if ln.strip()]

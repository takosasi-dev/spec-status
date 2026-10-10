# 朝の知らせ(前回から増えた待ち・脆弱な依存・仕様の変更を Windows の通知で出す)と、
# schtasks /XML での定期実行(毎朝 notify・毎週金曜 weekly --write。寝ていた時刻の分は起きた時に動く)の登録・削除・確認。
# PowerShell と schtasks は runner で差し替えられる(テストでは本物を呼ばない)。状態は %LOCALAPPDATA%\SpecStatus\ に置く。
from __future__ import annotations

import base64
import json
import locale
import os
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

from .config import ConfigError, load_config

TASK_NOTIFY = "SpecStatus 朝の知らせ"
TASK_WEEKLY = "SpecStatus 週のまとめ"
NAMES_MAX = 3                    # 本文に出すプロジェクト名の数
AUMID = "takosasi.SpecStatus"
AUMID_POWERSHELL = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
WAITING_KINDS = ("確認待ち", "実物待ち")
KINDS = (("waiting", "待ち"), ("vuln", "脆弱な依存"), ("changed", "仕様の変更"))
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _folder() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus")


def _decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode(locale.getencoding(), errors="replace")     # schtasks は cp932 で出す


def _run(args: list[str]) -> tuple[int, str, str]:
    try:
        r = subprocess.run(args, capture_output=True, timeout=60, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)
    return r.returncode, _decode(r.stdout), _decode(r.stderr)


# ---- 朝の知らせ ----------------------------------------------------------------

def current_sets(statuses) -> dict[str, set[str]]:
    return {
        "waiting": {ps.project.key for ps in statuses if ps.waiting in WAITING_KINDS},
        "vuln": {ps.project.key for ps in statuses if ps.vulns and ps.vulns.get("count")},
        "changed": {ps.project.key for ps in statuses if ps.spec_changed},
    }


def save_state(board, state_path: str | None = None) -> None:
    """今の状態を state_path(notify.json)に残す。次の notify はこれと比べる。"""
    path = state_path or os.path.join(_folder(), "notify.json")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: sorted(v) for k, v in current_sets(board.statuses).items()}, f, ensure_ascii=False)


def notify_summary(board, state_path: str | None = None, save: bool = True) -> tuple[str, str] | None:
    """前回から増えた物があれば (題, 本文)。無ければ None。save なら今の状態を state_path に残す
    (通知が出せたかを見てから残すときは save=False にして、出せた後に save_state を呼ぶ)。"""
    path = state_path or os.path.join(_folder(), "notify.json")
    now = current_sets(board.statuses)
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        prev = {k: set(saved[k]) for k, _ in KINDS}
    except (OSError, ValueError, KeyError, TypeError):
        prev = None                                   # 初回(か壊れている): 今ある物を全部「新しい」とみなす
    if save:
        save_state(board, path)

    new = {k: now[k] - (prev[k] if prev else set()) for k, _ in KINDS}
    new_keys = set().union(*new.values())
    if not new_keys:
        return None
    lines = []
    if prev is not None:
        lines.append("増えた物: " + " / ".join(f"{label} {len(new[k])}" for k, label in KINDS if new[k]))
        names = {ps.project.key: ps.project.name for ps in board.statuses}
        shown = sorted((names.get(k, k) for k in new_keys), key=str.casefold)
        more = f" ほか {len(shown) - NAMES_MAX} 件" if len(shown) > NAMES_MAX else ""
        lines.append("、".join(shown[:NAMES_MAX]) + more)
    lines.append("今: " + " / ".join(f"{label} {len(now[k])}" for k, label in KINDS))
    return f"SpecStatus: 新しく {len(new_keys)} 件", "\n".join(lines)


def _ps(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def toast_script(title: str, body: str) -> str:
    xml = ('<toast><visual><binding template="ToastText02">'
           f'<text id="1">{escape(title)}</text><text id="2">{escape(body)}</text>'
           '</binding></visual></toast>')
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null",
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null",
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument",
        f"$xml.LoadXml({_ps(xml)})",
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)",
        # 登録されていない ID は Setting を読むと例外か Enabled 以外になるので、PowerShell の ID に落とす
        f"try {{ $n = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier({_ps(AUMID)})",
        "  if ($n.Setting -ne 'Enabled') { throw 'not registered' }",
        "  $n.Show($toast) }",
        f"catch {{ [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier({_ps(AUMID_POWERSHELL)}).Show($toast) }}",
    ])


def toast(title: str, body: str, runner=None) -> None:
    """Windows の通知を出す。出せなければ OSError。"""
    enc = base64.b64encode(toast_script(title, body).encode("utf-16-le")).decode("ascii")
    code, _, err = (runner or _run)(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc])
    if code != 0:
        raise OSError(err.strip()[:500] or f"PowerShell が {code} で終わりました")


# ---- schtasks ------------------------------------------------------------------

def _python() -> str:
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return pyw if os.path.isfile(pyw) else sys.executable


# 日時の XML。StartBoundary の日付は過去なら何でもよい(時刻と曜日だけが効く)
DAILY_9 = ("<CalendarTrigger><StartBoundary>2026-01-01T09:00:00</StartBoundary>"
           "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>")
FRIDAY_18 = ("<CalendarTrigger><StartBoundary>2026-01-02T18:00:00</StartBoundary>"
             "<ScheduleByWeek><DaysOfWeek><Friday /></DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>"
             "</CalendarTrigger>")


def task_specs(vault: str, config: str | None) -> list[tuple[str, str, str, str]]:
    """(タスク名, python に渡す引数, 日時の XML, 説明)。"""
    script = os.path.join(vault, "spec-status", "specstatus.py")
    tail = f' --vault "{vault}"' + (f' --config "{config}"' if config else "")
    return [
        (TASK_NOTIFY, f'"{script}" notify{tail}', DAILY_9, "毎日 9:00"),
        (TASK_WEEKLY, f'"{script}" weekly --write{tail}', FRIDAY_18, "毎週金曜 18:00"),
    ]


def task_xml(command: str, arguments: str, trigger: str, description: str) -> str:
    """schtasks /XML に渡すタスクの定義。ログオン中だけ動き(通知を出すため)、寝ていた時刻の分は起きた時に動く。"""
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-16"?>',
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">',
        f"  <RegistrationInfo><Description>{escape(description)}</Description></RegistrationInfo>",
        f"  <Triggers>{trigger}</Triggers>",
        '  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType>'
        "<RunLevel>LeastPrivilege</RunLevel></Principal></Principals>",
        "  <Settings><StartWhenAvailable>true</StartWhenAvailable>"
        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries></Settings>",
        f'  <Actions Context="Author"><Exec><Command>{escape(command)}</Command>'
        f"<Arguments>{escape(arguments)}</Arguments></Exec></Actions>",
        "</Task>",
    ])


def _create(name: str, xml: str, runner, folder: str) -> None:
    """XML を UTF-16 の一時ファイルに書いて schtasks /Create /XML に渡す(同じ名前は上書き)。"""
    os.makedirs(folder, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".xml", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))
        code, _, err = (runner or _run)(["schtasks", "/Create", "/TN", name, "/XML", path, "/F"])
    finally:
        os.remove(path)
    if code != 0:
        raise OSError(f"{name} を登録できません: {err.strip()[:500] or code}")


def install(vault: str, python: str | None = None, config: str | None = None, runner=None,
            folder: str | None = None, weekly: bool = True) -> list[str]:
    """タスクを登録する(同じ名前は上書き)。weekly=False(設定 [schedule] weekly = false)の PC では週のまとめを
    登録せず、登録済みなら消す(2台が同じ週報を同時に書かないため)。やったことの行を返す。登録できなければ OSError。"""
    vault = os.path.abspath(vault)
    python = python or _python()
    config = os.path.abspath(config) if config else None
    out = []
    for name, args, trigger, label in task_specs(vault, config):
        if name == TASK_WEEKLY and not weekly:
            code, _, _ = (runner or _run)(["schtasks", "/Delete", "/TN", name, "/F"])
            out.append(f"{name} は登録しません(設定の [schedule] weekly = false)" + ("。登録済みの物は消しました" if code == 0 else ""))
            continue
        _create(name, task_xml(python, args, trigger, f"SpecStatus: {label}"), runner, folder or _folder())
        out.append(f"登録しました: {name}({label}。寝ていた時は起きた時に動きます)")
    return out


def remove(runner=None) -> list[str]:
    out = []
    for name in (TASK_NOTIFY, TASK_WEEKLY):
        code, _, err = (runner or _run)(["schtasks", "/Delete", "/TN", name, "/F"])
        out.append(f"消しました: {name}" if code == 0 else f"消せませんでした(未登録?): {name}  {err.strip()[:200]}".rstrip())
    return out


def status(runner=None) -> list[str]:
    out = []
    for name in (TASK_NOTIFY, TASK_WEEKLY):
        code, stdout, _ = (runner or _run)(["schtasks", "/Query", "/TN", name, "/FO", "LIST"])
        if code != 0:
            out.append(f"{name}: 未登録")
            continue
        nxt = next((ln.split(":", 1)[1].strip() for ln in stdout.splitlines()
                    if ":" in ln and ("Next Run" in ln.split(":", 1)[0] or "次回" in ln.split(":", 1)[0])), "?")
        out.append(f"{name}: 次回 {nxt}")
    return out


# ---- CLI の配線 ------------------------------------------------------------------

def add_commands(sub, common) -> None:
    p = sub.add_parser("notify", parents=[common], help="前回から増えた待ち・脆弱な依存・仕様の変更を通知する")
    p.add_argument("--quiet", action="store_true", help="通知を出さず、文だけ出す")
    p = sub.add_parser("schedule", parents=[common], help="朝の知らせと週のまとめを Windows のタスクに登録する")
    p.add_argument("action", choices=("install", "remove", "status"))
    p.add_argument("--python", help="タスクで使う pythonw.exe(既定は今の Python の隣)")


def run(args, vault: str) -> int:
    """0=済み、2=失敗。"""
    try:
        if args.cmd == "notify":
            from . import core
            board = core.load(vault, args.config)
            try:
                core.refresh_outputs(board)      # Obsidian や別の PC が足した記録を、朝に一覧ノートと JSON に追いつかせる
            except OSError:
                pass
            msg = notify_summary(board, save=False)
            if msg is None:
                save_state(board)
                print("前回から増えた物はありません。")
                return 0
            print(msg[0])
            print(msg[1])
            if not args.quiet:
                toast(*msg)               # 出せなければ OSError → 状態を残さず、次の notify でもう一度知らせる
            save_state(board)
            return 0
        if args.action == "install":
            weekly = load_config(vault, args.config).get("schedule", {}).get("weekly", True)
            lines = install(vault, args.python, args.config, weekly=weekly)
        else:
            lines = (remove if args.action == "remove" else status)()
        for ln in lines:
            print(ln)
        return 0
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 2
    except OSError as e:
        print(str(e), file=sys.stderr)
        return 2

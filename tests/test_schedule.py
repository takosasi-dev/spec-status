# 朝の知らせとタスク登録(schedule)のテスト: 前回から増えた物の数え方、schtasks の引数、
# /TR が長いときの .cmd、通知の PowerShell の文。schtasks・PowerShell は差し替え、本物は呼ばない。
from __future__ import annotations

import argparse
import base64
import os
from types import SimpleNamespace

from specstatus import schedule as S
from tests.test_guilogic import ps


def board(*rows):
    return SimpleNamespace(statuses=list(rows))


def vuln(p, n=1):
    p.vulns = {"count": n}
    return p


def changed(p):
    p.spec_changed = "2026-10-08"
    return p


class Fake:
    def __init__(self, code=0, out="", err=""):
        self.calls, self.code, self.out, self.err = [], code, out, err

    def __call__(self, args):
        self.calls.append(args)
        return self.code, self.out, self.err


# ---- notify_summary ----

def test_first_run_counts_only(tmp_path):
    st = str(tmp_path / "n" / "notify.json")
    b = board(ps("A", "W/A", waiting="確認待ち"), vuln(ps("B", "W/B")), ps("C", "W/C"))
    title, body = S.notify_summary(b, st)
    assert title == "SpecStatus: 新しく 2 件"
    assert body == "今: 待ち 1 / 脆弱な依存 1 / 仕様の変更 0"
    assert "A" not in body
    assert os.path.isfile(st)


def test_nothing_new_returns_none_and_saves(tmp_path):
    st = str(tmp_path / "notify.json")
    b = board(ps("A", "W/A", waiting="実物待ち"))
    assert S.notify_summary(b, st) is not None
    assert S.notify_summary(b, st) is None
    # 減った後に戻ってきたら、また新しい
    assert S.notify_summary(board(ps("A", "W/A")), st) is None
    assert S.notify_summary(b, st)[0] == "SpecStatus: 新しく 1 件"


def test_first_run_empty_is_none(tmp_path):
    assert S.notify_summary(board(ps("A", "W/A")), str(tmp_path / "x.json")) is None


def test_new_items_with_names(tmp_path):
    st = str(tmp_path / "notify.json")
    S.notify_summary(board(ps("A", "W/A", waiting="確認待ち")), st)
    rows = [ps("A", "W/A", waiting="確認待ち"), ps("beta", "W/B", waiting="確認待ち"),
            vuln(ps("Cc", "W/C")), changed(ps("D", "W/D")), changed(vuln(ps("E", "W/E")))]
    title, body = S.notify_summary(board(*rows), st)
    assert title == "SpecStatus: 新しく 4 件"
    lines = body.splitlines()
    assert lines[0] == "増えた物: 待ち 1 / 脆弱な依存 2 / 仕様の変更 2"
    assert lines[1] == "beta、Cc、D ほか 1 件"
    assert lines[2] == "今: 待ち 2 / 脆弱な依存 2 / 仕様の変更 2"
    assert len(lines) <= 4


def test_vuln_zero_count_ignored_and_broken_state(tmp_path):
    st = tmp_path / "notify.json"
    st.write_text("{壊れ", encoding="utf-8")
    assert S.notify_summary(board(vuln(ps("A", "W/A"), 0)), str(st)) is None


# ---- toast ----

def _script(call):
    i = call.index("-EncodedCommand")
    return base64.b64decode(call[i + 1]).decode("utf-16-le")


def test_toast_script_escapes_and_falls_back():
    f = Fake()
    S.toast("SpecStatus: <新しく> 1 件", "A & B's \"x\"", runner=f)
    assert f.calls[0][0] == "powershell"
    s = _script(f.calls[0])
    assert "&lt;新しく&gt;" in s and "<新しく>" not in s
    assert "A &amp; B''s" in s                   # XML の & と PowerShell の ' の両方
    assert 'template="ToastText02"' in s
    assert "CreateToastNotifier('takosasi.SpecStatus')" in s
    assert S.AUMID_POWERSHELL in s
    assert s.index("takosasi.SpecStatus") < s.index("catch") < s.index(S.AUMID_POWERSHELL)


def test_toast_failure_raises():
    try:
        S.toast("t", "b", runner=Fake(1, err="だめ"))
    except OSError as e:
        assert "だめ" in str(e)
    else:
        raise AssertionError("OSError が出ない")


# ---- schtasks ----

VAULT = r"E:\Obsidian 保管\Claude"
PY = r"C:\Program Files\Python311\pythonw.exe"


def test_install_command_lines(tmp_path):
    f = Fake()
    out = S.install(VAULT, PY, None, runner=f, folder=str(tmp_path))
    n, w = f.calls
    script = os.path.join(VAULT, "spec-status", "specstatus.py")
    assert n[:5] == ["schtasks", "/Create", "/TN", "SpecStatus 朝の知らせ", "/TR"]
    assert n[5] == f'"{PY}" "{script}" notify --vault "{VAULT}"'
    assert n[6:] == ["/SC", "DAILY", "/ST", "09:00", "/F"]
    assert w[3] == "SpecStatus 週のまとめ"
    assert w[5] == f'"{PY}" "{script}" weekly --write --vault "{VAULT}"'
    assert w[6:] == ["/SC", "WEEKLY", "/D", "FRI", "/ST", "18:00", "/F"]
    assert out == ["登録しました: SpecStatus 朝の知らせ(毎日 9:00)", "登録しました: SpecStatus 週のまとめ(毎週金曜 18:00)"]
    assert os.listdir(tmp_path) == []
    # subprocess に渡したときの引用符(schtasks は \" で読む)
    import subprocess
    assert '"\\"C:\\Program Files' in subprocess.list2cmdline(n)


def test_install_with_config():
    f = Fake()
    cfg = os.path.abspath("設定 フォルダ/c.toml")
    S.install(VAULT, PY, "設定 フォルダ/c.toml", runner=f)
    assert f.calls[0][5].endswith(f' --config "{cfg}"')


def test_install_long_tr_uses_launcher(tmp_path):
    f = Fake()
    vault = "E:\\" + "長い名前のフォルダ" * 20
    out = S.install(vault, PY, None, runner=f, folder=str(tmp_path))
    n, w = f.calls
    assert n[5] == f'"{tmp_path / "notify.cmd"}"' and w[5] == f'"{tmp_path / "weekly.cmd"}"'
    text = (tmp_path / "notify.cmd").read_bytes().decode("utf-8")
    assert text.startswith("@echo off\r\nchcp 65001 >nul\r\nstart \"\" ")
    assert f'notify --vault "{vault}"' in text
    assert any("起動用のファイル" in ln for ln in out)


def test_install_failure_raises():
    try:
        S.install(VAULT, PY, runner=Fake(1, err="アクセスが拒否されました"))
    except OSError as e:
        assert "拒否" in str(e)
    else:
        raise AssertionError("OSError が出ない")


def test_remove_and_status():
    f = Fake()
    assert S.remove(runner=f) == ["消しました: SpecStatus 朝の知らせ", "消しました: SpecStatus 週のまとめ"]
    assert f.calls[0] == ["schtasks", "/Delete", "/TN", "SpecStatus 朝の知らせ", "/F"]
    q = Fake(out="フォルダー: \\\nタスク名: \\SpecStatus 朝の知らせ\n次回の実行時刻: 2026/10/10 9:00:00\n状態: 準備完了\n")
    assert S.status(runner=q)[0] == "SpecStatus 朝の知らせ: 次回 2026/10/10 9:00:00"
    assert q.calls[0] == ["schtasks", "/Query", "/TN", "SpecStatus 朝の知らせ", "/FO", "LIST"]
    e = Fake(out="TaskName: x\nNext Run Time: 10/10/2026 9:00:00 AM\n")
    assert S.status(runner=e)[1] == "SpecStatus 週のまとめ: 次回 10/10/2026 9:00:00 AM"
    assert S.status(runner=Fake(1)) == ["SpecStatus 朝の知らせ: 未登録", "SpecStatus 週のまとめ: 未登録"]


# ---- CLI の配線 ----

def test_add_commands_parse():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--vault")
    common.add_argument("--config")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    S.add_commands(sub, common)
    a = ap.parse_args(["notify", "--quiet", "--vault", "v"])
    assert (a.cmd, a.quiet, a.vault) == ("notify", True, "v")
    a = ap.parse_args(["schedule", "install", "--python", "p.exe", "--config", "c.toml"])
    assert (a.cmd, a.action, a.python, a.config) == ("schedule", "install", "p.exe", "c.toml")


def test_run_notify_config_error(tmp_path, monkeypatch):
    from specstatus import core
    from specstatus.config import ConfigError

    def boom(vault, cfg):
        raise ConfigError("設定がありません")
    monkeypatch.setattr(core, "load", boom)
    assert S.run(argparse.Namespace(cmd="notify", config=None, quiet=True), str(tmp_path)) == 2

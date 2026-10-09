# 作業の配分(worklog): 開発ログの ### 見出しをプロジェクトごと・週ごとに数える。合成の一時フォルダだけを使う。
from __future__ import annotations

from datetime import date

from specstatus import worklog

from test_guilogic import ps

DAY = date(2026, 10, 9)          # 木曜。今週は 10/5〜


def _logs(tmp_path, files: dict[str, str]):
    d = tmp_path / "開発ログ"
    d.mkdir()
    for name, body in files.items():
        (d / name).write_text(body, encoding="utf-8")
    return str(tmp_path), {"evidence": {"devlog": {"dir": "開発ログ", "scope": [""]}}}


def test_counts_by_week(tmp_path):
    vault, cfg = _logs(tmp_path, {
        "2026-10-09.md": "# 2026-10-09 開発ログ\n### 🕒 [09:00] SpecStatus: 担当5\n### 🕒 [10:00] specstatus の続き\n"
                         "#### SpecStatus の小見出しは数えない\n本文の SpecStatus も数えない\n",
        "2026-10-05.md": "### 🕒 [09:00] KoeLoom と SpecStatus\n### 🕒 [10:00] SpecStatusX は別の語\n",
        "2026-09-14.md": "### 🕒 [09:00] KoeLoom を直した\n",          # 4 週前の月曜(入る)
        "2026-09-13.md": "### 🕒 [09:00] KoeLoom 範囲の外\n",
        "2026-10-10.md": "### 🕒 [09:00] KoeLoom 明日の分\n",
        "メモ.md": "### SpecStatus\n",
    })
    spec, koe, none = ps("SpecStatus", "W/SpecStatus"), ps("KoeLoom", "W/KoeLoom"), ps("Other", "W/Other")
    rows = worklog.counts(vault, cfg, [none, koe, spec], DAY)
    assert rows == [(spec.project.key, [0, 0, 0, 3]), (koe.project.key, [1, 0, 0, 1])]


def test_aliases_and_scope(tmp_path):
    vault, cfg = _logs(tmp_path, {"2026-10-08.md": "### 🕒 [09:00] ボイチェン(仮)を直した\n### 🕒 [10:00] Beta\n"})
    a = ps("KoeLoom", "Windows/KoeLoom")
    a.project.aliases = ["ボイチェン"]
    b = ps("Beta", "Linux/Beta")
    cfg["evidence"]["devlog"]["scope"] = ["Windows"]
    assert worklog.counts(vault, cfg, [a, b], DAY) == [(a.project.key, [0, 0, 0, 1])]


def test_no_dir_and_section(tmp_path):
    assert worklog.counts(str(tmp_path), {"evidence": {"devlog": {"dir": ""}}}, [], DAY) == []
    assert worklog.counts(str(tmp_path), {"evidence": {"devlog": {"dir": "無い"}}}, [], DAY) == []
    vault, cfg = _logs(tmp_path, {"2026-10-06.md": "### 🕒 [09:00] SpecStatus\n"})
    a = ps("SpecStatus", "W/SpecStatus")
    lines = worklog.section(vault, cfg, [a], DAY, lambda p: f"[[{p.project.name}]]")
    assert lines[0] == "## 作業の配分(直近 4 週)"
    assert lines[2] == "| プロジェクト | 9/14〜 | 9/21〜 | 9/28〜 | 10/5〜 | 計 |"
    assert lines[4] == "| [[SpecStatus]] | 0 | 0 | 0 | 1 | 1 |"
    assert "時間ではありません" in lines[-1]
    assert worklog.section(vault, cfg, [ps("Other", "W/Other")], DAY, str) == []

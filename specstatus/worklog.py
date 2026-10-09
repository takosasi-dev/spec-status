# 作業の配分: 開発ログ([evidence.devlog] dir の YYYY-MM-DD.md)の `### ` 見出しを、出てくるプロジェクトごとに週単位で数える。
# 名前の当て方は開発ログの読み手(evidence/devlog.py)と同じ(名前か別名が単語として出たら当たり)。数えるのは件数で、時間ではない。
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Callable

from .evidence.devlog import _FILE, _pattern
from .history import week_range
from .model import ProjectStatus
from .textutil import in_scope, nfc, read_text, resolve

LIMIT = 10
NOTE = "数えているのは開発ログの見出し(### の行)の件数で、かかった時間ではありません。1つの見出しに2本出ていれば両方に数えます。"


def _first_monday(today: date, weeks: int) -> date:
    return week_range(today)[0] - timedelta(days=7 * (weeks - 1))


def counts(vault: str, cfg: dict, statuses: list[ProjectStatus], today: date,
           weeks: int = 4) -> list[tuple[str, list[int]]]:
    """[(project.key, [週ごとの件数(古い週から。最後は今日を含む週)])]。件数の多い順。1件も無い物は出さない。
    開発ログの設定が空・フォルダが無ければ []。"""
    sec = cfg.get("evidence", {}).get("devlog", {})
    base = resolve(vault, sec["dir"]) if sec.get("dir") else ""
    if not base or not os.path.isdir(base):
        return []
    first = _first_monday(today, weeks)
    pats = {ps.project.key: pat for ps in statuses if in_scope(ps.project.spec_dir, sec.get("scope", [""]))
            and (pat := _pattern([ps.project.name, *ps.project.aliases]))}
    table = {k: [0] * weeks for k in pats}
    for name in os.listdir(base):
        if not _FILE.fullmatch(name):
            continue
        try:
            day = date.fromisoformat(name[:10])
        except ValueError:
            continue
        if not first <= day <= today:
            continue
        try:
            heads = [nfc(ln) for ln in read_text(os.path.join(base, name)).splitlines() if ln.startswith("### ")]
        except (OSError, UnicodeDecodeError):
            continue                 # 読めない日は数えない(読めない理由は開発ログの読み手が出す)
        week = (day - first).days // 7
        for key, pat in pats.items():
            table[key][week] += sum(1 for h in heads if pat.search(h))
    names = {ps.project.key: ps.project.name for ps in statuses}
    rows = [(k, v) for k, v in table.items() if sum(v)]
    rows.sort(key=lambda kv: (-sum(kv[1]), names[kv[0]].casefold()))
    return rows


def section(vault: str, cfg: dict, statuses: list[ProjectStatus], today: date,
            link: Callable[[ProjectStatus], str], weeks: int = 4, limit: int = LIMIT) -> list[str]:
    """週のまとめと一覧ノートの「## 作業の配分(直近 n 週)」の表(上位 limit 本)。何も無ければ []。"""
    rows = counts(vault, cfg, statuses, today, weeks)[:limit]
    if not rows:
        return []
    by_key = {ps.project.key: ps for ps in statuses}
    first = _first_monday(today, weeks)
    cols = [f"{d.month}/{d.day}〜" for d in (first + timedelta(days=7 * i) for i in range(weeks))]
    out = [f"## 作業の配分(直近 {weeks} 週)", "",
           "| プロジェクト | " + " | ".join(cols) + " | 計 |", "|---|" + "---:|" * (weeks + 1)]
    out += [f"| {link(by_key[k])} | " + " | ".join(map(str, v)) + f" | {sum(v)} |" for k, v in rows]
    return out + ["", NOTE]

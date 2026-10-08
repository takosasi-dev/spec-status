# 開発ログの日付(FR-13): dir 直下の YYYY-MM-DD.md の `###` 見出しに、プロジェクト名か別名が
# 単語として(前後が半角英数字でない・大小区別なし)出た最新の日付を返す。状態は決めない。
from __future__ import annotations

import os
import re

from ..model import Evidence, Project, ReadResult, Unreadable
from ..textutil import nfc, read_text, resolve, slash

NAME = "devlog"
_FILE = re.compile(r"\d{4}-\d{2}-\d{2}\.md")


def configured(vault: str, sec: dict) -> bool:
    return bool(sec.get("dir"))


def _pattern(words: list[str]) -> re.Pattern | None:
    alts = [re.escape(nfc(w)) for w in words if w]
    if not alts:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(alts) + r")(?![A-Za-z0-9])", re.IGNORECASE)


def read(vault: str, sec: dict, projects: list[Project]) -> ReadResult:
    base = resolve(vault, sec["dir"])
    if not os.path.isdir(base):
        raise FileNotFoundError(f"フォルダがありません: {slash(base)}")
    files = sorted((e for e in os.scandir(base) if e.is_file() and _FILE.fullmatch(e.name)),
                   key=lambda e: e.name, reverse=True)
    todo = {p.key: pat for p in projects if (pat := _pattern([p.name, *p.aliases]))}
    res = ReadResult()
    for e in files:                                  # 新しい日付から。全員見つかれば止める
        if not todo:
            break
        where = slash(e.path)
        try:
            heads = [(i, nfc(ln)) for i, ln in enumerate(read_text(e.path).splitlines(), 1)
                     if ln.startswith("###")]
        except (OSError, UnicodeDecodeError) as err:
            res.unreadable.append(Unreadable(NAME, f"読めません: {err}", where))
            continue
        for key, pat in list(todo.items()):
            hit = next((i for i, h in heads if pat.search(h)), None)
            if hit:
                res.found[key] = [Evidence(NAME, None, e.name[:10], f"{where}#L{hit}")]
                del todo[key]
    return res

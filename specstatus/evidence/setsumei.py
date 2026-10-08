# 説明書の証拠(FR-9): dir 直下の md の frontmatter `状態:` を map で6状態に写す。
# ファイル名(拡張子なし)をプロジェクト名と fold で比べる。読むだけ。本文は写さない(INV-7)。
from __future__ import annotations

import os

from ..model import Evidence, Project, ReadResult, Unreadable
from ..textutil import fold, read_text, resolve, slash, split_frontmatter

NAME = "setsumei"


def configured(vault: str, sec: dict) -> bool:
    return bool(sec.get("dir"))


def read(vault: str, sec: dict, projects: list[Project]) -> ReadResult:
    base = resolve(vault, sec["dir"])
    if not os.path.isdir(base):
        raise FileNotFoundError(f"フォルダがありません: {slash(base)}")
    by_name: dict[str, list[Project]] = {}
    for p in projects:
        by_name.setdefault(fold(p.name), []).append(p)
    mapping = sec.get("map", {})
    res = ReadResult()
    for entry in sorted(os.scandir(base), key=lambda e: e.name):
        stem, ext = os.path.splitext(entry.name)
        if not entry.is_file() or fold(ext) != ".md" or fold(stem) not in by_name:
            continue
        where = slash(entry.path)
        try:
            fm, _ = split_frontmatter(read_text(entry.path))
        except (OSError, UnicodeDecodeError) as e:
            res.unreadable.append(Unreadable(NAME, f"読めません: {e}", where))
            continue
        if fm is None:
            res.unreadable.append(Unreadable(NAME, "frontmatter が閉じていません", where))
            continue
        value = fm.get("状態")
        if not value:
            continue
        ev = (Evidence(NAME, mapping[value], value, where) if value in mapping
              else Evidence(NAME, None, value, where, note="写し方の無い値"))
        for p in by_name[fold(stem)]:
            res.found.setdefault(p.key, []).append(ev)
    return res

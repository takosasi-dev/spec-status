# 引き継ぎメモの証拠(FR-12): HandoffStub の [map] で仕様書フォルダからメモ名を引き、
# メモがあれば「着手済」、行頭 `状態:` の値がちょうど `未着手` の行があれば「未着手」。本文は写さない。
from __future__ import annotations

import os
import tomllib

from ..model import Evidence, Project, ReadResult, Unreadable
from ..textutil import fold, read_text, resolve, slash

NAME = "handoff"
_PREFIX = "状態:"


def configured(vault: str, sec: dict) -> bool:
    return bool(sec.get("handoffstub_toml")) and bool(sec.get("memo_dir"))


def _key(s: str) -> str:
    return fold(slash(s).strip("/"))


def read(vault: str, sec: dict, projects: list[Project]) -> ReadResult:
    with open(resolve(vault, sec["handoffstub_toml"]), "rb") as f:
        table = {_key(k): v for k, v in tomllib.load(f).get("map", {}).items() if isinstance(v, str)}
    memo_dir = resolve(vault, sec["memo_dir"])
    if not os.path.isdir(memo_dir):
        raise FileNotFoundError(f"フォルダがありません: {slash(memo_dir)}")
    res = ReadResult()
    for p in projects:
        rel = _key(p.spec_dir)
        memo = table.get(rel)                       # 相対パスのキーが優先
        if memo is None:
            memo = table.get(rel.rsplit("/", 1)[-1])
        if not memo:                                # 未登録・"" は対象外
            continue
        path = os.path.join(memo_dir, memo + ".md")
        if not os.path.isfile(path):
            continue
        where = slash(path)
        try:
            lines = read_text(path).splitlines()
        except (OSError, UnicodeDecodeError) as e:
            res.unreadable.append(Unreadable(NAME, f"読めません: {e}", where))
            continue
        hit = next((i for i, ln in enumerate(lines, 1)
                    if ln.startswith(_PREFIX) and ln[len(_PREFIX):].strip() == "未着手"), None)
        ev = (Evidence(NAME, "未着手", "未着手", f"{where}#L{hit}") if hit
              else Evidence(NAME, "着手済", where, where))
        res.found.setdefault(p.key, []).append(ev)
    return res

# ToolDeck の証拠(FR-10): tools.toml の [[tool]] の id をプロジェクト名と fold で比べ、
# state を map で6状態に写す(map に無い値は「写し方の無い値」)。読むだけ。
from __future__ import annotations

import tomllib

from ..model import Evidence, Project, ReadResult
from ..textutil import fold, resolve, slash

NAME = "tooldeck"


def configured(vault: str, sec: dict) -> bool:
    return bool(sec.get("toml"))


def read(vault: str, sec: dict, projects: list[Project]) -> ReadResult:
    path = resolve(vault, sec["toml"])
    with open(path, "rb") as f:          # 無い・壊れているは例外のまま(呼び手が Unreadable にする)
        data = tomllib.load(f)
    by_name: dict[str, list[Project]] = {}
    for p in projects:
        by_name.setdefault(fold(p.name), []).append(p)
    mapping = sec.get("map", {})
    where = slash(path)
    res = ReadResult()
    for tool in data.get("tool", []):
        tid, value = tool.get("id"), tool.get("state")
        if not isinstance(tid, str) or not isinstance(value, str) or not value:
            continue
        ev = (Evidence(NAME, mapping[value], value, where) if value in mapping
              else Evidence(NAME, None, value, where, note="写し方の無い値"))
        for p in by_name.get(fold(tid), []):
            res.found.setdefault(p.key, []).append(ev)
    return res

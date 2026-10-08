# 実装フォルダの証拠(FR-11): roots の直下にプロジェクト名と fold で一致するフォルダがあり、
# markers のどれかがその中にあれば(空なら有無だけ)「着手済」。名前の似具合では結ばない。
from __future__ import annotations

import os

from ..model import Evidence, Project, ReadResult
from ..textutil import fold, resolve, slash

NAME = "implroot"


def configured(vault: str, sec: dict) -> bool:
    return bool(sec.get("roots"))


def read(vault: str, sec: dict, projects: list[Project]) -> ReadResult:
    roots = [resolve(vault, r) for r in sec["roots"]]
    for r in roots:
        if not os.path.isdir(r):
            raise FileNotFoundError(f"フォルダがありません: {slash(r)}")
    markers = sec.get("markers", [])
    res = ReadResult()
    for r in roots:
        dirs = {fold(e.name): e.path for e in os.scandir(r) if e.is_dir()}
        for p in projects:
            d = dirs.get(fold(p.name))
            if d is None or (markers and not any(os.path.exists(os.path.join(d, m)) for m in markers)):
                continue
            path = slash(os.path.abspath(d))
            res.found.setdefault(p.key, []).append(Evidence(NAME, "着手済", path, path))
    return res

# 文書をプロジェクトにまとめる(FR-4)。同じフォルダ × 同じ製品名で1つ、registry の [[merge]] で統合、[[alias]] を付ける。
# 付属の文書は同じフォルダのプロジェクト(名前順の先頭)に入れる。読むだけ。
from __future__ import annotations

from .model import SUPPORT_KIND, Doc, Project
from .textutil import fold, nfc, slash


def group_docs(docs: list[Doc], registry: dict) -> tuple[list[Project], list[str]]:
    """戻り値: (プロジェクト, registry の不整合)。"""
    buckets: dict[tuple[str, str], list[Doc]] = {}
    for d in docs:
        if d.kind != SUPPORT_KIND:
            buckets.setdefault((d.spec_dir, fold(d.product)), []).append(d)

    issues: list[str] = []
    merged: dict[tuple[str, str], str] = {}        # バケツ -> merge 名
    merge_dirs: dict[str, list[str]] = {}
    for m in registry.get("merge", []):
        name = nfc(m["name"])
        dirs = [nfc(slash(s)).strip("/") for s in m.get("spec_dirs", [])]
        merge_dirs[name] = dirs
        for sd in dirs:
            hit = [b for b in buckets if b[0] == sd]
            if not hit:
                issues.append(f"[[merge]] {name} の spec_dirs が見つかりません: {sd}")
            for b in hit:
                merged[b] = name

    projects: dict[str, Project] = {}
    for b, ds in buckets.items():
        if b in merged:
            name = merged[b]
            sd = next(s for s in merge_dirs[name] if any(k[0] == s for k in buckets))
        else:
            name, sd = ds[0].product, b[0]
        key = f"{sd}#{name}"
        p = projects.setdefault(key, Project(key=key, name=name, spec_dir=sd, docs=[]))
        p.docs.extend(ds)

    by_dir: dict[str, list[Project]] = {}
    for p in sorted(projects.values(), key=lambda p: fold(p.name)):
        for d in p.docs:
            by_dir.setdefault(d.spec_dir, [])
            if p not in by_dir[d.spec_dir]:
                by_dir[d.spec_dir].append(p)
    for d in docs:
        if d.kind == SUPPORT_KIND and d.spec_dir in by_dir:
            by_dir[d.spec_dir][0].docs.append(d)

    aliases = {fold(a["name"]): list(a.get("words", [])) for a in registry.get("alias", [])}
    for p in projects.values():
        p.docs.sort(key=lambda d: fold(d.path))
        p.aliases = aliases.get(fold(p.name), [])
    return list(projects.values()), issues

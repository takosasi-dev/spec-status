# 仕様書どうしの依存: 「前提」の節のリンクと、「依存」「前提」と書き添えたリンクが指す別の仕様書のうち、
# 終わっていない物を ps.blocked_by に付ける。参考で張っただけのリンク(「関連:」の行の素のリンク)は見ない。
# 一覧ノートに入れる mermaid の図も作る。読むだけ。
from __future__ import annotations

import re
from typing import Callable

from .model import ProjectStatus
from .specinfo import doc_lines, section
from .textutil import fold, read_text

LINK_RE = re.compile(r"\[\[([^\]|#]+)[^\]]*\]\]")
DEP_WORD_RE = re.compile(r"(?<!非)依存(?!し?な|させ|せず)|前提")    # リンクの後ろの添え書き
DONE_STATES = ("実装完了", "導入済み")
MERMAID_MAX = 30          # 図に入れる矢印の数


def _stem(target: str) -> str:
    t = target.strip().replace("\\", "/").rsplit("/", 1)[-1]
    return t[:-3] if t.lower().endswith(".md") else t


def dep_links(lines: list[str]) -> list[str]:
    """依存を指すリンクの stem(出た順・重複なし)。前提の節は全部、ほかは添え書きに依存・前提がある物だけ。"""
    out = [m.group(1) for ln in section(lines, lambda h: "前提" in h) for m in LINK_RE.finditer(ln)]
    for ln in lines:
        ms = list(LINK_RE.finditer(ln))
        for m, nxt in zip(ms, ms[1:] + [None]):
            if DEP_WORD_RE.search(ln[m.end():nxt.start() if nxt else len(ln)]):
                out.append(m.group(1))
    return list(dict.fromkeys(_stem(t) for t in out))


def mark(statuses: list[ProjectStatus], read: Callable[[str], str] = read_text) -> None:
    """前提の仕様書のうち終わっていない物の名前を ps.blocked_by に。直接の依存だけを見るので循環しても止まる。"""
    by_stem: dict[str, list[ProjectStatus]] = {}
    for ps in statuses:
        for d in ps.project.spec_docs:
            by_stem.setdefault(fold(d.stem), []).append(ps)
    for ps in statuses:
        names: list[str] = []
        for lines in doc_lines(ps, read):
            for stem in dep_links(lines):
                for other in by_stem.get(fold(stem), []):
                    if other is not ps and other.state not in DONE_STATES and other.project.name not in names:
                        names.append(other.project.name)
        ps.blocked_by = names


def mermaid(statuses: list[ProjectStatus]) -> list[str]:
    """前提が未完の物だけの graph LR(前提 --> 使う側)。無ければ []。多ければ前提の多い順に MERMAID_MAX 本。"""
    rows = sorted((ps for ps in statuses if ps.blocked_by), key=lambda p: (-len(p.blocked_by), fold(p.project.name)))
    edges = [(dep, ps.project.name) for ps in rows for dep in ps.blocked_by][:MERMAID_MAX]
    if not edges:
        return []
    ids: dict[str, str] = {}

    def node(name: str) -> str:
        if name not in ids:
            ids[name] = f"n{len(ids)}"
            return f'{ids[name]}["{name.replace(chr(34), "#quot;")}"]'
        return ids[name]

    return ["```mermaid", "graph LR"] + [f"  {node(a)} --> {node(b)}" for a, b in edges] + ["```"]

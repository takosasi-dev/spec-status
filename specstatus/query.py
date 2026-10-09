# 検索欄の書き方(state:・待ち:・cat:・is:・has:・-語・"語 語")を読み、ProjectStatus が当てはまるかを決める。
# 素の語は名前・仕様書フォルダ・メモ・実装フォルダ・(渡されれば)仕様書の本文のどこかに全部あれば当たり。tkinter を使わない。
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .model import ProjectStatus
from .textutil import fold

# 書き方の頭(英語と日本語) → 種類
PREFIXES = {
    "state": "state", "状態": "state",
    "waiting": "waiting", "待ち": "waiting",
    "cat": "cat", "分類": "cat",
    "is": "is",
    "has": "has",
}
IS_VALUES = {
    "vuln": "vuln", "脆弱": "vuln",
    "stale": "stale", "止まり": "stale",
    "changed": "changed", "変更": "changed",
    "conflict": "conflict", "食い違い": "conflict",
}
HAS_VALUES = {"github": "github", "note": "note", "メモ": "note"}

_TOKEN = re.compile(r'(-?)(?:([^\s:"]+):)?(?:"([^"]*)"?|(\S+))')


def norm(s: str) -> str:
    """比べる形: 全角半角をそろえ(NFKC)、textutil.fold(NFC + casefold)。"""
    return fold(unicodedata.normalize("NFKC", s))


@dataclass
class Term:
    kind: str        # "word"・"state"・"waiting"・"cat"・"is"・"has"
    value: str       # norm 済み(is・has は IS_VALUES・HAS_VALUES の英語の値)
    negate: bool = False


@dataclass
class Query:
    terms: list[Term] = field(default_factory=list)

    @property
    def needs_body(self) -> bool:
        """素の語がある(本文を読む意味がある)か。"""
        return any(t.kind == "word" for t in self.terms)


def parse(text: str) -> Query:
    """検索欄の文字列を Query にする。知らない頭(例 foo:bar)と知らない is:/has: の値は、そのまま素の語として扱う。"""
    terms = []
    for m in _TOKEN.finditer(norm(text)):
        neg, prefix, quoted, bare = m.group(1) == "-", m.group(2), m.group(3), m.group(4)
        value = quoted if quoted is not None else bare
        kind = PREFIXES.get(prefix or "")
        if kind == "is":
            kind, value = ("is", IS_VALUES[value]) if value in IS_VALUES else (None, value)
        elif kind == "has":
            kind, value = ("has", HAS_VALUES[value]) if value in HAS_VALUES else (None, value)
        if kind is None:
            kind, value = "word", (f"{prefix}:{value}" if prefix else value)
        value = value.strip()
        if value:
            terms.append(Term(kind, value, neg))
    return Query(terms)


def _is(ps: ProjectStatus, v: str) -> bool:
    if v == "vuln":
        return bool(ps.vulns and ps.vulns.get("count"))
    if v == "stale":
        return bool(ps.stale_days)
    if v == "changed":
        return bool(ps.spec_changed)
    return ps.conflict


def _haystack(ps: ProjectStatus, body: str | None) -> list[str]:
    parts = [ps.project.name, ps.project.spec_dir, ps.folded.note or ""]
    parts += [i.path for i in ps.folded.impl]
    if body:
        parts.append(body)
    return [norm(p) for p in parts]


def _hit(ps: ProjectStatus, t: Term, hay: list[str]) -> bool:
    if t.kind == "state":
        return t.value in norm(ps.state)
    if t.kind == "waiting":
        return t.value in norm(ps.waiting)
    if t.kind == "cat":
        d = norm(ps.project.spec_dir)                # 先頭からの何段か、またはどれかの段の名前
        return d == t.value or d.startswith(t.value + "/") or t.value in d.split("/")
    if t.kind == "is":
        return _is(ps, t.value)
    if t.kind == "has":
        return bool(ps.github) if t.value == "github" else bool(ps.folded.note)
    return any(t.value in h for h in hay)


def match(ps: ProjectStatus, q: Query, body: str | None = None) -> bool:
    """全部の条件(AND)に当てはまれば True。頭に '-' の付いた条件は当てはまらないこと。空の Query は全部当たり。"""
    hay = _haystack(ps, body) if q.needs_body else []
    return all(_hit(ps, t, hay) != t.negate for t in q.terms)

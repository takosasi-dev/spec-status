# query(検索の書き方)のテスト: 頭(英語・日本語)・否定・引用・全角半角・知らない頭・本文。
from __future__ import annotations

from test_guilogic import ps

from specstatus import query as Q
from specstatus.model import ImplPath

A = ps("Alpha Tool", "Windows/ツール/Alpha", "実装完了")
A.folded.note = "ＵＩを直す"
A.github = {"repo": "o/alpha", "url": "https://github.com/o/alpha", "release": "v1.0"}
A.folded.impl = [ImplPath(path="L:/work/alpha-src", pc="pc", exists_here=True)]
B = ps("beta", "Linux/beta", "着手済", waiting="確認待ち", conflict=True)
B.vulns = {"count": 2, "total": 9, "packages": []}
B.stale_days = 20
C = ps("Gamma", "Windows/ゲーム/Gamma", "一部未実装")
C.spec_changed = "2026-10-01"
ALL = [A, B, C]


def hits(text, body=None):
    q = Q.parse(text)
    return [p.project.name for p in ALL if Q.match(p, q, body(p) if body else None)]


def test_empty_matches_all():
    assert hits("") == hits("   ") == ["Alpha Tool", "beta", "Gamma"]


def test_plain_words_and_fields():
    assert hits("alpha") == ["Alpha Tool"]
    assert hits("ゲーム") == ["Gamma"]                 # 仕様書フォルダ
    assert hits("ui") == ["Alpha Tool"]               # メモ(全角を半角にそろえる)
    assert hits("alpha-src") == ["Alpha Tool"]        # 実装フォルダ
    assert hits("alpha linux") == []                  # 全部の語(AND)
    assert hits("-alpha") == ["beta", "Gamma"]


def test_quoted_phrase():
    assert hits('"alpha tool"') == ["Alpha Tool"]
    assert hits('"tool alpha"') == []
    assert hits('-"alpha tool"') == ["beta", "Gamma"]


def test_state_waiting_cat_prefixes():
    assert hits("state:着手済") == hits("状態:着手済") == ["beta"]
    assert hits("state:未") == ["Gamma"]               # 部分一致(未着手・一部未実装)
    assert hits("waiting:確認待ち") == hits("待ち：確認待ち") == ["beta"]   # 全角のコロンも
    assert hits("cat:windows") == hits("分類:Windows") == ["Alpha Tool", "Gamma"]
    assert hits("cat:windows/ゲーム") == ["Gamma"]
    assert hits("cat:win") == []
    assert hits("-cat:windows") == ["beta"]


def test_is_and_has():
    assert hits("is:vuln") == hits("is:脆弱") == ["beta"]
    assert hits("is:stale") == hits("is:止まり") == ["beta"]
    assert hits("is:changed") == hits("is:変更") == ["Gamma"]
    assert hits("is:conflict") == hits("is:食い違い") == ["beta"]
    assert hits("IS:VULN") == ["beta"]
    assert hits("has:github") == ["Alpha Tool"]
    assert hits("has:note") == hits("has:メモ") == ["Alpha Tool"]
    assert hits("-has:github is:changed") == ["Gamma"]


def test_unknown_prefix_is_plain_word():
    q = Q.parse("foo:bar is:nope")
    assert [(t.kind, t.value) for t in q.terms] == [("word", "foo:bar"), ("word", "is:nope")]
    D = ps("foo:bar", "OS非依存/x")
    assert Q.match(D, Q.parse("foo:bar"))


def test_body_only_when_given():
    body = lambda p: "本文に ＫＥＹＷＯＲＤ がある" if p is C else ""   # noqa: E731
    assert hits("keyword") == []
    assert hits("keyword", body) == ["Gamma"]
    assert Q.parse("keyword").needs_body and not Q.parse("is:vuln").needs_body

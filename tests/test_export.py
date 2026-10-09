# export のテスト: CSV の見出し・行・改行・引用(to_csv)と、撮った画素の切り出し(crop_bgra)。窓は出さない。
from __future__ import annotations

import csv
import io

from test_guilogic import ps, rec

from specstatus import export
from specstatus import strings as S
from specstatus.guilogic import row_values


def test_to_csv_header_rows_and_crlf():
    a = ps("Alpha", "Windows/Alpha", "着手済", done=1, last=3, history=[rec("2026-10-01T10:00:00+09:00")])
    a.folded.note = 'メモ, "引用" と\n改行'
    a.vulns = {"count": 2, "total": 5, "packages": ["x@1(GHSA-1)", "y@2(GHSA-2)"]}
    b = ps("beta", "Linux/beta")
    text = export.to_csv([a, b])
    assert text.endswith("\r\n") and text.count("\r\n") == 3       # 見出し+2行(メモの中の \n は引用の中)
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert rows[0] == [t for _, t in S.COLUMNS] + ["メモ", "AC", "脆弱な依存"]
    assert rows[1][:len(S.COLUMNS)] == list(row_values(a))
    assert rows[1][-3:] == ['メモ, "引用" と\n改行', "", "2 件: x@1(GHSA-1) / y@2(GHSA-2)"]
    assert rows[2][-3:] == ["", "", ""]


def test_to_csv_empty():
    assert export.to_csv([]).count("\r\n") == 1


def test_crop_bgra_to_rgba():
    # 3x2 の BGRA。画素 (x, y) の値は B=x, G=y, R=9, A=0
    buf = bytes(v for y in range(2) for x in range(3) for v in (x, y, 9, 0))
    out = export.crop_bgra(buf, 3, 1, 1, 2, 1)
    assert out == bytes([9, 1, 1, 255, 9, 1, 2, 255])

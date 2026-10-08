# 記録(records.py)の検査・読み取り・畳み込み・追記のテスト。
# AC-13・AC-17・AC-19・AC-22 と §9.8 の各制約。合成の一時フォルダだけを使う。
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from specstatus import records as R
from specstatus.model import Record

ROOT = Path(__file__).resolve().parent.parent


def rec(**kw) -> dict:
    d = {"v": 1, "at": "2026-10-08T23:39:10+09:00", "pc": "pc", "by": "claude-code",
         "doc": "X_仕様書", "path": "仕様書MDファイル/X/X_仕様書.md"}
    d.update(kw)
    return d


def line(**kw) -> str:
    return R.dumps(rec(**kw))


# ---------- validate ----------

def test_validate_ok_and_unknown_key():
    assert R.validate(rec()) is None
    assert R.validate(rec(state="着手済", done_phase=2, last_phase=5, waiting="確認待ち",
                          note="Phase 2 完了。§8.5 待ち", impl_add=["L:/a"], impl_remove=[],
                          confirmed=True, undo=True, extra={"x": 1})) is None
    assert R.validate(rec(state=None, done_phase=None, last_phase=None, note=None)) is None
    assert R.validate(rec(done_phase=0, last_phase=99, note="あ" * 200)) is None
    assert R.validate(rec(at="2026-10-08T14:39:10Z")) is None


@pytest.mark.parametrize("bad", [
    [],
    "x",
    {k: v for k, v in rec().items() if k != "doc"},
    {k: v for k, v in rec().items() if k != "path"},
    rec(v=2), rec(v=True), rec(v="1"),
    rec(at="2026-10-08T23:39:10"),          # 時差なし
    rec(at="2026-10-08T23:39+09:00"),       # 秒なし
    rec(at="2026-10-08"), rec(at="2026-13-40T00:00:00+09:00"), rec(at=1),
    rec(pc=""), rec(pc=None), rec(doc=""), rec(doc=3),
    rec(path=None),
    rec(by="me"),
    rec(state="証拠なし"), rec(state="done"),
    rec(waiting="保留"), rec(waiting=None),
    rec(done_phase=True), rec(done_phase=-1), rec(done_phase=100), rec(last_phase=1.0),
    rec(last_phase="3"),
    rec(note=""), rec(note="あ" * 201), rec(note="a\nb"), rec(note="a\tb"), rec(note="a\x07b"),
    rec(note=1),
    rec(impl_add="L:/a"), rec(impl_add=[1]), rec(impl_remove=None),
    rec(confirmed=False), rec(undo=1),
])
def test_validate_rejects(bad):
    assert isinstance(R.validate(bad), str)


# ---------- read_all ----------

def write(p: Path, text: str) -> None:
    p.write_bytes(text.encode("utf-8"))


def test_read_all_missing_dir(tmp_path):
    assert R.read_all(str(tmp_path / "none")) == ([], [])


def test_read_all_problems_and_continue(tmp_path):
    long_line = line(note="a" * 200, impl_add=["L:/" + "b" * 4000])
    assert len(long_line.encode()) > 4096
    write(tmp_path / "pc.jsonl", "\n".join([
        line(note="一"),
        "{not json",
        line(state="証拠なし"),
        long_line,
        "",
        line(note="二"),
    ]) + "\n")
    write(tmp_path / "ignored.txt", "x\n")
    recs, probs = R.read_all(str(tmp_path))
    assert [r.fields["note"] for r in recs] == ["一", "二"]
    assert [(r.file, r.line) for r in recs] == [("pc.jsonl", 1), ("pc.jsonl", 6)]
    assert [(p.file, p.line) for p in probs] == [("pc.jsonl", 2), ("pc.jsonl", 3), ("pc.jsonl", 4)]
    assert all(p.reason for p in probs)
    assert recs[0].raw == line(note="一")


def test_read_all_sorts_by_time_then_pc(tmp_path):
    # 10:00+09:00 は 01:00Z。文字列で比べると逆になる
    write(tmp_path / "a.jsonl", line(at="2026-10-08T02:00:00+00:00", pc="a", note="後") + "\n")
    write(tmp_path / "b.jsonl", line(at="2026-10-08T10:00:00+09:00", pc="b", note="先") + "\n"
          + line(at="2026-10-08T10:00:00+09:00", pc="a", note="同時a") + "\n")
    recs, probs = R.read_all(str(tmp_path))
    assert probs == []
    assert [r.fields["note"] for r in recs] == ["同時a", "先", "後"]


def test_ac22_same_line_in_two_files_counted_once(tmp_path):
    same = line(note="同じ")
    write(tmp_path / "pc.jsonl", same + "\n" + line(note="pc だけ") + "\n")
    write(tmp_path / "pc (1).jsonl", same + "\n")
    recs, probs = R.read_all(str(tmp_path))
    assert probs == []
    assert [r.fields["note"] for r in recs].count("同じ") == 1
    assert len(R.fold(recs).history) == 2


# ---------- fold ----------

def mk(i: int, **kw) -> Record:
    d = rec(at=f"2026-10-08T10:00:{i:02d}+09:00", **kw)
    return Record(fields=d, file="pc.jsonl", line=i, raw=R.dumps(d))


def test_fold_empty():
    f = R.fold([])
    assert f.state is None and f.impl == [] and f.history == [] and f.state_record is None


def test_fold_overwrite_and_null(tmp_path):
    here = tmp_path / "Impl"
    here.mkdir()
    rs = [
        mk(1, state="着手済", done_phase=1, last_phase=5, waiting="確認待ち", note="a",
           impl_add=[str(here).replace("/", "\\"), "Z:/nowhere"]),
        mk(2, done_phase=2, note="b", pc="other", impl_add=["z:/NOWHERE/"]),
        mk(3, note=None, last_phase=None),
    ]
    f = R.fold(rs)
    assert (f.state, f.done_phase, f.last_phase, f.waiting, f.note) == ("着手済", 2, None, "確認待ち", None)
    assert f.state_record is rs[0]
    assert f.history == rs and f.last_record is rs[2]
    assert [(i.path, i.pc, i.exists_here) for i in f.impl] == [
        (str(here).replace("\\", "/"), "pc", True), ("Z:/nowhere", "pc", False)]

    rs.append(mk(4, state=None, waiting="なし", impl_remove=[str(here).upper() + "\\", "Z:\\Nowhere"]))
    f = R.fold(rs)
    assert f.state is None and f.state_record is None and f.waiting == "なし"
    assert f.impl == []

    rs.append(mk(5, state="実装完了"))
    rs.append(mk(6, note="c"))
    f = R.fold(rs)
    assert f.state == "実装完了" and f.state_record is rs[4]


# ---------- dumps / now_iso ----------

def test_dumps_and_now_iso():
    assert R.dumps({"a": "日本", "b": [1, 2]}) == '{"a":"日本","b":[1,2]}'
    at = R.now_iso()
    assert R.validate(rec(at=at)) is None


# ---------- append ----------

def test_ac13_append_keeps_prefix_and_adds_one_line(tmp_path):
    ev = tmp_path / "data" / "events"
    assert R.append(str(ev), "pc", line(note="一")) == 0     # フォルダが無ければ作る
    before = (ev / "pc.jsonl").read_bytes()
    assert R.append(str(ev), "pc", line(note="二")) == 0
    after = (ev / "pc.jsonl").read_bytes()
    assert after.startswith(before)
    assert after[len(before):] == (line(note="二") + "\n").encode("utf-8")
    assert not (ev / ".pc.lock").exists()


def test_ac19_unfinished_tail(tmp_path):
    good = [line(note="一"), line(note="二")]
    write(tmp_path / "pc.jsonl", "\n".join(good) + '\n{"v":1,"at":"2026')
    recs, probs = R.read_all(str(tmp_path))
    assert [r.fields["note"] for r in recs] == ["一", "二"]
    assert [(p.line, "末尾が未完" in p.reason) for p in probs] == [(3, True)]

    assert R.append(str(tmp_path), "pc", line(note="三")) == 0
    recs, probs = R.read_all(str(tmp_path))
    assert [r.fields["note"] for r in recs] == ["一", "二", "三"]
    assert [r.line for r in recs] == [1, 2, 4]
    assert [p.line for p in probs] == [3]       # 切れた行は「JSON でない」になる


def test_append_stale_lock_is_removed(tmp_path):
    lock = tmp_path / ".pc.lock"
    lock.write_bytes(b"")
    old = time.time() - 120
    os.utime(lock, (old, old))
    t = time.monotonic()
    assert R.append(str(tmp_path), "pc", line()) == 0
    assert time.monotonic() - t < 1.0
    assert not lock.exists()
    assert len((tmp_path / "pc.jsonl").read_bytes().splitlines()) == 1


def test_append_fresh_lock_gives_6(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "LOCK_TIMEOUT", 0.3)
    lock = tmp_path / ".pc.lock"
    lock.write_bytes(b"")
    assert R.append(str(tmp_path), "pc", line()) == 6
    assert lock.exists()                       # 他人のロックは消さない
    assert not (tmp_path / "pc.jsonl").exists()


CHILD = """
import sys
from specstatus import records as R
ev, tag = sys.argv[1], sys.argv[2]
for i in range(50):
    d = {"v": 1, "at": R.now_iso(), "pc": "pc", "by": "user", "doc": "X", "path": "X.md",
         "note": f"{tag}-{i}-" + "x" * 150}
    if R.append(ev, "pc", R.dumps(d)) != 0:
        sys.exit(6)
"""


def test_ac17_two_processes_50_each(tmp_path):
    lock = tmp_path / ".pc.lock"
    lock.write_bytes(b"")
    old = time.time() - 120
    os.utime(lock, (old, old))                 # 2分前のロックが残っていても書ける
    env = dict(os.environ, PYTHONUTF8="1")
    ps = [subprocess.Popen([sys.executable, "-c", CHILD, str(tmp_path), tag], cwd=ROOT, env=env)
          for tag in ("A", "B")]
    assert [p.wait(timeout=120) for p in ps] == [0, 0]
    raw = (tmp_path / "pc.jsonl").read_bytes()
    assert raw.endswith(b"\n")
    rows = raw.decode("utf-8").splitlines()
    assert len(rows) == 100
    notes = {json.loads(r)["note"].rsplit("-", 1)[0] for r in rows}
    assert notes == {f"{t}-{i}" for t in "AB" for i in range(50)}
    recs, probs = R.read_all(str(tmp_path))
    assert probs == [] and len(recs) == 100
    assert not lock.exists()

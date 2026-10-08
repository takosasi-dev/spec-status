# 記録ファイル data/events/*.jsonl の検査・読み取り・畳み込み・追記(§9.8・FR-16〜FR-22)。
# 書き込みはロックを取ってからの追記だけ(INV-2)。既にある行は変えない。
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from .model import BY_VALUES, RECORDABLE_STATES, WAITINGS, Folded, ImplPath, Record, RecordProblem
from .textutil import norm_path, slash

# §9.8 の固定値
MAX_LINE_BYTES = 4096
LOCK_INTERVAL = 0.1     # 秒
LOCK_TIMEOUT = 3.0      # 秒
LOCK_STALE = 60.0       # 秒。これより古いロックは前の実行の残り
NOTE_MAX = 200

REQUIRED = ("v", "at", "pc", "by", "doc", "path")
FOLD_KEYS = ("state", "done_phase", "last_phase", "waiting", "note")
_AT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _parse_at(s: str) -> datetime:
    return datetime.fromisoformat(s)


def validate(obj: object) -> str | None:
    """§9.8 の表の値の制約で検査する。問題の理由(日本語)か None。知らないキーは無視。"""
    if not isinstance(obj, dict):
        return "JSON のオブジェクトでない"
    for k in REQUIRED:
        if k not in obj:
            return f"要るキー {k} が無い"
    if not _is_int(obj["v"]) or obj["v"] != 1:
        return "v が 1 でない"
    at = obj["at"]
    if not isinstance(at, str) or not _AT_RE.fullmatch(at):
        return "at が ISO 8601(秒まで・時差付き)でない"
    try:
        _parse_at(at)
    except ValueError:
        return "at が日時として読めない"
    for k in ("pc", "doc"):
        if not isinstance(obj[k], str) or obj[k] == "":
            return f"{k} が空でない文字列でない"
    if not isinstance(obj["path"], str):
        return "path が文字列でない"
    if obj["by"] not in BY_VALUES:
        return "by が user / claude-code / claude のどれでもない"
    if "state" in obj and obj["state"] is not None and obj["state"] not in RECORDABLE_STATES:
        return "state が記録に書ける状態でない"
    if "waiting" in obj and obj["waiting"] not in WAITINGS:
        return "waiting が なし / 確認待ち / 実物待ち のどれでもない"
    for k in ("done_phase", "last_phase"):
        if k in obj and obj[k] is not None and not (_is_int(obj[k]) and 0 <= obj[k] <= 99):
            return f"{k} が 0〜99 の整数でない"
    if "note" in obj and obj["note"] is not None:
        note = obj["note"]
        if not isinstance(note, str) or not 1 <= len(note) <= NOTE_MAX:
            return f"note が 1〜{NOTE_MAX} 文字の文字列でない"
        if any(unicodedata.category(c) == "Cc" for c in note):
            return "note に改行・タブ・制御文字がある"
    for k in ("impl_add", "impl_remove"):
        if k in obj and not (isinstance(obj[k], list) and all(isinstance(p, str) for p in obj[k])):
            return f"{k} が文字列の配列でない"
    for k in ("confirmed", "undo"):
        if k in obj and obj[k] is not True:
            return f"{k} が true でない"
    return None


def read_all(events_dir: str) -> tuple[list[Record], list[RecordProblem]]:
    """events_dir の *.jsonl を名前順に全部読む(FR-16)。同じ中身の行は1回だけ(FR-19)。"""
    records: list[Record] = []
    problems: list[RecordProblem] = []
    d = Path(events_dir)
    if not d.is_dir():
        return [], []
    seen: set[str] = set()
    for p in sorted(d.glob("*.jsonl")):
        name = p.name
        try:
            data = p.read_bytes()
        except OSError as e:
            problems.append(RecordProblem(name, 0, f"ファイルが読めない: {e}"))
            continue
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        lines = data.split(b"\n")
        tail = lines.pop()          # \n で終わっていれば空
        unfinished = bool(tail.strip())
        if unfinished:
            lines.append(tail)
        for i, b in enumerate(lines, 1):
            if not b.strip():
                continue            # 空行は記録でも問題でもない
            if unfinished and i == len(lines):
                problems.append(RecordProblem(name, i, "末尾が未完(改行で終わっていない)"))
                continue
            if len(b) > MAX_LINE_BYTES:
                problems.append(RecordProblem(name, i, f"行が {MAX_LINE_BYTES} バイトを超える"))
                continue
            try:
                raw = b.decode("utf-8")
                obj = json.loads(raw)
            except UnicodeDecodeError:
                problems.append(RecordProblem(name, i, "UTF-8 で読めない"))
                continue
            except ValueError:
                problems.append(RecordProblem(name, i, "JSON として読めない"))
                continue
            reason = validate(obj)
            if reason:
                problems.append(RecordProblem(name, i, reason))
                continue
            if raw in seen:
                continue
            seen.add(raw)
            records.append(Record(fields=obj, file=name, line=i, raw=raw))
    records.sort(key=sort_key)
    return records, problems


def sort_key(r: Record) -> tuple:
    """FR-18 の並び: at を時刻として、同じなら pc、ファイル、行番号。"""
    return (_parse_at(r.at), r.pc, r.file, r.line)


def fold(records: list[Record]) -> Folded:
    """1プロジェクト分の記録を古い順に畳む(FR-18)。null は欄を空に戻す。"""
    f = Folded(history=list(records))
    impl: dict[str, ImplPath] = {}
    for r in records:
        x = r.fields
        for k in FOLD_KEYS:
            if k in x:
                setattr(f, k, x[k])
        if "state" in x:
            f.state_record = r if x["state"] is not None else None
        for p in x.get("impl_add", []):
            key = norm_path(p)
            if key not in impl:
                impl[key] = ImplPath(path=slash(p), pc=r.pc, exists_here=os.path.isdir(p))
        for p in x.get("impl_remove", []):
            impl.pop(norm_path(p), None)
    f.impl = list(impl.values())
    return f


def dumps(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _lock(lock: str) -> bool:
    """§9.8 書き方 1。取れたら True。"""
    deadline = time.monotonic() + LOCK_TIMEOUT
    stale_done = False
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except (FileExistsError, PermissionError):  # Windows は消している最中のファイルで PermissionError
            pass
        if not stale_done:
            try:
                old = time.time() - os.path.getmtime(lock) > LOCK_STALE
            except OSError:
                old = False
            if old:
                stale_done = True
                try:
                    os.remove(lock)
                except FileNotFoundError:
                    pass
                continue
        if time.monotonic() >= deadline:
            return False
        time.sleep(LOCK_INTERVAL)


def append(events_dir: str, pc_name: str, line: str) -> int:
    """FR-22: ロックを取り、<PC名>.jsonl に1行足す。0、ロックが取れなければ 6。OSError は投げる。"""
    os.makedirs(events_dir, exist_ok=True)
    lock = os.path.join(events_dir, f".{pc_name}.lock")
    if not _lock(lock):
        return 6
    try:
        with open(os.path.join(events_dir, f"{pc_name}.jsonl"), "a+b") as fp:
            fp.seek(0, os.SEEK_END)
            prefix = b""
            if fp.tell() > 0:
                fp.seek(-1, os.SEEK_END)
                if fp.read(1) != b"\n":
                    prefix = b"\n"      # 前の書き込みが途中で切れた
            fp.write(prefix + line.encode("utf-8") + b"\n")
            fp.flush()
            os.fsync(fp.fileno())
    finally:
        try:
            os.remove(lock)
        except FileNotFoundError:
            pass
    return 0


def now_iso() -> str:
    """秒まで・時差付きの今の時刻。"""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()

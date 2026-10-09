# 記録した時点の仕様書の写しを %LOCALAPPDATA%\SpecStatus\snapshots\ に置き、今の仕様書との差分を出す。
# 写しは文書ごとに1ファイル(名前は文書の vault からのパスのハッシュ。中に path・保存日時・本文)。vault には書かない。
# 差分は Claude Code に渡す指示文にもする。
from __future__ import annotations

import difflib
import hashlib
import json
import os
from datetime import datetime

from .model import Doc, ProjectStatus
from .textutil import nfc, read_text

PROMPT_MAX_LINES = 300       # 指示文に入れる差分の行の上限


def folder_path(folder: str | None = None) -> str:
    if folder:
        return folder
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus", "snapshots")


def _file(doc: Doc, folder: str | None) -> str:
    # vault ごとに分かれるよう絶対パスで名前を付ける(別の vault やテストの同じ相対パスと混ざらない)。
    # NFC にそろえる(NFD の名前のファイルも、実際のパスで読みつつ写しの名前は前と同じ)
    h = hashlib.sha1(nfc(os.path.normcase(os.path.abspath(doc.abs_path))).encode("utf-8")).hexdigest()[:20]
    return os.path.join(folder_path(folder), h + ".json")


def _read_snapshot(doc: Doc, folder: str | None) -> str | None:
    try:
        with open(_file(doc, folder), encoding="utf-8") as f:
            data = json.load(f)
        return data["text"] if data.get("path") == doc.path else None
    except (OSError, ValueError, KeyError, AttributeError):
        return None


def _save_doc(doc: Doc, folder: str | None) -> bool:
    try:
        text = read_text(doc.abs_path)
        path = _file(doc, folder)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"path": doc.path, "saved": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "text": text}, f, ensure_ascii=False)
        return True
    except (OSError, UnicodeDecodeError):
        return False


def save(ps: ProjectStatus, folder: str | None = None) -> None:
    """今の仕様書の文書(付属を除く)を写す。読めない文書は飛ばす。"""
    for d in ps.project.spec_docs:
        _save_doc(d, folder)


def ensure_baseline(statuses: list[ProjectStatus], folder: str | None = None) -> int:
    """記録があり、仕様が変わっていなくて、写しが無い文書だけ今の内容を写す。写した数を返す。"""
    n = 0
    for ps in statuses:
        if not ps.folded.history or ps.spec_changed:
            continue
        for d in ps.project.spec_docs:
            if not os.path.exists(_file(d, folder)) and _save_doc(d, folder):
                n += 1
    return n


def diff(ps: ProjectStatus, folder: str | None = None) -> list[tuple[str, list[str]]] | None:
    """(文書の vault からのパス, unified diff の行)。違いのある文書だけ。写しが1つも無ければ None。"""
    docs = ps.project.spec_docs
    olds = {d.path: _read_snapshot(d, folder) for d in docs}
    if all(o is None for o in olds.values()):
        return None
    out = []
    for d in docs:
        try:
            now = read_text(d.abs_path)
        except (OSError, UnicodeDecodeError):
            continue
        lines = list(difflib.unified_diff((olds[d.path] or "").splitlines(), now.splitlines(),
                                          "記録した時点", "今", lineterm=""))
        if lines:
            out.append((d.path, lines))
    return out


def diff_prompt(ps: ProjectStatus, folder: str | None = None) -> str:
    """Claude Code に渡す「仕様書のこの差分を実装して」の文。写しが無い・違いが無ければ空。"""
    parts = diff(ps, folder)
    if not parts:
        return ""
    body, total = [], 0
    for path, lines in parts:
        room = PROMPT_MAX_LINES - total
        if room <= 0:
            break
        body += [f"### {path}", "```diff", *lines[:room], "```", ""]
        total += min(len(lines), room)
    all_lines = sum(len(lines) for _, lines in parts)
    if all_lines > total:
        body.append(f"(差分が長いので {all_lines} 行のうち {total} 行で切りました。残りは仕様書を直接読んでください)")
    head = [
        f"仕様書「{ps.project.name}」が、実装状況を記録した時点から書き換えられています。",
        f"仕様書: {ps.project.primary_doc.abs_path}",
        "下の差分(- が記録した時点、+ が今)を読み、変わった所を実装に反映してください。",
        "反映が済んだら SpecStatus に記録を1行足してください。",
        "",
    ]
    return "\n".join(head + body).rstrip() + "\n"

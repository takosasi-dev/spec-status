# Board を、表(標準出力)・一覧ノート(§9.5)・JSON(§9.6)の文字列にする。
# 同じ Board と同じ日付なら同じ文字列になる(INV-6)。本文は写さない(INV-7)。ファイルは書かない。
from __future__ import annotations

import json
from datetime import date, timedelta

from .model import STATES, Board, Evidence, ProjectStatus
from .textutil import fold

SOURCE_LABEL = {"events": "記録", "setsumei": "説明書", "tooldeck": "ToolDeck",
                "implroot": "実装フォルダ", "handoff": "引き継ぎメモ", "none": "なし"}
BY_LABEL = {"user": "私", "claude-code": "Claude Code", "claude": "Claude"}
WAITING_TURN = ("確認待ち", "実物待ち")


def os_dir(ps: ProjectStatus) -> str:
    return ps.project.spec_dir.split("/", 1)[0]


def board_order(ps: ProjectStatus) -> tuple:
    return (STATES.index(ps.state), fold(os_dir(ps)), fold(ps.project.name), fold(ps.project.spec_dir))


def phase_text(ps: ProjectStatus) -> str:
    if ps.done_phase is None:
        return "-"
    return f"{ps.done_phase}/{'?' if ps.last_phase is None else ps.last_phase}"


def source_text(by: dict) -> str:
    if by["source"] == "none":
        return SOURCE_LABEL["none"]
    return f"{SOURCE_LABEL.get(by['source'], by['source'])}: {by['value']}"


def evidence_text(e: Evidence) -> str:
    return f"{SOURCE_LABEL.get(e.source, e.source)}: {e.state or e.value}"


def last_text(ps: ProjectStatus) -> str:
    r = ps.folded.last_record
    return f"{r.at[:10]}({BY_LABEL.get(r.by, r.by)})" if r else ""


def cell(s: str | None) -> str:
    return (s or "").replace("|", "\\|")


# ---- 表(list) -------------------------------------------------------------

LIST_HEADER = ("状態", "プロジェクト", "仕様書フォルダ", "Phase", "待ち", "最後の記録", "根拠")


def list_row(ps: ProjectStatus) -> tuple[str, ...]:
    return (ps.state, ps.project.name, ps.project.spec_dir, phase_text(ps), ps.waiting,
            last_text(ps), source_text(ps.decided_by))


def table(statuses: list[ProjectStatus]) -> str:
    rows = [LIST_HEADER] + [list_row(ps) for ps in statuses]
    return "\n".join(" | ".join(r) for r in rows) + f"\n({len(statuses)} 件)"


# ---- JSON ------------------------------------------------------------------

def _ev(e: Evidence) -> dict:
    d = {"source": e.source, "state": e.state, "value": e.value, "path": e.where}
    if e.note:
        d["note"] = e.note
    return d


def project_json(ps: ProjectStatus) -> dict:
    f = ps.folded
    r = f.last_record
    return {
        "name": ps.project.name,
        "spec_dir": ps.project.spec_dir,
        "docs": [{"path": d.path, "kind": d.kind, "created": d.created} for d in ps.project.docs],
        "state": ps.state,
        "decided_by": ps.decided_by,
        "evidence": [_ev(e) for e in ps.evidence],
        "conflict": ps.conflict,
        "last_devlog_date": ps.last_devlog_date,
        "note": f.note,
        "done_phase": f.done_phase,
        "last_phase": ps.last_phase,
        "waiting": ps.waiting,
        "impl_paths": [{"path": i.path, "pc": i.pc, "exists_here": i.exists_here} for i in f.impl],
        "last_record": {"at": r.at, "by": r.by, "pc": r.pc} if r else None,
        "conflicts": [_ev(e) for e in ps.conflicts],
    }


def board_json(board: Board, generated_at: str) -> str:
    obj = {
        "schema": 1,
        "generated_at": generated_at,
        "generated_on": board.pc_name,
        "skipped_evidence": board.skipped_evidence,
        "projects": [project_json(ps) for ps in board.statuses],
        "unreadable": [{"reader": u.reader, "path": u.path, "reason": u.reason} for u in board.unreadable],
        "record_problems": [{"file": p.file, "line": p.line, "reason": p.reason} for p in board.record_problems],
        "orphan_records": [{"doc": o.doc, "path": o.path, "at": o.at, "pc": o.pc} for o in board.orphans],
        "folders_without_specs": board.folders_without_specs,
    }
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


# ---- 一覧ノート ---------------------------------------------------------------

def _link(ps: ProjectStatus, dup_stems: set[str]) -> str:
    d = ps.project.primary_doc
    target = d.path[:-3] if fold(d.stem) in dup_stems else d.stem
    return f"[[{target}\\|{cell(ps.project.name)}]]"


def board_markdown(board: Board, generated: str, today: date, dup_stems: set[str]) -> str:
    """generated: 「2026-10-08 23:40」の形。dup_stems: vault の中で2つ以上ある md のファイル名(fold 済み)。"""
    st = board.statuses
    link = lambda ps: _link(ps, dup_stems)  # noqa: E731
    n_docs = sum(1 for d in board.docs if d.kind != "付属")
    out = [
        "---", "tags:", "  - 仕様書", "  - 自動生成", "---",
        "# 仕様書の実装状況", "",
        "自動生成(SpecStatus)。手で直さない。状態を変えるときは GUI か `mark` を使う。",
        f"生成: {generated} ({board.pc_name}) / 仕様書の文書 {n_docs} / プロジェクト {len(st)} / "
        f"食い違い {sum(1 for p in st if p.conflict)} / 記録 {board.record_count} 行",
        f"この PC で読まなかった証拠: {'・'.join(board.skipped_evidence) or '無し'}", "",
        "| 状態 | 件数 |", "|---|---|",
    ]
    out += [f"| {s} | {sum(1 for p in st if p.state == s)} |" for s in STATES]

    turn = sorted((p for p in st if p.waiting in WAITING_TURN),
                  key=lambda p: (p.folded.last_record.at if p.folded.last_record else "", board_order(p)))
    out += ["", f"## あなたの番({len(turn)})", "",
            "| プロジェクト | 待ち | Phase | 最後の記録 | メモ |", "|---|---|---|---|---|"]
    out += [f"| {link(p)} | {p.waiting} | {phase_text(p)} | {cell(last_text(p))} | {cell(p.folded.note)} |"
            for p in turn]

    days = board.config.get("board", {}).get("recent_days", 7)
    limit = board.config.get("board", {}).get("recent_max", 20)
    since = (today - timedelta(days=days - 1)).isoformat()
    recent = [p for p in st if p.folded.last_record and p.folded.last_record.at[:10] >= since]
    recent.sort(key=lambda p: (p.folded.last_record.at, ), reverse=True)
    recent = recent[:limit]
    out += ["", f"## 最近動いた物({len(recent)})", "",
            "| プロジェクト | 状態 | Phase | 最後の記録 |", "|---|---|---|---|"]
    out += [f"| {link(p)} | {p.state} | {phase_text(p)} | {cell(last_text(p))} |" for p in recent]

    for s in STATES:
        rows = [p for p in st if p.state == s]
        out += ["", f"## {s}({len(rows)})", "",
                "| プロジェクト | 仕様書フォルダ | Phase | 根拠 | 最後の記録 | 開発ログ | メモ |",
                "|---|---|---|---|---|---|---|"]
        out += [f"| {link(p)} | {cell(p.project.spec_dir)} | {phase_text(p)} | {cell(source_text(p.decided_by))} | "
                f"{cell(last_text(p))} | {p.last_devlog_date or ''} | {cell(p.folded.note)} |" for p in rows]

    conf = [p for p in st if p.conflict]
    out += ["", f"## 食い違い({len(conf)})", "", "| プロジェクト | 決めた根拠 | 食い違う証拠 |", "|---|---|---|"]
    out += [f"| {link(p)} | {cell(source_text(p.decided_by))} | "
            f"{cell(' / '.join(evidence_text(e) for e in p.conflicts))} |" for p in conf]

    if board.record_problems or board.orphans:
        out += ["", "## 記録の問題", ""]
        out += [f"- {cell(p.file)} {p.line} 行目: {cell(p.reason)}" for p in board.record_problems]
        out += [f"- 宛先の無い記録: {cell(o.doc)}({cell(o.path)}、{o.at}、{cell(o.pc)})" for o in board.orphans]
    if board.folders_without_specs:
        out += ["", "## 仕様書の見つからないフォルダ", ""]
        out += [f"- {cell(d)}" for d in board.folders_without_specs]
    if board.unreadable:
        out += ["", "## 読めなかった証拠", ""]
        out += [f"- {u.reader}: {cell(u.path)} {cell(u.reason)}".rstrip() for u in board.unreadable]
    return "\n".join(out) + "\n"

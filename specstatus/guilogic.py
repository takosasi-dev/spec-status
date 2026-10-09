# GUI の表と編集欄の中身を決める純関数(絞り込み・並べ替え・行の文字列・取り消しで戻す値)。
# tkinter を import しない。pytest はここだけを確かめる(AC-39・AC-42・AC-43)。
from __future__ import annotations

import os
from datetime import datetime

from . import render
from . import strings as S
from .model import RECORDABLE_STATES, STATES, WAITINGS, Folded, ProjectStatus, Record
from .textutil import fold, norm_path

_RECORD_META = ("v", "at", "pc", "by", "doc", "path")


def in_category(ps: ProjectStatus, category: str | None) -> bool:
    """category は仕様書フォルダの先頭の何段か(「Windows」「Windows/QOLツール」)。None はすべて。"""
    if not category:
        return True
    d, c = fold(ps.project.spec_dir), fold(category)
    return d == c or d.startswith(c + "/")


def category_tree(statuses: list[ProjectStatus]) -> list[tuple[str, str, str, int, int]]:
    """左の分類の木: (パス, 親のパス, 表示名, 件数, 実装完了の件数)。1段目は OS、2段目は3段以上ある仕様書フォルダの2段目。"""
    total: dict[str, list[int]] = {}
    for ps in statuses:
        parts = ps.project.spec_dir.split("/")
        keys = [parts[0]] + (["/".join(parts[:2])] if len(parts) >= 3 else [])
        for k in keys:
            t = total.setdefault(k, [0, 0])
            t[0] += 1
            t[1] += ps.state == "実装完了"
    out = []
    for k in sorted(total, key=lambda k: [fold(x) for x in k.split("/")]):
        parent, _, name = k.rpartition("/")
        out.append((k, parent, name, *total[k]))
    return out


def filter_rows(statuses: list[ProjectStatus], states: set[str], category: str | None,
                waiting_only: bool, conflict_only: bool, query: str, stale_only: bool = False,
                changed_only: bool = False, vuln_only: bool = False) -> list[ProjectStatus]:
    """状態の札(どれか)・分類(仕様書フォルダの先頭)・待ち・食い違い・検索語・止まっている物で絞る。並びは保つ。"""
    q = fold(query.strip())
    out = []
    for ps in statuses:
        if states and ps.state not in states:
            continue
        if not in_category(ps, category):
            continue
        if waiting_only and ps.waiting == "なし":
            continue
        if conflict_only and not ps.conflict:
            continue
        if stale_only and not ps.stale_days:
            continue
        if changed_only and not ps.spec_changed:
            continue
        if vuln_only and not (ps.vulns and ps.vulns["count"]):
            continue
        if q and q not in fold(ps.project.name) and q not in fold(ps.project.spec_dir):
            continue
        out.append(ps)
    return out


def _last_key(ps: ProjectStatus) -> tuple:
    r = ps.folded.last_record
    return (r is None, datetime.fromisoformat(r.at).timestamp() if r else 0.0)


def _none_last(v):
    return (v is None, v if v is not None else 0)


_SORT_KEYS = {
    "state": lambda ps: STATES.index(ps.state) if ps.state in STATES else len(STATES),
    "name": lambda ps: fold(ps.project.name),
    "spec_dir": lambda ps: fold(ps.project.spec_dir),
    "phase": lambda ps: (_none_last(ps.done_phase), _none_last(ps.last_phase)),
    "waiting": lambda ps: WAITINGS.index(ps.waiting) if ps.waiting in WAITINGS else len(WAITINGS),
    "last": _last_key,
    "source": lambda ps: fold(source_text(ps)),
    "conflict": lambda ps: ps.conflict,
    "github": lambda ps: (ps.github is None, (ps.github or {}).get("pushed_at") or ""),
}


def sort_rows(statuses: list[ProjectStatus], column: str, descending: bool) -> list[ProjectStatus]:
    """列で並べる(安定。同じ値は元の並び)。列名は strings.COLUMNS のキー。"""
    return sorted(statuses, key=_SORT_KEYS[column], reverse=descending)


def phase_text(ps: ProjectStatus) -> str:
    return render.phase_text(ps)


def source_text(ps: ProjectStatus) -> str:
    return render.source_text(ps.decided_by)


def last_record_text(ps: ProjectStatus) -> str:
    return render.last_text(ps)


def row_values(ps: ProjectStatus) -> tuple[str, ...]:
    """表の1行。並びは strings.COLUMNS と同じ。"""
    return (ps.state, ps.project.name, ps.project.spec_dir, phase_text(ps), ps.waiting,
            last_record_text(ps), source_text(ps), S.CONFLICT_MARK if ps.conflict else "",
            render.github_text(ps.github))


def activity_text(ps: ProjectStatus) -> str:
    if not ps.last_activity:
        return "-"
    return S.STALE_TEXT.format(date=ps.last_activity, days=ps.stale_days) if ps.stale_days else ps.last_activity


def changed_text(ps: ProjectStatus) -> str:
    return S.CHANGED_TEXT.format(date=ps.spec_changed) if ps.spec_changed else "-"


def ac_detail(ps: ProjectStatus) -> str:
    return S.AC_TEXT.format(done=ps.ac[0], total=ps.ac[1]) if ps.ac else "-"


def vulns_text(ps: ProjectStatus) -> str:
    v = ps.vulns
    if not v:
        return "-"
    if not v["count"]:
        return S.VULNS_NONE.format(total=v["total"])
    details = v.get("details") or []
    if details:     # 一番重い物の直し方を1つだけ(全部は一覧ノートと show に出る)
        d = details[0]
        fix = S.VULNS_FIX.format(package=d["package"], version=d["version"], fixed=d.get("fixed") or "?")
        return S.VULNS_TEXT_FIX.format(count=v["count"], total=v["total"], worst=v.get("worst") or "不明", fix=fix)
    names = ", ".join(p.split("(", 1)[0] for p in v["packages"][:2])     # 詳細の欄に収まるよう ID は省く(一覧ノートと show に出る)
    return S.VULNS_TEXT.format(count=v["count"], total=v["total"], packages=names)


def github_detail(ps: ProjectStatus) -> str:
    g = ps.github
    if not g:
        return "-"
    return S.GITHUB_TEXT.format(repo=g["repo"], release=g["release"] or "-", pushed=g["pushed_at"], ci=g["ci"] or "-")


def extra_details(ps: ProjectStatus) -> dict[str, str]:
    """v0.7.0 の欄(strings.EXTRA_FIELDS のキー → 文字)。値が無い物・0 の物は入れない。"""
    out: dict[str, str] = {}
    if ps.gap:
        out["gap"] = ps.gap
    q = ps.questions or {}
    if q.get("open"):
        out["questions"] = S.QUESTIONS_TEXT.format(open=q["open"]) + (
            S.QUESTIONS_MINE.format(mine=q["mine"]) if q.get("mine") else "")
    if ps.retreat and ps.retreat.get("due"):
        out["retreat"] = ps.retreat.get("phase") or "-"
    if ps.blocked_by:
        out["blocked_by"] = S.BLOCKED_SEP.join(ps.blocked_by)
    pace = ps.pace or {}
    if pace.get("remaining") and pace.get("eta_days") is not None:
        out["pace"] = S.PACE_TEXT.format(remaining=pace["remaining"], days=round(pace["eta_days"]))
    eol = ps.eol or {}
    ended = sum(1 for r in eol.get("runtimes") or [] if r.get("ended"))
    old = len(eol.get("outdated") or [])
    parts = [t.format(n=n) for t, n in ((S.EOL_ENDED, ended), (S.EOL_OUTDATED, old)) if n]
    if parts:
        out["eol"] = S.BLOCKED_SEP.join(parts)
    gh = ps.github or {}
    parts = [t.format(n=gh[k]) for t, k in ((S.GH_STARS, "stars"), (S.GH_FORKS, "forks"),
                                             (S.GH_DOWNLOADS, "downloads")) if gh.get(k) is not None]
    if parts:
        out["gh_stats"] = S.BLOCKED_SEP.join(parts)
    return out


def filter_summary(states: list[str], category: str | None, checks: list[str], query: str) -> str:
    """件数の横の「絞り込み中: 確認待ち・Windows」。checks は入っているチェックの見出し。何も無ければ ""。"""
    items = [*states, *([category] if category else []), *checks]
    q = query.strip()
    if q:
        items.append(S.FILTER_SEARCH.format(q=q if len(q) <= 20 else q[:20] + "…"))     # 帯を押し出さない長さに
    return S.FILTERING.format(items="・".join(items)) if items else ""


def flash_text(names: list[str], fields: dict) -> str:
    """記録した直後の一言。「○○を着手済にしました(Ctrl+Z で戻す)」。2件以上は「3 件を…」。"""
    who = names[0] if len(names) == 1 else S.FLASH_MANY.format(n=len(names))
    if fields.get("state"):
        text = S.FLASH_STATE.format(who=who, state=fields["state"])
    elif "waiting" in fields:
        text = S.FLASH_WAITING.format(who=who, waiting=fields["waiting"])
    elif "note" in fields:
        text = (S.FLASH_NOTE if fields["note"] else S.FLASH_NOTE_CLEARED).format(who=who)
    elif "impl_add" in fields:
        text = S.FLASH_IMPL_ADD.format(who=who)
    elif "impl_remove" in fields:
        text = S.FLASH_IMPL_REMOVE.format(who=who)
    else:
        text = S.FLASH_OTHER.format(who=who)
    return text + S.FLASH_UNDO_HINT


def events_stamp(events_dir: str) -> tuple[float, int, int]:
    """記録のフォルダの (*.jsonl の最新の更新時刻, 件数, 大きさの合計)。窓に戻ったときに前回と比べて読み直す。"""
    newest, n, size = 0.0, 0, 0
    try:
        with os.scandir(events_dir) as it:
            for e in it:
                if e.name.endswith(".jsonl") and e.is_file():
                    st = e.stat()
                    newest, n, size = max(newest, st.st_mtime), n + 1, size + st.st_size
    except OSError:         # フォルダがまだ無い
        pass
    return newest, n, size


def count_by_state(statuses: list[ProjectStatus]) -> dict[str, int]:
    counts = {s: 0 for s in STATES}
    for ps in statuses:
        counts[ps.state] = counts.get(ps.state, 0) + 1
    return counts


def undo_fields(before: Folded, fields: dict) -> dict:
    """fields で変えた項目を before の値に戻す記録(FR-36)。戻す項目が無ければ {'undo': True} だけ。"""
    out: dict = {}
    for k in ("state", "done_phase", "last_phase", "note"):
        if k in fields:
            out[k] = getattr(before, k)
    if "waiting" in fields:
        out["waiting"] = before.waiting or "なし"
    had = {norm_path(p.path) for p in before.impl}
    # 前から結ばれていた物を足しても集合は変わらない → 外さない。外したときは逆。
    add_back = [p for p in fields.get("impl_remove", []) if norm_path(p) in had]
    remove = [p for p in fields.get("impl_add", []) if norm_path(p) not in had]
    if remove:
        out["impl_remove"] = remove
    if add_back:
        out["impl_add"] = add_back
    out["undo"] = True
    return out


def parse_phase(text: str, label: str) -> tuple[int | None, str | None]:
    """編集欄のフェーズ。空なら (None, None)=変えない。整数 0〜99 以外は (None, 理由)。"""
    t = text.strip()
    if not t:
        return None, None
    if not t.isdecimal() or not 0 <= int(t) <= 99:
        return None, S.ERR_PHASE.format(label=label, value=t)
    return int(t), None


def make_fields(state: str, done: str, last: str, waiting: str, note: str,
                multi: bool) -> tuple[dict, str | None]:
    """編集欄の値から記録のキーを作る。複数選択のときは状態と待ちだけ(§9.9)。戻り値 (fields, 理由)。"""
    fields: dict = {}
    if state in RECORDABLE_STATES:
        fields["state"] = state
    if waiting in WAITINGS:
        fields["waiting"] = waiting
    if not multi:
        for key, text, label in (("done_phase", done, S.EDIT_DONE), ("last_phase", last, S.EDIT_LAST)):
            v, err = parse_phase(text, label)
            if err:
                return {}, err
            if v is not None:
                fields[key] = v
        if note.strip():
            if len(note) > 200:
                return {}, S.ERR_NOTE_LEN.format(n=len(note))
            fields["note"] = note
    if not fields:
        return {}, S.ERR_NO_FIELDS
    return fields, None


def confirm_text(n: int, fields: dict) -> str:
    return S.CONFIRM_BULK.format(n=n, state=fields.get("state", S.NO_CHANGE),
                                 waiting=fields.get("waiting", S.NO_CHANGE))


def bulk_plan(selected: list[ProjectStatus], fields: dict, answer: bool) -> list[tuple[ProjectStatus, dict, dict]]:
    """確認の後に書く物: [はい] なら選んだ件数ぶん (ps, 書く fields, 取り消しで戻す fields)、[いいえ] なら空(AC-42)。"""
    if not answer:
        return []
    return [(ps, dict(fields), undo_fields(ps.folded, fields)) for ps in selected]


def copy_text(template: str, ps: ProjectStatus) -> str:
    """FR-37: gui.copy_template の {abs_path} に主な文書のこの PC での絶対パスを入れる。"""
    return template.replace("{abs_path}", ps.project.primary_doc.abs_path)


def _show(v) -> str:
    if v is None:
        return S.CLEARED
    if isinstance(v, list):
        return ", ".join(map(str, v))
    if v is True:
        return ""
    return str(v)


def history_line(r: Record) -> str:
    """記録の履歴の1行: 日時・誰・PC・変わった項目。"""
    changes = []
    for k, v in r.fields.items():
        if k in _RECORD_META:
            continue
        label = S.FIELD_LABELS.get(k, k)
        shown = _show(v)
        changes.append(f"{label}={shown}" if shown else label)
    return S.HISTORY_LINE.format(at=r.at, by=S.BY_LABELS.get(r.by, r.by), pc=r.pc, changes=" / ".join(changes))

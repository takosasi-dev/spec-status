# 中核の入口: 設定→発見→まとめ→証拠→記録→決定 を通して Board を作り(load)、記録を1行足し(write_mark)、出力2ファイルを書く(build)。
# CLI も GUI もここだけを呼ぶ(INV-11)。書くのは記録ファイルの追記と出力2ファイルだけ(INV-1)。例外は weekly が書く週のまとめ1つ。
from __future__ import annotations

import importlib
import os
import time
from datetime import date, datetime, timedelta

from . import github, history, osv, records
from .config import ConfigError, events_dir, load_config, load_registry, pc_name
from .decide import decide
from .find import find_docs
from .group import group_docs
from .model import (BY_VALUES, EVIDENCE_SOURCES, RECORDABLE_STATES, WAITINGS, Board, Doc, Evidence,
                    Orphan, Project, ProjectStatus, Record, Unreadable)
from .render import board_json, board_markdown, board_order, weekly_markdown
from .textutil import fold, in_scope, nfc, norm_path, resolve, slash

NOTE_MAX = 200
LINE_MAX_BYTES = 4096
REPLACE_TRIES = 3
REPLACE_WAIT_S = 0.2
STALE_DAYS = 30           # [board] stale_days が無いとき
FIELD_ORDER = ("state", "done_phase", "last_phase", "waiting", "note", "impl_add", "impl_remove", "confirmed", "undo")
CONTENT_KEYS = FIELD_ORDER[:7]


# ---- load -----------------------------------------------------------------

def _read_evidence(vault: str, cfg: dict, projects: list[Project]):
    found: dict[str, dict[str, list[Evidence]]] = {}    # project.key -> source -> 証拠
    unreadable: list[Unreadable] = []
    skipped: list[str] = []
    for name in EVIDENCE_SOURCES:
        sec = cfg.get("evidence", {}).get(name, {})
        mod = importlib.import_module(f".evidence.{name}", __package__)
        try:
            if not mod.configured(vault, sec):
                skipped.append(name)
                continue
            scoped = [p for p in projects if in_scope(p.spec_dir, sec.get("scope", [""]))]
            res = mod.read(vault, sec, scoped)
        except Exception as e:  # FR-32: 1つの読み手が落ちても続ける
            unreadable.append(Unreadable(name, f"{type(e).__name__}: {e}"))
            continue
        unreadable += res.unreadable
        for key, evs in res.found.items():
            found.setdefault(key, {}).setdefault(name, []).extend(evs)
    return found, unreadable, skipped


def _bind_records(recs: list[Record], projects: list[Project], registry: dict):
    """FR-17。戻り値: (project.key -> 記録, 宛先の無い記録, rename の不整合)。"""
    by_stem: dict[str, list[tuple[Doc, Project]]] = {}
    for p in projects:
        for d in p.spec_docs:
            by_stem.setdefault(fold(d.stem), []).append((d, p))
    renames = {fold(r["from"]): r["to"] for r in registry.get("rename", [])}
    issues = [f"[[rename]] の to が見つかりません: {r['to']}" for r in registry.get("rename", [])
              if fold(r["to"]) not in by_stem]
    bound: dict[str, list[Record]] = {}
    orphans: list[Orphan] = []
    for r in recs:
        stem = fold(renames.get(fold(r.fields["doc"]), r.fields["doc"]))
        hits = by_stem.get(stem, [])
        if len(hits) > 1:
            hits = [h for h in hits if fold(h[0].path) == fold(nfc(slash(r.fields["path"])))]
        if len(hits) == 1:
            bound.setdefault(hits[0][1].key, []).append(r)
        else:
            orphans.append(Orphan(r.fields["doc"], r.fields["path"], r.at, r.pc))
    return bound, orphans, issues


def load(vault: str, config_path: str | None) -> Board:
    vault = os.path.abspath(vault)
    cfg = load_config(vault, config_path)
    registry = load_registry(vault)
    spec_root = os.path.join(vault, cfg["vault"]["spec_root"])
    if not os.path.isdir(spec_root):
        raise ConfigError(f"spec_root がありません: {spec_root}", spec_root)

    docs, unreadable, no_spec, issues = find_docs(vault, cfg, registry)
    projects, merge_issues = group_docs(docs, registry)
    found, ev_unreadable, skipped = _read_evidence(vault, cfg, projects)
    recs, problems = records.read_all(events_dir(vault))
    bound, orphans, rename_issues = _bind_records(recs, projects, registry)

    statuses = [decide(p, records.fold(bound.get(p.key, [])), found.get(p.key, {})) for p in projects]
    statuses.sort(key=board_order)
    history.mark_stale(statuses, date.today(), cfg.get("board", {}).get("stale_days", STALE_DAYS))
    history.mark_spec_changed(statuses)
    github_note = github.attach(statuses, cfg)
    osv_note = osv.attach(statuses, cfg)
    os_dirs = sorted((n for n in os.listdir(spec_root) if os.path.isdir(os.path.join(spec_root, n))), key=fold)
    board = Board(
        vault=vault, pc_name=pc_name(cfg), config=cfg, docs=docs, statuses=statuses,
        unreadable=unreadable + ev_unreadable, skipped_evidence=skipped,
        record_problems=problems, orphans=orphans, folders_without_specs=no_spec,
        registry_issues=issues + merge_issues + rename_issues, record_count=len(recs),
        os_dirs=[nfc(n) for n in os_dirs], reader_failed=bool(ev_unreadable), github_note=github_note,
        osv_note=osv_note,
    )
    output_paths(board)          # 出力先が許可外なら GUI のエラー表示にも出るよう、読む段で止める
    return board


# ---- 宛先(FR-23) ------------------------------------------------------------

def _resolve(board: Board, arg: str):
    """戻り値: (ProjectStatus か None, 宛先の文書か None, 候補)。"""
    rel = None
    name = arg
    if "\\" in arg or "/" in arg:
        name = slash(arg).rstrip("/").rsplit("/", 1)[-1]
        p = os.path.abspath(arg) if os.path.isabs(arg) else None
        if p and norm_path(p).startswith(norm_path(board.vault) + "/"):
            rel = slash(os.path.relpath(p, board.vault))
        elif p is None:
            rel = slash(arg)
    if name.lower().endswith(".md"):
        name = name[:-3]
    hits = [(d, ps) for ps in board.statuses for d in ps.project.spec_docs if fold(d.stem) == fold(name)]
    if len(hits) > 1 and rel is not None:
        hits = [h for h in hits if fold(h[0].path) == fold(nfc(rel))] or hits
    if len(hits) == 1:
        return hits[0][1], hits[0][0], []
    if hits:
        return None, None, list({id(h[1]): h[1] for h in hits}.values())[:10]
    named = [ps for ps in board.statuses if fold(ps.project.name) == fold(name)]
    if len(named) == 1:
        return named[0], None, []
    if named:
        return None, None, named[:10]
    q = fold(name)
    cands = [ps for ps in board.statuses
             if q in fold(ps.project.name) or q in fold(ps.project.spec_dir)
             or any(q in fold(d.path) for d in ps.project.docs)]
    return None, None, cands[:10]


def resolve_target(board: Board, arg: str) -> tuple[ProjectStatus | None, list[ProjectStatus]]:
    ps, _doc, cands = _resolve(board, arg)
    return ps, cands


def where(board: Board, folder: str) -> list[ProjectStatus]:
    """FR-28: folder が実装フォルダと同じか、その下。"""
    here = norm_path(os.path.realpath(folder))
    out = []
    for ps in board.statuses:
        paths = [i.path for i in ps.folded.impl] + [e.value for e in ps.evidence + [_decided_ev(ps)]
                                                     if e.source == "implroot"]
        for p in paths:
            root = norm_path(os.path.realpath(p))
            if here == root or here.startswith(root + "/"):
                out.append(ps)
                break
    return out


def _decided_ev(ps: ProjectStatus) -> Evidence:
    b = ps.decided_by
    return Evidence(b["source"], ps.state, b["value"], b["path"])


# ---- mark -----------------------------------------------------------------

def _check_fields(ps: ProjectStatus, fields: dict, by: str) -> tuple[int, str, dict]:
    if by not in BY_VALUES:
        return 2, f"--by の値が違います: {by}", {}
    unknown = set(fields) - set(FIELD_ORDER)
    if unknown:
        return 2, f"知らない項目: {', '.join(sorted(unknown))}", {}
    if not any(k in fields for k in CONTENT_KEYS):
        return 2, "記録する項目がありません(--state・--clear-state・--done-phase・--last-phase・--waiting・--note・--impl・--unimpl のどれか)", {}
    f = dict(fields)
    if "confirmed" in f and f["confirmed"] is not True or "undo" in f and f["undo"] is not True:
        return 2, "confirmed と undo は true だけ書けます", {}
    if f.get("confirmed") and f.get("state") is None:
        return 2, "--confirmed は --state と一緒のときだけ付けられます", {}
    if "state" in f and f["state"] is not None and f["state"] not in RECORDABLE_STATES:
        return 2, f"状態の値が違います: {f['state']}(書けるのは {'・'.join(RECORDABLE_STATES)})", {}
    if "waiting" in f and f["waiting"] not in WAITINGS:
        return 2, f"待ちの値が違います: {f['waiting']}(書けるのは {'・'.join(WAITINGS)})", {}
    for k in ("done_phase", "last_phase"):
        if k in f and f[k] is not None and (type(f[k]) is not int or not 0 <= f[k] <= 99):
            return 2, f"{k} は 0〜99 の整数です: {f[k]}", {}
    if "note" in f:
        if f["note"] == "":
            f["note"] = None
        n = f["note"]
        if n is not None:
            if len(n) > NOTE_MAX:
                return 2, f"メモは {NOTE_MAX} 文字までです({len(n)} 文字)", {}
            if any(ord(c) < 0x20 or ord(c) == 0x7F for c in n):
                return 2, "メモに改行・タブ・制御文字は入れられません", {}
    folded = ps.folded
    done = f["done_phase"] if "done_phase" in f else folded.done_phase
    last = f["last_phase"] if "last_phase" in f else ps.last_phase
    if done is not None and last is not None and done > last:
        return 2, f"終えたフェーズ {done} が最終フェーズ {last} より大きい", {}
    if "impl_add" in f:
        add = []
        for p in f["impl_add"]:
            if not os.path.isdir(p):
                return 2, f"フォルダがこの PC にありません: {p}", {}
            add.append(slash(os.path.abspath(p)))
        f["impl_add"] = add
    if "impl_remove" in f:
        bound = {norm_path(i.path): i.path for i in folded.impl}
        rem = []
        for p in f["impl_remove"]:
            k = norm_path(os.path.abspath(p) if os.path.isabs(p) else p)
            if k not in bound:
                return 2, f"このプロジェクトに結ばれていないフォルダです: {p}", {}
            rem.append(bound[k])
        f["impl_remove"] = rem
    if by == "claude-code" and f.get("state") in ("実装完了", "撤退") and not f.get("confirmed"):
        return 5, f"Claude Code は「{f['state']}」を --confirmed 無しで付けられません(依頼者が言ったときだけ --confirmed)", {}
    return 0, "", f


def write_mark(board: Board, ps: ProjectStatus, fields: dict, by: str, doc: Doc | None = None) -> tuple[int, str]:
    """§9.8 の検査に通れば1行足す。通らなければ何も書かない(INV-10)。build はしない。"""
    code, msg, f = _check_fields(ps, fields, by)
    if code:
        return code, msg
    doc = doc or ps.project.primary_doc
    obj = {"v": 1, "at": records.now_iso(), "pc": board.pc_name, "by": by, "doc": doc.stem, "path": doc.path}
    obj.update({k: f[k] for k in FIELD_ORDER if k in f})
    reason = records.validate(obj)
    if reason:
        return 2, f"記録の形が違います: {reason}"
    line = records.dumps(obj)
    if len(line.encode("utf-8")) + 1 > LINE_MAX_BYTES:
        return 2, f"記録の1行が {LINE_MAX_BYTES} バイトを超えます"
    try:
        code = records.append(events_dir(board.vault), board.pc_name, line)
    except OSError as e:
        return 2, f"記録ファイルに書けません: {e}"
    return (6, "ロックが取れませんでした(別の mark が書いています)") if code == 6 else (0, "")


# ---- build ----------------------------------------------------------------

def _dup_stems(vault: str) -> set[str]:
    seen: set[str] = set()
    dup: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.lower().endswith(".md"):
                k = fold(fn[:-3])
                (dup if k in seen else seen).add(k)
    return dup


def _replace(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    for i in range(REPLACE_TRIES):
        try:
            os.replace(tmp, path)
            return
        except OSError:
            if i == REPLACE_TRIES - 1:
                raise
            time.sleep(REPLACE_WAIT_S)


def output_paths(board: Board) -> tuple[str, str]:
    """INV-1: 出力2ファイルは <vault>\\<spec_root>\\ の直下だけ。外なら ConfigError。"""
    root = fold(nfc(slash(board.config["vault"]["spec_root"])).strip("/"))
    out = []
    for key in ("board", "json"):
        rel = nfc(slash(board.config["output"][key])).strip("/")
        if os.path.isabs(board.config["output"][key]) or fold(rel.rsplit("/", 1)[0]) != root or "/" not in rel:
            raise ConfigError(f"出力先が {board.config['vault']['spec_root']} の直下ではありません: {rel}")
        out.append(os.path.join(board.vault, rel))
    return out[0], out[1]


def write_outputs(board: Board, now: datetime | None = None) -> None:
    now = now or datetime.now().astimezone()
    md_path, json_path = output_paths(board)
    md = board_markdown(board, now.strftime("%Y-%m-%d %H:%M"), now.date(), _dup_stems(board.vault))
    js = board_json(board, now.isoformat(timespec="seconds"))
    _replace(md_path, md)
    _replace(json_path, js)


def build(vault: str, config_path: str | None) -> tuple[int, str, Board | None]:
    try:
        board = load(vault, config_path)
        write_outputs(board)
    except ConfigError as e:
        return 2, str(e), None
    except OSError as e:
        return 2, f"出力を書けません: {e}", None
    if board.reader_failed:
        names = "・".join(dict.fromkeys(u.reader for u in board.unreadable if u.reader != "find"))
        return 3, f"読めなかった証拠があります: {names}", board
    return 0, "", board


def weekly_path(board: Board, day: date) -> str:
    """週のまとめの置き場所: <vault>/<[weekly] dir>/<その週の金曜>_実装状況.md(週報と同じ日付の付け方)。"""
    rel = (board.config.get("weekly", {}).get("dir") or "").strip()
    if not rel:
        raise ConfigError("設定に [weekly] dir がありません(週のまとめの置き場所)")
    friday = history.week_range(day)[0] + timedelta(days=4)
    return os.path.join(resolve(board.vault, rel), f"{friday.isoformat()}_実装状況.md")


def write_weekly(board: Board, day: date) -> str:
    """週のまとめを書き(同じ週の物は上書き)、パスを返す。書くのは SpecStatus が作ったこのファイルだけ。"""
    path = weekly_path(board, day)
    if not os.path.isdir(os.path.dirname(path)):
        raise ConfigError(f"週のまとめの置き場所がありません: {os.path.dirname(path)}")
    _replace(path, weekly_markdown(board, day, date.today(), _dup_stems(board.vault)))
    return path


def problem_lines(board: Board) -> list[str]:
    """FR-31: check が数える問題。"""
    out = [f"食い違い: {ps.project.name}({ps.project.spec_dir})" for ps in board.statuses if ps.conflict]
    out += [f"記録の問題: {p.file} {p.line} 行目: {p.reason}" for p in board.record_problems]
    out += [f"宛先の無い記録: {o.doc}({o.path}、{o.at}、{o.pc})" for o in board.orphans]
    out += [f"registry の不整合: {i}" for i in board.registry_issues]
    return out


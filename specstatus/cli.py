# CLI のサブコマンド(list / show / where / mark / build / check / weekly / update / gui)の引数を読み、core を呼んで結果を出す(§9.1)。
# 書き込みは mark と build が core 経由で行うだけ。終了コードは §9.7。
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

from . import core, render
from .config import ConfigError, load_config
from .model import STATES, Board, ProjectStatus
from .textutil import fold, norm_path

HOOK_MAX = 5
HISTORY_DEFAULT = 5
CANDIDATES_MAX = 10
DEFAULT_JSON = "仕様書MDファイル/00_実装状況.json"


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--vault")
    common.add_argument("--config")
    ap = argparse.ArgumentParser(prog="specstatus.py", description="仕様書の実装状況ボード")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", parents=[common])
    p.add_argument("--state", action="append", choices=STATES, default=[])
    p.add_argument("--waiting", action="store_true")
    p.add_argument("--conflict", action="store_true")
    p.add_argument("--stale", action="store_true")
    p.add_argument("--changed", action="store_true")
    p.add_argument("--vuln", action="store_true")
    p.add_argument("--os")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("show", parents=[common])
    p.add_argument("target")
    p.add_argument("--history", type=int, default=HISTORY_DEFAULT)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("where", parents=[common])
    p.add_argument("folder", nargs="?")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--json", action="store_true")
    g.add_argument("--hook", action="store_true")

    p = sub.add_parser("mark", parents=[common])
    p.add_argument("target")
    p.add_argument("--state")
    p.add_argument("--done-phase", type=int)
    p.add_argument("--last-phase", type=int)
    p.add_argument("--waiting")
    p.add_argument("--note")
    p.add_argument("--impl", action="append", default=[])
    p.add_argument("--unimpl", action="append", default=[])
    p.add_argument("--clear-state", action="store_true")
    p.add_argument("--by", default="user")
    p.add_argument("--confirmed", action="store_true")
    p.add_argument("--no-build", action="store_true")

    p = sub.add_parser("weekly", parents=[common])
    p.add_argument("--date", type=date.fromisoformat, default=None, help="この日を含む週(既定は今日)")
    p.add_argument("--write", action="store_true", help="標準出力でなく [weekly] dir に書く")

    p = sub.add_parser("update", parents=[common])
    p.add_argument("--check", action="store_true", help="確かめるだけ(入れ替えない)")

    for name in ("build", "check", "gui"):
        sub.add_parser(name, parents=[common])
    return ap


def _out(s: str = "") -> None:
    print(s)


def _err(s: str) -> None:
    print(s, file=sys.stderr)


def _history(ps: ProjectStatus, n: int) -> list[dict]:
    hide = {"v", "doc", "path"}
    return [{k: v for k, v in r.fields.items() if k not in hide} for r in reversed(ps.folded.history[-n:] if n > 0 else [])]


def _show(board: Board, ps: ProjectStatus, n: int, as_json: bool) -> None:
    hist = _history(ps, n)
    if as_json:
        obj = render.project_json(ps)
        obj["history"] = hist
        _out(json.dumps(obj, ensure_ascii=False, indent=2))
        return
    p = ps.project
    _out(f"{p.name}  ({p.spec_dir})")
    _out(f"状態: {ps.state}  根拠: {render.source_text(ps.decided_by)} {ps.decided_by['path']}".rstrip())
    _out(f"Phase: {render.phase_text(ps)}  最終フェーズ: {ps.last_phase if ps.last_phase is not None else '?'}  待ち: {ps.waiting}")
    _out(f"メモ: {ps.folded.note or ''}")
    _out("文書:")
    for d in p.docs:
        _out(f"  {d.kind}  {d.path}  作成日 {d.created or '-'}")
    _out("実装フォルダ:")
    for i in ps.folded.impl:
        _out(f"  {i.path}" + ("" if i.exists_here else f"  (この PC に無い・{i.pc})"))
    for e in ps.evidence + [core._decided_ev(ps)]:
        if e.source == "implroot":
            _out(f"  {e.value}  (名前の一致)")
    _out("証拠(決めた根拠以外):")
    for e in ps.evidence:
        flag = "  ← 食い違い" if e in ps.conflicts else ""
        note = f"  ({e.note})" if e.note else ""
        _out(f"  {render.evidence_text(e)}  {e.where}{note}{flag}")
    _out(f"開発ログの最新: {ps.last_devlog_date or '-'}")
    if ps.last_activity:
        _out(f"最後に動いた日: {ps.last_activity}" + (f"  ({ps.stale_days} 日止まっている)" if ps.stale_days else ""))
    if ps.ac:
        _out(f"受け入れ基準: {render.ac_text(ps)} にチェック")
    if ps.spec_changed:
        _out(f"仕様書の更新: {ps.spec_changed}(最後の記録より後)")
    if ps.vulns:
        v = ps.vulns
        _out(f"依存の脆弱性: {v['count']} / {v['total']} 件  " + " / ".join(v["packages"]))
    if ps.github:
        g = ps.github
        _out(f"GitHub: {g['repo']}  版 {g['release'] or '-'}  最後の push {g['pushed_at']}  CI {g['ci'] or '-'}  {g['url']}")
    _out(f"記録の履歴(新しい順・{len(hist)} 件):")
    for h in hist:
        _out("  " + json.dumps(h, ensure_ascii=False))


def _candidates(cands: list[ProjectStatus]) -> None:
    _err("宛先が1つに決まりません。候補:" if cands else "宛先に当たる仕様書がありません。")
    for ps in cands[:CANDIDATES_MAX]:
        _err(f"  {ps.project.name}  ({ps.project.spec_dir})")
        for d in ps.project.spec_docs:
            _err(f"    {d.path}")


def _where_hook(vault: str, config_path: str | None, folder: str) -> int:
    """FR-29: 出力済みの JSON だけを読む。何があっても終了コード 0。"""
    try:
        rel = DEFAULT_JSON
        try:
            rel = load_config(vault, config_path)["output"]["json"]
        except ConfigError:
            pass
        with open(os.path.join(vault, rel), encoding="utf-8") as f:
            data = json.load(f)
        here = norm_path(os.path.realpath(folder))
        lines = []
        for p in data.get("projects", []):
            for i in p.get("impl_paths", []):
                root = norm_path(os.path.realpath(i["path"]))
                if here == root or here.startswith(root + "/"):
                    ph = "-" if p.get("done_phase") is None else f"{p['done_phase']}/{p.get('last_phase') or '?'}"
                    lines.append(f"SpecStatus: {p['name']}({p['spec_dir']}) 状態 {p['state']} / Phase {ph} / 待ち {p.get('waiting', 'なし')}")
                    break
        for ln in lines[:HOOK_MAX]:
            _out(ln)
    except Exception:
        pass
    return 0


def _mark_fields(a) -> dict | str:
    f: dict = {}
    if a.state is not None and a.clear_state:
        return "--state と --clear-state は一緒に付けられません"
    if a.state is not None:
        f["state"] = a.state
    if a.clear_state:
        f["state"] = None
    for k in ("done_phase", "last_phase", "waiting", "note"):
        v = getattr(a, k)
        if v is not None:
            f[k] = v
    if a.impl:
        f["impl_add"] = a.impl
    if a.unimpl:
        f["impl_remove"] = a.unimpl
    if a.confirmed:
        f["confirmed"] = True
    return f


def _update(vault: str, check_only: bool) -> int:
    """vault の spec-status を GitHub の最新の Release にする。0=最新か入れ替えた、1=新しい版あり(--check)、2=失敗。"""
    from . import update
    try:
        rel = update.latest(force=True)
    except update.UpdateError as e:
        _err(str(e))
        return 2
    have = update.vault_version(vault)
    _out(f"最新: {rel['tag']}  vault: {'v' + have if have else '(版が分からない)'}  {rel['url']}")
    if not update.is_newer(rel["tag"], have):
        _out("vault の SpecStatus は最新です。")
        return 0
    if check_only:
        _out(f"{rel['tag']} に更新できます(specstatus.py update)。")
        return 1
    try:
        _out(update.update_vault(vault, rel["tag"]))
    except (update.UpdateError, OSError) as e:
        _err(f"更新できませんでした: {e}")
        return 2
    return 0


def main(argv: list[str] | None = None, default_vault: str | None = None) -> int:
    a = _parser().parse_args(argv)
    vault = os.path.abspath(a.vault or default_vault or ".")

    if a.cmd == "where" and a.hook:
        return _where_hook(vault, a.config, a.folder or os.getcwd())
    if a.cmd == "gui":
        from . import gui
        return gui.run(vault, a.config)
    if a.cmd == "build":
        code, msg, _ = core.build(vault, a.config)
        if msg:
            _err(msg)
        return code
    if a.cmd == "update":
        return _update(vault, a.check)

    try:
        board = core.load(vault, a.config)
    except ConfigError as e:
        _err(str(e))
        return 2
    read_code = 3 if board.reader_failed else 0
    if board.reader_failed:
        _err("読めなかった証拠: " + " / ".join(f"{u.reader}({u.reason})" for u in board.unreadable if u.reader != "find"))
    for note in (board.github_note, board.osv_note):
        if note:
            _err(note)

    if a.cmd == "list":
        rows = board.statuses
        if a.state:
            rows = [p for p in rows if p.state in a.state]
        if a.waiting:
            rows = [p for p in rows if p.waiting != "なし"]
        if a.conflict:
            rows = [p for p in rows if p.conflict]
        if a.stale:
            rows = [p for p in rows if p.stale_days]
        if a.changed:
            rows = [p for p in rows if p.spec_changed]
        if a.vuln:
            rows = [p for p in rows if p.vulns and p.vulns["count"]]
        if a.os:
            rows = [p for p in rows if fold(render.os_dir(p)) == fold(a.os)]
        _out(json.dumps([render.project_json(p) for p in rows], ensure_ascii=False, indent=2) if a.json
             else render.table(rows))
        return read_code

    if a.cmd == "show":
        ps, cands = core.resolve_target(board, a.target)
        if ps is None:
            _candidates(cands)
            return 4
        _show(board, ps, a.history, a.json)
        return read_code

    if a.cmd == "where":
        hits = core.where(board, a.folder or os.getcwd())
        if a.json:
            _out(json.dumps([render.project_json(p) for p in hits], ensure_ascii=False, indent=2))
        else:
            for p in hits:
                _out(f"{p.project.name}  ({p.project.spec_dir})  {p.state}  Phase {render.phase_text(p)}  待ち {p.waiting}")
            if not hits:
                _out("このフォルダを実装フォルダにしているプロジェクトはありません。")
        return read_code

    if a.cmd == "check":
        lines = core.problem_lines(board)
        for ln in lines:
            _out(ln)
        _out(f"問題 {len(lines)} 件")
        return 1 if lines else read_code

    if a.cmd == "weekly":
        day = a.date or date.today()
        if not a.write:
            _out(render.weekly_markdown(board, day, date.today(), core._dup_stems(board.vault)))
            return read_code
        try:
            _out(f"書きました: {core.write_weekly(board, day)}")
        except ConfigError as e:
            _err(str(e))
            return 2
        except OSError as e:
            _err(f"週のまとめを書けません: {e}")
            return 2
        return read_code

    if a.cmd == "mark":
        fields = _mark_fields(a)
        if isinstance(fields, str):
            _err(fields)
            return 2
        ps, doc, cands = core._resolve(board, a.target)
        if ps is None:
            _candidates(cands)
            return 4
        code, msg = core.write_mark(board, ps, fields, a.by, doc)
        if code:
            _err(msg)
            return code
        _out(f"記録しました: {ps.project.name}")
        if a.no_build:
            return 0
        code, msg, _ = core.build(vault, a.config)
        if msg:
            _err(msg + ("(記録の1行は書いてあります)" if code == 2 else ""))
        return code
    return 2

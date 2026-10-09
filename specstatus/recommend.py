# 今日手を付けるとよい物を点数で選ぶ(待ち・脆弱な依存・仕様の変更・止まり・一部未実装・AC の進み・食い違い・
# 記録漏れ・撤退の判定・回答待ち。前提が未完なら下げる)。
# 一覧ノートの「## 今日のおすすめ」の行も作る。点の重みは下の定数(仮決め)。
from __future__ import annotations

from datetime import date
from typing import Callable

from .model import ProjectStatus

W_WAITING = 50              # 確認待ち・実物待ち
W_WAITING_PER_DAY = 1       # 待っている日数(最後の記録から)1日ごと
W_WAITING_DAYS_MAX = 30
W_VULN_EACH = 5             # 脆弱な依存1つごと
W_VULN_MAX = 25
W_SEVERITY = {"重大": 40, "高": 25, "中": 10, "低": 5, "不明": 5}   # 一番重い深刻度
W_SPEC_CHANGED = 30
W_STALE_PER_DAY = 1         # 止まっている日数1日ごと
W_STALE_MAX = 30
W_PARTIAL = 15              # 一部未実装
W_AC_PROGRESS = 20          # 着手済で AC が進んでいる(済の割合を掛ける)
W_CONFLICT = 10
W_GAP = 15                  # 記録漏れかも(最後の記録の後に git・開発ログ)
W_RETREAT_DUE = 25          # 撤退の判定の時期に来た
W_QUESTION_MINE_EACH = 5    # 回答者が「私」の未確定事項1つごと
W_QUESTION_MINE_MAX = 25
W_BLOCKED = -30             # 前提の仕様書が終わっていない(下げる)
QUESTION_STATES = ("着手済", "一部未実装")   # 回答待ちを点にする状態(未着手まで入れると大半に付いてうるさい)
SKIP_STATES = ("撤退", "証拠なし")
SEPARATOR = "・"
EXPLAIN = "待ち・脆弱な依存・仕様の変更・止まっている日数などを点にして、高い順に並べた物。"


def _waited_days(ps: ProjectStatus, today: date) -> int:
    r = ps.folded.last_record
    return max(0, (today - date.fromisoformat(r.at[:10])).days) if r else 0


def score(ps: ProjectStatus, today: date) -> tuple[int, list[str]]:
    """(点, 理由)。理由は短い日本語。"""
    pts, why = 0, []
    if ps.waiting in ("確認待ち", "実物待ち"):
        days = _waited_days(ps, today)
        pts += W_WAITING + min(days, W_WAITING_DAYS_MAX) * W_WAITING_PER_DAY
        why.append(f"{ps.waiting}({days}日)" if days else ps.waiting)
    v = ps.vulns or {}
    if v.get("count"):
        worst = v.get("worst") or "不明"
        pts += min(v["count"] * W_VULN_EACH, W_VULN_MAX) + W_SEVERITY.get(worst, 0)
        why.append(f"脆弱な依存 {v['count']}件" + (f"({worst})" if worst != "不明" else ""))
    if ps.spec_changed:
        pts += W_SPEC_CHANGED
        why.append(f"仕様が変わった({ps.spec_changed[5:]})")
    if ps.stale_days:
        pts += min(ps.stale_days, W_STALE_MAX) * W_STALE_PER_DAY
        why.append(f"{ps.stale_days}日止まっている")
    if ps.state == "一部未実装":
        pts += W_PARTIAL
        why.append("一部未実装")
    ac = ps.ac
    if ps.state == "着手済" and ac and 0 < ac[0] < ac[1]:
        pts += round(W_AC_PROGRESS * ac[0] / ac[1])
        why.append(f"AC {ac[0]}/{ac[1]}")
    if ps.conflict:
        pts += W_CONFLICT
        why.append("食い違い")
    if ps.gap:
        pts += W_GAP
        why.append("記録漏れかも")
    if (ps.retreat or {}).get("due"):
        pts += W_RETREAT_DUE
        why.append("撤退の判定の時期")
    mine = (ps.questions or {}).get("mine", 0)
    if mine and ps.state in QUESTION_STATES:
        pts += min(mine * W_QUESTION_MINE_EACH, W_QUESTION_MINE_MAX)
        why.append(f"あなたの回答待ち {mine}")
    if ps.blocked_by and pts > 0:
        pts = max(pts + W_BLOCKED, 1)
        why.append("前提が未完: " + SEPARATOR.join(ps.blocked_by))
    return pts, why


def recommend(statuses: list[ProjectStatus], today: date, limit: int = 5) -> list[tuple[ProjectStatus, int, list[str]]]:
    """点の高い順(同点は名前順)に limit 件。撤退・証拠なし・点の無い物(実装完了で何も無い物など)は出さない。"""
    out = []
    for ps in statuses:
        if ps.state in SKIP_STATES:
            continue
        pts, why = score(ps, today)
        if pts > 0:
            out.append((ps, pts, why))
    out.sort(key=lambda t: (-t[1], t[0].project.name.casefold(), t[0].project.key))
    return out[:limit]


def _cell(s: str) -> str:
    return s.replace("|", "\\|")


def section(statuses: list[ProjectStatus], today: date, link: Callable[[ProjectStatus], str]) -> list[str]:
    """一覧ノートの「## 今日のおすすめ(n)」の行。"""
    rows = recommend(statuses, today)
    out = [f"## 今日のおすすめ({len(rows)})", "", EXPLAIN, "",
           "| プロジェクト | 状態 | 理由 |", "|---|---|---|"]
    out += [f"| {link(ps)} | {ps.state} | {_cell(SEPARATOR.join(why))} |" for ps, _pts, why in rows]
    return out

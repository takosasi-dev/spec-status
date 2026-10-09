# 時間の流れを見る: ある日の状態の復元・週ごとの推移・止まっている物(最後に動いた日)・仕様書の書き換え・週の範囲。
# 状態の復元は記録(history)だけを使い、記録の無い時期は記録以外の証拠の状態とみなす(日付の無い証拠のため近似)。
from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Callable

from .model import ProjectStatus

DOING = ("着手済", "一部未実装")
BUILT = ("実装完了", "一部未実装")      # 仕様書の書き換えを見る状態
CHANGE_GRACE_S = 60                     # 記録と同じ作業で仕様書を直した分は数えない
GIT_TIMEOUT_S = 5
GIT_WORKERS = 8                         # git log を同時に走らせる数
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # 窓の exe から呼んでも黒い窓を出さない


def _baseline(ps: ProjectStatus) -> str | None:
    """記録が無いときの状態 = 記録以外の証拠で決まる状態。"""
    if ps.decided_by["source"] not in ("events", "none"):
        return ps.state
    return next((e.state for e in ps.evidence if e.source != "events" and e.state), None)


def state_at(ps: ProjectStatus, day: str) -> str | None:
    """day(YYYY-MM-DD)の終わりの状態。今日以降なら今の状態。"""
    state, found = None, False
    for r in ps.folded.history:
        if r.at[:10] > day:
            break
        if "state" in r.fields:
            state, found = r.fields["state"], True
    if found and state is not None:
        return state
    return _baseline(ps)


def series(statuses: list[ProjectStatus], today: date, weeks: int) -> list[tuple[str, int, int]]:
    """週ごと(今日から7日刻みでさかのぼる)の (日付 YYYY-MM-DD, 実装完了の数, 途中の数)。古い順。最後は今の状態。"""
    out = []
    for i in range(weeks - 1, -1, -1):
        day = (today - timedelta(days=7 * i)).isoformat()
        states = [ps.state if i == 0 else state_at(ps, day) for ps in statuses]
        out.append((day, states.count("実装完了"), sum(s in DOING for s in states)))
    return out


def week_range(day: date) -> tuple[date, date]:
    """day を含む月曜〜日曜。"""
    mon = day - timedelta(days=day.weekday())
    return mon, mon + timedelta(days=6)


def git_last_date(path: str) -> str | None:
    """path の git の最後のコミット日(YYYY-MM-DD)。git でない・git が無いなら None。"""
    try:
        r = subprocess.run(["git", "-c", "safe.directory=*", "-C", path, "log", "-1", "--format=%cs"],
                           capture_output=True, text=True, timeout=GIT_TIMEOUT_S, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and len(out) == 10 else None


def impl_dirs(ps: ProjectStatus) -> list[str]:
    """この PC にある実装フォルダ(記録と、名前の一致の証拠)。"""
    paths = [i.path for i in ps.folded.impl if i.exists_here]
    paths += [e.value for e in ps.evidence if e.source == "implroot"]
    if ps.decided_by["source"] == "implroot":
        paths.append(ps.decided_by["value"])
    return list(dict.fromkeys(paths))


def mark_spec_changed(statuses: list[ProjectStatus], mtime: Callable[[str], float] = os.path.getmtime) -> None:
    """実装完了・一部未実装で、最後の記録より後に仕様書(付属を除く)が書き換えられていれば、その日を spec_changed に入れる。
    記録をもう1行足す(状態を付け直す・待ちを変える等)と消える。"""
    for ps in statuses:
        r = ps.folded.last_record
        if ps.state not in BUILT or r is None:
            continue
        since = datetime.fromisoformat(r.at).timestamp() + CHANGE_GRACE_S
        times = []
        for d in ps.project.spec_docs:
            try:
                times.append(mtime(d.abs_path))
            except OSError:
                pass
        newest = max(times, default=0.0)
        if newest > since:
            ps.spec_changed = datetime.fromtimestamp(newest).date().isoformat()


def git_dates(paths: list[str], git_date: Callable[[str], str | None] = git_last_date) -> dict[str, str | None]:
    """フォルダごとの git の最後のコミット日。git は1本ずつ待つと遅いので、まとめて並列に走らせる(同じフォルダは1回)。"""
    uniq = list(dict.fromkeys(paths))
    if len(uniq) <= 1:
        return {p: git_date(p) for p in uniq}
    with ThreadPoolExecutor(max_workers=min(GIT_WORKERS, len(uniq))) as ex:
        return dict(zip(uniq, ex.map(git_date, uniq)))


def mark_stale(statuses: list[ProjectStatus], today: date, stale_days: int,
               git_date: Callable[[str], str | None] = git_last_date) -> None:
    """途中(着手済・一部未実装)の物に最後に動いた日を付け、stale_days 日以上動いていなければ stale_days に日数を入れる。"""
    doing = [ps for ps in statuses if ps.state in DOING]
    gits = git_dates([p for ps in doing for p in impl_dirs(ps)], git_date)
    for ps in doing:
        r = ps.folded.last_record
        dates = [r.at[:10] if r else None, ps.last_devlog_date] + [gits[p] for p in impl_dirs(ps)]
        dates = [d for d in dates if d]
        if not dates:
            continue
        ps.last_activity = max(dates)
        days = (today - date.fromisoformat(ps.last_activity)).days
        if days >= stale_days:
            ps.stale_days = days

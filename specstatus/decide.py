# §9.4 の規則で、記録と証拠からプロジェクトの状態を1つ決め、根拠・使わなかった証拠・食い違いを残す(FR-24・FR-25)。
# 入力を受けて結果を返すだけの純関数。
from __future__ import annotations

from .model import Evidence, Folded, Project, ProjectStatus

ADVANCED = ("実装完了", "一部未実装")


def _record_where(folded: Folded) -> str:
    r = folded.state_record
    return f"spec-status/data/events/{r.file}#L{r.line}" if r else ""


def decide(project: Project, folded: Folded, found: dict[str, list[Evidence]]) -> ProjectStatus:
    """found: 出所(setsumei / tooldeck / implroot / handoff / devlog) -> そのプロジェクトの証拠。"""
    ordered: list[Evidence] = []          # §9.4 の順に並べた候補
    if folded.state is not None:
        ordered.append(Evidence("events", folded.state, folded.state, _record_where(folded)))
    ordered += found.get("setsumei", [])
    ordered += found.get("tooldeck", [])
    handoff = found.get("handoff", [])
    ordered += [e for e in handoff if e.state == "未着手"]
    if folded.impl:
        last = folded.history[-1] if folded.history else None
        ordered.append(Evidence("events", "着手済", folded.impl[0].path,
                                f"spec-status/data/events/{last.file}#L{last.line}" if last else ""))
    ordered += found.get("implroot", [])
    ordered += [e for e in handoff if e.state != "未着手"]

    decided = next((e for e in ordered if e.state is not None), None)
    if decided is None:
        state, by = "証拠なし", {"source": "none", "value": "", "path": ""}
        rest = ordered
    else:
        state = decided.state
        by = {"source": decided.source, "value": decided.value, "path": decided.where}
        rest = [e for e in ordered if e is not decided]

    conflicts = [e for e in rest if e.state is not None and e.state != state
                 and not (state in ADVANCED and e.state == "着手済")]
    devlog = found.get("devlog", [])
    return ProjectStatus(project=project, state=state, decided_by=by, evidence=rest,
                         conflicts=conflicts, folded=folded,
                         last_devlog_date=devlog[0].value if devlog else None)

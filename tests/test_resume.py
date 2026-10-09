# 再開の指示文(resume)のテスト: 最初の行、次のフェーズ、未チェックの AC、未回答の Q、差分、行数の上限。
from __future__ import annotations

from specstatus import resume as R
from specstatus import snapshots

from test_guilogic import ps

SPEC = """\
# A 仕様書
## 12. 実装フェーズ
| Phase | 内容 | 完了条件 |
|---|---|---|
| 0 | 実物を集める | AC-1 |
| 1 | 読み取りを作る | AC-2 |
| 2 | 画面を作る | AC-3 |

### Phase 2 の補足
画面は1枚。
## 13. 未確定事項
| # | 内容 | 回答者 |
|---|---|---|
| Q-1 | 名前 | 私 |
| Q-2 | 済んだ。**回答済** | 私 |
## 14. 受け入れ基準
- [x] AC-1: 集めた
- [ ] AC-2: 読める
- [ ] **AC-3**: 見える
"""


def test_prompt_contents(tmp_path):
    p = ps("A", "W/A", "着手済", done=1, last=2, waiting="確認待ち")
    p.folded.note = "Phase 1 まで"
    text = R.prompt(p, read=lambda path: SPEC, folder=str(tmp_path))
    lines = text.splitlines()
    assert lines[0] == R.FIRST_LINE
    assert f"仕様書: {p.project.primary_doc.abs_path}" in lines
    assert "状態: 着手済 / 待ち: 確認待ち / 終えたフェーズ: 1(全 2)" in lines
    assert "最後のメモ: Phase 1 まで" in lines
    assert "| 2 | 画面を作る | AC-3 |" in lines
    assert "### Phase 2 の補足" in lines and "画面は1枚。" in lines
    assert "- [ ] AC-2: 読める" in lines and "- [ ] **AC-3**: 見える" in lines
    assert "- [x] AC-1: 集めた" not in lines
    assert "| Q-1 | 名前 | 私 |" in lines and not any("Q-2" in ln for ln in lines)
    assert "記録した後に仕様書が変わった所:" not in lines                # 写しが無い


def test_prompt_diff_and_limit(tmp_path):
    spec = tmp_path / "A_仕様書.md"
    spec.write_text("old\n", encoding="utf-8")
    p = ps("A", "W/A", "着手済")
    p.project.docs[0].abs_path = str(spec)
    snapshots.save(p, str(tmp_path / "snap"))
    spec.write_text("new\n" + "".join(f"- [ ] AC-{i}: x\n" for i in range(50)), encoding="utf-8")
    full = R.prompt(p, max_lines=200, folder=str(tmp_path / "snap")).splitlines()
    assert "記録した後に仕様書が変わった所:" in full and "+new" in full
    short = R.prompt(p, max_lines=12, folder=str(tmp_path / "snap")).splitlines()
    assert len(short) == 12 and short[-1] == R.CUT

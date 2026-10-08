# 合成の vault で、発見・まとめ・状態の決め方・mark・build・check・where・deploy を CLI と core から確かめる。
# AC-4・AC-5・AC-8〜AC-11・AC-14〜AC-16・AC-18・AC-20・AC-21・AC-23・AC-24・AC-26〜AC-30・AC-34・AC-35。
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from specstatus import cli, core, find  # noqa: E402

SPEC = "仕様書MDファイル"
DEV = "Windows/Claude・開発ツール"


def w(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


def spec_doc(title: str, created: str = "2026-09-26", phases: int | None = 3, body: str = "") -> str:
    s = f"---\ntags:\n  - 仕様書\n作成日: {created}\n---\n# {title}\n\n{body}\n"
    if phases is not None:
        rows = "\n".join(f"| {i} | 内容 | - | - |" for i in range(phases + 1))
        s += f"\n## 12. 実装フェーズ\n\n説明\n\n| Phase | 内容 | 開始 | 完了 |\n|---|---|---|---|\n{rows}\n"
    return s


def make_config(vault: Path, tooldeck: str = "", implroots: list[str] | None = None, handoff: str = "",
                board: str = f"{SPEC}/00_実装状況.md") -> str:
    roots = ", ".join(f'"{Path(r).as_posix()}"' for r in (implroots or []))
    text = f'''
[pc]
name = "pc"
[vault]
spec_root = "{SPEC}"
exclude_dirs = ["{DEV}/Claude_skill"]
exclude_files = ["{SPEC}/00_OS別の整理について.md"]
[docs]
kinds = [
  ["非機能要件定義書", "非機能要件"],
  ["要件定義書", "要件定義|(?i:requirements)"],
  ["画面設計書", "画面設計|(?i:(?:^|[_-])ui[_-]design)"],
  ["設計書", "設計書|(?i:(?:^|[_-])design(?:[_-]|$))"],
  ["仕様書", "仕様書|(?i:(?:^|[_-])spec(?:[_-]|$))"],
  ["プロンプト", "指示書|指示プロンプト|(?i:(?:^|[_-])prompt)"],
]
support = ["README.md", "CLAUDE.md", "HANDOFF.md"]
[evidence.setsumei]
dir = "説明書/Claude開発ツールについて"
scope = ["{DEV}"]
map = {{ "実装完了" = "実装完了", "一部未実装" = "一部未実装", "導入済み" = "実装完了" }}
[evidence.tooldeck]
toml = "{Path(tooldeck).as_posix() if tooldeck else ''}"
scope = ["{DEV}"]
map = {{ "実装完了" = "実装完了", "一部未実装" = "一部未実装" }}
[evidence.implroot]
roots = [{roots}]
markers = ["NOTES.md"]
scope = ["{DEV}"]
[evidence.handoff]
handoffstub_toml = "{Path(handoff).as_posix() if handoff else ''}"
memo_dir = "引き続きメモ"
scope = [""]
[evidence.devlog]
dir = "開発ログ"
scope = [""]
[output]
board = "{board}"
json = "{SPEC}/00_実装状況.json"
[board]
recent_days = 7
recent_max = 20
[gui]
copy_template = "仕様書: {{abs_path}}"
'''
    p = vault / "spec-status" / "data" / "config" / "pc.toml"
    w(p, text)
    return str(p)


@pytest.fixture
def vault(tmp_path):
    v = tmp_path / "vault"
    (v / "説明書" / "Claude開発ツールについて").mkdir(parents=True)
    (v / "開発ログ").mkdir()
    s = v / SPEC
    w(s / "00_OS別の整理について.md", "# 整理\n")
    w(s / DEV / "Alpha" / "Alpha_道具_仕様書.md", spec_doc("Alpha — 実装仕様書 v2"))
    w(s / DEV / "Beta" / "Beta_仕様書.md", spec_doc("Beta 仕様書"))
    w(s / "Android" / "App" / "App_仕様書.md", spec_doc("App 仕様書", phases=5))
    w(s / "Android" / "App" / "README.md", "# readme\n")
    w(s / "OS非依存" / "A" / "dup_prompt.md", "# Dup プロンプト\n")
    w(s / "OS非依存" / "B" / "dup_prompt.md", "# Dup プロンプト\n")
    return v


def run(vault, cfg, *args):
    return cli.main([*args, "--vault", str(vault), "--config", cfg])


def events(vault) -> list[dict]:
    p = vault / "spec-status" / "data" / "events" / "pc.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def st(vault, cfg, name):
    b = core.load(str(vault), cfg)
    return next(p for p in b.statuses if p.project.name == name)


# ---- Phase 1 --------------------------------------------------------------

def test_product_created_phase():  # AC-4
    assert find.product_name(["# X — 実装仕様書 v2"], "s") == "X"
    assert find.product_name(["# Todoウィジェット 仕様書"], "s") == "Todoウィジェット"
    assert find.product_name(["本文"], "abc_def_仕様書") == "abc"
    assert find.created_date({"作成日": "2026-09-26"}) == "2026-09-26"
    assert find.created_date({}) is None
    body = spec_doc("X", phases=4).splitlines()
    assert find.last_phase(body) == 4
    assert find.last_phase(["# X", "本文"]) is None


def test_grouping_merge_include_exclude(vault):  # AC-5
    s = vault / SPEC
    w(s / "Android" / "Two" / "One_仕様書.md", spec_doc("One 仕様書"))
    w(s / "Android" / "Two" / "Other_仕様書.md", spec_doc("Other 仕様書"))
    w(s / "Android" / "OnlyReadme" / "README.md", "# r\n")
    w(s / "Android" / "OnlyIndex" / "00_索引.md", "# i\n")
    w(s / "Android" / "Extra" / "メモ書き.md", "# Extra 仕様書\n")
    w(s / "Android" / "Two" / "Not_仕様書.md", "# Not\n")
    cfg = make_config(vault)
    b = core.load(str(vault), cfg)
    names = {p.project.name for p in b.statuses if p.project.spec_dir == "Android/Two"}
    assert names == {"One", "Other", "Not"}
    assert "Android/OnlyReadme" in b.folders_without_specs
    assert "Android/OnlyIndex" not in b.folders_without_specs
    assert "Android/Extra" in b.folders_without_specs
    app = next(p for p in b.statuses if p.project.name == "App")
    assert [d.kind for d in app.project.docs] == ["仕様書", "付属"]

    w(vault / "spec-status" / "data" / "registry.toml", f'''
[[merge]]
name = "Two"
spec_dirs = ["Android/Two"]
[[include]]
path = "{SPEC}/Android/Extra/メモ書き.md"
kind = "仕様書"
[[exclude]]
path = "{SPEC}/Android/Two/Not_仕様書.md"
''')
    b = core.load(str(vault), cfg)
    two = [p for p in b.statuses if p.project.spec_dir == "Android/Two"]
    assert [p.project.name for p in two] == ["Two"] and len(two[0].project.docs) == 2
    assert any(p.project.name == "Extra" for p in b.statuses)
    assert "Android/Extra" not in b.folders_without_specs
    assert b.registry_issues == []


# ---- Phase 2: 状態 ----------------------------------------------------------

def test_no_evidence(vault):  # AC-8
    ps = st(vault, make_config(vault), "App")
    assert ps.state == "証拠なし" and ps.decided_by["source"] == "none"


def tooldeck_toml(tmp_path, **states) -> str:
    body = "".join(f'[[tool]]\nid = "{k}"\nstate = "{v}"\n' for k, v in states.items())
    return str(w(tmp_path / "tools.toml", body))


def test_conflict_and_check(vault, tmp_path, capsys):  # AC-9
    w(vault / "説明書" / "Claude開発ツールについて" / "Alpha.md", "---\n状態: 実装完了\n---\n# a\n")
    cfg = make_config(vault, tooldeck=tooldeck_toml(tmp_path, Alpha="一部未実装"))
    ps = st(vault, cfg, "Alpha")
    assert ps.state == "実装完了" and ps.conflict
    assert run(vault, cfg, "check") == 1


def test_reader_exception(vault, tmp_path, monkeypatch):  # AC-10
    w(vault / "説明書" / "Claude開発ツールについて" / "Alpha.md", "---\n状態: 実装完了\n---\n")
    cfg = make_config(vault, tooldeck=tooldeck_toml(tmp_path, Alpha="実装完了"))
    from specstatus.evidence import tooldeck

    def boom(*a):
        raise RuntimeError("壊れた")
    monkeypatch.setattr(tooldeck, "read", boom)
    b = core.load(str(vault), cfg)
    assert next(p for p in b.statuses if p.project.name == "Alpha").state == "実装完了"
    assert any(u.reader == "tooldeck" for u in b.unreadable)
    assert run(vault, cfg, "build") == 3


def test_empty_and_missing_paths(vault, tmp_path):  # AC-11
    cfg = make_config(vault)
    b = core.load(str(vault), cfg)
    assert b.unreadable == [] and set(b.skipped_evidence) >= {"tooldeck", "implroot", "handoff"}
    assert run(vault, cfg, "build") == 0
    cfg = make_config(vault, tooldeck=str(tmp_path / "nothing.toml"))
    assert run(vault, cfg, "build") == 3
    assert any(u.reader == "tooldeck" for u in core.load(str(vault), cfg).unreadable)


def test_conflict_rules(vault, tmp_path):  # AC-21
    w(vault / "説明書" / "Claude開発ツールについて" / "Alpha.md", "---\n状態: 実装完了\n---\n")
    roots = tmp_path / "impl"
    w(roots / "Alpha" / "NOTES.md", "x")
    cfg = make_config(vault, implroots=[str(roots)])
    ps = st(vault, cfg, "Alpha")
    assert ps.state == "実装完了" and not ps.conflict
    assert run(vault, cfg, "mark", "Alpha", "--state", "着手済", "--no-build") == 0
    ps = st(vault, cfg, "Alpha")
    assert ps.state == "着手済" and ps.decided_by["source"] == "events" and ps.conflict


def test_clear_state(vault):  # AC-24
    w(vault / "説明書" / "Claude開発ツールについて" / "Alpha.md", "---\n状態: 一部未実装\n---\n")
    cfg = make_config(vault)
    run(vault, cfg, "mark", "Alpha", "--state", "撤退", "--no-build")
    run(vault, cfg, "mark", "Beta", "--state", "未着手", "--no-build")
    assert st(vault, cfg, "Alpha").state == "撤退"
    run(vault, cfg, "mark", "Alpha", "--clear-state", "--no-build")
    run(vault, cfg, "mark", "Beta", "--clear-state", "--no-build")
    assert st(vault, cfg, "Alpha").state == "一部未実装"
    assert st(vault, cfg, "Beta").state == "証拠なし"


# ---- Phase 2: mark --------------------------------------------------------

@pytest.mark.parametrize("args", [
    ["--state", "証拠なし"], ["--waiting", "保留"], ["--done-phase", "5", "--last-phase", "3"],
    ["--note", "あ" * 201], ["--note", "a\nb"], ["--impl", "Z:/無いフォルダ/x"], ["--unimpl", "C:/x"],
    [], ["--confirmed"], ["--state", "着手済", "--clear-state"], ["--done-phase", "4"],
])
def test_mark_rejects(vault, args):  # AC-14(App の最終フェーズは仕様書の表から 5、Alpha は 3)
    cfg = make_config(vault)
    run(vault, cfg, "mark", "Alpha", "--note", "最初", "--no-build")
    p = vault / "spec-status" / "data" / "events" / "pc.jsonl"
    before = p.read_bytes()
    assert run(vault, cfg, "mark", "Alpha", *args, "--no-build") == 2
    assert p.read_bytes() == before


def test_mark_appends_one_line(vault, tmp_path):  # AC-13 の CLI 側・impl の正規化
    cfg = make_config(vault)
    impl = tmp_path / "work"
    impl.mkdir()
    assert run(vault, cfg, "mark", "Alpha", "--done-phase", "1", "--waiting", "確認待ち", "--note", "a|b",
               "--impl", str(impl), "--no-build") == 0
    e = events(vault)[-1]
    assert e["doc"] == "Alpha_道具_仕様書" and e["path"] == f"{SPEC}/{DEV}/Alpha/Alpha_道具_仕様書.md"
    assert e["impl_add"] == [impl.as_posix()] and e["by"] == "user" and e["pc"] == "pc"
    assert run(vault, cfg, "mark", "Alpha", "--unimpl", str(impl).upper(), "--no-build") == 0


@pytest.mark.parametrize("state", ["実装完了", "撤退"])
def test_claude_code_needs_confirmed(vault, state):  # AC-15
    cfg = make_config(vault)
    assert run(vault, cfg, "mark", "Alpha", "--state", state, "--by", "claude-code", "--no-build") == 5
    assert events(vault) == []
    assert run(vault, cfg, "mark", "Alpha", "--state", state, "--by", "claude-code", "--confirmed", "--no-build") == 0
    assert events(vault)[-1]["confirmed"] is True


def test_duplicate_filename_target(vault, capsys):  # AC-16
    cfg = make_config(vault)
    assert run(vault, cfg, "mark", "dup_prompt", "--note", "x", "--no-build") == 4
    err = capsys.readouterr().err
    assert "OS非依存/A/dup_prompt.md" in err and "OS非依存/B/dup_prompt.md" in err
    assert events(vault) == []
    path = str(vault / SPEC / "OS非依存" / "B" / "dup_prompt.md")
    assert run(vault, cfg, "mark", path, "--note", "x", "--no-build") == 0
    assert events(vault)[-1]["path"] == f"{SPEC}/OS非依存/B/dup_prompt.md"
    b = core.load(str(vault), cfg)
    assert [p.folded.note for p in b.statuses if p.project.name == "Dup"] .count("x") == 1


def test_other_pc_records(vault, tmp_path):  # AC-18
    cfg = make_config(vault)
    ev = vault / "spec-status" / "data" / "events"
    base = {"v": 1, "by": "user", "doc": "App_仕様書", "path": f"{SPEC}/Android/App/App_仕様書.md"}
    rows_pc = [dict(base, at="2026-10-01T10:00:00+09:00", pc="pc", note="pc1"),
               dict(base, at="2026-10-01T12:00:00+09:00", pc="pc", waiting="確認待ち")]
    rows_other = [dict(base, at="2026-10-01T11:00:00+09:00", pc="pc2", note="other",
                       impl_add=["D:/無い/deskkit"]),
                  dict(base, at="2026-10-01T13:00:00+09:00", pc="pc2", waiting="実物待ち")]
    w(ev / "pc.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows_pc))
    w(ev / "pc2.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows_other))
    ps = st(vault, cfg, "App")
    assert ps.folded.note == "other" and ps.waiting == "実物待ち"
    assert ps.folded.impl[0].exists_here is False and ps.folded.impl[0].pc == "pc2"
    assert ps.state == "着手済" and ps.decided_by["source"] == "events"


def test_rename(vault):  # AC-20
    cfg = make_config(vault)
    run(vault, cfg, "mark", "Beta", "--note", "旧", "--no-build")
    old = vault / SPEC / DEV / "Beta" / "Beta_仕様書.md"
    old.rename(old.with_name("Beta_新_仕様書.md"))
    b = core.load(str(vault), cfg)
    assert [o.doc for o in b.orphans] == ["Beta_仕様書"]
    w(vault / "spec-status" / "data" / "registry.toml", '[[rename]]\nfrom = "Beta_仕様書"\nto = "Beta_新_仕様書"\n')
    b = core.load(str(vault), cfg)
    assert b.orphans == [] and next(p for p in b.statuses if p.project.name == "Beta").folded.note == "旧"


def test_list_filters_and_where(vault, tmp_path, capsys):  # AC-23
    cfg = make_config(vault)
    impl = tmp_path / "Work"
    (impl / "src").mkdir(parents=True)
    run(vault, cfg, "mark", "Alpha", "--state", "着手済", "--waiting", "確認待ち", "--impl", str(impl), "--no-build")
    run(vault, cfg, "mark", "Beta", "--state", "未着手", "--no-build")
    capsys.readouterr()

    def names(*args):
        run(vault, cfg, "list", "--json", *args)
        return sorted(p["name"] for p in json.loads(capsys.readouterr().out))
    assert names("--state", "着手済", "--state", "未着手") == ["Alpha", "Beta"]
    assert names("--waiting") == ["Alpha"]
    assert names("--conflict") == []
    assert names("--os", "Android") == ["App"]
    b = core.load(str(vault), cfg)
    hit = lambda f: [p.project.name for p in core.where(b, str(f))]  # noqa: E731
    assert hit(impl) == ["Alpha"] and hit(impl / "src") == ["Alpha"]
    assert hit(str(impl).upper()) == ["Alpha"] and hit(tmp_path) == []


# ---- Phase 3: build / check / deploy ---------------------------------------

def test_build_outputs_and_v1_keys(vault, tmp_path):  # AC-26・AC-28・AC-30
    marker = "目印の本文ZZZ"
    w(vault / SPEC / DEV / "Beta" / "Beta_仕様書.md", spec_doc("Beta 仕様書", body=marker))
    w(vault / "開発ログ" / "2026-10-01.md", f"### Beta を直した\n{marker}\n")
    cfg = make_config(vault)
    run(vault, cfg, "mark", "Alpha", "--note", "x|y", "--done-phase", "1", "--no-build")
    assert run(vault, cfg, "build") == 0
    md = (vault / SPEC / "00_実装状況.md").read_text(encoding="utf-8")
    js = json.loads((vault / SPEC / "00_実装状況.json").read_text(encoding="utf-8"))
    assert marker not in md and marker not in json.dumps(js, ensure_ascii=False)
    assert "x\\|y" in md and "1/3" in md
    v1 = {"schema": int, "generated_at": str, "projects": list, "unreadable": list}
    assert all(isinstance(js[k], t) for k, t in v1.items()) and js["schema"] == 1
    p1 = {"name": str, "spec_dir": str, "docs": list, "state": str, "decided_by": dict, "evidence": list,
          "conflict": bool}
    for p in js["projects"]:
        assert all(isinstance(p[k], t) for k, t in p1.items())
        assert "last_devlog_date" in p and "note" in p and p["decided_by"]["source"]
    beta = next(p for p in js["projects"] if p["name"] == "Beta")
    assert beta["last_devlog_date"] == "2026-10-01"
    for line in md.splitlines():  # INV-4: 状態の節の行は根拠の列が空でない
        if line.startswith("| [["):
            assert "|  |" not in line.split("|", 3)[2]

    md1, js1 = md, (vault / SPEC / "00_実装状況.json").read_text(encoding="utf-8")
    assert run(vault, cfg, "build") == 0
    md2 = (vault / SPEC / "00_実装状況.md").read_text(encoding="utf-8")
    js2 = (vault / SPEC / "00_実装状況.json").read_text(encoding="utf-8")
    strip = lambda s, k: [x for x in s.splitlines() if k not in x]  # noqa: E731
    assert strip(md1, "生成:") == strip(md2, "生成:")
    assert strip(js1, '"generated_at"') == strip(js2, '"generated_at"')
    assert not list((vault / SPEC).glob("*.tmp"))


def test_output_must_be_under_spec_root(vault):  # AC-27
    cfg = make_config(vault, board=f"{SPEC}/Windows/x.md")
    assert run(vault, cfg, "build") == 2
    assert not (vault / SPEC / "Windows" / "x.md").exists()


def test_registry_issues(vault, capsys):  # AC-34
    cfg = make_config(vault)
    w(vault / "spec-status" / "data" / "registry.toml", f'''
[[merge]]
name = "M"
spec_dirs = ["無い/フォルダ"]
[[rename]]
from = "a"
to = "無いファイル"
[[include]]
path = "{SPEC}/無い.md"
[[exclude]]
path = "{SPEC}/無い2.md"
''')
    assert run(vault, cfg, "check") == 1
    out = capsys.readouterr().out
    for k in ("[[merge]]", "[[rename]]", "[[include]]", "[[exclude]]"):
        assert k in out


def test_deploy(vault, tmp_path):  # AC-29
    ev = vault / "spec-status" / "data" / "events"
    dummy = w(ev / "dummy.jsonl", "keep\n")
    before = dummy.read_bytes()
    env = dict(os.environ, PYTHONUTF8="1")
    r = subprocess.run([sys.executable, str(ROOT / "deploy.py"), "--vault", str(vault)], env=env,
                       capture_output=True)
    assert r.returncode == 0, r.stderr
    assert dummy.read_bytes() == before
    dest = vault / "spec-status"
    assert (dest / "VERSION.txt").exists() and (dest / "specstatus" / "core.py").exists()
    make_config(vault)
    r = subprocess.run([sys.executable, str(dest / "specstatus.py"), "list", "--config",
                        str(vault / "spec-status" / "data" / "config" / "pc.toml")], env=env, capture_output=True)
    assert r.returncode == 0, r.stderr
    assert not list(dest.rglob("__pycache__"))
    notvault = tmp_path / "nv"
    notvault.mkdir()
    r = subprocess.run([sys.executable, str(ROOT / "deploy.py"), "--vault", str(notvault)], env=env,
                       capture_output=True)
    assert r.returncode == 2 and list(notvault.iterdir()) == []


# ---- Phase 4: where --hook ------------------------------------------------

def test_where_hook(vault, tmp_path, capsys):  # AC-35
    cfg = make_config(vault)
    impl = tmp_path / "w"
    impl.mkdir()
    jpath = vault / SPEC / "00_実装状況.json"
    assert run(vault, cfg, "where", str(impl), "--hook") == 0
    assert capsys.readouterr().out == ""
    run(vault, cfg, "mark", "Alpha", "--impl", str(impl))
    capsys.readouterr()
    assert run(vault, cfg, "where", str(impl), "--hook") == 0
    out = capsys.readouterr().out.splitlines()
    assert 1 <= len(out) <= 5 and "Alpha" in out[0]
    assert run(vault, cfg, "where", str(tmp_path), "--hook") == 0
    assert capsys.readouterr().out == ""
    jpath.write_text("{壊れた", encoding="utf-8")
    assert run(vault, cfg, "where", str(impl), "--hook") == 0
    assert capsys.readouterr().out == ""

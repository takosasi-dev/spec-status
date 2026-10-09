# 依存の古さ(eol): 版の書き方の読み・サポート期限と major の遅れの判定・保存と上限・offline。通信は差し替える。
from __future__ import annotations

import json
from datetime import datetime

from specstatus import eol
from specstatus.model import ImplPath

from test_guilogic import ps

NOW = datetime(2026, 10, 9, 12).timestamp()
CFG = {"eol": {"enabled": True}}

ANSWERS = {
    "https://endoflife.date/api/python.json": [{"cycle": "3.13", "eol": "2029-10-31"}, {"cycle": "3.9", "eol": "2025-10-31"},
                                               {"cycle": "3.10", "eol": "2026-10-31"}],
    "https://endoflife.date/api/nodejs.json": [{"cycle": "20", "eol": "2026-04-30"}, {"cycle": "22", "eol": False}],
    "https://pypi.org/pypi/requests/json": {"info": {"version": "2.34.2"}},
    "https://pypi.org/pypi/pillow/json": {"info": {"version": "12.0.0"}},
    "https://registry.npmjs.org/react/latest": {"version": "19.1.0"},
    "https://registry.npmjs.org/@types%2Fnode/latest": {"version": "26.6.4"},
    "https://registry.npmjs.org/vite/latest": {"version": "7.0.0"},
}


def fake(calls):
    def fetch(url):
        calls.append(url)
        return ANSWERS.get(url)
    return fetch


def project(tmp_path, files: dict[str, str], sub: str = "impl"):
    d = tmp_path / sub
    d.mkdir()
    for name, body in files.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")
    p = ps("App", "W/App", "着手済")
    p.folded.impl = [ImplPath(path=str(d).replace("\\", "/"), pc="pc", exists_here=True)]
    return p


def test_versions():
    assert [eol._major(s) for s in ("^1.2", ">=18", "v20.1.0", "~5", "*", "latest", "git+https://x/y", "file:../a")] \
        == [1, 18, 20, 5, None, None, None, None]
    assert eol._cycle("python", ">=3.11,<4") == "3.11" and eol._cycle("nodejs", ">=18.0.0") == "18"
    assert eol._cycle("python", "3") is None


def test_attach_runtimes_and_outdated(tmp_path):
    p = project(tmp_path, {
        "package.json": json.dumps({"engines": {"node": ">=20"}, "dependencies": {"react": "^18.2.0", "vite": "^7.0.0",
                                    "local": "file:../x"}, "devDependencies": {"@types/node": "~20.1.0"}}),
        "pyproject.toml": '[project]\nrequires-python = ">=3.9"\ndependencies = ["requests>=2.31", "pillow[x]==10.4.0; python_version>\'3\'"]\n',
        "sub/requirements.txt": "requests==2.32.0\nunknown\n",
        ".python-version": "3.10.4\n",
        "node_modules/deep/package.json": json.dumps({"dependencies": {"react": "^1.0.0"}}),
    })
    calls = []
    assert eol.attach([p], CFG, fetch=fake(calls), now=NOW, folder=str(tmp_path / "cache")) == ""
    assert p.eol["runtimes"] == [
        {"name": "Node.js", "version": "20", "eol": "2026-04-30", "ended": True},
        {"name": "Python", "version": "3.10", "eol": "2026-10-31", "ended": False},      # 90 日以内に切れる
        {"name": "Python", "version": "3.9", "eol": "2025-10-31", "ended": True},
    ]
    assert p.eol["outdated"] == [
        {"package": "@types/node", "version": "~20.1.0", "latest": "26.6.4", "behind": 6},
        {"package": "pillow", "version": "==10.4.0", "latest": "12.0.0", "behind": 2},
        {"package": "react", "version": "^18.2.0", "latest": "19.1.0", "behind": 1},
    ]
    assert len(calls) == 7                     # requests は2か所に出ても1回。node_modules の下は見ない

    # 新しいうちは聞き直さない。offline なら古くても聞かない
    calls.clear()
    q = project(tmp_path / "again", {"package.json": json.dumps({"dependencies": {"react": "^18"}})}) \
        if (tmp_path / "again").mkdir() is None else None
    eol.attach([q], CFG, fetch=fake(calls), now=NOW + 3600, folder=str(tmp_path / "cache"))
    eol.attach([q], CFG, fetch=fake(calls), now=NOW + 99 * 86400, folder=str(tmp_path / "cache"), offline=True)
    assert calls == [] and q.eol["outdated"][0]["package"] == "react"


def test_limit_failure_and_disabled(tmp_path):
    p = project(tmp_path, {"requirements.txt": "".join(f"p{i}==1.0\n" for i in range(5))})
    calls = []
    note = eol.attach([p], {"eol": {"enabled": True, "max_queries": 3}}, fetch=fake(calls), now=NOW,
                      folder=str(tmp_path / "c"))
    assert "上限(3)" in note and len(calls) == 3 and p.eol is None

    def down(url):
        raise OSError("no network")
    assert "繋がりません" in eol.attach([p], CFG, fetch=down, now=NOW, folder=str(tmp_path / "c"))
    assert eol.attach([p], {}, fetch=down) == "" and eol.attach([p], {"eol": {"enabled": False}}, fetch=down) == ""
    assert eol.attach([ps("No", "W/No")], CFG, fetch=down) == ""            # 実装フォルダが無い

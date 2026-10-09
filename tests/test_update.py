# ソフト内の更新(update): 版の比べ方・確認の間隔・vault の入れ替え(data\ に触らない)・exe の zip の広げ方・入れ替えの PowerShell。
# GitHub には繋がない(取りに行く関数を差し替える)。PowerShell の入れ替えは Windows でだけ実際に走らせる。
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import zipfile

import pytest

from specstatus import update


def make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def test_versions():
    assert update.parse_version("v0.3.0") == (0, 3, 0) and update.parse_version("0.10.2") == (0, 10, 2)
    assert update.parse_version("v1.0") is None
    assert update.is_newer("v0.10.0", "0.9.9")
    assert not update.is_newer("v0.3.0", "0.3.0") and not update.is_newer("v0.2.9", "0.3.0")
    assert update.is_newer("v0.3.0", None)            # 版の分からない古い置き方は更新できる
    assert not update.is_newer("nightly", "0.3.0")


def test_latest_is_cached_for_a_day(tmp_path):
    calls = []

    def fetch(url, timeout=15):
        calls.append(url)
        return json.dumps({"tag_name": "v0.3.0", "html_url": "u", "body": "notes",
                           "assets": [{"name": "SpecStatus-v0.3.0-windows.zip", "browser_download_url": "z"},
                                      {"name": "other.zip", "browser_download_url": "x"}]}).encode()
    path = str(tmp_path / "u.json")
    rel = update.latest(now=1000.0, fetch=fetch, path=path)
    assert rel == {"tag": "v0.3.0", "url": "u", "notes": "notes", "exe_zip": "z"}
    assert update.latest(now=1000.0 + 3600, fetch=fetch, path=path) == rel and len(calls) == 1
    update.latest(now=1000.0 + 25 * 3600, fetch=fetch, path=path)
    update.latest(force=True, now=1000.0 + 25 * 3600, fetch=fetch, path=path)
    assert len(calls) == 3


def vault_with_old_install(tmp_path):
    dest = tmp_path / "v" / "spec-status"
    (dest / "specstatus").mkdir(parents=True)
    (dest / "data" / "events").mkdir(parents=True)
    for f in update.FILES:
        (dest / f).write_text("old", encoding="utf-8")
    (dest / "specstatus" / "__init__.py").write_text('__version__ = "0.2.0"\n', encoding="utf-8")
    (dest / "specstatus" / "gone.py").write_text("old", encoding="utf-8")
    (dest / "data" / "events" / "pc.jsonl").write_text("{}\n", encoding="utf-8")
    return str(tmp_path / "v"), dest


def test_update_vault_keeps_data(tmp_path):
    vault, dest = vault_with_old_install(tmp_path)
    root = "spec-status-0.3.0/"
    files = {root + f: "new" for f in update.FILES}
    files.update({root + "specstatus/__init__.py": '__version__ = "0.3.0"\n', root + "specstatus/evidence/a.py": "x",
                  root + "tests/test_x.py": "t", root + "data/events/pc.jsonl": "BAD"})
    asked = []

    def fetch(url, timeout=15):
        asked.append(url)
        return make_zip(files)
    assert update.vault_version(vault) == "0.2.0"
    msg = update.update_vault(vault, "v0.3.0", fetch)
    assert asked == ["https://github.com/takosasi-dev/spec-status/archive/refs/tags/v0.3.0.zip"]
    assert "v0.3.0" in msg and update.vault_version(vault) == "0.3.0"
    assert (dest / "README.md").read_text(encoding="utf-8") == "new"
    assert (dest / "specstatus" / "evidence" / "a.py").is_file()
    assert not (dest / "specstatus" / "gone.py").exists()          # 消えたファイルは残さない
    assert not (dest / "tests").exists() and not (dest / update.STAGE).exists()
    assert (dest / "data" / "events" / "pc.jsonl").read_text(encoding="utf-8") == "{}\n"   # data\ はそのまま
    assert (dest / "VERSION.txt").read_text(encoding="utf-8").startswith("v0.3.0 GitHub")


def test_update_vault_refuses_bad_zips(tmp_path):
    vault, dest = vault_with_old_install(tmp_path)
    root = "r/"
    good = {root + f: "new" for f in update.FILES} | {root + "specstatus/__init__.py": "x"}
    with pytest.raises(update.UpdateError, match="怪しい"):
        update.update_vault(vault, "v9.9.9", lambda u, timeout=0: make_zip(good | {root + "specstatus/../../evil.py": "x"}))
    with pytest.raises(update.UpdateError, match="必要なファイル"):
        update.update_vault(vault, "v9.9.9", lambda u, timeout=0: make_zip({root + "README.md": "x"}))
    assert update.vault_version(vault) == "0.2.0" and (dest / "specstatus" / "gone.py").exists()   # 何も変えていない
    with pytest.raises(update.UpdateError, match="置かれていません"):
        update.update_vault(str(tmp_path / "none"), "v9.9.9", lambda u, timeout=0: b"")


def test_stage_exe(tmp_path):
    folder = tmp_path / "SpecStatus"
    folder.mkdir()
    (folder / "vault.txt").write_text("E:\\v\n", encoding="utf-8")
    data = make_zip({"SpecStatus/SpecStatus.exe": "exe", "SpecStatus/_internal/a.dll": "dll"})
    staged = update.stage_exe("z", str(folder), lambda u, timeout=0: data)
    assert staged == str(folder) + ".new"
    assert open(os.path.join(staged, "SpecStatus.exe")).read() == "exe"
    assert open(os.path.join(staged, "_internal", "a.dll")).read() == "dll"
    assert open(os.path.join(staged, "vault.txt")).read() == "E:\\v\n"       # この PC の vault の場所は引き継ぐ
    with pytest.raises(update.UpdateError, match="付いていません"):
        update.stage_exe(None, str(folder))
    with pytest.raises(update.UpdateError, match="ありません"):
        update.stage_exe("z", str(folder), lambda u, timeout=0: make_zip({"x/other.exe": "e"}))


@pytest.mark.skipif(os.name != "nt", reason="PowerShell の入れ替えは Windows だけ")
def test_swap_script_replaces_folder(tmp_path):
    folder, staged = tmp_path / "Spec Status'", tmp_path / "new"         # 空白と ' を含む名前でも崩れない
    folder.mkdir()
    staged.mkdir()
    (folder / "old.txt").write_text("old", encoding="utf-8")
    (staged / "new.txt").write_text("new", encoding="utf-8")
    script = update.swap_script(999999, str(folder), str(staged), "SpecStatus.exe", launch=False)
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc], check=True,
                   capture_output=True, timeout=60, cwd=str(tmp_path))
    assert (folder / "new.txt").is_file() and not (folder / "old.txt").exists()
    assert not staged.exists() and not (tmp_path / "Spec Status'.old").exists()

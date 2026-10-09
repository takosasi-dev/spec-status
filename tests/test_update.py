# ソフト内の更新(update): 版の比べ方・確認の間隔・vault の入れ替え(data\ に触らない・途中の失敗で全部戻す)・
# SHA256SUMS の照合・exe の zip の広げ方・入れ替えの PowerShell(一時フォルダだけ、Windows でだけ実際に走らせる)。GitHub には繋がない。
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
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
                                      {"name": "SpecStatus-v0.3.0-vault.zip", "browser_download_url": "vz"},
                                      {"name": "SHA256SUMS.txt", "browser_download_url": "s"},
                                      {"name": "other.zip", "browser_download_url": "x"}]}).encode()
    path = str(tmp_path / "u.json")
    rel = update.latest(now=1000.0, fetch=fetch, path=path)
    assert rel == {"tag": "v0.3.0", "url": "u", "notes": "notes", "exe_zip": "z", "vault_zip": "vz", "sums": "s"}
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
    (dest / "specstatus" / "assets").mkdir()
    os.chmod(dest / "specstatus" / "assets", stat.S_IREAD)     # 読み取り専用のフォルダ(vault で実際にあった)
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


# ---- 照合(SHA256SUMS.txt) ----

def sums_for(**named: bytes) -> bytes:
    return "".join(f"{hashlib.sha256(d).hexdigest()}  {n}\n" for n, d in named.items()).encode()


def test_sums_text_round_trip(tmp_path):
    a = tmp_path / "SpecStatus-v1.0.0-windows.zip"
    a.write_bytes(b"exe")
    text = update.sums_text([str(a)])
    assert text == f"{hashlib.sha256(b'exe').hexdigest()}  {a.name}\n"
    assert update.parse_sums(text) == {a.name: hashlib.sha256(b"exe").hexdigest()}
    assert update.parse_sums("ABC *b.zip\n\n") == {"b.zip": "abc"}        # sha256sum のバイナリの印


def test_verify():
    sums = sums_for(**{"a.zip": b"good"})
    fetch = lambda u, timeout=15: sums            # noqa: E731
    assert update.verify(b"good", "https://x/dl/a.zip", "s", fetch) is True
    assert update.verify(b"anything", "https://x/dl/a.zip", None, fetch) is False   # 一覧の無い古い Release
    with pytest.raises(update.UpdateError, match="合いません"):
        update.verify(b"evil", "https://x/dl/a.zip", "s", fetch)
    with pytest.raises(update.UpdateError, match="ありません"):
        update.verify(b"good", "https://x/dl/b.zip", "s", fetch)


# ---- vault の入れ替え: 照合と、途中の失敗で全部戻す ----

def new_release_zip():
    root = "spec-status-0.3.0/"
    files = {root + f: "new" for f in update.FILES}
    files.update({root + "specstatus/__init__.py": '__version__ = "0.3.0"\n', root + "specstatus/evidence/a.py": "x"})
    return make_zip(files)


def assert_old_install(dest):
    assert (dest / "specstatus" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.2.0"\n'
    assert (dest / "specstatus" / "gone.py").exists() and not (dest / "specstatus" / "evidence").exists()
    assert all((dest / f).read_text(encoding="utf-8") == "old" for f in update.FILES)
    assert (dest / "data" / "events" / "pc.jsonl").read_text(encoding="utf-8") == "{}\n"


def test_update_vault_verifies_release_zip(tmp_path):
    vault, dest = vault_with_old_install(tmp_path)
    data = new_release_zip()
    blobs = {"https://x/SpecStatus-v0.3.0-vault.zip": data, "https://x/SHA256SUMS.txt":
             sums_for(**{"SpecStatus-v0.3.0-vault.zip": data})}
    msg = update.update_vault(vault, "v0.3.0", lambda u, timeout=15: blobs[u],
                              zip_url="https://x/SpecStatus-v0.3.0-vault.zip", sums="https://x/SHA256SUMS.txt")
    assert "照合済み" in msg and update.vault_version(vault) == "0.3.0"
    assert "照合済み" in open(update.log_path(), encoding="utf-8").read()


def test_update_vault_without_sums_says_so(tmp_path):
    vault, _ = vault_with_old_install(tmp_path)
    assert "照合なし" in update.update_vault(vault, "v0.3.0", lambda u, timeout=15: new_release_zip())


def test_update_vault_tampered_zip_changes_nothing(tmp_path):
    vault, dest = vault_with_old_install(tmp_path)
    data = new_release_zip()
    blobs = {"z": data, "s": sums_for(**{"z": b"the real one"})}
    with pytest.raises(update.UpdateError, match="合いません"):
        update.update_vault(vault, "v0.3.0", lambda u, timeout=15: blobs[u], zip_url="z", sums="s")
    assert_old_install(dest)


@pytest.mark.parametrize("fail_on", ["specstatus", "README.md", "config.example.toml"])
def test_update_vault_rolls_back_everything(tmp_path, monkeypatch, fail_on):
    vault, dest = vault_with_old_install(tmp_path)
    real = os.replace

    def flaky(src, dst):
        if os.path.basename(dst) == fail_on and str(src).endswith(os.sep + update.STAGE + os.sep + fail_on):
            raise PermissionError("使用中")                              # 新しい物を置く所で失敗させる
        return real(src, dst)
    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(PermissionError):
        update.update_vault(vault, "v0.3.0", lambda u, timeout=15: new_release_zip())
    monkeypatch.undo()
    assert_old_install(dest)
    assert not (dest / "VERSION.txt").exists()


def test_update_vault_rollback_failure_points_to_backup(tmp_path, monkeypatch):
    vault, dest = vault_with_old_install(tmp_path)
    real = os.replace

    def broken(src, dst):
        if os.path.basename(dst) == "README.md":                       # 置くのも戻すのも失敗
            raise PermissionError("使用中")
        return real(src, dst)
    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(update.UpdateError, match="README.md"):
        update.update_vault(vault, "v0.3.0", lambda u, timeout=15: new_release_zip())
    monkeypatch.undo()
    assert (dest / update.STAGE / "README.md.old").read_text(encoding="utf-8") == "old"   # 前の版は消していない


def test_stage_exe_checks_sums(tmp_path):
    folder = tmp_path / "SpecStatus"
    folder.mkdir()
    data = make_zip({"SpecStatus/SpecStatus.exe": "exe"})
    blobs = {"https://x/SpecStatus-v1.0.0-windows.zip": data, "s": sums_for(**{"SpecStatus-v1.0.0-windows.zip": data})}
    update.stage_exe("https://x/SpecStatus-v1.0.0-windows.zip", str(folder), lambda u, timeout=15: blobs[u], sums="s")
    assert "照合済み" in open(update.log_path(), encoding="utf-8").read()
    blobs["s"] = sums_for(**{"SpecStatus-v1.0.0-windows.zip": b"other"})
    with pytest.raises(update.UpdateError, match="合いません"):
        update.stage_exe("https://x/SpecStatus-v1.0.0-windows.zip", str(folder), lambda u, timeout=15: blobs[u], sums="s")


def test_cleanup_old(tmp_path):
    folder = tmp_path / "SpecStatus"
    folder.mkdir()
    assert update.cleanup_old(str(folder)) is False and update.cleanup_old(None) is False
    (tmp_path / "SpecStatus.old" / "_internal").mkdir(parents=True)
    (tmp_path / "SpecStatus.old" / "SpecStatus.exe").write_text("x", encoding="utf-8")
    assert update.cleanup_old(str(folder) + "\\") is True
    assert not (tmp_path / "SpecStatus.old").exists() and folder.is_dir()


# ---- exe の入れ替え(PowerShell)。一時フォルダの中だけで走らせ、exe は起動しない(launch=False) ----

def run_swap(tmp_path, pid, folder, staged, wait=60):
    log = tmp_path / "update.log"
    script = update.swap_script(pid, str(folder), str(staged), "SpecStatus.exe", launch=False,
                                log_file=str(log), wait=wait)
    enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", enc], check=True,
                   capture_output=True, timeout=60, cwd=str(tmp_path))
    return log.read_text(encoding="utf-8").splitlines()


def two_folders(tmp_path):
    folder, staged = tmp_path / "Spec Status'", tmp_path / "new"         # 空白と ' を含む名前でも崩れない
    folder.mkdir()
    staged.mkdir()
    (folder / "old.txt").write_text("old", encoding="utf-8")
    (staged / "new.txt").write_text("new", encoding="utf-8")
    return folder, staged


@pytest.mark.skipif(os.name != "nt", reason="PowerShell の入れ替えは Windows だけ")
def test_swap_script_replaces_folder(tmp_path):
    folder, staged = two_folders(tmp_path)
    lines = run_swap(tmp_path, 999999, folder, staged)
    assert (folder / "new.txt").is_file() and not (folder / "old.txt").exists() and not staged.exists()
    assert (tmp_path / "Spec Status'.old" / "old.txt").is_file()          # .old は次の起動で消す
    assert "入れ替えました" in lines[0] and lines[-1].endswith("起動: " + str(folder / "SpecStatus.exe"))


@pytest.mark.skipif(os.name != "nt", reason="PowerShell の入れ替えは Windows だけ")
def test_swap_script_failure_restores_and_launches_old(tmp_path):
    folder, staged = two_folders(tmp_path)
    lines = run_swap(tmp_path, 999999, folder, tmp_path / "無い")       # 新しい版が無い → 元に戻す
    assert (folder / "old.txt").is_file() and not (tmp_path / "Spec Status'.old").exists()
    assert "失敗" in lines[0] and lines[-1].endswith("起動: " + str(folder / "SpecStatus.exe"))


@pytest.mark.skipif(os.name != "nt", reason="PowerShell の入れ替えは Windows だけ")
def test_swap_script_timeout_keeps_old(tmp_path):
    folder, staged = two_folders(tmp_path)
    lines = run_swap(tmp_path, os.getpid(), folder, staged, wait=1)     # 終わらないプロセス(このテスト自身)
    assert (folder / "old.txt").is_file() and staged.is_dir()
    assert "待ちきれません" in lines[0] and lines[-1].endswith("起動: " + str(folder / "SpecStatus.exe"))

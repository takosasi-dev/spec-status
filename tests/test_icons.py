# アイコン: PNG の読み書きと縮め方(pngutil)、実装フォルダと GitHub からの探し方(icons)、ショートカットの PowerShell(shortcut)。
# ネットワークには繋がない(取りに行く関数を差し替える)。
from __future__ import annotations

import json
import struct

from specstatus import icons, pngutil, shortcut
from specstatus.model import ImplPath

from test_guilogic import ps


def png(w: int, h: int, color=(255, 0, 0, 255)) -> bytes:
    return pngutil.encode(w, h, bytes(color) * (w * h))


def test_png_roundtrip_and_resize():
    data = png(4, 2, (10, 20, 30, 255))
    assert pngutil.size_of(data) == (4, 2)
    w, h, px = pngutil.decode(data)
    assert (w, h) == (4, 2) and bytes(px[:4]) == bytes((10, 20, 30, 255))
    out = pngutil.resize(w, h, px, 2)              # 横長は縦が余る(2x1 の絵 + 透明の1行)
    assert bytes(out[0:8]) == bytes((10, 20, 30, 255)) * 2 and out[3 + 2 * 4] == 0
    # 半分透明の白と不透明の赤を平均しても、色は黒ずまない(α を掛けて平均)
    mixed = bytes((255, 0, 0, 255)) + bytes((0, 0, 0, 0))
    r = pngutil.resize(2, 1, bytearray(mixed), 1)
    assert tuple(r) == (255, 0, 0, 128)


def test_png_from_ico():
    inner = png(16, 16)
    head = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 16, 16, 0, 0, 1, 32, len(inner), 22)
    assert pngutil.png_from_ico(head + inner) == inner
    assert len(pngutil.thumbnail(head + inner, 8)) > 0


def test_local_candidates(tmp_path):
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "icon.png").write_bytes(png(8, 8))
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "logo.png").write_bytes(png(8, 8))
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "icon.png").write_bytes(png(64, 64))
    assert icons.local_candidates(str(tmp_path))[0].endswith("icon.png")
    ext = tmp_path / "ext"
    (ext / "icons").mkdir(parents=True)
    (ext / "icons" / "i128.png").write_bytes(png(16, 16))
    (ext / "manifest.json").write_text(json.dumps({"manifest_version": 3, "icons": {"16": "icons/i16.png",
                                                                                    "128": "icons/i128.png"}}))
    assert icons.local_candidates(str(ext))[0].replace("\\", "/").endswith("ext/icons/i128.png")   # 無い i16 は飛ばす
    assert icons.rank("BP/pack_icon.png") == 1 and icons.rank("app/src/main/res/mipmap-hdpi/ic_launcher.png") == 1
    assert icons.rank("src/iconography.png") is None and icons.rank("icon_256.ico") == 3


def test_github_pick():
    tree = {"tree": [{"type": "blob", "path": "node_modules/a/icon.png"}, {"type": "blob", "path": "docs/img/logo.png"},
                     {"type": "blob", "path": "assets/icon.png"}, {"type": "blob", "path": "README.md"}]}
    assert icons.github_pick(tree) == "assets/icon.png"
    assert icons.github_pick({"tree": []}) is None


def test_find_all_local_then_github(tmp_path):
    impl = tmp_path / "impl"
    impl.mkdir()
    (impl / "icon.png").write_bytes(png(32, 32))
    local = ps("Local", "W/Local")
    local.folded.impl = [ImplPath(str(impl), "pc", True)]
    remote = ps("Remote", "W/Remote")
    remote.github = {"repo": "o/remote", "branch": "main"}
    none = ps("None", "W/None")
    asked = []

    def get(url):
        asked.append(url)
        if "git/trees" in url:
            return json.dumps({"tree": [{"type": "blob", "path": "res/logo.png"}]}).encode()
        return png(20, 20, (0, 0, 255, 255))
    folder = str(tmp_path / "cache")
    got = icons.find_all([local, remote, none], (8, 16), folder=folder, get=get, now=1000.0)
    assert set(got) == {local.project.key, remote.project.key}
    assert pngutil.size_of(open(got[remote.project.key][16], "rb").read()) == (16, 16)
    assert asked == ["https://api.github.com/repos/o/remote/git/trees/main?recursive=1",
                     "https://raw.githubusercontent.com/o/remote/main/res/logo.png"]
    asked.clear()
    icons.find_all([local, remote], (8, 16), folder=folder, get=get, now=2000.0)     # 縮めた物と一覧は使い回す
    assert asked == []

    def down(url):
        raise OSError("no network")
    other = ps("Other", "W/Other")
    other.github = {"repo": "o/other", "branch": "main"}
    assert set(icons.find_all([local, other], (8,), folder=folder, get=down, now=3000.0)) == {local.project.key}


def test_shortcut_script_escapes():
    s = shortcut.script("C:/a'b/SpecStatus.exe", "", "C:/a'b", "C:/a'b/SpecStatus.exe,0", ["Desktop", "Programs"])
    assert "'C:/a''b/SpecStatus.exe'" in s and s.count("$s.Save()") == 2
    tgt, args, work, icon = shortcut.target("E:/v", None)
    assert args == '"E:/v\\spec-status\\specstatus.py" gui --vault "E:/v"' or args.endswith('gui --vault "E:/v"')
    assert icon.endswith("icon.ico,0")

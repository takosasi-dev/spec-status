# prefs(GUI の gui.json)のテスト: 無い・壊れた・形の違うファイルは既定、範囲の切り詰め、書いて読み戻す。
from __future__ import annotations

import json

from specstatus import prefs


def test_missing_file_gives_defaults(tmp_path):
    assert prefs.load(str(tmp_path)) == prefs.DEFAULTS


def test_corrupt_and_non_dict_files(tmp_path):
    (tmp_path / "gui.json").write_text("{not json", encoding="utf-8")
    assert prefs.load(str(tmp_path)) == prefs.DEFAULTS
    (tmp_path / "gui.json").write_text("[1, 2]", encoding="utf-8")
    assert prefs.load(str(tmp_path)) == prefs.DEFAULTS
    (tmp_path / "gui.json").write_bytes(b"\xff\xfe\x00")
    assert prefs.load(str(tmp_path)) == prefs.DEFAULTS


def test_merge_validate_and_clamp(tmp_path):
    raw = {"geometry": "800x600+10+20", "font_delta": 99, "theme": "neon", "view": "cards",
           "sashes": [100, "x"], "states": ["着手済", 3], "checks": {"waiting": True, "stale": "yes"},
           "sort": {"column": "name", "descending": True}, "detail_tab": -3, "unknown": 1, "category": "Windows"}
    (tmp_path / "gui.json").write_text(json.dumps(raw), encoding="utf-8")
    p = prefs.load(str(tmp_path))
    assert p["geometry"] == "800x600+10+20"
    assert p["font_delta"] == 6
    assert p["theme"] == "auto"                     # 知らない値は既定
    assert p["view"] == "cards"
    assert p["sashes"] == []                        # 数でない物が混じれば既定
    assert p["states"] == ["着手済"]
    assert p["checks"] == {**prefs.DEFAULTS["checks"], "waiting": True}
    assert p["sort"] == {"column": "name", "descending": True}
    assert p["detail_tab"] == 0
    assert p["category"] == "Windows"
    assert "unknown" not in p
    (tmp_path / "gui.json").write_text(json.dumps({"font_delta": -9, "font_delta_x": True}), encoding="utf-8")
    assert prefs.load(str(tmp_path))["font_delta"] == -2


def test_save_roundtrip_atomic(tmp_path):
    folder = tmp_path / "sub"
    p = prefs.load(str(folder))
    p.update(view="dashboard", theme="dark", hidden_columns=["source"], font_delta=2, junk=1)
    prefs.save(p, str(folder))
    back = prefs.load(str(folder))
    assert back["view"] == "dashboard" and back["theme"] == "dark" and back["font_delta"] == 2
    assert back["hidden_columns"] == ["source"] and "junk" not in back
    assert sorted(x.name for x in folder.iterdir()) == ["gui.json"]   # 一時ファイルが残らない


def test_defaults_not_mutated(tmp_path):
    p = prefs.load(str(tmp_path))
    p["checks"]["waiting"] = True
    p["states"].append("x")
    assert prefs.DEFAULTS["checks"]["waiting"] is False and prefs.DEFAULTS["states"] == []

# GUI の見た目と絞り込みの状態(窓の大きさ・仕切り・分類・札・並べ替え・表示・テーマ・文字の大きさ)を残す。
# 置き場所はこの PC の %LOCALAPPDATA%\SpecStatus\gui.json(vault には書かない)。壊れていたら既定で動く。
from __future__ import annotations

import json
import os

FILE = "gui.json"
VIEWS = ("table", "cards", "dashboard")
THEMES = ("auto", "light", "dark")
FONT_DELTA_MIN, FONT_DELTA_MAX = -2, 6
CHECKS = ("waiting", "conflict", "stale", "changed", "vuln")

DEFAULTS: dict = {
    "geometry": "",                                  # Tk の "WxH+X+Y"。空なら本体の既定
    "sashes": [],                                    # 仕切りの位置(px)
    "category": None,                                # 分類のパス(None = すべて)
    "states": [],                                    # 押してある状態の札
    "checks": {k: False for k in CHECKS},            # 待ち・食い違い・止まり・変更・脆弱
    "sort": {"column": None, "descending": False},   # 列のキー(strings.COLUMNS)
    "view": "table",
    "detail_tab": 0,
    "theme": "auto",
    "font_delta": 0,
    "hidden_columns": [],
}


def folder_default() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "SpecStatus")


def _strs(v) -> list[str] | None:
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else None


def _clean(raw: dict) -> dict:
    """既定の上に、型と範囲が正しい値だけを重ねる。知らないキーは捨てる。"""
    out = json.loads(json.dumps(DEFAULTS))           # 深い写し
    g = raw.get
    if isinstance(g("geometry"), str):
        out["geometry"] = g("geometry")
    if isinstance(g("sashes"), list) and all(isinstance(x, int) and not isinstance(x, bool) for x in g("sashes")):
        out["sashes"] = g("sashes")
    if g("category") is None or isinstance(g("category"), str):
        out["category"] = g("category") or None
    for k in ("states", "hidden_columns"):
        if _strs(g(k)) is not None:
            out[k] = _strs(g(k))
    if isinstance(g("checks"), dict):
        for k in CHECKS:
            if isinstance(g("checks").get(k), bool):
                out["checks"][k] = g("checks")[k]
    if isinstance(g("sort"), dict):
        s = g("sort")
        if s.get("column") is None or isinstance(s.get("column"), str):
            out["sort"]["column"] = s.get("column")
        if isinstance(s.get("descending"), bool):
            out["sort"]["descending"] = s["descending"]
    if g("view") in VIEWS:
        out["view"] = g("view")
    if g("theme") in THEMES:
        out["theme"] = g("theme")
    for k in ("detail_tab", "font_delta"):
        v = g(k)
        if isinstance(v, int) and not isinstance(v, bool):
            out[k] = v
    out["detail_tab"] = max(0, out["detail_tab"])
    out["font_delta"] = min(FONT_DELTA_MAX, max(FONT_DELTA_MIN, out["font_delta"]))
    return out


def load(folder: str | None = None) -> dict:
    """gui.json を読む。無い・読めない・JSON でない・形が違う物は既定に戻す。例外は出さない。"""
    path = os.path.join(folder or folder_default(), FILE)
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        raw = {}
    return _clean(raw if isinstance(raw, dict) else {})


def save(prefs: dict, folder: str | None = None) -> None:
    """検査してから一時ファイルに書いて置き換える(途中で落ちても前の gui.json が残る)。OSError は投げる。"""
    folder = folder or folder_default()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, FILE)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_clean(prefs), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

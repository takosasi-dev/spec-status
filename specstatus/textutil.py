# 名前の比べ方(NFC + casefold)、パスの区切りの統一、frontmatter の読み取りなど、各段で共有する小道具。
# ファイルは読むだけ。
from __future__ import annotations

import os
import unicodedata
from pathlib import Path


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def fold(s: str) -> str:
    """名前の比べ方: NFC にそろえて casefold(§9.5・FR-17)。"""
    return nfc(s).casefold()


def slash(p: str) -> str:
    return p.replace("\\", "/")


def norm_path(p: str) -> str:
    """絶対パスを比べる形に: 区切り '/'、末尾の '/' なし、NFC、casefold。"""
    return fold(slash(p).rstrip("/"))


def read_text(path: str | Path) -> str:
    """UTF-8 で読む。読めなければ UnicodeDecodeError / OSError をそのまま投げる。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return f.read()


def split_frontmatter(text: str) -> tuple[dict[str, str] | None, list[str]]:
    """先頭の --- ... --- を `キー: 値` の辞書にする。
    戻り値: (frontmatter。無ければ {}、閉じていなければ None, 本文の行)"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm: dict[str, str] = {}
            for ln in lines[1:i]:
                if ln[:1] in (" ", "\t", "-", "#") or ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                fm[k.strip()] = v.strip().strip("'\"")
            return fm, lines[i + 1:]
    return None, lines


def in_scope(spec_dir: str, scopes: list[str]) -> bool:
    """FR-14: 仕様書フォルダの前方一致。'' は全部。"""
    d = nfc(slash(spec_dir)).strip("/")
    for s in scopes:
        s = nfc(slash(s)).strip("/")
        if s == "" or d == s or d.startswith(s + "/"):
            return True
    return False


def resolve(vault: str, p: str) -> str:
    """設定のパス: 絶対パスならそのまま、そうでなければ vault からの相対。"""
    return p if os.path.isabs(p) else os.path.join(vault, p)

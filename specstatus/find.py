# 仕様書MDファイル\ を走査して仕様書の文書を集め、種類・製品名・作成日・最終フェーズを読む(FR-1〜FR-3・FR-5〜FR-8)。
# 仕様書の見つからないフォルダと、registry の include / exclude の不整合もここで出す。読むだけ。
from __future__ import annotations

import os
import re

from .model import SUPPORT_KIND, Doc, Unreadable
from .textutil import fold, nfc, read_text, slash, split_frontmatter

KIND_WORDS = ("実装仕様書", "非機能要件定義書", "要件定義書", "画面設計書", "基本設計書",
              "設計書", "仕様書", "指示書", "プロンプト")          # FR-3: 長い物から順
VERSION_RE = re.compile(r"\s*v\d[\d.]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PHASE_CELL_RE = re.compile(r"^\s*(\d{1,2})\s*$")
AC_RE = re.compile(r"^\s*[-*] \[([ xX])\]\s*\**AC-\d+")     # 「- [ ] AC-3: …」「- [x] **AC-3**」
H1_SCAN_LINES = 30


def product_name(body: list[str], stem: str) -> str:
    """FR-3。"""
    for ln in body[:H1_SCAN_LINES]:
        if ln.startswith("# "):
            t = ln[2:].strip()
            if " — " in t:
                t = t.split(" — ", 1)[0]
            t = VERSION_RE.sub("", t.rstrip())
            for w in KIND_WORDS:
                if t.endswith(w):
                    t = t[: -len(w)]
                    break
            t = t.strip()
            if t:
                return nfc(t)
            break
    return nfc(stem.split("_", 1)[0])


def created_date(fm: dict[str, str] | None) -> str | None:
    """FR-5。"""
    v = (fm or {}).get("作成日", "")
    return v if DATE_RE.match(v) else None


def last_phase(body: list[str]) -> int | None:
    """FR-6: 「実装フェーズ」を含む最初の ## 見出しの後の、最初の表の3行目以降の1列目の数の最大値。"""
    start = next((i for i, ln in enumerate(body) if ln.startswith("## ") and "実装フェーズ" in ln), None)
    if start is None:
        return None
    table: list[str] = []
    for ln in body[start + 1:]:
        if ln.lstrip().startswith("|"):
            table.append(ln.strip())
        elif table:
            break
    nums = []
    for row in table[2:]:
        cells = row.split("|")
        if len(cells) > 1:
            m = PHASE_CELL_RE.match(cells[1])
            if m:
                nums.append(int(m.group(1)))
    return max(nums) if nums else None


def ac_count(body: list[str]) -> tuple[int, int] | None:
    """受け入れ基準のチェックボックス (チェック済み, 全部)。1つも無ければ None。"""
    marks = [m.group(1) for m in map(AC_RE.match, body) if m]
    return (sum(c in "xX" for c in marks), len(marks)) if marks else None


def kind_of(stem: str, kinds: list[tuple[str, re.Pattern]]) -> str | None:
    for name, rx in kinds:
        if rx.search(stem):
            return name
    return None


def find_docs(vault: str, cfg: dict, registry: dict):
    """戻り値: (docs, unreadable, folders_without_specs, registry_issues)。docs はパスの名前順。"""
    spec_root = nfc(slash(cfg["vault"]["spec_root"])).strip("/")
    root_abs = os.path.join(vault, slash(cfg["vault"]["spec_root"]).strip("/"))    # 実際のパスは NFC にしない
    excl_dirs = [fold(slash(d)).strip("/") for d in cfg["vault"].get("exclude_dirs", [])]
    excl_files = {fold(slash(f)) for f in cfg["vault"].get("exclude_files", [])}
    excl_files |= {fold(slash(cfg["output"]["board"])), fold(slash(cfg["output"]["json"]))}
    kinds = [(k, re.compile(rx)) for k, rx in cfg.get("docs", {}).get("kinds", [])]
    support = {fold(s) for s in cfg.get("docs", {}).get("support", [])}

    includes = {fold(slash(e["path"])): e.get("kind", "仕様書") for e in registry.get("include", [])}
    excludes = {fold(slash(e["path"])) for e in registry.get("exclude", [])}
    originals = {fold(slash(e["path"])): e["path"] for e in registry.get("include", []) + registry.get("exclude", [])}
    seen_inc: set[str] = set()
    seen_exc: set[str] = set()

    docs: list[Doc] = []
    unreadable: list[Unreadable] = []
    folder_has_spec: dict[str, bool] = {}

    for dirpath, dirnames, filenames in os.walk(root_abs):
        dirnames.sort()
        rel_dir = nfc(slash(os.path.relpath(dirpath, root_abs)))
        rel_dir = "" if rel_dir == "." else rel_dir
        if any(fold(rel_dir) == d or fold(rel_dir).startswith(d + "/") for d in excl_dirs):
            dirnames[:] = []
            continue
        for fn in sorted(filenames):
            if not fn.lower().endswith(".md"):
                continue
            abs_path = os.path.join(dirpath, fn)        # 実際のパスは元の名前(NFD のまま。NFC にすると開けない)
            fn = nfc(fn)                                # NFC は比べ方と表示だけ
            vrel = f"{spec_root}/{rel_dir}/{fn}" if rel_dir else f"{spec_root}/{fn}"
            key = fold(vrel)
            if key in excl_files:
                continue
            stem = fn[:-3]
            if not fn.startswith("00_"):
                folder_has_spec.setdefault(rel_dir, False)
            if key in excludes:
                seen_exc.add(key)
                continue
            if key in includes:
                seen_inc.add(key)
                kind = includes[key]
            else:
                kind = kind_of(stem, kinds)
            if kind is None:
                if fold(fn) in support:
                    docs.append(Doc(vrel, abs_path, stem, SUPPORT_KIND, "", None, None, rel_dir))
                continue
            try:
                text = read_text(abs_path)
            except (UnicodeDecodeError, OSError) as e:
                unreadable.append(Unreadable("find", f"{type(e).__name__}: {e}", vrel))
                continue
            fm, body = split_frontmatter(text)
            docs.append(Doc(
                path=vrel, abs_path=abs_path, stem=stem, kind=kind,
                product=product_name(body, stem),
                created=created_date(fm),
                last_phase=last_phase(body) if kind == "仕様書" else None,
                spec_dir=rel_dir,
                ac=ac_count(body),
            ))
            folder_has_spec[rel_dir] = True

    issues = [f"[[include]] の path がありません: {originals[p]}" for p in sorted(includes) if p not in seen_inc]
    issues += [f"[[exclude]] の path がありません: {originals[p]}" for p in sorted(excludes) if p not in seen_exc]
    no_spec = sorted((d for d, has in folder_has_spec.items() if not has), key=fold)
    docs.sort(key=lambda d: fold(d.path))
    return docs, unreadable, no_spec, issues

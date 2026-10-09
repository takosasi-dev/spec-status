# 架空のプロジェクトだけを入れたお試し用の vault を作る(README のスクリーンショットもこれで撮る)。
# 使い方: python tools/demo_vault.py <作る場所>
#   できたら: python specstatus.py gui --vault <作る場所> --config <作る場所>/spec-status/data/config/demo.toml
import os
import shutil
import sys
from datetime import datetime, timedelta

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from specstatus import core, pngutil, records  # noqa: E402

CONFIG = """[pc]
name = "pc"

[vault]
spec_root = "仕様書MDファイル"
exclude_dirs = []
exclude_files = []

[docs]
kinds = [["要件定義書", "要件定義"], ["画面設計書", "画面設計"], ["仕様書", "仕様書"]]
support = ["README.md"]

[evidence.setsumei]
dir = ""
[evidence.tooldeck]
toml = ""
[evidence.implroot]
roots = []
[evidence.handoff]
handoffstub_toml = ""
memo_dir = ""
[evidence.devlog]
dir = "開発ログ"
scope = [""]

[output]
board = "仕様書MDファイル/00_実装状況.md"
json = "仕様書MDファイル/00_実装状況.json"

[board]
recent_days = 7
recent_max = 20
stale_days = 30
progress_weeks = 12
"""

# (仕様書フォルダ, 名前, 説明, フェーズ数, 記録: (状態, 終えたフェーズ, 待ち, メモ) か None)
PROJECTS = [
    ("Windows/QOLツール", "ClipNote", "クリップボード履歴", 4, ("実装完了", 4, "なし", "全フェーズ済み。v1.2 を配布中")),
    ("Windows/QOLツール", "WinSnap", "窓の並べ替え", 5, ("一部未実装", 5, "確認待ち", "複数モニタの記憶だけ未実装")),
    ("Windows/QOLツール", "FocusTimer", "集中タイマー", 4, ("着手済", 2, "確認待ち", "Phase 2 まで。通知音の選択待ち")),
    ("Windows/QOLツール", "FontPeek", "フォント見比べ", 3, None),
    ("Windows/開発ツール", "LogLens", "ログの絞り込み", 3, ("実装完了", 3, "なし", "テスト 84 件合格")),
    ("Windows/開発ツール", "BuildBadge", "ビルド結果の札", 3, ("未着手", None, "なし", "優先度低")),
    ("Windows/開発ツール", "DiffDesk", "差分ビューア", 4, ("撤退", 1, "なし", "既製品で足りたので中止")),
    ("Android/家計簿アプリ", "Kakeibo", "家計簿", 3, ("着手済", 1, "実物待ち", "実機での確認待ち")),
    ("Android/習慣アプリ", "HabitDots", "習慣トラッカー", 4, ("未着手", None, "なし", None)),
    ("Web・ブラウザ/Chrome拡張", "TabShelf", "タブの棚", 3, ("実装完了", 3, "実物待ち", "ストア申請の結果待ち")),
    ("Web・ブラウザ/Chrome拡張", "ReadLater", "あとで読む", 2, ("実装完了", 2, "なし", None)),
    ("Web・ブラウザ/Chrome拡張", "PageTint", "ページの色替え", 3, ("一部未実装", 3, "なし", "ダークサイトの例外だけ残り")),
    ("OS非依存/Obsidianプラグイン", "DailyCard", "日記カード", 3, None),
    ("OS非依存/Obsidianプラグイン", "TagTidy", "タグの整理", 3, ("未着手", None, "なし", None)),
    ("OS非依存/Discord", "RollBot", "ダイスBot", 2, ("実装完了", 2, "なし", "サーバーで稼働中")),
    ("Linux/CLIツール", "dfwatch", "ディスク残量の見張り", 2, ("実装完了", 2, "なし", None)),
    ("iOS/ウィジェット", "MoonWidget", "月齢ウィジェット", 3, None),
]

# 記録した日(今日から何日前か)。推移のグラフが育ち、Kakeibo が「止まっている物」になるようにばらす
DAYS_AGO = {"ClipNote": 77, "LogLens": 63, "DiffDesk": 60, "Kakeibo": 45, "TabShelf": 42, "ReadLater": 35,
            "RollBot": 28, "PageTint": 21, "dfwatch": 14, "WinSnap": 9, "BuildBadge": 6, "HabitDots": 5,
            "TagTidy": 4, "FocusTimer": 2}


# 受け入れ基準のチェック(済の数)。4つのうち何個にチェックを付けておくか
AC_DONE = {"実装完了": 4, "一部未実装": 3, "着手済": 1}
COLORS = ["#2f7ed8", "#23a565", "#d4891a", "#8e5bd8", "#d84a6a", "#159aa8", "#5b6b7d", "#c25a1e"]
CHANGED = "LogLens"          # 記録の後に仕様書を書き換えた扱いにする(「仕様が変わった物」の見本)
VULNERABLE = {"ClipNote": "requests==2.19.0\n"}   # 既知の脆弱性がある古い版(「依存の脆弱性」の見本。OSV を有効にしたときだけ数える)


def spec_text(name: str, desc: str, phases: int, ac_done: int) -> str:
    rows = "\n".join(f"| {i} | {desc}の段階 {i} |" for i in range(1, phases + 1))
    acs = "\n".join(f"- [{'x' if i <= ac_done else ' '}] AC-{i}: {desc}の確認 {i}" for i in range(1, 5))
    return (f"---\n作成日: 2026-09-01\n---\n# {name} 仕様書\n\n{desc}のツール(架空)。\n\n"
            f"## 実装フェーズ\n\n| Phase | 内容 |\n|---|---|\n{rows}\n\n## 受け入れ基準\n\n{acs}\n")


def icon_png(color: str, shape: int, size: int = 64) -> bytes:
    """角の丸い色の四角に白い図形(架空のアプリのアイコン)。4点ずつ取ってなめらかにする。"""
    c = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    m, rad = size * 0.06, size * 0.24
    px = bytearray(size * size * 4)

    def in_box(x, y):
        dx = max(m + rad - x, 0, x - (size - m - rad))
        dy = max(m + rad - y, 0, y - (size - m - rad))
        return dx * dx + dy * dy <= rad * rad

    def in_glyph(x, y):
        u, v = (x - size / 2) / size, (y - size / 2) / size
        return [u * u + v * v <= 0.045,
                abs(u) <= 0.2 and abs(v) <= 0.2,
                -0.2 <= v <= 0.18 and abs(u) <= (v + 0.2) * 0.6,
                abs(v) <= 0.2 and (abs(u + 0.12) <= 0.05 or abs(u - 0.12) <= 0.05 or abs(u) <= 0.05 and v >= 0)][shape % 4]
    for y in range(size):
        for x in range(size):
            box = glyph = 0
            for sx, sy in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)):
                if in_box(x + sx, y + sy):
                    box += 1
                    glyph += in_glyph(x + sx, y + sy)
            if box:
                t = glyph / box
                i = (y * size + x) * 4
                px[i:i + 4] = bytes([round(ch * (1 - t) + 255 * t) for ch in c] + [round(255 * box / 4)])
    return pngutil.encode(size, size, px)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__ or "python tools/demo_vault.py <作る場所>", file=sys.stderr)
        return 2
    vault = os.path.abspath(sys.argv[1])
    if os.path.exists(vault):
        # 前に作ったお試し用だけ消して作り直す。ほかのフォルダは消さない
        if os.listdir(vault) and not os.path.isfile(os.path.join(vault, "spec-status", "data", "config", "demo.toml")):
            print(f"空でないフォルダには作りません: {vault}", file=sys.stderr)
            return 2
        shutil.rmtree(vault)
    for d in ("説明書", "開発ログ", "work", "spec-status/data/config", "spec-status/data/events"):
        os.makedirs(os.path.join(vault, d), exist_ok=True)
    cfg = os.path.join(vault, "spec-status", "data", "config", "demo.toml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(CONFIG)
    old = (datetime.now() - timedelta(days=100)).timestamp()
    spec_paths = {}
    for folder, name, desc, phases, rec in PROJECTS:
        d = os.path.join(vault, "仕様書MDファイル", folder, name)
        os.makedirs(d, exist_ok=True)
        spec_paths[name] = os.path.join(d, f"{name}_{desc}_仕様書.md")
        with open(spec_paths[name], "w", encoding="utf-8") as f:
            f.write(spec_text(name, desc, phases, AC_DONE.get(rec[0], 0) if rec else 0))
        os.utime(spec_paths[name], (old, old))      # 記録より前に書いた仕様書にする
    board = core.load(vault, cfg)
    by_name = {ps.project.name: ps for ps in board.statuses}
    for folder, name, desc, phases, rec in PROJECTS:
        if rec is None:
            continue
        state, done, waiting, note = rec
        fields = {"state": state, "waiting": waiting, "last_phase": phases}
        if done is not None:
            fields["done_phase"] = done
        if note:
            fields["note"] = note
        if state in ("着手済", "一部未実装", "実装完了"):
            work = os.path.join(vault, "work", name)
            os.makedirs(work, exist_ok=True)
            fields["impl_add"] = [work.replace("\\", "/")]
            i = [p[1] for p in PROJECTS].index(name)
            with open(os.path.join(work, "icon.png"), "wb") as f:
                f.write(icon_png(COLORS[i % len(COLORS)], i))
            if name in VULNERABLE:
                with open(os.path.join(work, "requirements.txt"), "w", encoding="utf-8") as f:
                    f.write(VULNERABLE[name])
        at = datetime.now().astimezone() - timedelta(days=DAYS_AGO.get(name, 0))
        records.now_iso = lambda at=at: at.isoformat(timespec="seconds")
        code, msg = core.write_mark(board, by_name[name], fields, "user")
        if code:
            print("記録できません:", name, msg, file=sys.stderr)
            return 1
    recent = (datetime.now() - timedelta(days=3)).timestamp()
    os.utime(spec_paths[CHANGED], (recent, recent))
    code, msg, _ = core.build(vault, cfg)
    print(f"作りました: {vault}(build {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())

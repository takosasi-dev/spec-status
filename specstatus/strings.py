# GUI の画面に出す文言をまとめた所(§9.9「画面の文言は strings.py に集める」)。
# 文字列と、表示用の対応表だけ。振る舞いは持たない。
from __future__ import annotations

TITLE = "SpecStatus — 仕様書の実装状況"
APP_NAME = "SpecStatus"
APP_SUB = "仕様書の実装状況"
FONT_FAMILY = "Yu Gothic UI"
FONT_SIZE = 10

# 上の帯
SEARCH = "検索"
CATEGORIES = "分類"
CAT_ALL = "すべて"
RATIO = "実装完了 {done} / {total}({pct}%)"
ROW_COUNT = "{n} 件を表示 / 全 {total} 件"
SEARCH_TIP = "例: state:着手済 待ち:確認待ち is:脆弱 -Android \"語 句\""
FILTER_LABEL = "絞る:"
WAITING_ONLY = "待ち"
CONFLICT_ONLY = "食い違い"
STALE_ONLY = "止まり"
CHANGED_ONLY = "仕様変更"
VULN_ONLY = "脆弱性"
VIEWS = (("table", "表"), ("cards", "カード"), ("dashboard", "概要"))
FILTERING = "絞り込み中: {items}"      # 件数の横。何も絞っていなければ出さない
FILTER_SEARCH = "検索「{q}」"
FILTER_X = "×"

# 記録した直後の一言(見出しの帯に数秒)
FLASH_MANY = "{n} 件"
FLASH_STATE = "{who}を{state}にしました"
FLASH_WAITING = "{who}の待ちを{waiting}にしました"
FLASH_NOTE = "{who}のメモを記録しました"
FLASH_NOTE_CLEARED = "{who}のメモを消しました"
FLASH_IMPL_ADD = "{who}に実装フォルダを足しました"
FLASH_IMPL_REMOVE = "{who}から実装フォルダを外しました"
FLASH_OTHER = "{who}に記録しました"
FLASH_UNDO_HINT = "(Ctrl+Z で戻す)"
FLASH_UNDONE = "取り消しました"

# 表示と書き出しのメニュー
MENU = "表示"
MENU_THEME = "色"
THEMES = (("auto", "Windows に合わせる"), ("light", "ライト"), ("dark", "ダーク"))
THEME_RESTART = "色は次に開いたときから変わります。"
MENU_FONT_UP = "文字を大きく(Ctrl + ホイール)"
MENU_FONT_DOWN = "文字を小さく"
MENU_FONT_RESET = "文字の大きさを戻す"
MENU_COLUMNS = "表の列"
MENU_CSV = "今の一覧を CSV で書き出す…"
MENU_PNG = "今の画面を画像で書き出す…"
MENU_KEYS = "キー操作の一覧(?)"
EXPORT_TITLE = "書き出し"
EXPORT_DONE = "書き出しました: {path}"
EXPORT_FAILED = "書き出せませんでした。\n{err}"

# 詳細の「仕様の差分」タブ
TAB_DIFF = "差分"
DIFF_NONE = "記録した時点の仕様書の写しがありません。次に記録したときから比べられます。"
DIFF_SAME = "記録した時点から、仕様書は変わっていません。"
DIFF_COPY = "差分を Claude Code に渡す文をコピー"
PROGRESS = "推移({weeks}週)"
PROGRESS_TIP = "実装完了 {first} → {last}"
RELOAD = "再読み込み"
OPEN_BOARD = "一覧ノートを開く"
GENERATED = "読み込み: {at} ({pc})"
LOADING = "読み込み中…"
UNREADABLE_LINE = "読めなかった証拠: {items}"
UNREADABLE_ITEM = "{reader}({reason})"

# 状態の札
CHIP = "{state} {count}"

# 表の列(キー → 見出し)。キーは guilogic.sort_rows の列名
COLUMNS = (
    ("state", "状態"),
    ("name", "プロジェクト"),
    ("spec_dir", "仕様書フォルダ"),
    ("phase", "Phase"),
    ("waiting", "待ち"),
    ("last", "最後の記録"),
    ("source", "根拠"),
    ("conflict", "食い違い"),
    ("github", "公開"),
)
CONFLICT_MARK = "!"
SORT_ASC = " ▲"
SORT_DESC = " ▼"
EMPTY = "条件に合う仕様書はありません"
CLEAR_FILTERS = "絞り込みを外す"
ERROR_TITLE = "読み込めません"
ERROR_PATH = "パス: {path}"

# §9.5 書き方の約束
# 出所と「誰」の表記は一覧ノートと同じ物を使う(§9.5)
from .render import BY_LABEL as BY_LABELS, SOURCE_LABEL as SOURCE_LABELS  # noqa: E402,F401

# 右の詳細
DETAIL_NONE = "1件選ぶと詳細を出します"
DETAIL_MULTI = "{n} 件を選んでいます"
# v0.7.0 の欄(キー → 見出し)。詳細とツールチップに、値がある物だけ出す(guilogic.extra_details)
EXTRA_FIELDS = (
    ("pace", "見込み"),
    ("gap", "記録漏れ?"),
    ("questions", "未確定"),
    ("retreat", "撤退の判定の時期"),
    ("blocked_by", "前提が未完"),
    ("eol", "依存の古さ"),
    ("gh_stats", "GitHub の反響"),
)
_EXTRA = dict(EXTRA_FIELDS)
DETAIL_FIELDS = (          # 詳細の表(キー → 見出し)
    ("source", "根拠"),
    ("where", "場所"),
    ("spec_dir", "仕様書フォルダ"),
    ("phase", "Phase"),
    ("pace", _EXTRA["pace"]),
    ("waiting", "待ち"),
    ("note", "メモ"),
    ("gap", _EXTRA["gap"]),
    ("questions", _EXTRA["questions"]),
    ("retreat", _EXTRA["retreat"]),
    ("blocked_by", _EXTRA["blocked_by"]),
    ("activity", "最後に動いた日"),
    ("changed", "仕様書の更新"),
    ("ac", "受け入れ基準"),
    ("vulns", "依存の脆弱性"),
    ("eol", _EXTRA["eol"]),
    ("github", "GitHub"),
    ("gh_stats", _EXTRA["gh_stats"]),
)
DETAIL_HIDE_EMPTY = ("activity", "changed", "ac", "vulns", "github", *_EXTRA)    # 値が無ければ行ごと隠す
QUESTIONS_TEXT = "{open}"
QUESTIONS_MINE = "(あなたの番 {mine})"
BLOCKED_SEP = "・"
PACE_TEXT = "残り {remaining} フェーズ ≒ {days} 日"
EOL_ENDED = "サポート切れ {n}"
EOL_OUTDATED = "遅れている依存 {n}"
GH_STARS = "スター {n}"
GH_FORKS = "フォーク {n}"
GH_DOWNLOADS = "ダウンロード {n}"
CHANGED_TEXT = "{date}(最後の記録より後)"
AC_TEXT = "{done} / {total} にチェック"
VULNS_TEXT = "{count} / {total} 件(例: {packages})"
VULNS_TEXT_FIX = "{count} / {total} 件・一番重い {worst}\n{fix}"
VULNS_FIX = "{package} {version} → {fixed} に上げる"
VULNS_NONE = "なし(依存 {total} 件)"
STALE_TEXT = "{date}({days} 日止まっている)"
GITHUB_TEXT = "{repo}\n{release} / push {pushed} / CI {ci}"
TAB_DOCS = "文書"
TAB_IMPLS = "実装"
TAB_EVIDENCE = "証拠"
TAB_HISTORY = "履歴"
DOCS_HINT = "ダブルクリックで Obsidian で開きます"
IMPL_MISSING = "{path}  (この PC に無い: {pc})"
IMPL_OPEN = "開く"
IMPL_ADD = "フォルダを足す"
IMPL_REMOVE = "外す"
IMPL_PICK = "実装フォルダを選ぶ"
EVIDENCE = "証拠"
EVIDENCE_LINE = "{source}: {value}  {where}"
EVIDENCE_CONFLICT = "[食い違い] "
EVIDENCE_NOTE = "  ({note})"
HISTORY = "記録の履歴(新しい順)"
HISTORY_LINE = "{at}  {by}  {pc}  {changes}"
FIELD_LABELS = {
    "state": "状態",
    "done_phase": "終えたフェーズ",
    "last_phase": "最終フェーズ",
    "waiting": "待ち",
    "note": "メモ",
    "impl_add": "フォルダを足す",
    "impl_remove": "フォルダを外す",
    "confirmed": "確認済み",
    "undo": "取り消し",
}
CLEARED = "(消す)"

# 下の編集欄
NO_CHANGE = "変えない"
EDIT_STATE = "状態"
EDIT_DONE = "終えたフェーズ"
EDIT_LAST = "最終フェーズ"
EDIT_WAITING = "待ち"
EDIT_NOTE = "メモ"
CLEAR_NOTE = "メモを消す"
RECORD = "記録する"
UNDO = "取り消し"
COPY = "Claude Code に渡す文をコピー"
DEFAULT_COPY_TEMPLATE = "次の仕様書を実装して。着手する前に SpecStatus の show で状態を確かめること。\n仕様書: {abs_path}"

# 窓
CONFIRM_TITLE = "まとめて記録"
CONFIRM_BULK = "{n} 件に記録します(状態: {state} / 待ち: {waiting}。変えない項目は書かない)。よろしいですか"
ERR_PHASE = "{label} は 0〜99 の整数で入れてください: {value}"
ERR_NO_FIELDS = "変える項目がありません。"
ERR_NOTE_LEN = "メモは 200 字までです(今 {n} 字)。"
WRITE_FAILED_TITLE = "記録できませんでした"
WRITE_FAILED = "記録できませんでした(終了コード {code})。\n{reason}"
WRITE_PARTIAL = "{done} 件は記録しました。残りは書いていません。"
BUILD_FAILED_TITLE = "一覧ノートを書けませんでした"
BUILD_FAILED = "{msg}\n(記録は書いてあります)"
UNDO_EMPTY = "取り消せる記録はありません。"
UNDO_TITLE = "取り消し"
OBSIDIAN_FAILED_TITLE = "Obsidian で開けませんでした"
OBSIDIAN_FAILED = "次のファイルを手で開いてください。\n{path}"
EXPLORER_FAILED = "フォルダを開けませんでした。\n{path}\n{err}"
COPIED = "コピーしました: {name}"

# 更新
UPDATE_AVAILABLE = "{tag} が出ています"
UPDATE_BUTTON = "更新する"
UPDATE_TITLE = "SpecStatus の更新"
UPDATE_CONFIRM = "{tag} に更新します。\n\n{what}\n\n記録(data\\)には触りません。よろしいですか\n\n{notes}"
UPDATE_WHAT_VAULT = "・vault の spec-status(同期でほかの PC にも届きます)"
UPDATE_WHAT_EXE = "・この exe(窓を閉じてから入れ替えて、開き直します)"
UPDATE_RUNNING = "更新しています…"
UPDATE_DONE_VAULT = "vault の SpecStatus を {tag} にしました。"
UPDATE_FAILED = "更新できませんでした。\n{err}"

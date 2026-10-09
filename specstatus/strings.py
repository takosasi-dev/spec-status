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
WAITING_ONLY = "待ちだけ"
CONFLICT_ONLY = "食い違いだけ"
STALE_ONLY = "止まっている物だけ"
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
DETAIL_FIELDS = (          # 詳細の表(キー → 見出し)
    ("source", "根拠"),
    ("where", "場所"),
    ("spec_dir", "仕様書フォルダ"),
    ("phase", "Phase"),
    ("waiting", "待ち"),
    ("note", "メモ"),
    ("activity", "最後に動いた日"),
    ("github", "GitHub"),
)
STALE_TEXT = "{date}({days} 日止まっている)"
GITHUB_TEXT = "{repo}\n{release} / push {pushed} / CI {ci}"
DOCS = "文書(ダブルクリックで Obsidian)"
IMPLS = "実装フォルダ"
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

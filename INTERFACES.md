# SpecStatus 内部の契約(並列作業用)

型は `specstatus/model.py` だけ。ここに書いた関数の名前・引数・戻り値を変えない。変えたくなったら作業を止めて報告。

共通の決まり
- Python 3.11、標準ライブラリだけ。各ソースファイルの先頭に責務を3行以内の日本語コメント。
- 名前の比べ方は `textutil.fold`(NFC + casefold)。パスの区切りは `textutil.slash`。
- 数の閾値をコードに書かない(設定から読む)。テストは `tests/` に pytest、合成の一時フォルダだけを使う(本物の vault・L: に触らない)。
- 実行は `PYTHONUTF8=1`。`python -m pytest -q`(`L:\仕様書管理ソフト` で)。

## 1. 証拠の読み手 `specstatus/evidence/<name>.py`(担当 A)

1種類 = 1ファイル: `setsumei.py` `tooldeck.py` `implroot.py` `handoff.py` `devlog.py`。各ファイルに:

```python
NAME = "tooldeck"
def configured(vault: str, sec: dict) -> bool          # FR-15: 設定のパスが空文字(roots が [])なら False
def read(vault: str, sec: dict, projects: list[Project]) -> ReadResult
```

- `sec` は設定の `[evidence.<name>]` の辞書。`projects` は呼び手が `scope` で絞った後の物(読み手は scope を見ない)。
- パスは `textutil.resolve(vault, p)`(絶対ならそのまま)。
- 全体が読めない(設定したファイル・フォルダが無い等)は例外を投げてよい。呼び手が `Unreadable(reader=NAME, reason=str(e))` にする。1本だけ読めない(説明書の frontmatter が壊れている等)は `ReadResult.unreadable` に足して続ける。
- 返す `Evidence` の `source` は NAME。本文を写さない(INV-7): `value` は状態の値・パス・日付だけ。
- setsumei: `dir` 直下の `*.md`。ファイル名(拡張子なし)を `fold` でプロジェクト名と比べる。frontmatter(`textutil.split_frontmatter`)の `状態:` を `map` で写す。`map` に無い値は `Evidence(state=None, value=値, note="写し方の無い値")`。`状態:` が無ければ証拠なし。frontmatter が閉じていなければ unreadable。
- tooldeck: `toml` を tomllib で読み、`[[tool]]` の `id` を名前と比べ、`state` を `map` で写す(無い値は setsumei と同じ扱い)。
- implroot: `roots` の各フォルダ直下に、名前が `fold` で一致するフォルダがあり、`markers` のどれかがその中にあれば(空なら有無だけ)`Evidence(state="着手済", value=フォルダの絶対パス('/' 区切り))`。root が無ければ unreadable(例外でよい)。
- handoff: `handoffstub_toml` の `[map]` を読む(実物: `L:\Claude開発ツール\HandoffStub\handoffstub.toml`)。キーは仕様書フォルダ名か spec_root からの相対パス(相対パスのキーが優先)。値 `""` は対象外。メモは `<vault>/<memo_dir>/<値>.md`。メモがあれば `着手済`、行頭が `状態:` で、その後ろを strip した値がちょうど `未着手` の行があれば `未着手`(それ以外の値の `状態:` 行は使わない)。メモが無ければ証拠なし。
- devlog: `dir` の `YYYY-MM-DD.md`。`###` で始まる行に、プロジェクト名か `aliases` のどれかが単語として(前後の文字が半角英数字でない。大文字小文字は区別しない)出た最新の日付を `Evidence(state=None, value="YYYY-MM-DD", where=パス)` で1つ返す。
- テスト: `tests/test_evidence.py`(AC-10〜AC-12 の読み手側。AC-12 の例は必ず入れる)。

## 2. 記録 `specstatus/records.py`(担当 B)

```python
def validate(obj: object) -> str | None                     # §9.8 の表で検査。問題の理由(日本語)か None
def read_all(events_dir: str) -> tuple[list[Record], list[RecordProblem]]
def sort_key(r: Record) -> tuple                             # (at を datetime にした物, pc, file, line)
def fold(records: list[Record]) -> Folded                    # 1プロジェクト分。並びは呼び手が sort_key 済み
def dumps(obj: dict) -> str                                  # ensure_ascii=False, separators=(",", ":")
def append(events_dir: str, pc_name: str, line: str) -> int  # FR-22。0 か 6。OSError は投げる
def now_iso() -> str                                         # 秒まで・時差付き
```

- `read_all`: `events_dir` が無ければ `([], [])`。`*.jsonl` を全部(名前順)読む。末尾が `\n` で終わらない最後の行は「末尾が未完」。4096 バイト超・JSON でない・`validate` の理由がある行は問題に出す。中身が1文字も違わない行(`raw`)が既に取れていれば2回目以降は捨てる(FR-19)。戻す記録は `sort_key` 順。
- `fold`: 項目ごとに後の値で上書き。キーがあって値が null なら空に戻す。`impl_add` は集合に足し(ImplPath.pc は足した記録の pc、`exists_here=os.path.isdir`)、`impl_remove` は引く(比べ方は `textutil.norm_path`)。`history` は全記録、`state_record` は `state` キーを最後に持った記録(null で消したら None)。
- `append`: §9.8「書き方」の 0〜4 そのまま(ロックは `data/events/.<PC名>.lock`、100ms 間隔で最大3秒、60秒より古いロックは消して1回だけ再試行、取れなければ 6)。追記・バイナリ、末尾が `\n` でなければ先に `\n`、1回の write、flush と fsync、finally でロックを消す。秒数・回数はモジュール先頭の定数でよい(仕様書の固定値)。
- テスト: `tests/test_records.py`(AC-13・AC-17・AC-19・AC-22 と、`validate` の各制約、`fold` の上書き・null・impl の足し引き)。AC-17 は `multiprocessing` か `subprocess` で2プロセス×50回。

## 3. 中核 `specstatus/core.py`(担当: 本体。GUI はここだけを呼ぶ)

```python
def load(vault: str, config_path: str | None) -> Board       # 読むだけ。ConfigError を投げる
def write_mark(board: Board, ps: ProjectStatus, fields: dict, by: str) -> tuple[int, str]
def build(vault: str, config_path: str | None) -> tuple[int, str, Board | None]
def resolve_target(board: Board, arg: str) -> tuple[ProjectStatus | None, list[ProjectStatus]]
def where(board: Board, folder: str) -> list[ProjectStatus]
```

- `write_mark`: `fields` は記録の行に入れるキーだけの辞書。キー: `state`(str か None=記録の状態を消す)、`done_phase`、`last_phase`、`waiting`、`note`(str か None)、`impl_add`(list)、`impl_remove`(list)、`confirmed`(True)、`undo`(True)。§9.8 の検査に通れば1行書き `(0, "")`。通らなければ何も書かず `(2|5|6, 理由)`。build はしない。
- `build`: 読み直して出力2ファイルを書く。`(0|2|3, メッセージ, Board)`。2 のとき Board は None のことがある。
- `Board.statuses` は一覧ノートと同じ並び。

## 4. GUI `specstatus/gui.py` `specstatus/guilogic.py` `specstatus/strings.py` `start_gui.cmd`(担当 C)

- §9.9 のとおり。tkinter。画面の文言は全部 `strings.py`。
- `guilogic.py` は tkinter を import しない純関数:
  - `filter_rows(statuses, states: set[str], os_dir: str | None, waiting_only: bool, conflict_only: bool, query: str) -> list[ProjectStatus]`
  - `sort_rows(statuses, column: str, descending: bool) -> list[ProjectStatus]`(列名は strings の列キー: state/name/spec_dir/phase/waiting/last/source/conflict)
  - `row_values(ps) -> tuple[str, ...]`(表の1行の文字列。Phase・最後の記録・根拠の書き方は §9.5 の約束と同じ)
  - `undo_fields(before: Folded, fields: dict) -> dict`(fields で変えた項目を before の値に戻す記録。`state` が before で None なら `state: None`、`impl_add` → `impl_remove`、`impl_remove` → `impl_add`、`waiting` が before で None なら `"なし"`、`note` は before の値か None、`done_phase`/`last_phase` も before の値か None。`undo: True` を付ける)
  - `count_by_state(statuses) -> dict[str, int]`
- 記録は `core.write_mark(board, ps, fields, "user")` だけで書き、その後 `core.build(...)` を別スレッドで1回。部品にはメインスレッドからだけ触る(`after`)。
- 取り消しの単位 = [記録する] 1回分。最大20回。
- テスト: `tests/test_guilogic.py`(AC-39・AC-42 の確認後の関数・AC-43 の戻す値の計算)。core を呼ぶテストは書かない(core は並行して作っている)。
- `start_gui.cmd`: `pyw -3 "%~dp0specstatus.py" gui`。`pyw` が無ければ `pythonw`。どちらも無ければ理由を出して `pause`。
- `specstatus.py gui` からの入口は `gui.run(vault: str, config_path: str | None) -> int`。

## 5. 時間の流れと GitHub(2026-10-09 に追加)

- `history.py`: `state_at(ps, day) -> str | None`、`series(statuses, today, weeks) -> [(日付, 実装完了, 途中)]`、`week_range(day) -> (月, 日)`、`mark_stale(statuses, today, stale_days, git_date=git_last_date)`(`ps.last_activity` と `ps.stale_days` を付ける)。
- `github.py`: `attach(statuses, cfg, now=None, fetch=http_get, path=None) -> str`(`ps.github` を付け、止めた理由を返す。`[github] owner` が空なら何もしない)。
- `core.load` が両方を呼ぶ。`core.write_weekly(board, day) -> パス`、`render.weekly_markdown(board, day, today, dup_stems)`、`render.github_text(gh)`。
- テストは `tests/test_timeline.py`(git と通信は差し替える)。

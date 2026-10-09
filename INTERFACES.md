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

## 6. v0.6.0 の並列作業(2026-10-09)

共通の決まり(1〜4 章に加えて)
- **既存のファイルは、各担当の「触ってよい」に書いた物だけ直す。** `gui.py`・`cli.py`・`core.py`・`render.py`・`model.py`・`strings.py`・`guilogic.py`・`theme.py` は本体(統合役)だけが直す。各担当は新しいファイルに関数・部品を作り、本体が配線する。
- 画面の文言は各担当のモジュールの先頭に定数でまとめてよい。
- 通信・git・PowerShell・schtasks は引数で差し替えられるようにし、テストでは本物を呼ばない。窓を出すテストは書かない(純関数を分けて確かめる)。`python -m pytest -q` が全部通ること。
- 保存は `%LOCALAPPDATA%\SpecStatus\` の下(vault には書かない)。場所は引数 `folder` で差し替えられるように。
- 型は `model.py` の `ProjectStatus` をそのまま使う。持っている物: `project`(`name`・`key`・`spec_dir`・`docs`・`spec_docs`・`primary_doc`)、`state`、`waiting`、`folded`(`note`・`impl`・`history`・`last_record`)、`done_phase`・`last_phase`、`conflict`、`last_devlog_date`、`github`(dict か None)、`last_activity`・`stale_days`、`spec_changed`、`vulns`(dict か None)、`ac`((済, 全部) か None)。テストで ProjectStatus を作るときは `tests/test_guilogic.py` の `ps()` と `rec()` を使う。

### 担当 A: おすすめ・仕様書の差分・脆弱性の直し先
- `specstatus/recommend.py`: `recommend(statuses, today: date, limit: int = 5) -> list[tuple[ProjectStatus, int, list[str]]]`(点数の高い順。理由は短い日本語)、`section(statuses, today, link) -> list[str]`(一覧ノートの「## 今日のおすすめ(n)」の行。`link(ps)` はリンクの文字を返す関数)。
  - 点の付け方(仮決め): 確認待ち・実物待ち、脆弱な依存(数と深刻度)、仕様が変わった、止まっている(日数)、一部未実装、着手済で AC が進んでいる、などを足す。実装完了で何も無い物・撤退・証拠なしは出さない。重みはモジュールの先頭の定数に。
- `specstatus/snapshots.py`: 記録した時点の仕様書の写しを置いて差分を出す。`save(ps, folder=None)`(今の仕様書の文書を写す)、`ensure_baseline(statuses, folder=None)`(記録があり、仕様が変わっていなくて、写しが無い物だけ今の内容を写す)、`diff(ps, folder=None) -> list[tuple[str, list[str]]] | None`(文書の vault からのパスと unified diff の行。写しが無ければ None)、`diff_prompt(ps, folder=None) -> str`(Claude Code に「仕様書のこの差分を実装して」と渡す文。差分そのものを含める)。写しのキーは文書の `path`。
- `specstatus/osv.py` を拡張(触ってよい): `ps.vulns` に `"details": [{"package", "version", "ids", "severity", "fixed"}]`(深刻度の重い順)と `"worst"`(一番重い深刻度)を足す。深刻度と直る版は `GET https://api.osv.dev/v1/vulns/{id}`(登録不要)から取り、ID ごとに7日残す。直る版は、今の版と同じ先頭の数字の `fixed` を優先し、複数の脆弱性があれば一番大きい版。既存の `tests/test_checks.py` は通ったままにする。
- テスト: `tests/test_recommend.py`・`tests/test_snapshots.py`・`tests/test_osv_details.py`。

### 担当 B: 朝の知らせと週のまとめの自動化
- `specstatus/schedule.py`:
  - `notify_summary(board, state_path=None) -> tuple[str, str] | None`(題と本文。前回から増えた物(確認待ち・脆弱な依存・仕様が変わった物)と今の件数。何も無ければ None。前回の状態は `state_path` の JSON に書く)。
  - `toast(title, body, runner=None)`(Windows の通知。PowerShell の WinRT の ToastNotificationManager。AppUserModelID は "takosasi.SpecStatus" を試し、出せなければ PowerShell の ID に落とす)。
  - `install(vault, python=None, config=None, runner=None) -> list[str]`(schtasks で「SpecStatus 朝の知らせ」毎日 9:00 に `notify`、「SpecStatus 週のまとめ」毎週金曜 18:00 に `weekly --write`。pythonw で窓を出さない。同名は上書き)、`remove(runner=None) -> list[str]`、`status(runner=None) -> list[str]`。
  - CLI の配線用: `add_commands(sub, common)`(`notify` と `schedule {install,remove,status}` の subparser を足す)と `run(args, vault) -> int`。本体が cli.py から呼ぶ。
- テスト: `tests/test_schedule.py`(runner を差し替えて、組み立てたコマンドと PowerShell の文を確かめる)。

### 担当 C: 概要の画面とカード表示
- `specstatus/dashboard.py`: `class DashboardView(ttk.Frame)`。`__init__(self, parent, app)`、`refresh(self, statuses: list[ProjectStatus]) -> None`(今の分類の範囲の全件)。中身: 状態のドーナツ(状態の色)、分類ごとの完了率の横棒(上位10)、大きい推移の折れ線(`history.series`)、今週動いた物、今日のおすすめ(`recommend.recommend`。担当 A と並行なので try で import し、無ければ空として動く)。項目をクリックしたら `app.select_keys([key])`。
- `specstatus/cards.py`: `class CardView(ttk.Frame)`。`__init__(self, parent, app)`、`refresh(self, rows: list[ProjectStatus], selected: set[str]) -> None`。Canvas に縦スクロールのタイル: 大きいアイコン(`app.icon(key, size)`)・名前・状態の色の帯・Phase の進みの棒・待ち/脆弱性/止まり/仕様変更の小さな印。クリックで `app.select_keys([key])`、Ctrl クリックで足す、ダブルクリックで `app.open_ps(ps)`、右クリックで `app.context_menu(event, [ps])`。窓の幅で列の数を変える。
- 本体が用意する `app` の物(これ以外は使わない): `app.p`(色の辞書。`bg`・`panel`・`panel2`・`fg`・`muted`・`line`・`accent`・`accent_fg`・`select`・`select_fg`・`error`・`stripe`・`states`(状態→色)・`dark`)、`app.px(v)`(96dpi 基準→画面)、`app.font`・`app.bold`(タプル)、`app.root`、`app.board`、`app.icon(key, size) -> tk.PhotoImage | None`、`app.select_keys(keys: list[str])`、`app.selected_keys() -> set[str]`、`app.open_ps(ps)`、`app.context_menu(event, ps_list)`。
- テスト: 窓を出さない純関数(タイルの配置の計算・ドーナツの角度・分類ごとの完了率など)を分けて `tests/test_views.py` で確かめる。

### 担当 D: 細かい UI(設定の保存・ツールチップ・右クリックとキー・検索・書き出し)
- `specstatus/prefs.py`: `load(folder=None) -> dict`・`save(prefs, folder=None)`(`gui.json`。壊れていたら既定)。`DEFAULTS` を持つ: 窓の大きさと位置(`geometry`)、仕切りの位置(`sashes`)、分類、状態の札、チェック(待ち・食い違い・止まり・変更・脆弱)、並べ替え、表示(`view`: "table"・"cards"・"dashboard")、詳細のタブ、テーマ("auto"・"light"・"dark")、文字の大きさの差(`font_delta`: -2〜+6)、隠す列(`hidden_columns`)。
- `specstatus/tooltip.py`: `class TreeTooltip`(`__init__(self, widget, text_for_event, app)`。マウスが止まって 500ms で小窓、動いたり離れたら消す。`text_for_event(event) -> str | None`)。`tooltip_text(ps) -> str`(名前の全文・状態・待ち・メモ全文・脆弱性・仕様の更新・AC。純関数)。
- `specstatus/actions.py`: 右クリックのメニューとキー操作。`build_menu(app, ps_list) -> tk.Menu`(Obsidian で開く・実装フォルダを開く・GitHub を開く・状態を変える(下の段)・待ちを変える・指示文をコピー・差分の指示文をコピー(`snapshots.diff_prompt` が import できて写しがあれば))、`bind_keys(app)`(1〜5 で状態、W で待ちを順に、/ で検索、Enter で開く、F2 でメモ、? でキーの一覧の小窓)。キーは検索欄やメモ欄に文字を打っている間は効かせない。本体が用意する `app` の物は担当 C と同じ+ `app.set_state(ps_list, state)`・`app.set_waiting(ps_list, waiting)`・`app.copy_text(text)`・`app.focus_search()`・`app.focus_note()`・`app.selected() -> list[ProjectStatus]`・`app.open_primary()`・`app.open_impl_of(ps)`。
- `specstatus/query.py`: 検索の書き方。`parse(text) -> Query`、`match(ps, q, body: str | None = None) -> bool`。`state:着手済`(`状態:`)・`waiting:確認待ち`(`待ち:`)・`cat:Windows`(`分類:`)・`is:vuln`/`is:stale`/`is:changed`/`is:conflict`(日本語 `is:脆弱`/`is:止まり`/`is:変更`/`is:食い違い` も)・`has:github`/`has:note`・`-語`(含まない)・`"空白を含む語"`。素の語は名前・仕様書フォルダ・メモ・実装フォルダのパス・(body があれば)仕様書の本文に当てる。大文字小文字・全角半角は `textutil.fold`。
- `specstatus/export.py`: `to_csv(rows) -> str`(列は表と同じ+メモ・AC・脆弱性。書く側で utf-8-sig)、`capture_png(widget, path)`(Windows の PrintWindow で部品の範囲を撮って `pngutil.encode` で書く)。
- テスト: `tests/test_prefs.py`・`tests/test_query.py`・`tests/test_export.py`・`tests/test_tooltip.py`(純関数だけ)。

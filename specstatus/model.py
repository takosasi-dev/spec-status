# 中核の各段(find / group / evidence / records / decide / render / GUI)が受け渡すデータの形。
# ここにある型だけが段のあいだの契約。振る舞いは持たない。
from __future__ import annotations

from dataclasses import dataclass, field

STATES = ("実装完了", "一部未実装", "着手済", "未着手", "撤退", "証拠なし")
RECORDABLE_STATES = STATES[:5]          # 記録に書ける状態(「証拠なし」は書けない)
WAITINGS = ("なし", "確認待ち", "実物待ち")
BY_VALUES = ("user", "claude-code", "claude")
SUPPORT_KIND = "付属"
EVIDENCE_SOURCES = ("setsumei", "tooldeck", "implroot", "handoff", "devlog")


@dataclass
class Doc:
    path: str                 # vault からの相対パス。区切り '/'、NFC
    abs_path: str             # この PC での絶対パス
    stem: str                 # ファイル名(拡張子なし)、NFC
    kind: str                 # docs.kinds の種類名、または SUPPORT_KIND
    product: str              # FR-3 の製品名(付属は "")
    created: str | None       # FR-5 の YYYY-MM-DD
    last_phase: int | None    # FR-6(種類が「仕様書」の物だけ)
    spec_dir: str             # spec_root からの相対フォルダ。区切り '/'、NFC
    ac: tuple[int, int] | None = None   # 受け入れ基準のチェック「- [x] AC-n」の (済, 全部)。無ければ None


@dataclass
class Project:
    key: str                  # 一意の鍵 = f"{spec_dir}#{name}"
    name: str
    spec_dir: str             # 仕様書フォルダ(merge のときは spec_dirs の先頭で、実在する物)
    docs: list[Doc]           # パスの名前順。付属も含む
    aliases: list[str] = field(default_factory=list)   # registry の [[alias]] words

    @property
    def spec_docs(self) -> list[Doc]:
        return [d for d in self.docs if d.kind != SUPPORT_KIND]

    @property
    def primary_doc(self) -> Doc:
        specs = self.spec_docs
        for d in specs:
            if d.kind == "仕様書":
                return d
        return specs[0] if specs else self.docs[0]

    @property
    def last_phase(self) -> int | None:
        vals = [d.last_phase for d in self.spec_docs if d.last_phase is not None]
        return max(vals) if vals else None


@dataclass
class Evidence:
    source: str               # EVIDENCE_SOURCES のどれか、または "events"
    state: str | None         # 写した6状態。写し方が無い値・devlog は None
    value: str                # 元の値(devlog は日付 YYYY-MM-DD)
    where: str                # 場所(パス。行が分かれば "パス#L12")
    note: str = ""            # 例: "写し方の無い値"


@dataclass
class Unreadable:
    reader: str               # 読み手の名前(find / setsumei / tooldeck / ...)
    reason: str
    path: str = ""


@dataclass
class ReadResult:
    found: dict[str, list[Evidence]] = field(default_factory=dict)    # Project.key -> 証拠
    unreadable: list[Unreadable] = field(default_factory=list)


@dataclass
class Record:
    fields: dict              # 行の JSON そのもの(検査済み)
    file: str                 # 記録ファイル名(例 "pc.jsonl")
    line: int                 # 1 始まり
    raw: str                  # 行の文字列(改行なし)。FR-19 の重複判定に使う

    @property
    def at(self) -> str:
        return self.fields["at"]

    @property
    def pc(self) -> str:
        return self.fields["pc"]

    @property
    def by(self) -> str:
        return self.fields["by"]


@dataclass
class ImplPath:
    path: str                 # 絶対パス、区切り '/'
    pc: str                   # 足した記録の PC
    exists_here: bool


@dataclass
class Folded:
    """プロジェクトごとに記録を畳んだ結果(FR-18)。記録が無ければ全部空。"""
    state: str | None = None
    done_phase: int | None = None
    last_phase: int | None = None
    waiting: str | None = None          # None = 記録に無い(表示は「なし」)
    note: str | None = None
    impl: list[ImplPath] = field(default_factory=list)
    history: list[Record] = field(default_factory=list)   # 古い順
    state_record: Record | None = None  # state を最後に決めた記録

    @property
    def last_record(self) -> Record | None:
        return self.history[-1] if self.history else None


@dataclass
class RecordProblem:
    file: str
    line: int
    reason: str


@dataclass
class Orphan:
    doc: str
    path: str
    at: str
    pc: str


@dataclass
class ProjectStatus:
    project: Project
    state: str
    decided_by: dict                    # {"source", "value", "path"}
    evidence: list[Evidence]            # 決めた根拠以外の状態の証拠
    conflicts: list[Evidence]
    folded: Folded
    last_devlog_date: str | None = None
    github: dict | None = None          # github.attach が付ける {repo, url, pushed_at, release, release_at, ci}
    last_activity: str | None = None    # 最後に動いた日 YYYY-MM-DD(記録・開発ログ・実装フォルダの git の新しい方)
    stale_days: int | None = None       # 止まっている物なら、最後に動いてからの日数
    spec_changed: str | None = None     # 実装完了・一部未実装の最後の記録より後に仕様書が書き換えられた日(YYYY-MM-DD)
    vulns: dict | None = None           # osv.attach が付ける {count, total, packages, ids, lockfiles}

    @property
    def conflict(self) -> bool:
        return bool(self.conflicts)

    @property
    def ac(self) -> tuple[int, int] | None:
        """仕様書の文書を合わせた受け入れ基準のチェック (済, 全部)。"""
        acs = [d.ac for d in self.project.spec_docs if d.ac]
        return (sum(a[0] for a in acs), sum(a[1] for a in acs)) if acs else None

    @property
    def done_phase(self) -> int | None:
        return self.folded.done_phase

    @property
    def last_phase(self) -> int | None:
        return self.folded.last_phase if self.folded.last_phase is not None else self.project.last_phase

    @property
    def waiting(self) -> str:
        return self.folded.waiting or "なし"


@dataclass
class Board:
    vault: str
    pc_name: str
    config: dict
    docs: list[Doc]
    statuses: list[ProjectStatus]       # 一覧ノートと同じ並び
    unreadable: list[Unreadable]
    skipped_evidence: list[str]         # 設定が空で読まなかった証拠(FR-15)
    record_problems: list[RecordProblem]
    orphans: list[Orphan]
    folders_without_specs: list[str]
    registry_issues: list[str]
    record_count: int
    os_dirs: list[str]                  # spec_root 直下のフォルダ名(GUI の OS の選択)
    reader_failed: bool = False         # 読み手のどれかが例外で落ちた(終了コード 3)
    github_note: str = ""               # GitHub を取りに行けなかった等の一言(終了コードには響かない)
    osv_note: str = ""                  # OSV.dev を取りに行けなかった等の一言(同上)

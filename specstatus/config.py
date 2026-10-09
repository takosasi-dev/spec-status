# 設定ファイル data\config\<PC名>.toml と registry.toml を読み、PC 名と data\ の場所を決める(§2・§9.2・§9.3)。
# 読むだけ。設定の不備は ConfigError(終了コード 2)にする。
from __future__ import annotations

import os
import platform
import tomllib


class ConfigError(Exception):
    """設定・引数の不備。message をそのまま利用者に見せる。"""

    def __init__(self, message: str, path: str = ""):
        super().__init__(message)
        self.path = path


def _load_toml(path: str) -> dict:
    """PowerShell やメモ帳が付ける BOM を許す。"""
    with open(path, "r", encoding="utf-8-sig") as f:
        return tomllib.loads(f.read())


def data_dir(vault: str) -> str:
    return os.path.join(vault, "spec-status", "data")


def events_dir(vault: str) -> str:
    return os.path.join(data_dir(vault), "events")


def default_config_path(vault: str) -> str:
    return os.path.join(data_dir(vault), "config", f"{platform.node()}.toml")


def load_config(vault: str, path: str | None) -> dict:
    path = path or default_config_path(vault)
    if not os.path.isfile(path):
        raise ConfigError(
            f"設定ファイルがありません。config.example.toml を写して作ってください: {path}", path)
    try:
        cfg = _load_toml(path)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"設定ファイルを読めません: {path}: {e}", path) from e
    cfg["_path"] = path
    for sec, key in (("vault", "spec_root"), ("output", "board"), ("output", "json")):
        if not isinstance(cfg.get(sec, {}).get(key), str):
            raise ConfigError(f"設定に [{sec}] {key} がありません: {path}", path)
    return cfg


def pc_name(cfg: dict) -> str:
    return (cfg.get("pc", {}).get("name") or "").strip() or platform.node()


def pc_name_conflicts(vault: str) -> list[str]:
    """data\\config\\*.toml の [pc] name が2つ以上のファイルで同じなら、その知らせ。空の name はかぶりの対象外。
    記録ファイルは PC 名ごとなので、かぶると同期で互いの記録を上書きして消す。読めないファイルは飛ばす。"""
    folder = os.path.join(data_dir(vault), "config")
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".toml"))
    except OSError:
        return []
    by_name: dict[str, list[str]] = {}
    shown: dict[str, str] = {}
    for fn in names:
        try:
            name = _load_toml(os.path.join(folder, fn)).get("pc", {}).get("name") or ""
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, AttributeError):
            continue
        name = name.strip() if isinstance(name, str) else ""
        if name:
            k = name.casefold()                         # 記録ファイルの名前になるので、大文字小文字の違いもかぶり
            by_name.setdefault(k, []).append(fn)
            shown.setdefault(k, name)
    return [f"PC 名 {shown[k]} が {' と '.join(fs)} でかぶっています。記録が同期で消えます"
            for k, fs in by_name.items() if len(fs) > 1]


def load_registry(vault: str) -> dict:
    """data\\registry.toml(無ければ空)。"""
    path = os.path.join(data_dir(vault), "registry.toml")
    if not os.path.isfile(path):
        return {}
    try:
        return _load_toml(path)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"registry.toml を読めません: {path}: {e}", path) from e

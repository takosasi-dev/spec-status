# テスト全体の共通: %LOCALAPPDATA% を一時フォルダに向け、本物の保存(GitHub・OSV・アイコン・仕様書の写し・設定)を汚さない。
import pytest


@pytest.fixture(autouse=True)
def _private_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))

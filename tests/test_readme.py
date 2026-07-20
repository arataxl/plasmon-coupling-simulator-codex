"""READMEの言語分割と相互リンクを確認する。"""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_english_and_japanese_readmes_link_to_each_other() -> None:
    """提出時の入口から両言語のREADMEへ到達できる。"""
    english_readme = REPOSITORY_ROOT / "README.md"
    japanese_readme = REPOSITORY_ROOT / "README-JP.md"

    assert english_readme.is_file()
    assert japanese_readme.is_file()
    assert "Japanese version: [README-JP.md](README-JP.md)" in english_readme.read_text(
        encoding="utf-8"
    )
    assert "English version: [README.md](README.md)" in japanese_readme.read_text(
        encoding="utf-8"
    )

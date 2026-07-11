"""Tests for the knowledge store (ryft.knowledge.store)."""

from pathlib import Path

from ryft.knowledge.store import KnowledgeStore, Symbol


def _make_symbol(name: str, file: str = "sample.py") -> Symbol:
    return Symbol(
        name=name,
        kind="function",
        file=file,
        line=1,
        end_line=3,
        signature=f"def {name}():",
        doc="",
        hash="h1",
    )


def test_upsert_and_search_roundtrip(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    assert store.symbol_count() == 0

    store.upsert_symbols("sample.py", [_make_symbol("do_thing")])
    assert store.symbol_count() == 1

    hits = store.search_symbols("do_thing", limit=5)
    assert hits
    assert hits[0].name == "do_thing"
    assert hits[0].file == "sample.py"


def test_search_miss_returns_empty(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.upsert_symbols("sample.py", [_make_symbol("alpha")])
    assert store.search_symbols("nonexistent_symbol_xyz", limit=5) == []


def test_remove_file_decrements_count(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.upsert_symbols("a.py", [_make_symbol("fn_a", "a.py")])
    store.upsert_symbols("b.py", [_make_symbol("fn_b", "b.py")])
    assert store.symbol_count() == 2

    store.remove_file("a.py")
    assert store.symbol_count() == 1
    assert store.search_symbols("fn_a", limit=5) == []
    assert store.search_symbols("fn_b", limit=5)

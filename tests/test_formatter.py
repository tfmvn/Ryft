from pathlib import Path

from ryft import formatter


def test_python_comment_remover_strips_comments():
    src = "x = 1  # comment\ny = 2\n"
    out = formatter.PythonCommentRemover().process(src)
    assert "#" not in out
    assert "x = 1" in out and "y = 2" in out


def test_python_comment_remover_respects_remove_comments_false():
    src = "x = 1  # keep me\n"
    out = formatter.PythonCommentRemover(remove_comments=False).process(src)
    assert "# keep me" in out


def test_python_comment_remover_collapses_blanks():
    src = "a\n\n\n\n\nb\n"
    out = formatter.PythonCommentRemover(max_blank_lines=1).process(src)
    assert out == "a\n\nb\n"


def test_python_comment_remover_preserves_string_hash():
    src = 'x = "not a # comment"\n'
    out = formatter.PythonCommentRemover().process(src)
    assert out == src


def test_lua_comment_remover_strips_line_and_block_comments():
    src = "x = 1 -- line comment\n--[[ block\ncomment ]]\ny = 2\n"
    out = formatter.LuaCommentRemover().process(src)
    assert "--" not in out
    assert "x = 1" in out and "y = 2" in out


def test_format_file_writes_changes_and_reports_true(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1  # c\n\n\n\ny = 2\n")
    changed = formatter.format_file(f, max_blank_lines=1, remove_comments=True)
    assert changed is True
    assert f.read_text() == "x = 1\n\ny = 2\n"


def test_format_file_no_change_returns_false(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    assert formatter.format_file(f, max_blank_lines=2, remove_comments=True) is False


def test_format_file_rejects_syntax_breaking_output(tmp_path, monkeypatch):
    f = tmp_path / "a.py"
    f.write_text("x = 1  # c\n")

    # Force the processor to emit invalid Python; format_file must refuse
    # to write it rather than corrupt the file.
    monkeypatch.setattr(
        formatter.PythonCommentRemover, "process",
        lambda self, source: "def (::: broken"
    )
    changed = formatter.format_file(f, max_blank_lines=2, remove_comments=True)
    assert changed is False
    assert f.read_text() == "x = 1  # c\n"


def test_format_file_unsupported_extension_skipped(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello\n")
    assert formatter.format_file(f) is False


def test_format_paths_returns_only_changed(tmp_path):
    a = tmp_path / "a.py"
    a.write_text("x = 1  # c\n")
    b = tmp_path / "b.py"
    b.write_text("y = 2\n")
    changed = formatter.format_paths([a, b], max_blank_lines=2, remove_comments=True)
    assert changed == [a]

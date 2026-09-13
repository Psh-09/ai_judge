from app.services.code import (
    check_length,
    compute_code_hash,
    normalize_newlines,
    split_lines,
    strip_comments,
    total_lines,
)


def test_normalize_newlines_converts_crlf_and_cr_to_lf():
    assert normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"


def test_split_lines_counts_blank_lines_and_does_not_trim():
    code = "a\n\nb\n"
    lines = split_lines(code)
    assert lines == ["a", "", "b", ""]
    assert total_lines(code) == 4


def test_split_lines_handles_crlf_as_single_newline():
    assert split_lines("a\r\nb") == ["a", "b"]


def test_check_length_within_limits():
    result = check_length("a\nb\n")
    assert result.exceeds is False
    assert result.exceeds_lines is False
    assert result.exceeds_chars is False


def test_check_length_exceeds_lines():
    code = "\n".join(["x"] * 501)
    result = check_length(code)
    assert result.exceeds_lines is True
    assert result.exceeds is True


def test_check_length_exceeds_chars():
    code = "a" * 20001
    result = check_length(code)
    assert result.exceeds_chars is True
    assert result.exceeds is True


def test_strip_comments_python_removes_hash_comment_but_not_inside_string():
    code = 'x = 1  # comment\ny = "a#b"\n'
    stripped = strip_comments(code, "python")
    assert "# comment" not in stripped
    assert '"a#b"' in stripped


def test_strip_comments_javascript_removes_line_and_block_comments():
    code = 'const x = 1; // line comment\n/* block\ncomment */\nconst y = "http://not-a-comment";\n'
    stripped = strip_comments(code, "javascript")
    assert "// line comment" not in stripped
    assert "block" not in stripped
    assert '"http://not-a-comment"' in stripped


def test_strip_comments_unsupported_language_returns_unchanged():
    code = "# not stripped for java\nint x = 1;\n"
    assert strip_comments(code, "java") == code


def test_compute_code_hash_ignores_whitespace_and_comment_differences():
    a = "def f():\n    return 1\n"
    b = "def f():\n\n    return 1  # trailing comment\n"
    assert compute_code_hash(a, "python") == compute_code_hash(b, "python")


def test_compute_code_hash_ignores_literal_value_differences():
    a = 'x = "hello"\ny = 42\n'
    b = 'x = "goodbye"\ny = 99\n'
    assert compute_code_hash(a, "python") == compute_code_hash(b, "python")


def test_compute_code_hash_differs_on_structural_change():
    a = "def f():\n    return 1\n"
    b = "def g():\n    return 1\n"
    assert compute_code_hash(a, "python") != compute_code_hash(b, "python")

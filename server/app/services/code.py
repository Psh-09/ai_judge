import hashlib
import re
from dataclasses import dataclass

MAX_LINES = 500
MAX_CHARS = 20000

_STRING_LITERAL_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_NUMBER_LITERAL_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")
_WHITESPACE_RUN_RE = re.compile(r"[ \t]+")

_COMMENT_QUOTE_CHARS = {
    "python": ("'", '"'),
    "javascript": ("'", '"', "`"),
    "typescript": ("'", '"', "`"),
}


def normalize_newlines(code: str) -> str:
    return code.replace("\r\n", "\n").replace("\r", "\n")


def split_lines(code: str) -> list[str]:
    """1-based 라인 번호의 근거. 빈 줄도 포함하고 앞뒤를 트림하지 않는다."""
    return normalize_newlines(code).split("\n")


def total_lines(code: str) -> int:
    return len(split_lines(code))


@dataclass(frozen=True)
class LengthCheck:
    total_lines: int
    total_chars: int
    exceeds_lines: bool
    exceeds_chars: bool

    @property
    def exceeds(self) -> bool:
        return self.exceeds_lines or self.exceeds_chars


def check_length(code: str) -> LengthCheck:
    lines = split_lines(code)
    return LengthCheck(
        total_lines=len(lines),
        total_chars=len(code),
        exceeds_lines=len(lines) > MAX_LINES,
        exceeds_chars=len(code) > MAX_CHARS,
    )


def _strip_comments_with_quotes(code: str, quote_chars: tuple[str, ...], block_comments: bool) -> str:
    result = []
    in_string: str | None = None
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                result.append(code[i + 1])
                i += 2
                continue
            if ch == in_string:
                in_string = None
            i += 1
            continue
        if ch in quote_chars:
            in_string = ch
            result.append(ch)
            i += 1
            continue
        if ch == "#" and not block_comments:
            while i < n and code[i] != "\n":
                i += 1
            continue
        if block_comments and ch == "/" and i + 1 < n and code[i + 1] == "/":
            while i < n and code[i] != "\n":
                i += 1
            continue
        if block_comments and ch == "/" and i + 1 < n and code[i + 1] == "*":
            i += 2
            while i + 1 < n and not (code[i] == "*" and code[i + 1] == "/"):
                i += 1
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def strip_comments(code: str, language: str) -> str:
    """python/javascript/typescript만 주석을 제거한다. 그 외 언어는 그대로 반환한다."""
    quote_chars = _COMMENT_QUOTE_CHARS.get(language)
    if quote_chars is None:
        return code
    return _strip_comments_with_quotes(code, quote_chars, block_comments=language != "python")


def _normalize_whitespace(code: str) -> str:
    lines = (_WHITESPACE_RUN_RE.sub(" ", line.strip()) for line in code.split("\n"))
    return "\n".join(line for line in lines if line)


def _mask_literals(code: str) -> str:
    code = _STRING_LITERAL_RE.sub("<STR>", code)
    return _NUMBER_LITERAL_RE.sub("<NUM>", code)


def compute_code_hash(code: str, language: str) -> str:
    """주석 제거 → 공백 정리 → 리터럴 마스킹 순으로 정규화한 뒤 SHA-256 해시를 낸다."""
    normalized = normalize_newlines(code)
    without_comments = strip_comments(normalized, language)
    whitespace_normalized = _normalize_whitespace(without_comments)
    masked = _mask_literals(whitespace_normalized)
    return hashlib.sha256(masked.encode("utf-8")).hexdigest()

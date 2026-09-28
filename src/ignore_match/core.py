from __future__ import annotations

import os
import posixpath
import re
from typing import Iterable, List, Optional, Tuple


def _split_lines(text: str) -> List[str]:
    """Split text into lines, normalizing line endings.

    We split on \n after converting \r\n and lone \r to \n so that files written on
    Windows or classic Mac do not produce phantom trailing characters that would
    silently corrupt the last token of a line.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.split("\n")


def _strip_trailing_spaces(pattern: str) -> str:
    """Remove trailing whitespace unless it is backslash-escaped.

    gitignore treats unescaped trailing spaces as insignificant. A backslash
    before a space means the space is part of the pattern, so we must not strip
    past an odd-length run of trailing backslashes.
    """
    end = len(pattern)
    while end > 0 and pattern[end - 1] == " ":
        backslashes = 0
        i = end - 2
        while i >= 0 and pattern[i] == "\\":
            backslashes += 1
            i -= 1
        if backslashes % 2 == 1:
            break
        end -= 1
    return pattern[:end]


def _split_dirs(pattern: str) -> Tuple[List[str], bool]:
    """Split a pattern on '/' and report whether it was anchored.

    A leading slash anchors the pattern to the root. We strip it here and return
    True so the matcher knows not to search in subdirectories. Internal slashes
    do not anchor to the root; they only constrain the relative structure of the
    match, so a pattern like a/foo can still match at any depth (x/a/foo).
    """
    anchored = False
    if pattern.startswith("/"):
        pattern = pattern[1:]
        anchored = True
    parts = pattern.split("/")
    # Collapse consecutive empty segments from doubled slashes; they carry no
    # semantic meaning and would otherwise create empty regex groups.
    parts = [p for p in parts if p != ""]
    return parts, anchored


def _translate_segment(segment: str) -> str:
    """Translate a single path segment (no slashes) into a regex string.

    Supports the gitignore glob subset: *, ?, [...], and backslash escapes.
    Character classes honor ! negation and ] as the first character. We do NOT
    support brace expansion {a,b} because git itself does not.
    """
    out: List[str] = []
    i = 0
    n = len(segment)
    while i < n:
        c = segment[i]
        if c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            end = i + 1
            negate = False
            if end < n and segment[end] == "!":
                negate = True
                end += 1
            # A ] immediately after [ or [! is a literal member of the class.
            if end < n and segment[end] == "]":
                end += 1
            while end < n and segment[end] != "]":
                end += 1
            if end >= n:
                # No closing bracket: treat '[' as a literal character.
                out.append(re.escape("["))
                i += 1
                continue
            inner = segment[i + 1 : end]
            if negate:
                inner = inner[1:]
            # Escape backslashes inside the class so regex compiles them as
            # literals, matching git's treatment of them in this context.
            inner = inner.replace("\\", "\\\\")
            prefix = "^" if negate else ""
            out.append("[" + prefix + inner + "]")
            i = end + 1
        elif c == "\\":
            if i + 1 < n:
                out.append(re.escape(segment[i + 1]))
                i += 2
            else:
                out.append(re.escape("\\"))
                i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return "".join(out)


def _translate_pattern(pattern: str) -> Tuple[re.Pattern, bool]:
    """Translate a gitignore pattern into a compiled regex.

    Returns (regex, dir_only). dir_only is True when the pattern ends with a
    slash, meaning it only matches directories.
    """
    dir_only = False
    if pattern.endswith("/"):
        dir_only = True
        pattern = pattern[:-1]
    if pattern == "":
        return re.compile("$^"), dir_only
    parts, anchored = _split_dirs(pattern)
    seg_regex = [_translate_segment(p) for p in parts]
    if anchored:
        body = "/".join(seg_regex)
        regex = "^(?:" + body + ")(?:/.*)?$"
    else:
        # Unanchored: match the segments anywhere in the path, at any depth.
        body = "/".join(seg_regex)
        regex = "^(?:.*/)??" + body + "(?:/.*)?$"
    return re.compile(regex), dir_only


def _normalize_path(path: str) -> str:
    """Normalize a path to forward-slash, no-leading-./ form.

    gitignore operates on forward-slash paths. We accept OS-native separators
    so callers can pass os.path.join results without translation.
    """
    path = path.replace(os.sep, "/")
    if path == ".":
        return ""
    if path.startswith("./"):
        path = path[2:]
    while path.startswith("/"):
        path = path[1:]
    if path.endswith("/"):
        path = path[:-1]
    return path


class _Rule:
    """A single compiled ignore rule."""

    __slots__ = ("regex", "dir_only", "negate", "source")

    def __init__(self, regex: re.Pattern, dir_only: bool, negate: bool, source: str) -> None:
        self.regex = regex
        self.dir_only = dir_only
        self.negate = negate
        self.source = source


class IgnoreMatch:
    """Match paths against a set of gitignore-style rules.

    Rules are evaluated in order. Later rules override earlier ones, and a
    negation (!pattern) re-includes a path that an earlier rule excluded. This
    matches git's documented precedence: the last matching rule wins.
    """

    def __init__(self, rules: Optional[Iterable[_Rule]] = None) -> None:
        self._rules: List[_Rule] = list(rules) if rules is not None else []

    def add_pattern(self, pattern: str) -> None:
        """Add a single gitignore-style pattern."""
        rule = self._compile_pattern(pattern)
        if rule is not None:
            self._rules.append(rule)

    @staticmethod
    def _compile_pattern(pattern: str) -> Optional[_Rule]:
        if pattern == "":
            return None
        if pattern.startswith("#"):
            return None
        negate = False
        if pattern.startswith("!"):
            negate = True
            pattern = pattern[1:]
            if pattern == "":
                return None
        pattern = _strip_trailing_spaces(pattern)
        if pattern == "":
            return None
        regex, dir_only = _translate_pattern(pattern)
        return _Rule(regex, dir_only, negate, pattern)

    def add_patterns(self, patterns: Iterable[str]) -> None:
        """Add several patterns, preserving order."""
        for p in patterns:
            self.add_pattern(p)

    def match(self, path: str, is_dir: bool = False) -> bool:
        """Return True if *path* is ignored under the current rules.

        is_dir should be True when the path refers to a directory. Rules that
        end with a trailing slash only match directories; passing is_dir=False
        for such a path means the rule does not apply.
        """
        norm = _normalize_path(path)
        if norm == "":
            return False
        ignored = False
        for rule in self._rules:
            if rule.dir_only and not is_dir:
                continue
            if rule.regex.match(norm):
                ignored = not rule.negate
        return ignored

    def filter(self, paths: Iterable[str], dirs: Optional[Iterable[bool]] = None) -> List[str]:
        """Return the subset of *paths* that are NOT ignored.

        dirs, if given, is a parallel iterable of is_dir flags. When omitted,
        every path is treated as a file.
        """
        paths_list = list(paths)
        if dirs is None:
            dirs_iter = iter(lambda: False, None)
        else:
            dirs_iter = iter(dirs)
        return [p for p, d in zip(paths_list, dirs_iter) if not self.match(p, d)]


def parse_ignore_file(text: str) -> IgnoreMatch:
    """Build an IgnoreMatch from the contents of a gitignore-style file."""
    matcher = IgnoreMatch()
    for line in _split_lines(text):
        matcher.add_pattern(line)
    return matcher

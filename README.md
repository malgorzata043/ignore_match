# Ignore Match

Match paths against gitignore-style rules, with last-match-wins precedence.

## Usage

```python
from ignore_match import IgnoreMatch, parse_ignore_file

m = IgnoreMatch()
m.add_pattern("*.log")
m.add_pattern("!keep.log")
m.add_pattern("build/")

m.match("debug.log")        # True
m.match("keep.log")         # False
m.match("build", is_dir=True)  # True
m.match("build", is_dir=False) # False

m.filter(["a.log", "keep.log", "b.txt", "c.log"])
# ['keep.log', 'b.txt']

text = "*.log\n!keep.log\nbuild/\n"
m2 = parse_ignore_file(text)
m2.match("debug.log")  # True
```

## Why this exists

The problem: you have a list of filesystem paths and a gitignore-style ruleset,
and you need to know which paths survive. The standard library does not ship a
gitignore matcher, and pulling in a dependency for this is often overkill.

The trade-off: this library implements a deliberate subset of gitignore
globbing. It supports `*`, `?`, `[...]` character classes, `!` negation,
trailing-slash directory-only rules, leading-slash anchoring, backslash
escapes, and `#` comments. It does **not** support `**` as a directory-spanning
wildcard — in gitignore, `**` only has special meaning between slashes
(`a/**/b`), and supporting that one case would double the complexity of the
matcher for marginal gain. Instead `**` is treated as two literal `*` segments
within a path component, which matches git's behavior for patterns like
`a/**b`. If you need `a/**/b`, express it as two rules or preprocess your
patterns.

## Edge cases you will hit

- **Last match wins.** A negation (`!pattern`) re-includes a path only if no
  later rule excludes it again. Order matters.
- **Trailing slash means directories only.** Pass `is_dir=True` to `match` for
  directory paths, or a `build/` rule will not fire on a file named `build`.
- **Internal slashes anchor.** `a/foo` matches `a/foo` and `x/a/foo` but not
  `b/foo`, because the slash ties it to a specific parent. A leading slash
  (`/foo`) anchors to the root only.
- **Trailing spaces are stripped** unless backslash-escaped. `foo\ ` (with an
  escaped space) matches a path containing a literal trailing space.
- **Path normalization** converts OS-native separators to `/` and strips a
  leading `./`, so you can pass `os.path.join` results directly.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.


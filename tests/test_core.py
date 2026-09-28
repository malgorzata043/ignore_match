import os
import unittest

from ignore_match import IgnoreMatch, parse_ignore_file


class TestPatternBasics(unittest.TestCase):
    def test_simple_filename_matches_anywhere(self):
        m = IgnoreMatch()
        m.add_pattern("foo")
        self.assertTrue(m.match("foo"))
        self.assertTrue(m.match("a/foo"))
        self.assertTrue(m.match("a/b/foo"))
        self.assertFalse(m.match("foobar"))
        self.assertFalse(m.match("a/foobar"))

    def test_anchored_pattern_only_matches_at_root(self):
        m = IgnoreMatch()
        m.add_pattern("/foo")
        self.assertTrue(m.match("foo"))
        self.assertFalse(m.match("a/foo"))
        self.assertFalse(m.match("a/b/foo"))

    def test_internal_slash_anchors(self):
        m = IgnoreMatch()
        m.add_pattern("a/foo")
        self.assertTrue(m.match("a/foo"))
        self.assertTrue(m.match("x/a/foo"))
        self.assertFalse(m.match("b/foo"))

    def test_star_matches_within_segment(self):
        m = IgnoreMatch()
        m.add_pattern("*.txt")
        self.assertTrue(m.match("a.txt"))
        self.assertTrue(m.match("dir/a.txt"))
        self.assertFalse(m.match("a.txt.bak"))
        self.assertFalse(m.match("a/other"))

    def test_question_mark_matches_single_char(self):
        m = IgnoreMatch()
        m.add_pattern("f?o")
        self.assertTrue(m.match("foo"))
        self.assertTrue(m.match("fao"))
        self.assertFalse(m.match("fooo"))
        self.assertFalse(m.match("fo"))

    def test_double_star_in_segment_is_literal(self):
        m = IgnoreMatch()
        m.add_pattern("a/**b")
        self.assertTrue(m.match("a/**b"))
        self.assertTrue(m.match("x/a/**b"))
        self.assertTrue(m.match("a/xb"))

    def test_trailing_slash_only_matches_dirs(self):
        m = IgnoreMatch()
        m.add_pattern("build/")
        self.assertTrue(m.match("build", is_dir=True))
        self.assertFalse(m.match("build", is_dir=False))
        self.assertTrue(m.match("src/build", is_dir=True))
        self.assertFalse(m.match("src/build", is_dir=False))

    def test_negation_reincludes(self):
        m = IgnoreMatch()
        m.add_pattern("*.log")
        m.add_pattern("!keep.log")
        self.assertTrue(m.match("a.log"))
        self.assertFalse(m.match("keep.log"))
        self.assertTrue(m.match("dir/a.log"))
        self.assertFalse(m.match("dir/keep.log"))

    def test_last_match_wins(self):
        m = IgnoreMatch()
        m.add_pattern("*.log")
        m.add_pattern("!keep.log")
        m.add_pattern("keep.log")
        self.assertTrue(m.match("keep.log"))

    def test_comment_lines_ignored(self):
        m = IgnoreMatch()
        m.add_pattern("# this is a comment")
        m.add_pattern("foo")
        self.assertFalse(m.match("# this is a comment"))
        self.assertTrue(m.match("foo"))

    def test_blank_lines_ignored(self):
        m = IgnoreMatch()
        m.add_pattern("")
        m.add_pattern("foo")
        self.assertFalse(m.match(""))
        self.assertTrue(m.match("foo"))


class TestCharacterClasses(unittest.TestCase):
    def test_character_class(self):
        m = IgnoreMatch()
        m.add_pattern("file[abc].txt")
        self.assertTrue(m.match("filea.txt"))
        self.assertTrue(m.match("fileb.txt"))
        self.assertTrue(m.match("filec.txt"))
        self.assertFalse(m.match("filed.txt"))

    def test_negated_character_class(self):
        m = IgnoreMatch()
        m.add_pattern("file[!abc].txt")
        self.assertFalse(m.match("filea.txt"))
        self.assertFalse(m.match("fileb.txt"))
        self.assertTrue(m.match("filed.txt"))

    def test_bracket_as_first_member(self):
        m = IgnoreMatch()
        m.add_pattern("file[]a].txt")
        self.assertTrue(m.match("file].txt"))
        self.assertTrue(m.match("filea.txt"))
        self.assertFalse(m.match("fileb.txt"))

    def test_unmatched_bracket_is_literal(self):
        m = IgnoreMatch()
        m.add_pattern("file[.txt")
        self.assertTrue(m.match("file[.txt"))
        self.assertFalse(m.match("filea.txt"))


class TestEdgeCases(unittest.TestCase):
    def test_trailing_spaces_stripped(self):
        m = IgnoreMatch()
        m.add_pattern("foo   ")
        self.assertTrue(m.match("foo"))
        self.assertFalse(m.match("foo   "))

    def test_escaped_trailing_space_kept(self):
        m = IgnoreMatch()
        m.add_pattern("foo\\ ")
        self.assertTrue(m.match("foo "))
        self.assertFalse(m.match("foo"))

    def test_backslash_escape_special_char(self):
        m = IgnoreMatch()
        m.add_pattern("a\\*b")
        self.assertTrue(m.match("a*b"))
        self.assertFalse(m.match("aXb"))

    def test_leading_bang_alone_is_ignored(self):
        m = IgnoreMatch()
        m.add_pattern("!")
        self.assertFalse(m.match("foo"))
        self.assertFalse(m.match("!"))

    def test_empty_pattern_object(self):
        m = IgnoreMatch()
        self.assertFalse(m.match("foo"))
        self.assertFalse(m.match("anything"))

    def test_dot_slash_normalized(self):
        m = IgnoreMatch()
        m.add_pattern("foo")
        self.assertTrue(m.match("./foo"))
        self.assertTrue(m.match("./a/foo"))

    def test_os_sep_normalized(self):
        m = IgnoreMatch()
        m.add_pattern("a/foo")
        self.assertTrue(m.match(os.path.join("a", "foo")))
        self.assertTrue(m.match(os.path.join("x", "a", "foo")))

    def test_trailing_slash_on_input_normalized(self):
        m = IgnoreMatch()
        m.add_pattern("foo")
        self.assertTrue(m.match("foo/", is_dir=True))
        self.assertTrue(m.match("a/foo/", is_dir=True))

    def test_doubled_slash_in_pattern(self):
        m = IgnoreMatch()
        m.add_pattern("a//foo")
        self.assertTrue(m.match("a/foo"))
        self.assertTrue(m.match("x/a/foo"))

    def test_root_path_not_ignored(self):
        m = IgnoreMatch()
        m.add_pattern("*")
        self.assertFalse(m.match("."))
        self.assertFalse(m.match(""))


class TestParseIgnoreFile(unittest.TestCase):
    def test_parse_multiline(self):
        text = "# comment\n*.log\n\n!keep.log\nbuild/\n"
        m = parse_ignore_file(text)
        self.assertTrue(m.match("debug.log"))
        self.assertFalse(m.match("keep.log"))
        self.assertTrue(m.match("build", is_dir=True))
        self.assertFalse(m.match("build", is_dir=False))

    def test_parse_crlf(self):
        text = "*.log\r\n!keep.log\r\n"
        m = parse_ignore_file(text)
        self.assertTrue(m.match("a.log"))
        self.assertFalse(m.match("keep.log"))

    def test_parse_cr_only(self):
        text = "*.log\r!keep.log\r"
        m = parse_ignore_file(text)
        self.assertTrue(m.match("a.log"))
        self.assertFalse(m.match("keep.log"))


class TestFilter(unittest.TestCase):
    def test_filter_returns_unignored(self):
        m = IgnoreMatch()
        m.add_pattern("*.log")
        m.add_pattern("!keep.log")
        paths = ["a.log", "keep.log", "b.txt", "c.log"]
        self.assertEqual(m.filter(paths), ["keep.log", "b.txt"])

    def test_filter_with_dirs(self):
        m = IgnoreMatch()
        m.add_pattern("build/")
        paths = ["build", "src", "build/file"]
        dirs = [True, True, False]
        self.assertEqual(m.filter(paths, dirs), ["src", "build/file"])

    def test_filter_empty_input(self):
        m = IgnoreMatch()
        m.add_pattern("*")
        self.assertEqual(m.filter([]), [])


if __name__ == "__main__":
    unittest.main()

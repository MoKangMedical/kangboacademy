"""Test backend extraction without importing the application or opening its database."""
import ast
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'server_patch/backend/main.py'
names = {'html_article_from_page', 'strip_audio_blocks', 'remove_audio_player_blocks', 'split_practice_from_html'}
module = ast.parse(source.read_text(encoding='utf-8'))
functions = ast.Module(body=[node for node in module.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
scope = {'Path': Path, 're': re}
exec(compile(functions, str(source), 'exec'), scope)


class ExtractionTests(unittest.TestCase):
    def extract(self, html, strip_practice=False):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'book.html'
            file.write_text(html, encoding='utf-8')
            return scope['html_article_from_page'](file, strip_practice)

    def test_nested_content_and_reordered_attributes(self):
        body = '<h2>Main</h2><div><p>Book ideas</p></div><p>End</p>'
        self.assertEqual(self.extract('<html><body><div id="a" class="content reader">' + body + '</div><div id="b" class="bottom-nav">Next</div></body></html>'), body)

    def test_core_article(self):
        self.assertEqual(self.extract('<ARTICLE><p>Core</p><article>Nested</article><p>End</p></ARTICLE>'), '<p>Core</p><article>Nested</article><p>End</p>')

    def test_practice_is_separate(self):
        self.assertEqual(self.extract('<div class="content"><p>Main</p><h2>课后练习</h2><p>Question</p></div>', True), '<p>Main</p>')

    def test_audio_does_not_eat_following_text(self):
        self.assertEqual(self.extract('<div class="content"><div class="audio-player"><div>Player</div><audio>x</audio></div><p>Body</p></div>'), '<p>Body</p>')

    def test_missing_container_does_not_return_full_document(self):
        self.assertEqual(self.extract('<html><head><title>Book</title></head><body>Menu</body></html>'), '')

    def test_fragment_is_preserved(self):
        self.assertEqual(self.extract('<p>Standalone</p>'), '<p>Standalone</p>')

    def test_case_quotes_comments_and_multiline(self):
        self.assertEqual(self.extract('<!--<div class="content">Fake</div>-->\n<DIV ID="x" CLASS=\'content\'>\n<p>Real</p>\n</DIV>'), '\n<p>Real</p>\n')

    def test_captured_live_page_regression(self):
        fixture = ROOT / 'reports/book-content-check-20260831/book63.html'
        if not fixture.exists():
            self.skipTest('Live snapshot not present')
        raw = fixture.read_text(encoding='utf-8')
        old_pattern = r'<div class="content">([\s\S]*?)\n\s*</div>\s*\n\s*<div class="bottom-nav">'
        self.assertIsNone(re.search(old_pattern, raw))
        content = self.extract(raw, True)
        self.assertIn('抵押品渠道', content)
        self.assertIn('核心思想', content)
        self.assertNotRegex(content, r'<(?:html|head|body)\b')
        self.assertNotIn('课后练习', content)


if __name__ == '__main__':
    unittest.main()

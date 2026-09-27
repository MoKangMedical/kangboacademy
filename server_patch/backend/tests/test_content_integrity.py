"""Offline regression tests: AST-only application code, virtual files, RAM SQLite."""
import ast
import asyncio
import html
import re
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
from urllib import parse


SOURCE = Path(__file__).resolve().parents[1] / 'main.py'
NAMES = {
    'public_url', 'frontend_audio_path', 'audio_url_from_page',
    'html_article_from_page', 'strip_audio_blocks', 'remove_audio_player_blocks',
    'split_practice_from_html', 'get_book_course_content',
    'validate_progress_request', 'update_progress', 'update_user_progress_alias',
    'course_record_from_markdown',
}


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


class VirtualPath:
    files = {}

    def __init__(self, value):
        self.value = str(value)

    def __truediv__(self, name):
        return VirtualPath(self.value.rstrip('/') + '/' + name)

    @property
    def name(self):
        return Path(self.value).name

    @property
    def stem(self):
        return Path(self.value).stem

    def exists(self):
        return self.value in self.files or any(key.startswith(self.value + '/') for key in self.files)

    def is_file(self):
        return self.value in self.files

    def read_text(self, **kwargs):
        return self.files[self.value]

    def stat(self):
        return SimpleNamespace(st_size=len(self.read_text()))

    def resolve(self):
        return self

    def glob(self, pattern):
        return [VirtualPath(key) for key in self.files
                if str(Path(key).parent) == self.value and Path(key).match(pattern)]


def load_functions():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES]
    for node in nodes:
        node.decorator_list = []
    scope = dict(
        Path=VirtualPath, Optional=Optional, List=List, re=re, html=html, parse=parse,
        datetime=datetime, HTTPException=HTTPError, ProgressReq=object,
        Depends=lambda value: None, Header=lambda value: None, get_current_user=lambda: None,
        FRONTEND_DIR=VirtualPath('/frontend'), COURSES_DIR=VirtualPath('/frontend/courses'),
        PUBLIC_BASE_URL='https://kangboacademy.cn',
        user_from_authorization=lambda value: None, can_access_book_course=lambda *args: True,
        public_access_open=lambda: True, FREE_BOOK_COURSES={1},
        parse_book_courses=lambda: [{'n': 1}, {'n': 500}],
        catalog_metadata=lambda *args: {}, book_course_title=lambda number: f'Book {number}',
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), scope)
    return scope


class IntegrityFixture(unittest.TestCase):
    def setUp(self):
        VirtualPath.files = {
            '/frontend/courses/01-Core.md': '# Core',
            '/frontend/courses/65-Last.md': '# Last',
            '/frontend/lesson1.html': '<article>Core</article>',
            '/frontend/lesson65.html': '<article>Last</article>',
            '/frontend/book1.html': '<article>Book</article>',
            '/frontend/book500.html': '<article>Last book</article>',
        }
        self.scope = load_functions()

    def extract(self, body):
        VirtualPath.files['/frontend/sample.html'] = body
        return self.scope['html_article_from_page'](VirtualPath('/frontend/sample.html'), True)


class IntegrityTests(IntegrityFixture):
    def test_book_does_not_fallback_to_core(self):
        VirtualPath.files['/frontend/audio/lesson1.mp3'] = 'core'
        result = asyncio.run(self.scope['get_book_course_content']('book1.html', None))
        self.assertEqual(result['audioUrl'], '')
        self.assertFalse(result['audioAvailable'])

    def test_book_uses_own_audio(self):
        VirtualPath.files['/frontend/audio/books/lesson1.mp3'] = 'book'
        result = asyncio.run(self.scope['get_book_course_content']('book1.html', None))
        self.assertEqual(result['audioUrl'], 'https://kangboacademy.cn/audio/books/lesson1.mp3')
        self.assertTrue(result['audioAvailable'])

    def test_book_rejects_explicit_cross_kind_audio(self):
        VirtualPath.files['/frontend/book1.html'] = '<article>Book</article><audio src="audio/lesson1.mp3"></audio>'
        VirtualPath.files['/frontend/audio/lesson1.mp3'] = 'core'
        result = asyncio.run(self.scope['get_book_course_content']('book1.html', None))
        self.assertEqual(result['audioUrl'], '')
        VirtualPath.files['/frontend/audio/books/lesson1.mp3'] = 'book'
        result = asyncio.run(self.scope['get_book_course_content']('book1.html', None))
        self.assertEqual(result['audioUrl'], 'https://kangboacademy.cn/audio/books/lesson1.mp3')

    def test_core_audio_fallback_unchanged(self):
        VirtualPath.files['/frontend/audio/lesson1.mp3'] = 'core'
        self.assertEqual(self.scope['audio_url_from_page'](
            VirtualPath('/frontend/lesson1.html'), ['audio/lesson1.mp3']),
            'https://kangboacademy.cn/audio/lesson1.mp3')

    def test_safe_images_and_attributes(self):
        for src in ['/images/a.png', 'images/a.png', 'https://kangboacademy.cn/images/a.png',
                    '//kangboacademy.cn/images/a.png']:
            with self.subTest(src=src):
                result = self.extract('<article><p>Before</p><IMG SRC="' + src +
                                      '" onerror="bad()" srcset="https://evil.test/x" style="x" '
                                      'alt="A &amp; B" width="320"/><p>After</p></article>')
                self.assertIn('src="https://kangboacademy.cn/images/a.png"', result)
                self.assertIn('alt="A &amp; B" width="320"', result)
                self.assertNotRegex(result, r'onerror|srcset|style=|evil')
                self.assertIn('<p>Before</p>', result)
                self.assertTrue(result.endswith('<p>After</p>'))

    def test_illegal_images_removed(self):
        for src in ['', 'javascript:alert(1)', 'data:image/png;base64,AAA',
                    'https://evil.test/x', '//evil.test/x', 'https://kangboacademy.cn.evil.test/x',
                    'https://user@kangboacademy.cn/x', 'https://kangboacademy.cn:444/x',
                    'http://kangboacademy.cn/x', '/\\evil.test/x', 'java&#10;script:bad',
                    'https://[bad/x']:
            with self.subTest(src=src):
                self.assertEqual(self.extract('<article><img src="' + src + '"><p>Text</p></article>'), '<p>Text</p>')

    def test_image_quoted_angle_and_multiline(self):
        result = self.extract('<article>\n<img\n src=/images/a.png title="A > B" ONLOAD="bad()">\nEnd</article>')
        self.assertIn('title="A &gt; B"', result)
        self.assertNotIn('ONLOAD', result)
        self.assertTrue(result.endswith('\nEnd'))

    def test_body_practice_and_audio_boundaries(self):
        result = self.extract('<article><div class="audio-player"><audio>x</audio></div>'
                              '<p>Body</p><img src=/images/a.png><h2>课后练习</h2><p>Quiz</p></article>')
        self.assertIn('<p>Body</p>', result)
        self.assertIn('<img ', result)
        self.assertNotRegex(result, 'audio|Quiz|课后练习')
        self.assertEqual(self.extract('<html><body>No article</body></html>'), '')


class ProgressTests(IntegrityFixture):
    def setUp(self):
        super().setUp()
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE course_progress (
                id INTEGER PRIMARY KEY, user_id INTEGER, course_id INTEGER,
                status TEXT, progress_percent INTEGER, started_at TEXT, completed_at TEXT,
                updated_at TEXT DEFAULT (datetime('now')), UNIQUE(user_id,course_id));
            CREATE TABLE learning_streaks (
                user_id INTEGER, date TEXT, courses_viewed INTEGER, UNIQUE(user_id,date));
        ''')
        self.opens = 0
        self.closes = 0
        owner = self

        class Connection:
            def __getattr__(self, name):
                return getattr(owner.db, name)

            def close(self):
                owner.closes += 1

        def get_db():
            self.opens += 1
            return Connection()

        self.scope['get_db'] = get_db

    def tearDown(self):
        self.db.close()

    def save(self, cid=1, status='completed', percent=100, user=1, alias=False):
        return asyncio.run(self.scope['update_user_progress_alias' if alias else 'update_progress'](
            SimpleNamespace(course_id=cid, status=status, progress_percent=percent), {'id': user}))

    def test_core_book_identity_and_boundaries(self):
        for cid in [1, 65, 10001, 10500]:
            self.assertEqual(self.save(cid), {'success': True})
        rows = self.db.execute('SELECT * FROM course_progress').fetchall()
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row['completed_at'] and row['started_at'] for row in rows))

    def test_invalid_payload_never_opens_database(self):
        for cid, status, percent in [(-1, 'completed', 100), (True, 'completed', 100),
                                     (1, 'unknown', 100), (1, '', 100), (1, 'completed', -1),
                                     (1, 'completed', 101), (1, 'completed', 1.5),
                                     (1, 'completed', True), (1, 'completed', '100')]:
            with self.subTest(payload=(cid, status, percent)):
                with self.assertRaises(HTTPError) as error:
                    self.save(cid, status, percent)
                self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.opens, 0)

    def test_missing_catalog_or_page_rejected(self):
        VirtualPath.files['/frontend/lesson2.html'] = '<article>Orphan</article>'
        VirtualPath.files['/frontend/courses/03-Only.md'] = '# No page'
        del VirtualPath.files['/frontend/book500.html']
        for cid in [2, 3, 66, 9999, 10000, 10002, 10500, 10501]:
            with self.subTest(cid=cid):
                with self.assertRaises(HTTPError) as error:
                    self.save(cid)
                self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.opens, 0)

    def test_completion_retry_preserves_time_and_streak(self):
        self.save(10001)
        self.db.execute("UPDATE course_progress SET completed_at='2000-01-01', updated_at='2000-01-02'")
        self.db.commit()
        self.save(10001, alias=True)
        row = self.db.execute('SELECT * FROM course_progress').fetchone()
        self.assertEqual(row['completed_at'], '2000-01-01')
        self.assertEqual(row['updated_at'], '2000-01-02')
        self.assertEqual(self.db.execute('SELECT SUM(courses_viewed) FROM learning_streaks').fetchone()[0], 1)
        self.assertEqual(self.opens, self.closes)

    def test_transition_and_optional_fields(self):
        self.save(status='not_started', percent=0)
        self.save(status='in_progress', percent=50)
        self.save(status=None, percent=60)
        row = self.db.execute('SELECT * FROM course_progress').fetchone()
        self.assertEqual((row['status'], row['progress_percent']), ('in_progress', 60))
        self.assertIsNone(row['completed_at'])
        self.save()
        self.assertIsNotNone(self.db.execute('SELECT completed_at FROM course_progress').fetchone()[0])

    def test_repeated_completion_with_percent_change_does_not_count_twice(self):
        self.save(percent=90)
        self.save(percent=100)
        self.save(status=None, percent=None)
        self.assertEqual(self.db.execute('SELECT progress_percent FROM course_progress').fetchone()[0], 100)
        self.assertEqual(self.db.execute('SELECT SUM(courses_viewed) FROM learning_streaks').fetchone()[0], 1)

    def test_repair_legacy_completion_without_extra_streak(self):
        self.save()
        self.db.execute('UPDATE course_progress SET completed_at=NULL')
        self.db.commit()
        self.save()
        self.assertIsNotNone(self.db.execute('SELECT completed_at FROM course_progress').fetchone()[0])
        self.assertEqual(self.db.execute('SELECT SUM(courses_viewed) FROM learning_streaks').fetchone()[0], 1)

    def test_users_are_isolated(self):
        self.save(user=1)
        self.save(user=2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM course_progress').fetchone()[0], 2)

    def test_failure_rolls_back_and_closes(self):
        self.db.execute('DROP TABLE learning_streaks')
        self.db.commit()
        with self.assertRaises(sqlite3.OperationalError):
            self.save()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM course_progress').fetchone()[0], 0)
        self.assertEqual(self.opens, self.closes)


if __name__ == '__main__':
    unittest.main()

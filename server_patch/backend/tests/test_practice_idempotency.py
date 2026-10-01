"""Exercise actual endpoint/DDL with synthetic SQLite data and a local AI stub."""
import ast
import asyncio
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional

from fastapi import HTTPException
from pydantic import BaseModel

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from practice_idempotency import PracticeSubmission


class PracticeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = str(Path(self.temp.name) / 'synthetic.sqlite')
        self.ai_calls = 0
        self.ai_started = threading.Event()
        self.ai_release = threading.Event()
        self.ai_release.set()
        tree = ast.parse((BACKEND / 'main.py').read_text())
        names = {'init_db', 'PracticeSubmitReq', 'submit_practice'}
        nodes = [n for n in tree.body if getattr(n, 'name', None) in names]
        for node in nodes:
            node.decorator_list = []
        self.scope = dict(
            get_db=self.connect, json=json, datetime=datetime, HTTPException=HTTPException,
            BaseModel=BaseModel, Dict=Dict, Optional=Optional,
            Depends=lambda f: None, get_current_user=lambda: None,
            resolve_lesson=lambda lesson: {'page': SimpleNamespace(exists=lambda: True),
                                         'courseRef': 1, 'isBookCourse': False},
            can_access_lesson=lambda *args: True, lesson_free=lambda meta: True,
            build_practice_questions=lambda *args: {'questions': [{'id': 'q', 'title': 'Test'}],
                                                     'keywords': ['test']},
            score_answer=lambda *args: {'score': 90},
            build_agent_feedback=lambda *args: 'feedback',
            build_practice_ai_analysis=self.ai,
            consecutive_practice_days=lambda *args: 1,
            award_badges=self.award,
        )
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'main.py', 'exec'), self.scope)
        self.scope['init_db']()
        self.scope['init_db']()  # Migration is safe to rerun.
        with self.connect() as conn:
            for uid in (1, 2):
                conn.execute('INSERT INTO users(id,email,username,password_hash,salt) VALUES(?,?,?,?,?)',
                             (uid, f'{uid}@example.test', 'test', 'not-a-password', 'test'))
        conn.close()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=2)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    def ai(self, *args):
        self.ai_calls += 1
        # Another connection can acquire a write lock while AI is running.
        conn = self.connect()
        conn.execute('BEGIN IMMEDIATE')
        conn.rollback()
        conn.close()
        self.ai_started.set()
        if not self.ai_release.wait(5):
            raise RuntimeError('Test AI release timed out')
        return {'status': 'ready', 'feedback': 'synthetic', 'followUps': ['next']}

    def award(self, conn, user_id, keys):
        earned = []
        for key in keys:
            cursor = conn.execute('''INSERT OR IGNORE INTO user_badges
                (user_id,badge_key,badge_name,badge_desc,badge_icon) VALUES(?,?,?,?,?)''',
                (user_id, key, key, 'test', 'test'))
            if cursor.rowcount:
                earned.append({'key': key})
        return earned

    def request(self, key='submission-1', answer='test', reflection='', **extra):
        return self.scope['PracticeSubmitReq'](lesson='lesson1', answers={'q': answer},
                                               reflection=reflection, submission_id=key, **extra)

    async def submit(self, req=None, user_id=1):
        return await self.scope['submit_practice'](req or self.request(), {'id': user_id})

    def counts(self, user_id=1):
        conn = self.connect()
        try:
            return (
                conn.execute('SELECT count(*) FROM practice_attempts WHERE user_id=?', (user_id,)).fetchone()[0],
                conn.execute('SELECT coalesce(sum(quiz_taken),0) FROM learning_streaks WHERE user_id=?', (user_id,)).fetchone()[0],
                conn.execute('SELECT coalesce(sum(practice_count),0) FROM daily_refinements WHERE user_id=?', (user_id,)).fetchone()[0],
            )
        finally:
            conn.close()

    async def test_retry_returns_exact_response_and_scores_once(self):
        first = await self.submit()
        second = await self.submit()
        self.assertEqual(first, second)
        self.assertEqual(self.ai_calls, 1)
        self.assertEqual(self.counts(), (1, 1, 1))
        self.assertTrue(first['badgesEarned'])
        self.assertEqual(first['dailyRefinement']['score_total'], 90)

    async def test_same_key_changed_payload_conflicts_before_ai(self):
        await self.submit()
        for req in (self.request(answer='changed'), self.request(reflection='changed')):
            with self.assertRaises(HTTPException) as error:
                await self.submit(req)
            self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.ai_calls, 1)
        self.assertEqual(self.counts(), (1, 1, 1))

    async def test_user_isolation_new_key_and_old_client(self):
        await self.submit()
        await self.submit(user_id=2)
        await self.submit(self.request(key='submission-2', answer='changed'))
        self.assertEqual(self.counts(), (2, 2, 2))
        self.assertEqual(self.counts(2), (1, 1, 1))
        old = self.request(key=None)
        self.assertEqual(await self.submit(old), await self.submit(old))
        self.assertEqual(self.counts(), (3, 3, 3))

    async def test_concurrent_retry_during_ai_wait(self):
        self.ai_release.clear()
        first = asyncio.create_task(self.submit())
        await asyncio.to_thread(self.ai_started.wait, 2)
        self.assertTrue(self.ai_started.is_set())
        second = asyncio.create_task(self.submit())
        await asyncio.sleep(0.15)
        self.assertEqual(self.ai_calls, 1)
        self.ai_release.set()
        responses = await asyncio.gather(first, second)
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(self.counts(), (1, 1, 1))

    async def test_independent_workers_share_claim(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = await asyncio.gather(*[
                asyncio.wrap_future(pool.submit(lambda: asyncio.run(self.submit()))) for _ in range(4)
            ])
        self.assertTrue(all(item == responses[0] for item in responses))
        self.assertEqual(self.ai_calls, 1)
        self.assertEqual(self.counts(), (1, 1, 1))

    async def test_write_failure_rolls_back_all_scoring_then_retry_recovers(self):
        original = self.scope['award_badges']
        self.scope['award_badges'] = lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic failure'))
        with self.assertRaises(RuntimeError):
            await self.submit()
        self.assertEqual(self.counts(), (0, 0, 0))
        self.scope['award_badges'] = original
        response = await self.submit()
        self.assertTrue(response['success'])
        self.assertEqual(self.counts(), (1, 1, 1))

    async def test_ai_exception_releases_claim_but_keeps_payload_binding(self):
        self.scope['build_practice_ai_analysis'] = lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic AI failure'))
        with self.assertRaises(RuntimeError):
            await self.submit()
        with self.assertRaises(HTTPException) as error:
            await self.submit(self.request(answer='changed'))
        self.assertEqual(error.exception.status_code, 409)
        self.scope['build_practice_ai_analysis'] = self.ai
        await self.submit()
        self.assertEqual(self.counts(), (1, 1, 1))

    async def test_abandoned_lease_is_fenced_and_completed_atomically(self):
        payload = {'lesson': 'test', 'answers': {'q': 'test'}}
        first = PracticeSubmission(self.connect, 1, 'lease-test', payload, lease_seconds=-1)
        second = PracticeSubmission(self.connect, 1, 'lease-test', payload)
        async with first:
            async with second:
                with self.assertRaises(HTTPException):
                    with first.transaction():
                        self.fail('Stale worker acquired the transaction')
                with second.transaction() as conn:
                    second.complete(conn, {'attemptId': 123})
        async with PracticeSubmission(self.connect, 1, 'lease-test', payload) as retry:
            self.assertEqual(retry.response, {'attemptId': 123})

    async def test_pending_conflict_and_bounded_retry_wait(self):
        async with PracticeSubmission(self.connect, 1, 'pending', {'q': 'a'}):
            with self.assertRaises(HTTPException) as conflict:
                async with PracticeSubmission(self.connect, 1, 'pending', {'q': 'b'}):
                    pass
            self.assertEqual(conflict.exception.status_code, 409)
            with self.assertRaises(HTTPException) as pending:
                async with PracticeSubmission(self.connect, 1, 'pending', {'q': 'a'}, wait_seconds=0):
                    pass
            self.assertEqual(pending.exception.status_code, 503)

    async def test_invalid_id_never_calls_ai(self):
        for key in ('', 'bad key', 'x' * 129):
            with self.assertRaises(HTTPException) as error:
                await self.submit(self.request(key=key))
            self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.ai_calls, 0)


if __name__ == '__main__':
    unittest.main()

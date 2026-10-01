"""SQLite-backed submission claims; no connection is held during AI work."""
import asyncio
import hashlib
import json
import re
import time
import uuid
from contextlib import contextmanager

from fastapi import HTTPException


class PracticeSubmission:
    def __init__(self, get_db, user_id, key, payload, lease_seconds=180, wait_seconds=35):
        self.get_db = get_db
        self.user_id = user_id
        self.payload_hash = hashlib.sha256(json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')
        ).encode('utf-8')).hexdigest()
        # Old clients also get retry protection instead of silently double scoring.
        self.key = key if key is not None else 'legacy-' + self.payload_hash
        if not isinstance(self.key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', self.key):
            raise HTTPException(422, '练习提交标识无效，请刷新页面后重试')
        self.owner = uuid.uuid4().hex
        self.lease_seconds = lease_seconds
        self.wait_seconds = wait_seconds
        self.response = None
        self.claimed = False

    def _claim(self):
        conn = self.get_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(
                'SELECT * FROM practice_submissions WHERE user_id=? AND submission_key=?',
                (self.user_id, self.key),
            ).fetchone()
            if row and row['payload_hash'] != self.payload_hash:
                raise HTTPException(409, '该提交标识已用于其他答案，请重新提交当前答案')
            if row and row['response_json'] is not None:
                self.response = json.loads(row['response_json'])
                return True
            now = time.time()
            if row and row['lease_until'] > now:
                return False
            conn.execute('''
                INSERT INTO practice_submissions
                    (user_id, submission_key, payload_hash, owner, lease_until)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, submission_key) DO UPDATE SET
                    owner=excluded.owner, lease_until=excluded.lease_until
            ''', (self.user_id, self.key, self.payload_hash, self.owner, now + self.lease_seconds))
            conn.commit()
            self.claimed = True
            return True
        finally:
            conn.rollback()
            conn.close()

    async def __aenter__(self):
        deadline = time.monotonic() + self.wait_seconds
        while not self._claim():
            if time.monotonic() >= deadline:
                raise HTTPException(503, '练习正在处理中，请稍后重试，无需修改答案',
                                    headers={'Retry-After': '2'})
            await asyncio.sleep(0.1)
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if self.claimed:
            conn = self.get_db()
            try:
                conn.execute('''UPDATE practice_submissions SET lease_until=0
                    WHERE user_id=? AND submission_key=? AND owner=? AND response_json IS NULL''',
                    (self.user_id, self.key, self.owner))
                conn.commit()
            finally:
                conn.close()

    @contextmanager
    def transaction(self):
        conn = self.get_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT owner, response_json FROM practice_submissions
                WHERE user_id=? AND submission_key=?''', (self.user_id, self.key)).fetchone()
            if not row or row['owner'] != self.owner or row['response_json'] is not None:
                raise HTTPException(503, '练习已由重试请求继续处理，请稍后重试，无需修改答案')
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def complete(self, conn, response):
        conn.execute('''UPDATE practice_submissions SET response_json=?, lease_until=0
            WHERE user_id=? AND submission_key=? AND owner=?''',
            (json.dumps(response, ensure_ascii=False), self.user_id, self.key, self.owner))

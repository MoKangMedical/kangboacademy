#!/usr/bin/env python3
"""Run over authorized SSH; back up production without deploying or restarting."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def main():
    os.umask(0o077)
    root = Path('/var/www/kangboacademy')
    target = Path.home() / 'kangbo-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if shutil.disk_usage(root).free < 3 * 1024 ** 3:
        raise RuntimeError('Need at least 3 GiB free before backup')
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    db = root / 'data/kangboacademy.db'
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(target / 'kangboacademy.db') as destination:
            source.backup(destination, pages=256, sleep=0.1)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database backup integrity failed')
    protected = ['frontend/learn.html', 'frontend/index.html', 'frontend/courses.html', 'backend/main.py']
    hashes = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in protected}
    excluded = {'venv', '.venv', '__pycache__', 'node_modules'}

    def include(info):
        parts = Path(info.name).parts
        if any(part in excluded for part in parts):
            return None
        if parts[:1] == ('data',) and any(part.endswith(('.db', '.db-wal', '.db-shm', '.sqlite', '.sqlite3')) for part in parts):
            return None
        return info

    archive = target / 'production-files.tar.gz'
    with tarfile.open(archive, 'w:gz', compresslevel=1, dereference=False) as tar:
        for name in ('backend', 'frontend', 'data'):
            tar.add(root / name, arcname=name, filter=include)
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        for name, expected in hashes.items():
            handle = tar.extractfile(name)
            if handle is None or hashlib.sha256(handle.read()).hexdigest() != expected:
                raise RuntimeError('Protected file changed during backup: ' + name)
    if any(hashlib.sha256((root / p).read_bytes()).hexdigest() != value for p, value in hashes.items()):
        raise RuntimeError('Protected live files changed during backup')
    for args, name in [(['diff', '--binary', 'HEAD'], 'working-tree.patch'), (['status', '--porcelain'], 'git-status.txt')]:
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True)
        (target / name).write_bytes(result.stdout)
    digest = hashlib.sha256()
    with archive.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    report = {'backupDirectory': str(target), 'archiveBytes': archive.stat().st_size,
              'archiveSha256': digest.hexdigest(), 'archiveMembers': len(members),
              'databaseIntegrity': 'ok', 'protectedHashes': hashes,
              'scope': 'backend frontend including audio and data; SQLite online snapshot; excludes virtualenv and extra database files',
              'deployed': False}
    (target / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

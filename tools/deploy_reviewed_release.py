#!/usr/bin/env python3
"""Deploy a verified staged release with a fresh backup and code-only rollback."""
import ast
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

LIVE = Path('/var/www/kangboacademy')
STAGE = Path.home() / 'kangbo-staging/release-20261001'
BACKUP = Path.home() / 'kangbo-backups/release-20261001-rc6'
BASELINE = {
    'frontend/learn.html': '478becd47b66908994b59f9f8a291189b100be0cbafa82e9a54f19f1a68109f7',
    'backend/main.py': '7751ff3b525f7b77f5615e40c2f502fa5e99fb58d21d4e0b236889bbd10d1385',
    'frontend/index.html': '9206781a5a269a455f4b8c435d345949173899f19cd2338b758e846e24fdbc38',
    'frontend/courses.html': '00c022b678dd612f442591aa1773df4817a4a8f059dd5a56807a9eee63beea21',
    'frontend/book-courses.html': 'b0bad0cd6e70c34a5c2e50920f00b93a793043c530d89f351a50fcb356ad66cb',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def routes(path):
    return {(node.func.attr, ast.literal_eval(node.args[0]))
            for tree in ast.walk(ast.parse(path.read_text()))
            for node in getattr(tree, 'decorator_list', [])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == 'app'
            and node.func.attr in ('get', 'post', 'put', 'delete', 'patch') and node.args}


def atomic_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o755)
    temporary = target.with_name(target.name + '.release-20261001.tmp')
    shutil.copyfile(source, temporary)
    os.chmod(temporary, 0o644)
    os.replace(temporary, target)


def restart():
    subprocess.run(['sudo', '-n', 'systemctl', 'restart', 'kangboacademy.service'], check=True)


def health():
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8088/api/health', timeout=2) as response:
                if response.status == 200:
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def main():
    os.umask(0o077)
    lock = open(Path.home() / '.kangbo-release.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for name, expected in BASELINE.items():
        if digest(LIVE / name) != expected:
            raise RuntimeError('Production baseline changed: ' + name)
    for name in ('server-smoke.json', 'production-content-check.json'):
        if json.loads((STAGE / name).read_text()).get('passed') is not True:
            raise RuntimeError('Staging check missing or failed: ' + name)
    if shutil.disk_usage(LIVE).free < 512 * 1024 ** 2:
        raise RuntimeError('Insufficient disk space')
    process_ids = subprocess.check_output(['pgrep', '-f', 'uvicorn main:app'], text=True).split()
    for pid in process_ids:
        env = Path('/proc') / pid / 'environ'
        if env.exists():
            try:
                overridden = b'KANGBO_PROJECT_ROOT=' in env.read_bytes()
            except PermissionError:
                check = subprocess.check_output([
                    'sudo', '-n', sys.executable, '-c',
                    'from pathlib import Path; import sys; print(int(b"KANGBO_PROJECT_ROOT=" in Path(sys.argv[1]).read_bytes()))',
                    str(env)], text=True).strip()
                overridden = check == '1'
            if overridden:
                raise RuntimeError('Unexpected project-root override in live process')
    source = STAGE / 'server_patch/backend'
    if not routes(LIVE / 'backend/main.py').issubset(routes(source / 'main.py')):
        raise RuntimeError('Existing routes would be removed')
    web = STAGE / 'output/kangbo-delivery-20261001-rc6/web-patch'
    files = [(source / name, 'backend/' + name) for name in
             ('main.py', 'content_contract.py', 'payment_security.py', 'practice_idempotency.py')]
    files += [(p, 'frontend/' + p.name) for p in sorted(web.glob('*.*'))
              if p.name in ('index.html', 'courses.html', 'book-courses.html', 'book-shop.html', 'content-manifest.json')
              or re.fullmatch(r'(content-manifest|catalog-contract|membership-catalog)\.[a-f0-9]{16}\.js', p.name)]
    files += [(p, 'frontend/vendor/' + p.name) for p in sorted((web / 'vendor').iterdir())
              if p.is_file() and not p.name.startswith('.')]
    for src, target in files:
        parent = (LIVE / target).parent
        while not parent.exists():
            parent = parent.parent
        if not src.is_file() or not os.access(parent, os.W_OK):
            raise RuntimeError('Missing source or unwritable target: ' + target)
    BACKUP.mkdir(parents=True, exist_ok=False, mode=0o700)
    with sqlite3.connect((LIVE / 'data/kangboacademy.db').as_uri() + '?mode=ro', uri=True) as original:
        with sqlite3.connect(BACKUP / 'kangboacademy.db') as snapshot:
            original.backup(snapshot)
            if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database snapshot failed integrity check')
    overwritten, created = [], []
    for _, relative in files:
        target = LIVE / relative
        if target.exists():
            saved = BACKUP / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            overwritten.append(relative)
        else:
            created.append(relative)
    plan = {'version': '1.0.7-rc6', 'backup': str(BACKUP), 'overwritten': overwritten,
            'created': created, 'sourceHashes': {relative: digest(src) for src, relative in files}}
    (BACKUP / 'plan.json').write_text(json.dumps(plan, indent=2))
    # Install static dependencies before HTML references and restart after matched backend files.
    ordered = sorted(files, key=lambda item: item[1].endswith('.html'))
    applied = []
    try:
        for src, relative in ordered:
            if relative in BASELINE and digest(LIVE / relative) != BASELINE[relative]:
                raise RuntimeError('Concurrent production change: ' + relative)
            atomic_copy(src, LIVE / relative)
            applied.append(relative)
        restart()
        if not health():
            raise RuntimeError('New service failed health check')
        if digest(LIVE / 'frontend/learn.html') != BASELINE['frontend/learn.html']:
            raise RuntimeError('Protected page changed')
        for src, relative in files:
            if digest(LIVE / relative) != digest(src):
                raise RuntimeError('Installed hash mismatch: ' + relative)
        with sqlite3.connect((LIVE / 'data/kangboacademy.db').as_uri() + '?mode=ro', uri=True) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='practice_submissions'").fetchone():
                raise RuntimeError('Practice retry schema missing')
    except BaseException:
        for relative in reversed(applied):
            if relative in overwritten:
                atomic_copy(BACKUP / relative, LIVE / relative)
            else:
                (LIVE / relative).unlink(missing_ok=True)
        restart()
        (BACKUP / 'rollback.json').write_text(json.dumps({'restoredCode': True, 'healthy': health()}))
        raise
    result = {**plan, 'deployed': True, 'localHealth': True, 'databaseSnapshotIntegrity': 'ok',
              'protectedLearnUnchanged': True, 'deployedAtUTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    (BACKUP / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()

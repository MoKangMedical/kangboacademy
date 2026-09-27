#!/usr/bin/env python3
"""Import public metadata once, then build/check identical client artifacts."""
import argparse
import ast
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / 'shared/content-contract.json'
TARGETS = [ROOT / 'kangboacademy-miniapp/data/content-contract.json',
           ROOT / 'server_patch/frontend/content-manifest.json']
JS_TARGET = ROOT / 'server_patch/frontend/content-manifest.js'


class LiteralParser:
    """Parse only data literals. Never evaluate downloaded JavaScript."""
    token = re.compile(r'''\s*(?:(//[^\n]*|/\*[\s\S]*?\*/)|('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")|(-?\d+)|([A-Za-z_$][\w$]*)|([\[\]{},:]))''')

    def __init__(self, text):
        self.text, self.pos = text, 0

    def read(self):
        while True:
            match = self.token.match(self.text, self.pos)
            if not match:
                raise ValueError(f'Unsupported catalog syntax at {self.pos}')
            self.pos = match.end()
            comment, string, number, name, punctuation = match.groups()
            if not comment:
                return ('string', ast.literal_eval(string)) if string else ('number', int(number)) if number else ('name', name) if name else (punctuation, punctuation)

    def value(self, token=None):
        kind, value = token or self.read()
        if kind in ('string', 'number'):
            return value
        if kind == '[':
            result = []
            token = self.read()
            while token[0] != ']':
                result.append(self.value(token))
                token = self.read()
                if token[0] == ']':
                    break
                if token[0] != ',':
                    raise ValueError('Expected array separator')
                token = self.read()
            return result
        if kind == '{':
            result = {}
            token = self.read()
            while token[0] != '}':
                if token[0] not in ('string', 'name') or token[1] in result:
                    raise ValueError('Invalid or duplicate object key')
                key = token[1]
                if self.read()[0] != ':':
                    raise ValueError('Expected property value')
                result[key] = self.value()
                token = self.read()
                if token[0] == '}':
                    break
                if token[0] != ',':
                    raise ValueError('Expected object separator')
                token = self.read()
            return result
        if kind == 'name' and value in ('true', 'false', 'null'):
            return {'true': True, 'false': False, 'null': None}[value]
        raise ValueError('Executable expressions are not catalog data')


def parse_phases(page):
    match = re.search(r'\bconst\s+PHASES\s*=\s*', page)
    if not match:
        raise ValueError('Website PHASES declaration missing')
    return LiteralParser(page[match.end():]).value()


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def validate(manifest):
    if manifest.get('schemaVersion') != 1:
        raise ValueError('Unsupported schema')
    courses = manifest['courses']
    keys, lessons, refs = set(), set(), set()
    for row in courses:
        kind, number = row['kind'], row['number']
        expected_lesson = f'{"lesson" if kind == "core" else "book"}{number}.html'
        if kind not in ('core', 'book') or not isinstance(number, int) or number < 1:
            raise ValueError('Invalid identity')
        if row['key'] != f'{kind}:{number}' or row['lesson'] != expected_lesson:
            raise ValueError('Inconsistent identity')
        if row['legacyCourseRef'] != number + (10000 if kind == 'book' else 0):
            raise ValueError('Invalid legacy progress reference')
        if row['key'] in keys or row['lesson'] in lessons or row['legacyCourseRef'] in refs:
            raise ValueError('Duplicate identity')
        if any(key in row for key in ('free', 'accessible', 'locked', 'token', 'price')):
            raise ValueError('Public metadata cannot carry entitlements or prices')
        keys.add(row['key']); lessons.add(row['lesson']); refs.add(row['legacyCourseRef'])
        expected_audio = f'audio/{"books/" if kind == "book" else ""}lesson{number}.mp3'
        if row['audioPath'] != expected_audio:
            raise ValueError('Cross-kind audio reference')
    grouped = [key for phase in manifest['phases'] for key in phase['courseKeys']]
    core_keys = {row['key'] for row in courses if row['kind'] == 'core'}
    if len(grouped) != len(set(grouped)) or set(grouped) != core_keys:
        raise ValueError('Phases must cover each core course exactly once')


def refresh(import_file=None):
    snapshots = json.loads(Path(import_file).read_text(encoding='utf-8')) if import_file else {}
    if not import_file:
        for route in ('courses.html', 'api/courses', 'api/book-courses'):
            with urlopen('https://kangboacademy.cn/' + route, timeout=25) as response:
                snapshots[route] = response.read().decode('utf-8')
            time.sleep(3)
    phases = parse_phases(snapshots['courses.html'])
    core = json.loads(snapshots['api/courses'])
    books = json.loads(snapshots['api/book-courses'])
    if core['total'] != len(core['courses']) or books['total'] != len(books['courses']):
        raise ValueError('Incomplete API response')
    metadata = {int(row['n']): row for phase in phases for row in phase['courses']}
    if set(metadata) != {int(row['id']) for row in core['courses']}:
        raise ValueError('Website and API course identity sets differ')
    data = {'schemaVersion': 1, 'importedAt': datetime.now(timezone.utc).isoformat(),
            'sources': {route: hashlib.sha256(body.encode()).hexdigest() for route, body in snapshots.items()},
            'phases': [], 'categories': books['categories'], 'categoryOrder': list(books['categories']),
            'waves': books['waves'], 'courses': []}
    for index, phase in enumerate(phases, 1):
        data['phases'].append({'id': f'phase-{index}', 'title': phase['title'], 'description': phase['sub'],
                               'courseKeys': [f'core:{row["n"]}' for row in phase['courses']]})
    for kind, response in [('core', core), ('book', books)]:
        for row in response['courses']:
            number = int(row.get('id') or row['n'])
            title = row.get('title') or row['t']
            meta = metadata[number] if kind == 'core' else {}
            data['courses'].append({'key': f'{kind}:{number}', 'kind': kind, 'number': number,
                'legacyCourseRef': number + (10000 if kind == 'book' else 0),
                'lesson': f'{"lesson" if kind == "core" else "book"}{number}.html',
                'title': title, 'displayTitle': meta.get('title') or title,
                'description': meta.get('desc', ''), 'difficulty': meta.get('diffLabel', ''),
                'durationLabel': meta.get('time', ''), 'author': row.get('author', ''),
                'category': row.get('category', ''),
                'audioPath': f'audio/{"books/" if kind == "book" else ""}lesson{number}.mp3',
                'audioRevision': None})
    validate(data)
    MASTER.parent.mkdir(exist_ok=True)
    MASTER.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(check=False):
    data = json.loads(MASTER.read_text(encoding='utf-8'))
    validate(data)
    data['contentVersion'] = hashlib.sha256(packed(data).encode()).hexdigest()[:16]
    body = packed(data) + '\n'
    generated = {target: body for target in TARGETS}
    generated[JS_TARGET] = '// Generated by tools/build_content_contract.py; do not edit.\nwindow.KANGBO_CONTENT=' + packed(data) + ';\n'
    for target, text in generated.items():
        if check:
            if not target.exists() or target.read_text(encoding='utf-8') != text:
                raise ValueError(f'Generated artifact drift: {target.relative_to(ROOT)}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
    print(json.dumps({'version': data['contentVersion'], 'courses': len(data['courses']),
                      'phases': len(data['phases']), 'artifacts': len(generated), 'check': check}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Explicitly import current public website metadata')
    parser.add_argument('--check', action='store_true', help='Verify generated files without modifying them')
    parser.add_argument('--import-file', help='Public browser capture with the same three source keys')
    args = parser.parse_args()
    if (args.refresh or args.import_file) and args.check:
        parser.error('--refresh and --check are mutually exclusive')
    if args.refresh or args.import_file:
        refresh(args.import_file)
    build(args.check)

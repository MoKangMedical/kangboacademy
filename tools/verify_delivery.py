#!/usr/bin/env python3
"""Verify a delivery directory without trusting paths in its manifest."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


def verify(root):
    root = Path(root).resolve(strict=True)
    manifest = json.loads((root / 'SHA256.json').read_text())
    seen = set()
    for row in manifest:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts or str(relative) in seen:
            raise ValueError('Unsafe or duplicate delivery path')
        seen.add(str(relative))
        target = root / relative
        if not target.resolve().is_relative_to(root) or target.is_symlink() or not target.is_file():
            raise ValueError(f'Unsafe or missing file: {relative}')
        body = target.read_bytes()
        if len(body) != row['bytes'] or hashlib.sha256(body).hexdigest() != row['sha256']:
            raise ValueError(f'Content changed: {relative}')
    config = json.loads((root / 'miniapp/project.config.json').read_text())
    assert config['appid'] == 'wx3bfed43762c89c86'
    assert config['setting']['urlCheck'] is True
    assert not (root / 'miniapp/project.private.config.json').exists()
    for name in ('index.html', 'courses.html', 'book-shop.html'):
        body = (root / 'web-patch' / name).read_text()
        assert 'src="content-manifest.js"' not in body
        for asset in re.findall(r'src="((?:content-manifest|catalog-contract|membership-catalog)\.[a-f0-9]{16}\.js)"', body):
            assert (root / 'web-patch' / asset).is_file(), asset
    rows = list(csv.DictReader((root / 'merchant/500-books-to-match.csv').open(encoding='utf-8-sig')))
    assert len(rows) == 500
    assert all(not value for row in rows for key, value in row.items() if key not in ('bookId', 'title', 'author'))
    status = json.loads((root / 'release-status.json').read_text())
    return {'integrity': 'passed', 'filesChecked': len(manifest), 'merchantWorksheetRows': len(rows),
            'candidateVersion': status['candidateVersion'], 'released': status['released'],
            'scope': 'local-package-integrity-not-platform-approval'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), ensure_ascii=False))

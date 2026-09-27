#!/usr/bin/env python3
"""Create a local-only website preview; never deploy or touch production files."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from build_content_contract import ROOT, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--shop-fixture', help='Optional public captured shop JSON; local preview only')
    parser.add_argument('--membership-fixture', help='Optional public membership JSON; local preview only')
    args = parser.parse_args()
    build(check=True)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    sources = {'index.html': ROOT / 'server_index.html'}
    for name in ['courses.html', 'book-shop.html', 'content-manifest.json', 'content-manifest.js', 'catalog-contract.js', 'membership-catalog.js']:
        sources[name] = ROOT / 'server_patch/frontend' / name
    rows = []
    for name, source in sources.items():
        shutil.copy2(source, output / name)
        rows.append({'file': name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    if args.shop_fixture:
        fixture = Path(args.shop_fixture)
        data = json.loads(fixture.read_text())
        if not isinstance(data.get('books'), list):
            raise ValueError('Invalid public shop fixture')
        target = output / 'api/shop/books'
        target.parent.mkdir(parents=True)
        shutil.copy2(fixture, target)
    if args.membership_fixture:
        target = output / 'api/membership/plans'
        target.parent.mkdir(parents=True)
        shutil.copy2(args.membership_fixture, target)
    (output / 'preview-manifest.json').write_text(json.dumps({'productionDeployed': False,
        'shopDataMode': 'captured-public-fixture' if args.shop_fixture else 'no-backend', 'files': rows}, indent=2))
    print(f'Local preview only: {output}')


if __name__ == '__main__':
    main()

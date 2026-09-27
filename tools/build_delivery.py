#!/usr/bin/env python3
"""Build an isolated, tested delivery candidate. Never deploy or submit it."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSITIVE = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9]{24,}')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files():
    mini = ROOT / 'kangboacademy-miniapp'
    pairs = []
    for folder in ('pages', 'components', 'utils', 'assets', 'data'):
        pairs.extend((p, Path('miniapp') / p.relative_to(mini)) for p in (mini / folder).rglob('*')
                     if p.is_file() and p.suffix in {'.js', '.json', '.wxml', '.wxss', '.png', '.jpg', '.svg'})
    for name in ('app.js', 'app.json', 'app.wxss', 'project.config.json', 'sitemap.json', 'README.md'):
        pairs.append((mini / name, Path('miniapp') / name))
    for folder in ('tests',):
        pairs.extend((p, Path('source/kangboacademy-miniapp') / p.relative_to(mini))
                     for p in (mini / folder).glob('*.js'))
    pairs.extend((p, Path('source') / p.relative_to(ROOT)) for p in (ROOT / 'tools').glob('*.py'))
    pairs.extend((p, Path('source') / p.relative_to(ROOT)) for p in (ROOT / 'tools').glob('*.cjs'))
    pairs.extend((p, Path('source') / p.relative_to(ROOT)) for p in (ROOT / 'shared').glob('*.json'))
    pairs.extend((p, Path('source/tests') / p.name) for p in (ROOT / 'tests').glob('*.test.js'))
    pairs.extend((p, Path('backend-candidate') / p.name) for p in (ROOT / 'server_patch/backend').glob('*.py'))
    pairs.extend((p, Path('backend-candidate/tests') / p.name) for p in (ROOT / 'server_patch/backend/tests').glob('*.py'))
    for name in ('courses.html', 'book-shop.html', 'content-manifest.js', 'content-manifest.json', 'catalog-contract.js', 'membership-catalog.js'):
        pairs.append((ROOT / 'server_patch/frontend' / name, Path('web-patch') / name))
    pairs.append((ROOT / 'server_index.html', Path('web-patch/index.html')))
    for name in ('DELIVERY.md', 'partner-products.md', '合作书商对接说明.md'):
        pairs.append((ROOT / 'docs' / name, Path('docs') / name))
    pairs.append((ROOT / 'data/partner-products.template.csv', Path('merchant/partner-products.template.csv')))
    pairs.append((ROOT / 'requirements-validation.txt', Path('source/requirements-validation.txt')))
    for name in ('backend-500-optimized-smoke.json', '交付验收.md'):
        pairs.append((ROOT / 'reports/delivery-20260927' / name, Path('evidence') / name))
    pairs.append((ROOT / 'reports/book-content-check-20260831/book63.html',
                  Path('source/reports/book-content-check-20260831/book63.html')))
    return pairs


def build(output):
    output = output.resolve()
    if output.exists() or output.with_suffix('.zip').exists():
        raise ValueError('Use a new output directory and archive path')
    pairs = source_files()
    for src, _ in pairs:
        if src.is_symlink() or not src.is_file():
            raise ValueError(f'Missing or symbolic source: {src.relative_to(ROOT)}')
        if SENSITIVE.search(src.read_bytes()):
            raise ValueError(f'Potential secret in source: {src.relative_to(ROOT)}')
    commands = [
        [sys.executable, 'tools/build_content_contract.py', '--check'],
        ['node', '--test', *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'kangboacademy-miniapp/tests').glob('*.test.js'))],
         *[str(p.relative_to(ROOT)) for p in sorted((ROOT / 'tests').glob('*.test.js'))]],
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_*.py', '-v'],
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'server_patch/backend/tests', '-v']]
    results = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError('Validation failed:\n' + result.stdout + result.stderr)
        results.append({'command': command, 'returncode': result.returncode, 'output': result.stdout + result.stderr})
    output.mkdir(parents=True, exist_ok=False)
    for src, relative in pairs:
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    # Include the runnable source layout for the same tests, without private config or production data.
    shutil.copytree(output / 'miniapp', output / 'source/kangboacademy-miniapp', dirs_exist_ok=True)
    shutil.copytree(output / 'backend-candidate', output / 'source/server_patch/backend')
    shutil.copytree(output / 'web-patch', output / 'source/server_patch/frontend')
    shutil.copy2(ROOT / 'server_index.html', output / 'source/server_index.html')
    shutil.copytree(output / 'docs', output / 'source/docs')
    shutil.copytree(output / 'evidence', output / 'source/reports/delivery-20260927')
    (output / 'source/data').mkdir()
    shutil.copy2(ROOT / 'data/partner-products.template.csv', output / 'source/data/partner-products.template.csv')
    config_path = output / 'miniapp/project.config.json'
    config = json.loads(config_path.read_text())
    config.pop('projectArchitecture', None)
    config['setting']['urlCheck'] = True
    config['setting']['uploadWithSourceMap'] = False
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    web = output / 'web-patch'
    for name in ('content-manifest.js', 'catalog-contract.js', 'membership-catalog.js'):
        asset = web / name
        versioned = f'{asset.stem}.{digest(asset)[:16]}{asset.suffix}'
        shutil.copy2(asset, web / versioned)
        for page in web.glob('*.html'):
            html = page.read_text(encoding='utf-8')
            page.write_text(html.replace(f'src="{name}"', f'src="{versioned}"'), encoding='utf-8')
    subprocess.run([sys.executable, str(ROOT / 'tools/import_partner_products.py'),
                    '--generate-matching-csv', str(output / 'merchant/500-books-to-match.csv')], check=True, cwd=ROOT)
    status = {'generatedAt': datetime.now(timezone.utc).isoformat(), 'candidateVersion': '1.0.7-rc2',
              'localChecks': 'passed', 'productionDeployed': False, 'uploaded': False,
              'reviewSubmitted': False, 'released': False, 'completeProductionBackup': False,
              'merchantAuthorizationProvided': False, 'confirmedPartnerProducts': 0,
              'requiredGates': ['authorized-server-access-and-production-rebase',
                                'correct-miniapp-account-and-login', 'domain-privacy-filing-review-verification',
                                'simulator-and-physical-device-validation', 'authoritative-audio-intro-audit',
                                'merchant-authorization-and-real-products', 'final-owner-approval']}
    (output / 'release-status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
    (output / 'test-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    files = [{'path': str(p.relative_to(output)), 'bytes': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(output.rglob('*')) if p.is_file()]
    (output / 'SHA256.json').write_text(json.dumps(files, ensure_ascii=False, indent=2) + '\n')
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as bundle:
        for p in sorted(output.rglob('*')):
            if p.is_file():
                bundle.write(p, str(Path(output.name) / p.relative_to(output)))
    print(json.dumps({'candidate': str(output), 'archive': str(archive), 'files': len(files),
                      'archiveSHA256': digest(archive), 'released': False}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    build(Path(args.output))

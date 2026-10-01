#!/usr/bin/env python3
"""Test the candidate against read-only live content and a disposable database."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    checkout = Path(__file__).resolve().parents[1]
    live = Path('/var/www/kangboacademy')
    report = checkout / 'production-content-check.json'
    if report.exists():
        raise RuntimeError('Use a new staging directory')
    with tempfile.TemporaryDirectory(prefix='kangbo-merge-check-') as folder:
        root = Path(folder)
        front = root / 'frontend'
        front.mkdir()
        (root / 'data').mkdir()
        for path in (live / 'frontend').iterdir():
            if path.name != 'content-manifest.json':
                (front / path.name).symlink_to(path, target_is_directory=path.is_dir())
        shutil.copy2(checkout / 'server_patch/frontend/content-manifest.json', front / 'content-manifest.json')
        for name in ('shop-products.json', 'knowledge-graph.json'):
            if (live / 'data' / name).is_file():
                (root / 'data' / name).symlink_to(live / 'data' / name)
        os.environ['KANGBO_PROJECT_ROOT'] = str(root)
        source = checkout / 'server_patch/backend/main.py'
        sys.path.insert(0, str(source.parent))
        spec = importlib.util.spec_from_file_location('candidate_readonly_content_check', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert Path(module.DB_PATH).parent == root / 'data'
        module.PAYMENT_ENV_PATH = root / 'data/test-payment.env'
        module.LEGACY_PAYMENT_ENV_PATH = root / 'data/test-legacy-payment.env'
        module.PAYMENT_PRIVATE_KEY_PATH = root / 'data/test-private-key.pem'
        module.PAYMENT_ADMIN_TOKEN = ''
        from fastapi.testclient import TestClient
        with TestClient(module.app) as client:
            statuses = {route: client.get(route).status_code for route in
                        ['/api/health', '/api/courses', '/api/book-courses', '/api/progress']}
            assert list(statuses.values()) == [200, 200, 200, 401], statuses
            shop = client.get('/api/shop/books?limit=500').json()
            assert len(shop['books']) == 500
            payment_ready = client.get('/api/membership/plans').json().get('payment', {}).get('ready')
        errors, short = [], []
        for kind, size in [('core', 65), ('book', 500)]:
            for number in range(1, size + 1):
                key = f'{kind}:{number}'
                page = front / f'{"lesson" if kind == "core" else "book"}{number}.html'
                try:
                    module.validate_progress_request(module.ProgressReq(
                        course_id=number if kind == 'core' else 10000 + number,
                        status='in_progress', progress_percent=1))
                    body = module.html_article_from_page(page, strip_practice=True)
                    if len(body) < 200:
                        short.append({'course': key, 'characters': len(body)})
                except Exception as error:
                    errors.append({'course': key, 'errorType': type(error).__name__})
        result = {'scope': 'server-runtime-candidate-with-readonly-production-content-and-disposable-database',
                  'productionModified': False, 'routes': statuses, 'coursesChecked': 565,
                  'progressOrContentErrors': errors, 'shortExtractedContent': short,
                  'shopRows': len(shop['books']),
                  'purchaseReadyRows': sum(book.get('purchaseEntryReady') is True for book in shop['books']),
                  'paymentReadyInIsolatedProcess': payment_ready,
                  'passed': not errors and not short}
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

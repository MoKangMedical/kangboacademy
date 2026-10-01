#!/usr/bin/env python3
"""Start the actual ASGI app against disposable fixtures, never production data."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    report = Path(args.report)
    if report.exists():
        raise ValueError('Report must be a new file')
    source = ROOT / 'server_patch/backend/main.py'
    if 'KANGBO_PROJECT_ROOT' not in source.read_text():
        raise RuntimeError('Backend has no isolated project-root support')
    with tempfile.TemporaryDirectory(prefix='kangbo-asgi-fixture-') as folder:
        root = Path(folder)
        (root / 'data').mkdir()
        frontend = root / 'frontend'
        (frontend / 'courses').mkdir(parents=True)
        (frontend / 'courses/01-fixture.md').write_text('# Fixture core course\n\nTest content only.\n')
        (frontend / 'lesson1.html').write_text('<article><h1>Fixture</h1><p>Test content only.</p></article>')
        (frontend / 'book-courses.html').write_text('\n'.join(
            f'{{n:{number},t:"Fixture book {number}",a:"Fixture author",d:1,c:"period"}}'
            for number in range(1, 501)))
        (frontend / 'book1.html').write_text('<div class="content"><h1>Fixture book</h1><p>Test content only.</p></div>')
        shutil.copy2(ROOT / 'server_patch/frontend/content-manifest.json', frontend / 'content-manifest.json')
        os.environ['KANGBO_PROJECT_ROOT'] = folder
        os.environ['BOOK_AFFILIATE_URL_TEMPLATE'] = ''
        for name in ('WECHAT_SHOP_APPID', 'WECHAT_SHOP_BUSINESS_TYPE', 'PAYMENT_ADMIN_TOKEN',
                     'WECHAT_PAY_LIVE_ENABLED', 'WECHAT_PAY_PLATFORM_PUBLIC_KEY_ID', 'WECHAT_PAY_PLATFORM_PUBLIC_KEY_PATH',
                     'WECHAT_PAY_CERT_SERIAL_NO', 'WECHAT_PAY_PRIVATE_KEY_PATH',
                     'WECHAT_MINIAPP_SECRET', 'WECHAT_PAY_MCHID', 'WECHAT_PAY_API_V3_KEY', 'DEEPSEEK_API_KEY'):
            os.environ.pop(name, None)
        sys.path.insert(0, str(source.parent))
        spec = importlib.util.spec_from_file_location('kangbo_isolated_smoke', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert Path(module.DB_PATH).is_relative_to(root)
        module.PAYMENT_ENV_PATH = root / 'data/test-payment.env'
        module.LEGACY_PAYMENT_ENV_PATH = root / 'data/test-legacy-payment.env'
        module.PAYMENT_PRIVATE_KEY_PATH = root / 'data/test-private-key.pem'
        module.PAYMENT_ADMIN_TOKEN = ''
        from fastapi.testclient import TestClient
        checks = []
        with TestClient(module.app) as client:
            for route, expected in [('/api/health', 200), ('/api/courses', 200),
                                    ('/api/book-courses', 200), ('/api/shop/books?limit=500', 200),
                                    ('/api/progress', 401), ('/api/shop/purchases', 401)]:
                response = client.get(route)
                assert response.status_code == expected, (route, response.status_code)
                checks.append({'route': route, 'status': response.status_code})
            diagnostic = client.get('/api/payment/diagnostics')
            assert diagnostic.status_code == 403
            checks.append({'route': '/api/payment/diagnostics', 'status': diagnostic.status_code})
            started = time.monotonic()
            shop = client.get('/api/shop/books?limit=500').json()
            elapsed = time.monotonic() - started
            assert len(shop['books']) == 500
            assert shop['shop']['purchaseEntryBooks'] == 0
            assert shop['books'][0]['purchaseEntryReady'] is False
            assert shop['books'][0]['purchaseEntryType'] == 'search'
            checks.append({'check': 'search-not-product', 'passed': True, 'books': 500,
                           'localFixtureResponseSeconds': round(elapsed, 3)})
            for route, payload, expected in [
                ('/api/payment/wechat/notify', {}, 400),
                ('/api/payment/create', {'plan': 'core_year'}, 401),
                ('/api/practice/submit', {'lesson': 'lesson1.html', 'answers': {}}, 401),
            ]:
                response = client.post(route, json=payload)
                assert response.status_code == expected, (route, response.status_code)
                checks.append({'route': route, 'method': 'POST', 'status': response.status_code})
            connection = module.get_db()
            try:
                assert connection.execute('SELECT COUNT(*) FROM payments').fetchone()[0] == 0
                assert connection.execute('SELECT COUNT(*) FROM practice_attempts').fetchone()[0] == 0
            finally:
                connection.close()
        result = {'scope': 'actual-ASGI-with-disposable-fixtures', 'productionTouched': False,
                  'fixtureContentNotProductionCourses': True, 'checks': checks, 'passed': True}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

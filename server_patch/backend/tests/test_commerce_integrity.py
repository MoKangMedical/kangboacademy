"""Commerce boundary tests without application imports, network or disk databases."""
import ast
import asyncio
import json
import re
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from urllib import parse


SOURCE = Path(__file__).resolve().parents[1] / 'main.py'
FUNCTIONS = {
    'render_book_url_template', 'generated_book_product', 'merge_product_config',
    'product_has_direct_commission', 'product_has_purchase_entry', 'affiliate_programs',
    'shop_config', 'shop_book_detail', 'product_channel', 'product_target_url',
    'safe_commerce_url', 'commerce_link_kind', 'book_open_action', 'record_shop_lead',
    'public_merchant_info', 'commerce_authorization_ready',
    'purchase_public', 'get_shop_books', 'record_shop_click', 'resolve_shop_book',
    'redirect_shop_book', 'get_shop_purchases', 'launch_stats', 'launch_sprint',
    'shop_commission_report',
}


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


class CommerceTests(unittest.TestCase):
    def setUp(self):
        self.products = {}
        self.env = {}
        self.opens = 0
        self.events = []
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE shop_clicks (user_id INTEGER, book_id INTEGER, source TEXT,
                target TEXT, created_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE book_purchases (id INTEGER PRIMARY KEY, user_id INTEGER,
                book_id INTEGER, title TEXT, author TEXT, price TEXT, price_text TEXT,
                quantity INTEGER, status TEXT, source TEXT, target TEXT, raw_json TEXT,
                order_no TEXT, purchased_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE launch_events (event_type TEXT, source TEXT, channel TEXT,
                ip_hash TEXT, created_at TEXT DEFAULT (datetime('now')));
            CREATE TABLE payments (status TEXT, amount_fen INTEGER, paid_at TEXT,
                created_at TEXT DEFAULT (datetime('now')));
        ''')
        owner = self

        class Connection:
            def __getattr__(self, name):
                return getattr(owner.db, name)

            def close(self):
                pass

        def get_db():
            self.opens += 1
            return Connection()

        self.scope = dict(
            re=re, json=json, parse=parse, Optional=Optional, datetime=datetime, timedelta=timedelta,
            os=SimpleNamespace(getenv=lambda key, default='': self.env.get(key, default)),
            BOOK_AFFILIATE_URL_TEMPLATE='',
            BOOK_AFFILIATE_FALLBACK_URL_TEMPLATE='https://search.jd.com/Search?keyword={encodedTitle}',
            parse_book_courses=lambda: [{'n': 1, 'title': 'Book', 'author': 'Author', 'category': 'period'}],
            load_shop_product_map=lambda: self.products,
            HTTPException=HTTPError, get_db=get_db, get_current_user=lambda: None,
            Depends=lambda value: None, Header=lambda value: None, Request=object,
            ShopClickReq=object, ShopResolveReq=object,
            LaunchEventReq=lambda **kwargs: SimpleNamespace(**kwargs),
            user_from_authorization=lambda value: {'id': 7},
            JSONResponse=lambda **kwargs: SimpleNamespace(**kwargs),
            RedirectResponse=lambda url, status_code: SimpleNamespace(url=url, status_code=status_code),
            record_launch_event=lambda *args: self.events.append(args),
            payment_config=lambda: {},
            public_url=lambda value: 'https://example.test/' + value.lstrip('/'),
            promo_week_start=lambda: datetime.now(timezone.utc) + timedelta(hours=8),
        )
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in FUNCTIONS]
        self.assertEqual({node.name for node in nodes}, FUNCTIONS)
        for node in nodes:
            node.decorator_list = []
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), self.scope)

    def tearDown(self):
        self.db.close()

    def action(self, product, config=None):
        return self.scope['book_open_action'](1, product, config or {})

    def authorized(self, **product):
        return {
            'merchantName': 'Test Merchant', 'authorizationReference': 'TEST-AUTH-001',
            'authorizationStatus': 'confirmed',
            'afterSales': {'contact': 'support@example.test', 'description': 'Contact merchant for returns'},
            **product,
        }

    def test_search_is_openable_not_a_product_or_commission(self):
        product = self.scope['generated_book_product'](1, 'Book', '')
        product.update(purchaseEntryReady=True, commissionReady=True, productId='123',
                       settlementMode='cps', commissionRate='10%')
        action = self.action(product)
        self.assertEqual(action['entryKind'], 'search')
        self.assertTrue(action['canOpen'])
        self.assertFalse(action['canBuy'])
        self.assertFalse(self.scope['product_has_purchase_entry'](product))
        self.assertFalse(self.scope['product_has_direct_commission'](product))

    def test_search_catalog_does_not_advertise_price_or_purchase(self):
        self.products['1'] = {'price': '68.00', 'purchaseEntryReady': True}
        result = asyncio.run(self.scope['get_shop_books']())
        book = result['books'][0]
        self.assertFalse(book['canBuy'])
        self.assertTrue(book['canOpen'])
        self.assertEqual(book['price'], '')
        self.assertEqual(result['shop']['purchaseEntryBooks'], 0)
        self.assertEqual(result['shop']['directCommissionBooks'], 0)
        self.assertTrue(result['shop']['enabled'])

    def test_explicit_target_replaces_generated_alias(self):
        base = self.scope['generated_book_product'](1, 'Book', '')
        product = self.scope['merge_product_config'](base, self.authorized(externalUrl='https://item.jd.com/123.html'))
        self.assertEqual(self.action(product)['url'], 'https://item.jd.com/123.html')
        self.assertTrue(self.action(product)['canBuy'])
        self.assertNotIn('search', product['affiliateUrl'])

    def test_generic_affiliate_link_requires_product_identity(self):
        product = {'affiliateUrl': 'https://shop.example/offer', 'commissionReady': True,
                   'settlementMode': 'cps', 'commissionRate': '10%'}
        self.assertEqual(self.action(product)['entryKind'], 'unverified_link')
        self.assertFalse(self.scope['product_has_direct_commission'](product))
        product['productId'] = 'sku_123'
        product = self.authorized(**product)
        self.assertTrue(self.scope['product_has_direct_commission'](product))
        self.assertEqual(self.action(product)['entryKind'], 'configured_product')

    def test_invalid_url_and_open_type_fail_closed(self):
        for url in ['javascript:alert(1)', 'data:text/html,test', '//evil.test',
                    'http://shop.example/a', 'https://u:p@shop.example/a',
                    'https://shop.example:444/a', 'https://shop.example/{id}',
                    'https://shop.example/\r\na', 'https://shop.example/\\x', 'https://[bad/a']:
            with self.subTest(url=url):
                self.assertEqual(self.action({'affiliateUrl': url})['type'], 'none')
        self.assertEqual(self.action({'externalUrl': 'https://item.jd.com/1.html', 'openType': 'shell'})['type'], 'none')

    def test_search_url_overrides_product_flags(self):
        for url in ['https://search.jd.com/Search?keyword=Book', 'https://shop.example/search/Book',
                    'https://shop.example/list?q=Book']:
            self.assertEqual(self.action({'url': url, 'productId': '123', 'purchaseEntryReady': True})['entryKind'], 'search')

    def test_mini_program_requires_valid_app_and_specific_target(self):
        config = {'appId': 'wx0123456789abcdef', 'homePath': 'pages/index/index'}
        self.assertEqual(self.action({}, config)['entryKind'], 'store')
        product = {'productId': '123', 'path': 'pages/product/detail?id=123'}
        self.assertEqual(self.action(product, config)['entryKind'], 'configured_product')
        for bad in ['bad', 'wx123', 'wx0123456789abcdeg']:
            self.assertEqual(self.action(product, {'appId': bad})['type'], 'none')
        for path in ['https://evil.test', '../pages/product', 'pages/../evil', 'pages/product?id={productId}']:
            self.assertEqual(self.action({**product, 'path': path}, config)['type'], 'none')
        self.assertFalse(self.action({'productId': '123'}, config)['canBuy'])

    def test_global_template_matches_catalog_readiness(self):
        self.env.update(WECHAT_SHOP_APPID='wx0123456789abcdef',
                        WECHAT_SHOP_PRODUCT_PATH_TEMPLATE='pages/product/detail?id={productId}')
        self.products['1'] = self.authorized(productId='123')
        result = asyncio.run(self.scope['get_shop_books']())
        self.assertTrue(result['books'][0]['canBuy'])
        self.assertEqual(result['shop']['purchaseEntryBooks'], 1)

    def test_business_view_requires_product_query(self):
        product = {'openType': 'business_view', 'businessType': 'shop', 'productId': '123'}
        self.assertEqual(self.action(product)['type'], 'none')
        self.assertEqual(self.action({**product, 'queryString': 'productId=999'})['type'], 'none')
        action = self.action(self.authorized(**product, queryString='productId=123'))
        self.assertEqual(action['type'], 'none')
        self.assertFalse(action['canBuy'])
        self.assertFalse(self.scope['product_has_purchase_entry'](self.authorized(**product, queryString='productId=123')))

    def test_web_view_is_not_purchase_ready(self):
        product = self.authorized(externalUrl='https://item.jd.com/123.html', openType='web_view')
        self.assertFalse(self.action(product)['canBuy'])
        self.assertFalse(self.scope['product_has_purchase_entry'](product))

    def test_program_descriptions_match_supported_actions_and_merchant_responsibility(self):
        programs = self.scope['affiliate_programs']()
        self.assertEqual({program['key'] for program in programs},
                         {'wechat_shop', 'jd_union', 'dangdang_affiliate', 'taobao_union', 'custom'})
        for program in programs:
            with self.subTest(program=program['key']):
                self.assertTrue(program['openTypes'])
                self.assertLessEqual(set(program['openTypes']), {'mini_program', 'clipboard'})
                self.assertIn('发货与售后由实际商家负责', program['notes'])
                self.assertNotIn('微信负责', program['notes'])

    def test_product_id_must_match_resolvable_target(self):
        self.assertEqual(self.action({'url': 'https://item.jd.com/999.html', 'productId': '123'})['type'], 'none')
        self.assertEqual(self.action({'productId': '123', 'path': 'pages/product/detail?id=999'},
                                    {'appId': 'wx0123456789abcdef'})['type'], 'none')

    def test_product_and_reference_alone_do_not_establish_authorization(self):
        for override in [{}, {'authorizationReference': '/private/auth.pdf'},
                         {'authorizationStatus': 'expired'}, {'authorizationStatus': 'revoked'},
                         {'authorizationStatus': True}]:
            self.products['1'] = {'externalUrl': 'https://item.jd.com/123.html', **override}
            result = asyncio.run(self.scope['get_shop_books']())
            self.assertFalse(result['books'][0]['purchaseEntryReady'])
            self.assertFalse(result['books'][0]['canBuy'])
            self.assertFalse(result['books'][0]['commissionReady'])

    def test_public_merchant_service_fields_and_private_reference_redaction(self):
        self.products['1'] = self.authorized(
            externalUrl='https://item.jd.com/123.html', authorizationReference='/private/contracts/test.pdf',
            afterSales={'contact': 'support@example.test', 'policyUrl': 'https://shop.example/returns',
                        'description': 'Returns via merchant', 'authorizationDocumentPath': '/private/contracts/test.pdf'})
        result = asyncio.run(self.scope['get_shop_books']())
        book = result['books'][0]
        self.assertTrue(book['purchaseEntryReady'])
        self.assertEqual(book['merchantName'], 'Test Merchant')
        self.assertEqual(book['afterSales']['contact'], 'support@example.test')
        self.assertEqual(book['afterSales']['policyUrl'], 'https://shop.example/returns')
        self.assertNotIn('/private/', json.dumps(result))
        self.assertNotIn('authorizationReference', json.dumps(result))
        self.assertNotIn('authorizationDocumentPath', json.dumps(result))
        self.assertEqual(book['paymentEvidence'], 'none')
        self.assertEqual(book['action']['url'], 'https://item.jd.com/123.html')

    def test_private_service_paths_cannot_enable_readiness_or_leak(self):
        self.products['1'] = self.authorized(externalUrl='https://item.jd.com/123.html',
            afterSales={'contact': '/Users/test/auth.pdf', 'description': 'file:///private/doc.pdf',
                        'policyUrl': 'https://shop.example/returns?token=PRIVATE'})
        result = asyncio.run(self.scope['get_shop_books']())
        book = result['books'][0]
        self.assertFalse(book['purchaseEntryReady'])
        self.assertEqual(book['afterSales'], {'contact': '', 'description': '', 'policyUrl': ''})

    def test_search_never_becomes_ready_even_with_complete_merchant_fields(self):
        self.products['1'] = self.authorized(externalUrl='https://search.jd.com/Search?keyword=Book',
                                             commissionRate='10%', settlementMode='cps')
        result = asyncio.run(self.scope['get_shop_books']())
        self.assertEqual(result['books'][0]['entryKind'], 'search')
        self.assertFalse(result['books'][0]['purchaseEntryReady'])
        self.assertEqual(result['shop']['purchaseEntryBooks'], 0)
        self.assertEqual(result['shop']['directCommissionBooks'], 0)

    def test_500_search_entries_without_authorization_stay_unready(self):
        courses = [{'n': n, 'title': f'Book {n}', 'author': 'Author', 'category': 'period'}
                   for n in range(1, 501)]
        self.scope['parse_book_courses'] = lambda: courses
        result = asyncio.run(self.scope['get_shop_books'](500))
        self.assertEqual(result['total'], 500)
        self.assertEqual(result['shop']['purchaseEntryBooks'], 0)
        self.assertEqual(result['shop']['directCommissionBooks'], 0)
        for book in result['books']:
            self.assertEqual(book['channel'], 'jd_search')
            self.assertEqual(book['purchaseStatus'], 'search')
            self.assertEqual(book['authorizationStatus'], 'unverified')
            self.assertFalse(book['purchaseEntryReady'])
            self.assertFalse(book['canBuy'])
            self.assertFalse(book['commissionReady'])
        self.assertEqual(self.opens, 0)

    def test_500_books_parse_and_load_once_with_consistent_identity_and_authorization(self):
        calls = {'parse': 0, 'load': 0}
        courses = [{'n': n, 'title': f'Snapshot Book {n}', 'author': 'Author', 'category': 'period'}
                   for n in range(1, 501)]
        products = {}
        for n in range(1, 501):
            if n % 3 == 0:
                products[str(n)] = self.authorized(
                    productId=str(n), externalUrl=f'https://item.jd.com/{n}.html',
                    commissionRate='10%', settlementMode='cps')
            elif n % 3 == 1:
                products[str(n)] = {'productId': str(n), 'externalUrl': f'https://item.jd.com/{n}.html',
                                    'merchantName': 'Unverified Merchant', 'authorizationReference': 'UNVERIFIED'}

        def parse_courses():
            calls['parse'] += 1
            return courses if calls['parse'] == 1 else [{**course, 'title': f'New Book {course["n"]}'} for course in courses]

        def load_products():
            calls['load'] += 1
            return products if calls['load'] == 1 else {}

        self.scope['parse_book_courses'] = parse_courses
        self.scope['load_shop_product_map'] = load_products
        result = asyncio.run(self.scope['get_shop_books'](500))
        self.assertEqual(calls, {'parse': 1, 'load': 1})
        self.assertEqual(result['total'], 500)
        self.assertEqual([book['id'] for book in result['books']], list(range(1, 501)))
        for book in result['books']:
            n = book['id']
            self.assertEqual(book['title'], f'Snapshot Book {n}')
            self.assertEqual(book['purchaseEntryReady'], n % 3 == 0)
            self.assertEqual(book['commissionReady'], n % 3 == 0)
            self.assertEqual(book['authorizationStatus'], 'confirmed' if n % 3 == 0 else 'unverified')
            self.assertEqual(book['entryKind'], 'search' if n % 3 == 2 else 'configured_product')
            if n % 3 != 2:
                self.assertEqual(book['action']['url'], f'https://item.jd.com/{n}.html')
        self.assertEqual(result['shop']['purchaseEntryBooks'], 166)
        self.assertEqual(result['shop']['directCommissionBooks'], 166)
        # A later request must see fresh inputs, not a permanent global cache.
        refreshed = asyncio.run(self.scope['get_shop_books'](500))
        self.assertEqual(calls, {'parse': 2, 'load': 2})
        self.assertEqual(refreshed['shop']['purchaseEntryBooks'], 0)
        self.assertTrue(all(book['title'] == f'New Book {book["id"]}' for book in refreshed['books']))
        self.assertTrue(all(book['entryKind'] == 'search' for book in refreshed['books']))
        self.assertEqual(self.opens, 0)

    def test_explicit_empty_snapshots_do_not_reload(self):
        def unexpected_load():
            raise AssertionError('Injected snapshots must not trigger another read')

        self.scope['parse_book_courses'] = unexpected_load
        self.scope['load_shop_product_map'] = unexpected_load
        self.assertEqual(self.scope['shop_config'](courses=[], product_map={})['purchaseEntryBooks'], 0)
        course = {'n': 1, 'title': 'Snapshot Book', 'author': 'Author'}
        detail = self.scope['shop_book_detail'](1, course=course, product_map={})
        self.assertEqual(detail['title'], 'Snapshot Book')
        with self.assertRaises(HTTPError) as error:
            self.scope['shop_book_detail'](2, course=course, product_map={})
        self.assertEqual(error.exception.status_code, 404)

    def test_nonexistent_book_rejected_before_config_or_database(self):
        with self.assertRaises(HTTPError) as error:
            self.scope['shop_book_detail'](999)
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(HTTPError):
            self.scope['record_shop_lead']({'id': 7}, 999)
        self.assertEqual(self.opens, 0)

    def test_redirect_never_bypasses_validation(self):
        self.products['1'] = {'externalUrl': 'javascript:alert(1)'}
        response = asyncio.run(self.scope['redirect_shop_book'](1, SimpleNamespace(url='test', headers={}), authorization=None))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.opens, 0)
        self.assertEqual(self.events, [])

    def test_native_action_is_json_not_http_redirect(self):
        self.products['1'] = {'miniProgramAppId': 'wx0123456789abcdef', 'productId': '123',
                              'path': 'pages/product/detail?id=123'}
        response = asyncio.run(self.scope['redirect_shop_book'](1, SimpleNamespace(url='test', headers={}), authorization=None))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content['action']['type'], 'mini_program')

    def test_click_uses_server_target_and_never_marks_paid(self):
        req = SimpleNamespace(book_id=1, source='test', target='https://forged.example/paid')
        asyncio.run(self.scope['record_shop_click'](req, None))
        asyncio.run(self.scope['record_shop_click'](req, None))
        purchases = asyncio.run(self.scope['get_shop_purchases']({'id': 7}))
        self.assertEqual(purchases['summary'], {'total': 1, 'paid': 0, 'pending': 1})
        row = purchases['purchases'][0]
        self.assertEqual(row['paymentEvidence'], 'interaction_only')
        self.assertIsNone(row['purchasedAt'])
        self.assertIsNotNone(row['interactionAt'])
        self.assertNotIn('forged', row['target'])

    def test_click_does_not_downgrade_existing_paid_record(self):
        self.scope['record_shop_lead']({'id': 7}, 1)
        self.db.execute("UPDATE book_purchases SET status='paid',order_no='test-order'")
        self.db.commit()
        self.scope['record_shop_lead']({'id': 7}, 1)
        result = asyncio.run(self.scope['get_shop_purchases']({'id': 7}))
        self.assertEqual(result['summary']['paid'], 0)
        self.assertEqual(result['summary']['total'], 1)
        self.assertEqual(result['summary']['pending'], 1)
        self.assertEqual(result['purchases'][0]['status'], 'paid')
        self.assertIs(result['purchases'][0]['paymentVerified'], False)
        self.assertEqual(result['purchases'][0]['paymentEvidence'], 'reported_unverified')
        self.assertIsNone(result['purchases'][0]['purchasedAt'])

    def test_untrusted_verification_flags_never_verify_purchase(self):
        result = self.scope['purchase_public']({
            'status': 'paid', 'paymentVerified': True,
            'raw_json': '{"paymentVerified":true}', 'order_no': 'self-reported',
        })
        self.assertIs(result['paymentVerified'], False)

    def test_commission_report_does_not_count_legacy_paid_as_verified(self):
        self.db.execute("INSERT INTO book_purchases(user_id,book_id,status) VALUES (7,1,'paid')")
        self.db.commit()
        report = self.scope['shop_commission_report']()
        self.assertEqual(report['summary']['paidPurchases'], 0)
        self.assertEqual(report['summary']['pendingPurchases'], 1)
        self.assertEqual(report['rows'][0]['paidPurchases'], 0)

    def test_manual_reports_and_clicks_are_not_paid_in_both_dashboards(self):
        for event in ['manual_purchase'] * 3 + ['book_click', 'purchase_intent']:
            self.db.execute("INSERT INTO launch_events(event_type,source,channel,ip_hash) VALUES (?,'xhs','','test')", (event,))
        self.db.execute("INSERT INTO payments(status,amount_fen) VALUES ('paid',100)")
        self.db.execute("INSERT INTO payments(status,amount_fen) VALUES ('pending',200)")
        self.db.execute("INSERT INTO book_purchases(user_id,book_id,status) VALUES (7,1,'paid')")
        self.db.commit()
        stats = asyncio.run(self.scope['launch_stats']())
        sprint = asyncio.run(self.scope['launch_sprint']())
        self.assertEqual(stats['paidPurchases'], 1)
        self.assertEqual(stats['unverifiedBookPaid'], 1)
        self.assertEqual(stats['manualPurchases'], 3)
        self.assertEqual(sprint['totals']['paidPurchases'], 1)
        self.assertEqual(sprint['totals']['unverifiedBookPaid'], 1)
        self.assertEqual(sprint['totals']['manualPurchases'], 3)
        self.assertEqual(sprint['platformTotals']['xhs']['manualPurchases'], 3)
        self.assertEqual(sprint['platformTotals']['xhs']['paidPurchases'], 0)


if __name__ == '__main__':
    unittest.main()

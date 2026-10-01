"""Synthetic keys and in-memory orders only; never use live credentials or money."""
import ast
import asyncio
import base64
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from datetime import datetime, timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException
from fastapi.responses import JSONResponse

BACKEND = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('payment_security_tested', BACKEND / 'payment_security.py')
security = importlib.util.module_from_spec(spec)
spec.loader.exec_module(security)


class PaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        public = Path(self.temp.name) / 'synthetic-public.pem'
        public.write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.config = {'platformPublicKeyId': 'PUB_KEY_ID_TEST', 'platformPublicKeyPath': str(public), 'mchid': 'test-merchant'}
        self.order = {'order_no': 'test-order', 'amount_fen': 39900, 'provider': 'wechat',
                      'status': 'pending', 'user_id': 1, 'plan': 'core_year', 'transaction_id': None}
        self.transaction = {'out_trade_no': 'test-order', 'amount': {'total': 39900, 'currency': 'CNY'},
                            'appid': 'test-app', 'mchid': 'test-merchant', 'payer': {'openid': 'test-payer'},
                            'trade_type': 'JSAPI', 'trade_state': 'SUCCESS', 'transaction_id': 'test-transaction'}
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY,wechat_openid TEXT,plan TEXT,plan_expires_at TEXT,updated_at TEXT);
            INSERT INTO users(id,wechat_openid) VALUES(1,'test-payer');
            CREATE TABLE payments(order_no TEXT PRIMARY KEY,user_id INTEGER,plan TEXT,provider TEXT,status TEXT,
                amount_fen INTEGER,transaction_id TEXT,paid_at TEXT,updated_at TEXT,notify_payload TEXT,amount REAL);
            INSERT INTO payments(order_no,user_id,plan,provider,status,amount_fen,amount)
                VALUES('test-order',1,'core_year','wechat','pending',39900,399);
            CREATE TABLE user_entitlements(user_id INTEGER,scope TEXT,plan TEXT,order_no TEXT,starts_at TEXT,expires_at TEXT,status TEXT);
        ''')
        owner = self

        class Connection:
            def __getattr__(self, name):
                return getattr(owner.db, name)

            def close(self):
                pass

        self.scope = dict(json=json, datetime=datetime, timedelta=timedelta, Optional=dict,
                          HTTPException=HTTPException, Request=object, PaymentReq=object,
                          Depends=lambda value: None, get_current_user=lambda: None,
                          JSONResponse=JSONResponse, PaymentSecurityError=security.PaymentSecurityError,
                          verify_message=security.verify_message, validate_transaction=security.validate_transaction,
                          read_notification_body=security.read_notification_body,
                          payment_runtime_config=lambda: self.config, WECHAT_MINIAPP_APPID='test-app',
                          decrypt_wechat_resource=lambda resource: copy.deepcopy(self.transaction),
                          PLANS={'core_year': {'price': 399, 'scope': 'core', 'duration_days': 365}},
                          payment_config=lambda: {'ready': True}, get_db=lambda: Connection(),
                          query_wechat_order=lambda number: copy.deepcopy(self.transaction))
        tree = ast.parse((BACKEND / 'main.py').read_text())
        names = {'wechat_payment_notify', 'payment_status', 'apply_paid_order', 'create_payment'}
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'main.py', 'exec'), self.scope)

    def headers(self, body, timestamp=None):
        stamp = str(int(time.time()) if timestamp is None else timestamp)
        message = stamp.encode() + b'\nnonce\n' + body + b'\n'
        signature = self.key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        return {'Wechatpay-Timestamp': stamp, 'Wechatpay-Nonce': 'nonce',
                'Wechatpay-Serial': 'PUB_KEY_ID_TEST', 'Wechatpay-Signature': base64.b64encode(signature).decode()}

    def notify(self, body=None, headers=None):
        body = body or b'{"event_type":"TRANSACTION.SUCCESS","resource":{}}'
        request = SimpleNamespace(headers=self.headers(body) if headers is None else headers)
        async def stream():
            yield body
        request.stream = stream
        return asyncio.run(self.scope['wechat_payment_notify'](request))

    def validate(self, transaction=None, payment=None):
        security.validate_transaction(transaction or self.transaction, payment or self.order,
                                      self.config, 'test-app', 'test-payer')

    def test_signature_raw_bytes_and_header_case(self):
        body = b'{ "hello": "world" }'
        security.verify_message(body, self.headers(body), self.config)
        with self.assertRaises(security.PaymentSecurityError):
            security.verify_message(b'{"hello":"world"}', self.headers(body), self.config)

    def test_signature_missing_unknown_tampered_and_probe(self):
        body = b'{}'
        for field, value in [('Wechatpay-Serial', 'PUB_KEY_ID_OTHER'), ('Wechatpay-Nonce', ''),
                             ('Wechatpay-Signature', 'WECHATPAY/SIGNTEST/probe'), ('Wechatpay-Timestamp', 'bad')]:
            with self.subTest(field=field):
                headers = self.headers(body)
                headers[field] = value
                with self.assertRaises(security.PaymentSecurityError):
                    security.verify_message(body, headers, self.config)

    def test_signature_rejects_stale_and_future_messages(self):
        for offset in [-301, 301]:
            with self.assertRaises(security.PaymentSecurityError):
                security.verify_message(b'{}', self.headers(b'{}', 1000 + offset), self.config, now=1000)

    def test_invalid_or_missing_trust_key_fails_closed(self):
        self.config['platformPublicKeyPath'] = str(Path(self.temp.name) / 'absent')
        with self.assertRaises(security.PaymentSecurityError):
            security.verify_message(b'{}', self.headers(b'{}'), self.config)

    def test_valid_order_and_discount_preserve_total_matching(self):
        self.transaction['amount']['payer_total'] = 39000
        self.validate()

    def test_order_identity_and_amount_mismatches(self):
        changes = [('appid', 'other'), ('mchid', 'other'), ('out_trade_no', 'other'),
                   ('trade_type', 'NATIVE'), ('payer', {'openid': 'other'}), ('transaction_id', ''),
                   ('amount', {'total': 1, 'currency': 'CNY'}),
                   ('amount', {'total': '39900', 'currency': 'CNY'}),
                   ('amount', {'total': 39900, 'currency': 'USD'})]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                transaction = copy.deepcopy(self.transaction)
                transaction[field] = value
                with self.assertRaises(security.PaymentSecurityError):
                    self.validate(transaction)

    def test_transaction_id_cannot_change_after_payment(self):
        self.order['transaction_id'] = 'different-transaction'
        with self.assertRaises(security.PaymentSecurityError):
            self.validate()

    def test_notify_requires_valid_signature_before_database(self):
        self.scope['get_db'] = lambda: self.fail('Unsigned request reached the database')
        self.assertEqual(self.notify(headers={}).status_code, 400)

    def test_notify_duplicate_has_exactly_one_entitlement(self):
        self.assertEqual(self.notify()['code'], 'SUCCESS')
        self.assertEqual(self.notify()['code'], 'SUCCESS')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM user_entitlements').fetchone()[0], 1)

    def test_notify_mismatch_does_not_grant_access(self):
        self.transaction['amount']['total'] = 1
        self.assertEqual(self.notify().status_code, 400)
        self.assertEqual(self.db.execute('SELECT status FROM payments').fetchone()[0], 'pending')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM user_entitlements').fetchone()[0], 0)

    def test_notify_non_success_never_downgrades_paid(self):
        self.notify()
        self.transaction['trade_state'] = 'CLOSED'
        self.assertEqual(self.notify().status_code, 400)
        self.assertEqual(self.db.execute('SELECT status FROM payments').fetchone()[0], 'paid')

    def test_atomic_update_rejects_stale_prepaid_snapshot(self):
        self.notify()
        result = self.scope['apply_paid_order'](self.db, self.order, 'test-transaction')
        self.assertTrue(result['alreadyPaid'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM user_entitlements').fetchone()[0], 1)

    def test_query_mismatch_never_grants_access(self):
        self.transaction['mchid'] = 'other'
        result = asyncio.run(self.scope['payment_status']('test-order', {'id': 1, 'wechat_openid': 'test-payer'}))
        self.assertFalse(result['paid'])
        self.assertEqual(result['syncStatus'], 'QUERY_FAILED')

    def test_closed_query_does_not_require_success_only_fields(self):
        self.transaction['trade_state'] = 'CLOSED'
        self.transaction.pop('payer')
        self.transaction.pop('trade_type')
        self.transaction.pop('amount')
        result = asyncio.run(self.scope['payment_status']('test-order', {'id': 1, 'wechat_openid': 'test-payer'}))
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(result['syncStatus'], 'CLOSED')

    def test_success_query_without_amount_never_grants_access(self):
        self.transaction.pop('amount')
        result = asyncio.run(self.scope['payment_status']('test-order', {'id': 1, 'wechat_openid': 'test-payer'}))
        self.assertFalse(result['paid'])
        self.assertEqual(result['syncStatus'], 'QUERY_FAILED')

    def test_checkout_disabled_still_reconciles_existing_order(self):
        self.scope['payment_config'] = lambda: {'ready': False, 'orderQueryReady': True}
        result = asyncio.run(self.scope['payment_status']('test-order', {'id': 1, 'wechat_openid': 'test-payer'}))
        self.assertTrue(result['paid'])

    def test_notification_size_limit_stops_reading_early(self):
        consumed = []
        async def stream():
            for number in range(3):
                consumed.append(number)
                yield b'x' * 10
        with self.assertRaises(security.PaymentSecurityError):
            asyncio.run(security.read_notification_body(SimpleNamespace(stream=stream), limit=15))
        self.assertEqual(consumed, [0, 1])

    def test_disabled_checkout_creates_no_order(self):
        self.scope['payment_config'] = lambda: {'ready': False}
        self.scope['get_db'] = lambda: self.fail('Disabled checkout opened database')
        with self.assertRaises(HTTPException) as caught:
            asyncio.run(self.scope['create_payment'](SimpleNamespace(plan='core_year', method='wechat'), {'id': 1}))
        self.assertEqual(caught.exception.status_code, 503)

    def test_readiness_requires_explicit_enable_and_trusted_key(self):
        tree = ast.parse((BACKEND / 'main.py').read_text())
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'payment_config')
        runtime = {**self.config, 'certSerialNo': 'test-serial',
                   'privateKeyPath': self.config['platformPublicKeyPath'],
                   'apiV3Key': 'synthetic-not-a-real-key', 'notifyUrl': 'https://example.test/notify',
                   'envFile': '', 'legacyEnvFile': ''}
        scope = {'Path': Path, 'PaymentSecurityError': security.PaymentSecurityError,
                 'load_verification_key': security.load_verification_key,
                 'payment_runtime_config': lambda: runtime}
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'main.py', 'exec'), scope)
        self.assertFalse(scope['payment_config']()['ready'])
        runtime['liveEnabled'] = True
        self.assertTrue(scope['payment_config']()['ready'])
        for field in ('privateKeyPath', 'envFile', 'legacyEnvFile', 'platformPublicKeyPath'):
            self.assertNotIn(field, scope['payment_config']())
        runtime['platformPublicKeyId'] = ''
        self.assertFalse(scope['payment_config']()['ready'])


if __name__ == '__main__':
    unittest.main()

"""Fail-closed WeChat Pay APIv3 public-key verification and order matching.

Only an operator-pinned public key is trusted; no key is accepted from a request.
Reference: https://pay.wechatpay.cn/doc/v3/merchant/4013053249
"""
import base64
import re
import time
from pathlib import Path


class PaymentSecurityError(ValueError):
    pass


def load_verification_key(config):
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    key_id = config.get('platformPublicKeyId', '')
    path = config.get('platformPublicKeyPath', '')
    if not re.fullmatch(r'PUB_KEY_ID_[A-Za-z0-9_]+', key_id) or not path:
        raise PaymentSecurityError('Payment verification key is not configured')
    try:
        key = serialization.load_pem_public_key(Path(path).read_bytes())
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError('Invalid RSA public key')
        return key
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm) as error:
        raise PaymentSecurityError('Payment verification key is unavailable') from error


def verify_message(body, headers, config, now=None):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    headers = {str(k).lower(): v for k, v in headers.items()}
    timestamp = headers.get('wechatpay-timestamp', '')
    nonce = headers.get('wechatpay-nonce', '')
    signature = headers.get('wechatpay-signature', '')
    serial = headers.get('wechatpay-serial', '')
    if not isinstance(body, bytes) or len(body) > 1024 * 1024:
        raise PaymentSecurityError('Invalid payment message size')
    if not re.fullmatch(r'[0-9]{1,12}', timestamp) or not nonce or len(nonce) > 256 or '\n' in nonce or '\r' in nonce:
        raise PaymentSecurityError('Invalid payment signature headers')
    if abs((time.time() if now is None else now) - int(timestamp)) > 300:
        raise PaymentSecurityError('Expired payment signature')
    if not serial or serial != config.get('platformPublicKeyId'):
        raise PaymentSecurityError('Untrusted payment key identifier')
    key = load_verification_key(config)
    message = timestamp.encode() + b'\n' + nonce.encode() + b'\n' + body + b'\n'
    try:
        key.verify(base64.b64decode(signature, validate=True), message, padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, ValueError, TypeError) as error:
        raise PaymentSecurityError('Invalid payment signature') from error


def validate_transaction(transaction, payment, config, app_id, expected_openid):
    if not isinstance(transaction, dict) or payment.get('provider') != 'wechat':
        raise PaymentSecurityError('Invalid payment transaction')
    for field, expected in [('appid', app_id), ('mchid', config.get('mchid')),
                            ('out_trade_no', payment.get('order_no'))]:
        if not expected or transaction.get(field) != expected:
            raise PaymentSecurityError('Payment identity mismatch')
    amount = transaction.get('amount')
    success = transaction.get('trade_state') == 'SUCCESS'
    if success and (not isinstance(amount, dict) or type(amount.get('total')) is not int):
        raise PaymentSecurityError('Invalid payment amount')
    if amount is not None and not isinstance(amount, dict):
        raise PaymentSecurityError('Invalid payment amount')
    if type(payment.get('amount_fen')) is not int or payment['amount_fen'] <= 0:
        raise PaymentSecurityError('Payment amount or currency mismatch')
    if isinstance(amount, dict):
        if (success or 'total' in amount) and (type(amount.get('total')) is not int or amount['total'] != payment['amount_fen']):
            raise PaymentSecurityError('Payment amount mismatch')
        if (success or 'currency' in amount) and amount.get('currency') != 'CNY':
            raise PaymentSecurityError('Payment currency mismatch')
    if success:
        payer = transaction.get('payer')
        if not expected_openid or not isinstance(payer, dict) or payer.get('openid') != expected_openid:
            raise PaymentSecurityError('Payment payer mismatch')
        if transaction.get('trade_type') != 'JSAPI':
            raise PaymentSecurityError('Unexpected payment trade type')
        transaction_id = transaction.get('transaction_id')
        if not isinstance(transaction_id, str) or not transaction_id.strip():
            raise PaymentSecurityError('Missing payment transaction identifier')
        if payment.get('transaction_id') and payment['transaction_id'] != transaction_id:
            raise PaymentSecurityError('Payment transaction identifier mismatch')


async def read_notification_body(request, limit=1024 * 1024):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise PaymentSecurityError('Payment notification too large')
        body.extend(chunk)
    return bytes(body)

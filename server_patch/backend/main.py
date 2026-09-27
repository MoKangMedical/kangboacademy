"""
康波研究院 API 后端 v2.0
kangboacademy.cn
完整功能：用户认证 + 课程进度 + 支付系统
"""
import os, json, hashlib, secrets, sqlite3, re, time, uuid, base64, subprocess, html, csv, io
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
from urllib import parse, request as urlrequest, error as urlerror
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    AESGCM = None

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, EmailStr, StrictInt
from typing import Optional, List, Dict
from content_contract import catalog_metadata

# ============================================================
# CONFIG
# ============================================================
PROJECT_ROOT = Path(os.getenv("KANGBO_PROJECT_ROOT", "/var/www/kangboacademy"))
DB_PATH = str(PROJECT_ROOT / "data" / "kangboacademy.db")
FRONTEND_DIR = PROJECT_ROOT / "frontend"
COURSES_DIR = FRONTEND_DIR / "courses"
BOOK_COURSES_HTML = FRONTEND_DIR / "book-courses.html"
KNOWLEDGE_GRAPH_JSON = PROJECT_ROOT / "data" / "knowledge-graph.json"
SHOP_PRODUCTS_JSON = PROJECT_ROOT / "data" / "shop-products.json"
SECRET_KEY = secrets.token_hex(32)
TOKEN_EXPIRE_DAYS = 30
WECHAT_MINIAPP_APPID = os.getenv("WECHAT_MINIAPP_APPID", "wx3bfed43762c89c86")
WECHAT_MINIAPP_SECRET = os.getenv("WECHAT_MINIAPP_SECRET", "")
WECHAT_OFFICIAL_APPID = os.getenv("WECHAT_OFFICIAL_APPID", "wx27418d6823daef09")
WECHAT_PAY_MCHID = os.getenv("WECHAT_PAY_MCHID", "")
WECHAT_PAY_CERT_SERIAL_NO = os.getenv("WECHAT_PAY_CERT_SERIAL_NO", "")
WECHAT_PAY_PRIVATE_KEY_PATH = os.getenv("WECHAT_PAY_PRIVATE_KEY_PATH", "")
WECHAT_PAY_API_V3_KEY = os.getenv("WECHAT_PAY_API_V3_KEY", "")
WECHAT_PAY_NOTIFY_URL = os.getenv("WECHAT_PAY_NOTIFY_URL", "https://kangboacademy.cn/api/payment/wechat/notify")
PAYMENT_ENV_PATH = Path(os.getenv("KANGBO_PAYMENT_ENV_PATH", "/var/www/kangboacademy/data/payment.env"))
PAYMENT_PRIVATE_KEY_PATH = Path(os.getenv("KANGBO_PAYMENT_PRIVATE_KEY_PATH", "/var/www/kangboacademy/data/apiclient_key.pem"))
LEGACY_PAYMENT_ENV_PATH = Path("/etc/kangboacademy/wechat.env")
PAYMENT_ADMIN_TOKEN = os.getenv("PAYMENT_ADMIN_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://kangboacademy.cn")
PUBLIC_ACCESS_MODE = os.getenv("PUBLIC_ACCESS_MODE", "paid").strip().lower()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_THINKING = os.getenv("DEEPSEEK_THINKING", "disabled")
DEEPSEEK_TIMEOUT_SECONDS = int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "20"))
BOOK_AFFILIATE_URL_TEMPLATE = os.getenv("BOOK_AFFILIATE_URL_TEMPLATE", "")
BOOK_AFFILIATE_FALLBACK_URL_TEMPLATE = os.getenv("BOOK_AFFILIATE_FALLBACK_URL_TEMPLATE", "https://search.jd.com/Search?keyword={encodedTitle}")
DOUYIN_RTMP_URL = os.getenv("DOUYIN_RTMP_URL", "")
WECHAT_CHANNELS_RTMP_URL = os.getenv("WECHAT_CHANNELS_RTMP_URL", "")
DIGITAL_HUMAN_SOURCE_URL = os.getenv("DIGITAL_HUMAN_SOURCE_URL", "")
DOUYIN_LIVE_PERMISSION = os.getenv("DOUYIN_LIVE_PERMISSION", "").strip().lower() in {"1", "true", "yes", "on"}
WECHAT_CHANNELS_LIVE_PERMISSION = os.getenv("WECHAT_CHANNELS_LIVE_PERMISSION", "").strip().lower() in {"1", "true", "yes", "on"}
DIGITAL_HUMAN_STREAM_SERVICES = os.getenv(
    "DIGITAL_HUMAN_STREAM_SERVICES",
    "kangbo-digital-live-douyin,kangbo-digital-live-channels",
)
LIVE_ENV_PATH = Path(os.getenv("KANGBO_LIVE_ENV_PATH", "/var/www/kangboacademy/data/live.env"))
LEGACY_LIVE_ENV_PATH = Path("/etc/kangboacademy/wechat.env")

# ============================================================
# DATABASE
# ============================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        username TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        phone TEXT,
        avatar TEXT DEFAULT '',
        plan TEXT DEFAULT 'free',
        plan_expires_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        last_login TEXT,
        is_active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS user_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS course_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        status TEXT DEFAULT 'not_started',
        progress_percent INTEGER DEFAULT 0,
        quiz_score INTEGER,
        quiz_total INTEGER,
        started_at TEXT,
        completed_at TEXT,
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, course_id)
    );

    CREATE TABLE IF NOT EXISTS quiz_answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        question_idx INTEGER NOT NULL,
        answer INTEGER NOT NULL,
        is_correct INTEGER,
        submitted_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        order_no TEXT UNIQUE NOT NULL,
        plan TEXT NOT NULL,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'CNY',
        method TEXT,
        status TEXT DEFAULT 'pending',
        paid_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS user_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS user_bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        lesson TEXT DEFAULT '',
        title TEXT DEFAULT '',
        is_book_course INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT (datetime('now')),
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, course_id)
    );

    CREATE TABLE IF NOT EXISTS learning_streaks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        courses_viewed INTEGER DEFAULT 0,
        quiz_taken INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, date)
    );

    CREATE TABLE IF NOT EXISTS practice_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        lesson TEXT NOT NULL,
        course_id INTEGER NOT NULL,
        is_book_course INTEGER DEFAULT 0,
        score INTEGER NOT NULL,
        max_score INTEGER DEFAULT 100,
        answers_json TEXT NOT NULL,
        results_json TEXT NOT NULL,
        feedback TEXT NOT NULL,
        badges_json TEXT DEFAULT '[]',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS daily_refinements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        practice_count INTEGER DEFAULT 0,
        score_total INTEGER DEFAULT 0,
        minutes INTEGER DEFAULT 0,
        badges_earned INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, date)
    );

    CREATE TABLE IF NOT EXISTS user_badges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        badge_key TEXT NOT NULL,
        badge_name TEXT NOT NULL,
        badge_desc TEXT NOT NULL,
        badge_icon TEXT NOT NULL,
        earned_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(user_id, badge_key)
    );

    CREATE TABLE IF NOT EXISTS user_entitlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        scope TEXT NOT NULL,
        plan TEXT NOT NULL,
        order_no TEXT,
        starts_at TEXT DEFAULT (datetime('now')),
        expires_at TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS shop_clicks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        book_id INTEGER NOT NULL,
        source TEXT DEFAULT 'miniapp',
        target TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS book_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        book_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        author TEXT DEFAULT '',
        price TEXT DEFAULT '',
        price_text TEXT DEFAULT '',
        quantity INTEGER DEFAULT 1,
        status TEXT DEFAULT 'pending',
        order_no TEXT DEFAULT '',
        source TEXT DEFAULT 'miniapp',
        target TEXT DEFAULT '',
        raw_json TEXT DEFAULT '{}',
        purchased_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE INDEX IF NOT EXISTS idx_course_progress_user ON course_progress(user_id);
    CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
    CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(order_no);
    CREATE INDEX IF NOT EXISTS idx_user_tokens_token ON user_tokens(token);
    CREATE INDEX IF NOT EXISTS idx_user_entitlements_user ON user_entitlements(user_id, scope, status);
    CREATE INDEX IF NOT EXISTS idx_shop_clicks_book ON shop_clicks(book_id);
    CREATE INDEX IF NOT EXISTS idx_book_purchases_user ON book_purchases(user_id, purchased_at);

    CREATE TABLE IF NOT EXISTS launch_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        event_type TEXT NOT NULL,
        source TEXT DEFAULT '',
        channel TEXT DEFAULT '',
        campaign TEXT DEFAULT '',
        path TEXT DEFAULT '',
        referrer TEXT DEFAULT '',
        target TEXT DEFAULT '',
        plan TEXT DEFAULT '',
        book_id INTEGER,
        order_no TEXT DEFAULT '',
        amount_fen INTEGER,
        ip_hash TEXT DEFAULT '',
        user_agent TEXT DEFAULT '',
        raw_json TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS idx_book_purchases_book ON book_purchases(book_id, status);
    CREATE INDEX IF NOT EXISTS idx_launch_events_created ON launch_events(created_at);
    CREATE INDEX IF NOT EXISTS idx_launch_events_type_source ON launch_events(event_type, source, created_at);
    CREATE INDEX IF NOT EXISTS idx_practice_attempts_user ON practice_attempts(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_daily_refinements_user ON daily_refinements(user_id, date);
    CREATE INDEX IF NOT EXISTS idx_user_badges_user ON user_badges(user_id, badge_key);
    """)
    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    optional_user_columns = {
        "wechat_openid": "wechat_openid TEXT",
        "wechat_unionid": "wechat_unionid TEXT",
        "wechat_session_key": "wechat_session_key TEXT",
        "wechat_bound_at": "wechat_bound_at TEXT",
    }
    for column, ddl in optional_user_columns.items():
        if column not in user_columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {ddl}")
    payment_columns = {row["name"] for row in conn.execute("PRAGMA table_info(payments)").fetchall()}
    optional_payment_columns = {
        "amount_fen": "amount_fen INTEGER",
        "provider": "provider TEXT",
        "provider_order_no": "provider_order_no TEXT",
        "transaction_id": "transaction_id TEXT",
        "prepay_id": "prepay_id TEXT",
        "entitlement_scope": "entitlement_scope TEXT",
        "payment_payload": "payment_payload TEXT",
        "notify_payload": "notify_payload TEXT",
        "expires_at": "expires_at TEXT",
        "updated_at": "updated_at TEXT",
    }
    for column, ddl in optional_payment_columns.items():
        if column not in payment_columns:
            conn.execute(f"ALTER TABLE payments ADD COLUMN {ddl}")
    practice_columns = {row["name"] for row in conn.execute("PRAGMA table_info(practice_attempts)").fetchall()}
    optional_practice_columns = {
        "reflection_text": "reflection_text TEXT",
        "ai_analysis_json": "ai_analysis_json TEXT",
        "ai_followups_json": "ai_followups_json TEXT",
        "ai_status": "ai_status TEXT",
    }
    for column, ddl in optional_practice_columns.items():
        if column not in practice_columns:
            conn.execute(f"ALTER TABLE practice_attempts ADD COLUMN {ddl}")
    bookmark_columns = {row["name"] for row in conn.execute("PRAGMA table_info(user_bookmarks)").fetchall()}
    optional_bookmark_columns = {
        "lesson": "lesson TEXT DEFAULT ''",
        "title": "title TEXT DEFAULT ''",
        "is_book_course": "is_book_course INTEGER DEFAULT 0",
        "updated_at": "updated_at TEXT",
    }
    for column, ddl in optional_bookmark_columns.items():
        if column not in bookmark_columns:
            conn.execute(f"ALTER TABLE user_bookmarks ADD COLUMN {ddl}")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_openid
        ON users(wechat_openid)
        WHERE wechat_openid IS NOT NULL
    """)
    conn.commit()
    conn.close()

init_db()

# ============================================================
# HELPERS
# ============================================================
def public_access_open() -> bool:
    return PUBLIC_ACCESS_MODE in {"open", "free", "public", "true", "1", "yes"}

def hash_password(password: str, salt: str = None) -> tuple:
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return h.hex(), salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    h, _ = hash_password(password, salt)
    return h == password_hash

def create_token(user_id: int, conn: sqlite3.Connection = None) -> str:
    token = secrets.token_urlsafe(48)
    expires = (datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)).isoformat()
    owns_conn = conn is None
    if owns_conn:
        conn = get_db()
    conn.execute("INSERT INTO user_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                 (user_id, token, expires))
    if owns_conn:
        conn.commit()
        conn.close()
    return token

def get_current_user(authorization: str = Header(None)) -> dict:
    user = user_from_authorization(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期")
    return user

def call_wechat_code2session(code: str) -> dict:
    if not WECHAT_MINIAPP_SECRET:
        raise HTTPException(status_code=500, detail="微信小程序密钥未配置")

    params = parse.urlencode({
        "appid": WECHAT_MINIAPP_APPID,
        "secret": WECHAT_MINIAPP_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    })
    url = f"https://api.weixin.qq.com/sns/jscode2session?{params}"
    try:
        with urlrequest.urlopen(url, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"微信登录服务暂不可用: {exc}")

def call_wechat_access_token() -> str:
    if not WECHAT_MINIAPP_SECRET:
        raise HTTPException(status_code=500, detail="微信小程序密钥未配置")

    params = parse.urlencode({
        "grant_type": "client_credential",
        "appid": WECHAT_MINIAPP_APPID,
        "secret": WECHAT_MINIAPP_SECRET,
    })
    url = f"https://api.weixin.qq.com/cgi-bin/token?{params}"
    try:
        with urlrequest.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"微信接口服务暂不可用: {exc}")
    if data.get("errcode"):
        raise HTTPException(status_code=400, detail=data.get("errmsg", "微信 access_token 获取失败"))
    token = data.get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="微信接口未返回 access_token")
    return token

def call_wechat_phone_number(code: str) -> dict:
    access_token = call_wechat_access_token()
    url = f"https://api.weixin.qq.com/wxa/business/getuserphonenumber?access_token={parse.quote(access_token)}"
    body = json.dumps({"code": code}, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"微信手机号接口暂不可用: {exc}")
    if data.get("errcode"):
        raise HTTPException(status_code=400, detail=data.get("errmsg", "微信手机号授权失败"))
    phone_info = data.get("phone_info") or {}
    phone = phone_info.get("phoneNumber") or phone_info.get("purePhoneNumber")
    if not phone:
        raise HTTPException(status_code=400, detail="微信未返回手机号")
    return phone_info

def normalize_phone(phone: str) -> str:
    value = (phone or "").strip()
    if not value:
        return ""
    compact = re.sub(r"[\s\-()]", "", value)
    if not re.fullmatch(r"\+?\d{6,20}", compact):
        raise HTTPException(status_code=400, detail="手机号格式不正确")
    return compact

def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "nickName": user["username"],
        "avatar": user["avatar"],
        "avatarUrl": user["avatar"],
        "phone": user.get("phone") or "",
        "hasPhone": bool(user.get("phone")),
        "plan": user["plan"],
        "planExpiresAt": user.get("plan_expires_at"),
    }

def parse_book_courses() -> list:
    if not BOOK_COURSES_HTML.exists():
        return []
    text = BOOK_COURSES_HTML.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\{n:(?P<n>\d+),t:"(?P<t>.*?)",a:"(?P<a>.*?)",d:(?P<d>\d+),c:"(?P<c>.*?)"\}'
    )
    courses = []
    expected_n = 1
    for match in pattern.finditer(text):
        raw_n = int(match.group("n"))
        if raw_n == expected_n:
            n = raw_n
        elif expected_n < raw_n <= 500 and raw_n - expected_n <= 3:
            while expected_n < raw_n:
                missing = book_record_from_page(expected_n)
                if missing:
                    courses.append(missing)
                expected_n += 1
            n = raw_n
        else:
            n = expected_n
        category = match.group("c")
        if category == "kk":
            category = "tech"
        courses.append({
            "n": n,
            "id": n,
            "title": match.group("t"),
            "t": match.group("t"),
            "author": match.group("a"),
            "a": match.group("a"),
            "difficulty": int(match.group("d")),
            "d": int(match.group("d")),
            "category": category,
            "c": category,
            "lesson": f"book{n}.html",
            "audio": f"audio/books/lesson{n}.mp3",
        })
        expected_n = n + 1
    while expected_n <= 500:
        missing = book_record_from_page(expected_n)
        if missing:
            courses.append(missing)
        expected_n += 1
    for course in courses:
        course.update(catalog_metadata(FRONTEND_DIR, 'book', int(course['n'])))
    return courses

def book_record_from_page(n: int) -> Optional[dict]:
    page = FRONTEND_DIR / f"book{n}.html"
    if not page.exists():
        return None
    text = page.read_text(encoding="utf-8", errors="ignore")
    h1 = re.search(r"<h1>(.*?)</h1>", text, re.S)
    h2 = re.search(r"<h2>(.*?)</h2>", text, re.S)
    title = re.sub(r"<.*?>", "", h1.group(1)).strip() if h1 else f"书目课程 {n}"
    subtitle = re.sub(r"<.*?>", "", h2.group(1)).strip() if h2 else ""
    author = subtitle.split(" · ", 1)[0].strip() if " · " in subtitle else ""
    return {
        "n": n,
        "id": n,
        "title": title,
        "t": title,
        "author": author,
        "a": author,
        "difficulty": 3,
        "d": 3,
        "category": "tech",
        "c": "tech",
        "lesson": f"book{n}.html",
        "audio": f"audio/books/lesson{n}.mp3",
    }

def get_wave(n: int) -> int:
    ranges = [
        (1, 62), (63, 92), (93, 117), (118, 147), (148, 177),
        (178, 207), (208, 238), (239, 268), (269, 298), (299, 328),
        (329, 336), (337, 363), (364, 390), (391, 418), (419, 445),
        (446, 472), (473, 500),
    ]
    for idx, (start, end) in enumerate(ranges, 1):
        if start <= n <= end:
            return idx
    return 0

def load_shop_product_map() -> dict:
    if not SHOP_PRODUCTS_JSON.exists():
        return {}
    try:
        data = json.loads(SHOP_PRODUCTS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def render_book_url_template(template: str, book_id: int, title: str, author: str) -> str:
    if not template:
        return ""
    clean_title = re.sub(r"^《|》$", "", title or "").strip()
    values = {
        "bookId": str(book_id),
        "id": str(book_id),
        "title": clean_title,
        "rawTitle": title or "",
        "author": author or "",
        "encodedTitle": parse.quote(clean_title or title or ""),
        "encodedAuthor": parse.quote(author or ""),
    }
    try:
        return template.format(**values)
    except Exception:
        return ""

def render_affiliate_template(template: str, book_id: int, title: str, author: str, product_id: str = "") -> str:
    if not template:
        return ""
    clean_title = re.sub(r"^《|》$", "", title or "").strip()
    values = {
        "bookId": str(book_id),
        "id": str(book_id),
        "title": clean_title,
        "rawTitle": title or "",
        "author": author or "",
        "encodedTitle": parse.quote(clean_title or title or ""),
        "encodedAuthor": parse.quote(author or ""),
        "productId": product_id or "",
    }
    try:
        return template.format(**values)
    except Exception:
        return ""

def generated_book_product(book_id: int, title: str, author: str) -> dict:
    direct_url = render_book_url_template(BOOK_AFFILIATE_URL_TEMPLATE, book_id, title, author)
    fallback_url = render_book_url_template(BOOK_AFFILIATE_FALLBACK_URL_TEMPLATE, book_id, title, author)
    url = direct_url or fallback_url
    direct_ready = bool(direct_url)
    purchase_ready = False
    return {
        "title": title,
        "author": author,
        "price": "去渠道查看",
        "affiliateUrl": url,
        "externalUrl": url,
        "openType": "clipboard",
        "source": os.getenv("BOOK_AFFILIATE_MODE", "jd_union") if direct_ready else "jd_search",
        "channel": os.getenv("BOOK_AFFILIATE_MODE", "jd_union") if direct_ready else "jd_search",
        "channelName": "联盟分成链接" if direct_ready else "京东搜索链接",
        "settlementMode": "cps" if direct_ready else "pending_affiliate",
        "commissionRate": os.getenv("BOOK_AFFILIATE_RATE", "待联盟后台结算" if direct_ready else "待配置"),
        "commissionReady": False,
        "purchaseEntryReady": purchase_ready,
        "purchaseEntryType": "affiliate" if direct_ready else "search",
        "linkGenerated": bool(url),
    }

def merge_product_config(base: dict, override: dict) -> dict:
    merged = dict(base or {})
    override = override or {}
    for key, value in override.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    # An explicit target replaces generated search aliases, not just one alias.
    target_keys = ("affiliateUrl", "externalUrl", "shortUrl", "url")
    if any(override.get(key) for key in target_keys):
        for key in target_keys:
            merged.pop(key, None)
        merged.update({key: override[key] for key in target_keys if override.get(key)})
        merged['channel'] = override.get('channel') or override.get('source') or 'custom'
        merged['source'] = override.get('source') or merged['channel']
        merged['purchaseEntryType'] = override.get('purchaseEntryType') or 'link'
    if any(override.get(key) for key in ('path', 'shopPath', 'businessType')) or (
        any(override.get(key) for key in ('productId', 'shopProductId'))
        and not any(override.get(key) for key in target_keys)
    ):
        if not any(override.get(key) for key in target_keys):
            for key in target_keys:
                merged.pop(key, None)
        merged['openType'] = override.get('openType') or ('business_view' if override.get('businessType') else 'mini_program')
        merged['channel'] = override.get('channel') or override.get('source') or 'wechat_shop'
        merged['source'] = override.get('source') or merged['channel']
        merged['purchaseEntryType'] = override.get('purchaseEntryType') or 'product'
    if not merged.get("externalUrl") and merged.get("affiliateUrl"):
        merged["externalUrl"] = merged["affiliateUrl"]
    if not merged.get("affiliateUrl") and merged.get("externalUrl"):
        merged["affiliateUrl"] = merged["externalUrl"]
    merged['purchaseEntryReady'] = product_has_purchase_entry(merged)
    merged['commissionReady'] = product_has_direct_commission(merged)
    return merged

def product_has_direct_commission(product: dict, config: Optional[dict] = None) -> bool:
    # Configuration readiness is not proof of a sale or settled commission.
    return bool(product_has_purchase_entry(product, config)
                and product.get('settlementMode') in ('cps', 'commission', 'affiliate', 'wechat_shop', 'direct')
                and re.fullmatch(r'(?:0|[1-9]\d?)(?:\.\d+)?%|100(?:\.0+)?%', str(product.get('commissionRate') or '')))

def product_has_purchase_entry(product: dict, config: Optional[dict] = None) -> bool:
    return book_open_action(0, product, config or {}).get('canBuy') is True

def affiliate_programs() -> list[dict]:
    return [
        {
            "key": "wechat_shop",
            "name": "微信小店/小商店",
            "settlement": "店铺后台结算或分销结算",
            "openTypes": ["mini_program"],
            "recommended": True,
            "notes": "本轮仅支持已校验的商家小程序及具体商品路径，不支持 business_view。需核验商家授权；发货与售后由实际商家负责，跳转不代表支付成功。",
        },
        {
            "key": "jd_union",
            "name": "京东联盟",
            "settlement": "CPS 分佣",
            "openTypes": ["clipboard"],
            "recommended": True,
            "notes": "本轮仅支持复制已校验的 HTTPS 链接，不支持 web_view。搜索链接不是真实商品；推广授权需核验，发货与售后由实际商家负责，分佣以渠道核验结算为准。",
        },
        {
            "key": "dangdang_affiliate",
            "name": "当当/图书联盟",
            "settlement": "CPS 分佣",
            "openTypes": ["clipboard"],
            "recommended": False,
            "notes": "本轮仅支持复制已校验的 HTTPS 链接；需核验推广授权及具体商品，发货与售后由实际商家负责。",
        },
        {
            "key": "taobao_union",
            "name": "淘宝联盟",
            "settlement": "CPS 分佣",
            "openTypes": ["clipboard"],
            "recommended": False,
            "notes": "本轮仅支持复制已校验的 HTTPS 链接，不支持纯文本淘口令；短链不能单独证明商品身份，发货与售后由实际商家负责。",
        },
        {
            "key": "custom",
            "name": "出版社/书商直连",
            "settlement": "协议分成",
            "openTypes": ["mini_program", "clipboard"],
            "recommended": False,
            "notes": "本轮仅支持已校验的具体商品小程序路径或复制 HTTPS 链接；合作授权须人工核验，发货与售后由实际商家负责。",
        },
    ]

def shop_config(courses: Optional[list] = None, product_map: Optional[dict] = None) -> dict:
    app_id = os.getenv("WECHAT_SHOP_APPID", "")
    business_type = os.getenv("WECHAT_SHOP_BUSINESS_TYPE", "")
    affiliate_mode = os.getenv("BOOK_AFFILIATE_MODE", "wechat_shop" if app_id or business_type else "jd_search")
    if courses is None:
        courses = parse_book_courses()
    total_books = len(courses)
    if product_map is None:
        product_map = load_shop_product_map()
    direct_template_ready = bool(BOOK_AFFILIATE_URL_TEMPLATE)
    configured_direct = 0
    generated_links = 0
    purchase_entries = 0
    action_config = {
        'appId': app_id, 'businessType': business_type,
        'homePath': os.getenv('WECHAT_SHOP_HOME_PATH', 'pages/index/index'),
        'productPathTemplate': os.getenv('WECHAT_SHOP_PRODUCT_PATH_TEMPLATE', ''),
        'queryString': os.getenv('WECHAT_SHOP_QUERY_STRING', ''),
    }
    for course in courses:
        base = generated_book_product(int(course["n"]), course["title"], course.get("author", ""))
        product = merge_product_config(base, product_map.get(str(course["n"]), {}) if isinstance(product_map, dict) else {})
        generated_links += int(book_open_action(int(course['n']), product, action_config)['canOpen'])
        purchase_entries += int(product_has_purchase_entry(product, action_config))
        configured_direct += int(product_has_direct_commission(product, action_config))
    direct_commission_ready = configured_direct >= total_books and total_books > 0
    purchase_entry_ready = purchase_entries >= total_books and total_books > 0
    return {
        "enabled": generated_links > 0,
        "mode": os.getenv("WECHAT_SHOP_MODE", "mini_program" if app_id else ("affiliate_template" if direct_template_ready else "search_fallback")),
        "affiliateMode": affiliate_mode,
        "commissionTrackingEnabled": configured_direct > 0,
        "readinessEvidence": "configuration_only",
        "purchaseEntryReady": purchase_entry_ready,
        "purchaseEntryBooks": purchase_entries,
        "directCommissionReady": direct_commission_ready,
        "directCommissionBooks": configured_direct,
        "linkCoverage": {"linked": generated_links, "total": total_books},
        "appId": app_id,
        "homePath": os.getenv("WECHAT_SHOP_HOME_PATH", "pages/index/index"),
        "productPathTemplate": os.getenv("WECHAT_SHOP_PRODUCT_PATH_TEMPLATE", ""),
        "businessType": business_type,
        "queryString": os.getenv("WECHAT_SHOP_QUERY_STRING", ""),
        "message": f"已配置{purchase_entries}/{total_books}个商品入口；搜索链接不计入商品，配置不代表成交或分佣到账",
        "affiliatePrograms": affiliate_programs(),
    }

def shop_book_detail(book_id: int, course: Optional[dict] = None, product_map: Optional[dict] = None) -> dict:
    if course is None:
        course = next((item for item in parse_book_courses() if int(item.get("n", 0)) == int(book_id)), None)
    if not course or int(course.get("n", 0)) != int(book_id):
        raise HTTPException(404, "图书不存在")
    if product_map is None:
        product_map = load_shop_product_map()
    configured = product_map.get(str(book_id), {}) if isinstance(product_map, dict) else {}
    title = configured.get("title") or (course or {}).get("title") or f"图书 {book_id}"
    author = configured.get("author") or (course or {}).get("author") or ""
    product = merge_product_config(generated_book_product(int(book_id), title, author), configured)
    price = product.get("price", "")
    price_text = f"¥{price}" if re.match(r"^\d", str(price)) else str(price or "去渠道查看")
    return {
        "book_id": int(book_id),
        "title": title,
        "author": author,
        "price": str(price or ""),
        "price_text": price_text,
        "product": product,
    }

def product_channel(product: dict) -> str:
    return str(product.get("channel") or product.get("source") or "wechat_shop")

def product_target_url(product: dict) -> str:
    return str(
        product.get("affiliateUrl")
        or product.get("externalUrl")
        or product.get("shortUrl")
        or product.get("url")
        or ""
    )

def safe_commerce_url(value: str) -> str:
    value = str(value or '')
    if not value or any(ord(c) <= 32 or ord(c) == 127 or c in '\\{}' for c in value):
        return ''
    try:
        url = parse.urlsplit(value)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.port not in (None, 443):
            return ''
    except ValueError:
        return ''
    return value

def commerce_link_kind(url: str, product: dict) -> str:
    parsed = parse.urlsplit(url)
    keys = {key.lower() for key, _ in parse.parse_qsl(parsed.query)}
    if ('search' in parsed.hostname.lower() or 'search' in parsed.path.lower()
            or keys.intersection({'keyword', 'q', 'query', 'searchkey'})
            or product.get('purchaseEntryType') == 'search'
            or str(product.get('channel') or product.get('source') or '').endswith('_search')):
        return 'search'
    known_id = ''
    if parsed.hostname == 'item.jd.com' and re.fullmatch(r'/\d+\.html', parsed.path):
        known_id = parsed.path[1:-5]
    elif parsed.hostname in ('item.taobao.com', 'detail.tmall.com'):
        candidate = dict(parse.parse_qsl(parsed.query)).get('id', '')
        known_id = candidate if candidate.isdigit() else ''
    product_id = str(product.get('productId') or product.get('shopProductId') or '')
    if known_id and product_id and known_id != product_id:
        return 'unavailable'
    return 'configured_product' if known_id or re.fullmatch(r'[A-Za-z0-9_-]+', product_id) else 'unverified_link'

def public_merchant_info(product: dict) -> dict:
    def public_text(value, limit=500):
        if not isinstance(value, str):
            return ''
        value = value.strip()
        # Never surface local document paths or the private authorization reference.
        reference = product.get('authorizationReference')
        if ((isinstance(reference, str) and reference and reference in value)
                or re.search(r'file:|(?:^|\s)(?:~[/\\]|[A-Za-z]:\\|/(?:Users|home|root|var|tmp|etc|private|mnt)/)', value, re.I)):
            return ''
        return value[:limit]

    after_sales = product.get('afterSales')
    if isinstance(after_sales, str):
        after_sales = {'description': after_sales}
    if not isinstance(after_sales, dict):
        after_sales = {}
    policy_url = safe_commerce_url(public_text(after_sales.get('policyUrl'), 2000))
    if policy_url and any(key.lower() in ('token', 'signature', 'key', 'authorization')
                          for key, _ in parse.parse_qsl(parse.urlsplit(policy_url).query)):
        policy_url = ''
    status = product.get('authorizationStatus')
    if status not in ('confirmed', 'unverified', 'expired', 'revoked'):
        status = 'unverified'
    return {
        'merchantName': public_text(product.get('merchantName'), 200),
        'afterSales': {
            'contact': public_text(after_sales.get('contact'), 200),
            'description': public_text(after_sales.get('description')),
            'policyUrl': policy_url,
        },
        'authorizationStatus': status,
    }

def commerce_authorization_ready(product: dict) -> bool:
    info = public_merchant_info(product)
    reference = product.get('authorizationReference')
    return bool(info['authorizationStatus'] == 'confirmed'
                and isinstance(reference, str) and reference.strip()
                and info['merchantName']
                and (info['afterSales']['contact'] or info['afterSales']['policyUrl']))

def book_open_action(book_id: int, product: dict, config: dict) -> dict:
    channel = product_channel(product)
    app_id = str(product.get("miniProgramAppId") or product.get("appId") or config.get("appId") or "")
    template = str(product.get("productPathTemplate") or config.get("productPathTemplate") or "")
    product_id = str(product.get("productId") or product.get("shopProductId") or "")
    path = str(product.get("path") or product.get("shopPath") or "")
    open_type = str(product.get('openType') or '')
    target_url = product_target_url(product)
    authorized = commerce_authorization_ready(product)
    no_action = {"type": "none", "channel": channel, "target": "", "entryKind": "unavailable",
                 "canOpen": False, "canBuy": False, "message": "商品入口配置不完整或不合法"}
    private_reference = product.get('authorizationReference')
    if isinstance(private_reference, str) and private_reference and any(
        private_reference in value for value in (target_url, path)
    ):
        return no_action
    if open_type not in ('', 'mini_program', 'business_view', 'clipboard', 'web_view'):
        return no_action
    if open_type in ('clipboard', 'web_view') or (target_url and not open_type):
        target_url = safe_commerce_url(target_url)
        if not target_url:
            return no_action
        kind = commerce_link_kind(target_url, product)
        if kind == 'unavailable':
            return no_action
        return {"type": open_type or "clipboard", "channel": channel, "url": target_url,
                "target": target_url, "entryKind": kind, "canOpen": True,
                "canBuy": kind == 'configured_product' and authorized and open_type != 'web_view',
                "message": "书名搜索，不是已确认商品" if kind == 'search' else "打开配置链接；商品及支付状态以渠道为准"}
    if not path and product_id and template and '{productId}' in template:
        path = template.replace("{productId}", parse.quote(product_id, safe=''))
    if open_type in ('', 'mini_program') and app_id:
        path = path or str(config.get("homePath") or "")
        valid_path = re.fullmatch(r'/?pages/[A-Za-z0-9_/-]+(?:\?[^\s{}\\#]+)?', path)
        if not re.fullmatch(r'wx[0-9a-fA-F]{16}', app_id) or not valid_path or '..' in path:
            return no_action
        parsed_path = parse.urlsplit(path)
        target_ids = [parse.unquote(part) for part in parsed_path.path.split('/')]
        target_ids += [value for _, value in parse.parse_qsl(parsed_path.query)]
        specific = bool(re.fullmatch(r'[A-Za-z0-9_-]+', product_id) and product_id in target_ids)
        if product_id and (product.get('path') or product.get('shopPath') or template) and not specific:
            return no_action
        return {
            "type": "mini_program",
            "channel": channel,
            "appId": app_id,
            "path": path,
            "target": f"{app_id}:{path}",
            "entryKind": "configured_product" if specific else "store",
            "canOpen": True,
            "canBuy": specific and authorized,
            "message": "跳转微信小店或渠道小程序完成购买",
        }

    # No verified businessType integration exists; configuration cannot enable it.
    if open_type == 'business_view' or product.get('businessType') or config.get('businessType'):
        return {**no_action, 'message': '交易组件尚未验证，暂不提供购买入口'}

    return no_action

def record_shop_lead(user: Optional[dict], book_id: int, source: str = "miniapp", target: str = "") -> None:
    detail = shop_book_detail(book_id)
    action = book_open_action(book_id, detail['product'], shop_config())
    if not action.get('canOpen'):
        raise HTTPException(409, "图书入口尚未配置")
    target = action['target']
    conn = get_db()
    conn.execute(
        "INSERT INTO shop_clicks (user_id, book_id, source, target) VALUES (?, ?, ?, ?)",
        (user["id"] if user else None, book_id, source or "miniapp", (target or "")[:500])
    )
    if user and book_id:
        detail = shop_book_detail(book_id)
        existing = conn.execute("""
            SELECT id, status FROM book_purchases
            WHERE user_id=? AND book_id=?
            ORDER BY CASE WHEN status='paid' THEN 0 ELSE 1 END, purchased_at DESC
            LIMIT 1
        """, (user["id"], book_id)).fetchone()
        if not existing:
            conn.execute("""
                INSERT INTO book_purchases (
                    user_id, book_id, title, author, price, price_text,
                    quantity, status, source, target, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, 'pending', ?, ?, ?)
            """, (
                user["id"],
                book_id,
                detail["title"],
                detail["author"],
                detail["price"],
                detail["price_text"],
                source or "miniapp",
                (target or "")[:500],
                json.dumps(detail.get("product") or {}, ensure_ascii=False),
            ))
        elif existing["status"] != "paid":
            conn.execute("""
                UPDATE book_purchases
                SET source=?, target=?, updated_at=datetime('now')
                WHERE id=?
            """, (source or "miniapp", (target or "")[:500], existing["id"]))
    conn.commit()
    conn.close()

def purchase_public(row) -> dict:
    data = dict(row)
    status = data.get("status") or "pending"
    return {
        "id": data.get("id"),
        "bookId": data.get("book_id"),
        "title": data.get("title"),
        "author": data.get("author") or "",
        "price": data.get("price") or "",
        "priceText": data.get("price_text") or data.get("price") or "价格待同步",
        "quantity": data.get("quantity") or 1,
        "status": status,
        "statusLabel": "历史支付声明，尚未核验" if status == "paid" else "已点击，支付待确认",
        # No trusted merchant callback is connected. Never trust legacy status alone.
        "paymentVerified": False,
        "paymentEvidence": "reported_unverified" if status == "paid" else "interaction_only",
        "orderNo": data.get("order_no") or "",
        "source": data.get("source") or "",
        "target": data.get("target") or "",
        "purchasedAt": None,
        "interactionAt": data.get("purchased_at"),
        "updatedAt": data.get("updated_at"),
    }

def course_record_from_markdown(path: Path) -> Optional[dict]:
    parts = path.stem.split("-", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    cid = int(parts[0])
    return {
        "id": cid,
        "n": cid,
        "title": parts[1],
        "filename": path.name,
        "file": f"courses/{path.name}",
        "lesson": f"lesson{cid}.html",
        "size": path.stat().st_size,
        **catalog_metadata(FRONTEND_DIR, 'core', cid),
    }

def core_course_title(course_id: int) -> str:
    if COURSES_DIR.exists():
        candidates = list(COURSES_DIR.glob(f"{course_id:02d}-*.md")) + list(COURSES_DIR.glob(f"{course_id}-*.md"))
        if candidates:
            record = course_record_from_markdown(sorted(candidates)[0])
            if record:
                return record["title"]
    return f"第 {course_id} 课"

def book_course_title(book_id: int) -> str:
    course = next((item for item in parse_book_courses() if int(item.get("n", 0)) == int(book_id)), None)
    return (course or {}).get("title") or f"书目课程 {book_id}"

def course_ref_from_payload(course_id: int, lesson: str = "", is_book_course: bool = False) -> int:
    lesson = lesson or ""
    meta = None
    if lesson:
        try:
            meta = resolve_lesson(lesson)
        except HTTPException:
            meta = None
    if meta:
        return int(meta["courseRef"])
    if is_book_course and course_id < 10000:
        return 10000 + int(course_id)
    return int(course_id)

def course_public_from_ref(course_ref: int, title: str = "", lesson: str = "", is_book_course: Optional[bool] = None, user: Optional[dict] = None) -> dict:
    course_ref = int(course_ref)
    inferred_book = course_ref >= 10000
    book_course = inferred_book or bool(is_book_course)
    if book_course:
        book_id = course_ref - 10000 if inferred_book else course_ref
        safe_lesson = lesson or f"book{book_id}.html"
        safe_title = title or book_course_title(book_id)
        accessible = can_access_book_course(user, book_id) if user else False
        free = public_access_open() or book_id in FREE_BOOK_COURSES
        return {
            "courseId": book_id,
            "courseRef": 10000 + book_id,
            "lesson": safe_lesson,
            "title": safe_title,
            "isBookCourse": True,
            "type": "book",
            "typeLabel": "书目课程",
            "free": free,
            "accessible": accessible,
            "locked": not accessible,
        }
    core_id = course_ref
    safe_lesson = lesson or f"lesson{core_id}.html"
    safe_title = title or core_course_title(core_id)
    accessible = can_access_core_course(user, core_id) if user else False
    free = public_access_open() or core_id in FREE_CORE_COURSES
    return {
        "courseId": core_id,
        "courseRef": core_id,
        "lesson": safe_lesson,
        "title": safe_title,
        "isBookCourse": False,
        "type": "core",
        "typeLabel": "主干课程",
        "free": free,
        "accessible": accessible,
        "locked": not accessible,
    }

def safe_json_loads(raw, fallback):
    try:
        if not raw:
            return fallback
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback

def row_to_dict(row) -> Optional[dict]:
    return dict(row) if row else None

def user_from_authorization(authorization: Optional[str]) -> Optional[dict]:
    if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    conn = get_db()
    row = conn.execute("""
        SELECT u.* FROM users u
        JOIN user_tokens t ON u.id = t.user_id
        WHERE t.token = ? AND t.expires_at > datetime('now') AND u.is_active = 1
    """, (token,)).fetchone()
    conn.close()
    return row_to_dict(row)


def request_ip_hash(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    raw_ip = forwarded.split(",", 1)[0].strip() if forwarded else ""
    if not raw_ip and request.client:
        raw_ip = request.client.host or ""
    if not raw_ip:
        return ""
    return hashlib.sha256((raw_ip + SECRET_KEY[:16]).encode("utf-8")).hexdigest()[:24]

def record_launch_event(req, request: Request, user: Optional[dict] = None) -> dict:
    event_type = re.sub(r"[^a-zA-Z0-9_:-]", "", (req.event or "event").strip().lower())[:40] or "event"
    payload = {
        "extra": req.extra or {},
        "query": dict(parse.parse_qsl(parse.urlsplit(req.path or "").query)) if req.path else {},
    }
    conn = get_db()
    conn.execute(
        """
        INSERT INTO launch_events (
            user_id, event_type, source, channel, campaign, path, referrer,
            target, plan, book_id, order_no, amount_fen, ip_hash, user_agent, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user.get("id") if user else None,
            event_type,
            (req.source or "")[:80],
            (req.channel or "")[:80],
            (req.campaign or "")[:120],
            (req.path or "")[:500],
            (req.referrer or "")[:500],
            (req.target or "")[:500],
            (req.plan or "")[:80],
            req.book_id,
            (req.order_no or "")[:80],
            req.amount_fen,
            request_ip_hash(request),
            (request.headers.get("user-agent") or "")[:300],
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    return {"success": True, "event": event_type}

def manual_metric_count(value, maximum: int = 5000) -> int:
    try:
        count = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(count, maximum))

def manual_metric_created_at(date_value: str = "") -> str:
    day = parse_promo_date(date_value).date()
    return datetime.combine(day, datetime.min.time()).replace(hour=4).strftime("%Y-%m-%d %H:%M:%S")

def insert_manual_launch_metrics(req, request: Request) -> dict:
    platform_keys = {"xhs", "douyin", "wechat_channels"}
    platform = (req.platform or "xhs").strip().lower()
    if platform not in platform_keys:
        platform = "xhs"
    event_counts = {
        "view": manual_metric_count(req.views, 50000),
        "cta_click": manual_metric_count(req.conversionClicks, 10000),
        "purchase_intent": manual_metric_count(req.purchaseIntents, 2000),
        "manual_purchase": manual_metric_count(req.purchases, 2000),
        "book_click": manual_metric_count(req.bookClicks, 10000),
        "publish_task": manual_metric_count(req.publishTasks, 100),
        "promo_review": manual_metric_count(req.reviews, 100),
    }
    total = sum(event_counts.values())
    batch_id = uuid.uuid4().hex[:16]
    created_at = manual_metric_created_at(req.date or "")
    campaign = (req.campaign or "").strip()[:120]
    if not campaign:
        try:
            start = promo_week_start().date()
            day = parse_promo_date(req.date or "").date()
            offset = max(0, (day - start).days)
            campaign = f"week{(offset // 7) + 1}_day{(offset % 7) + 1}"
        except Exception:
            campaign = "manual"
    raw = json.dumps({
        "extra": {
            "manual": True,
            "batchId": batch_id,
            "counts": event_counts,
            "note": (req.note or "")[:300],
        },
        "query": {},
    }, ensure_ascii=False)
    rows = []
    for event_type, count in event_counts.items():
        for _ in range(count):
            rows.append((
                None,
                event_type,
                platform,
                platform,
                campaign,
                "/growth-sprint.html",
                "",
                "manual_metrics",
                "",
                None,
                "",
                None,
                request_ip_hash(request),
                (request.headers.get("user-agent") or "")[:300],
                raw,
                created_at,
            ))
    if rows:
        conn = get_db()
        conn.executemany(
            """
            INSERT INTO launch_events (
                user_id, event_type, source, channel, campaign, path, referrer,
                target, plan, book_id, order_no, amount_fen, ip_hash, user_agent, raw_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()
    return {
        "success": True,
        "batchId": batch_id,
        "inserted": total,
        "platform": platform,
        "campaign": campaign,
        "date": parse_promo_date(req.date or "").strftime("%Y-%m-%d"),
        "counts": event_counts,
    }

MANUAL_METRIC_FIELD_ALIASES = {
    "date": {"date", "日期", "day", "发布时间", "统计日期"},
    "platform": {"platform", "平台", "source", "渠道", "来源"},
    "views": {"views", "浏览", "浏览量", "播放", "播放量", "曝光", "曝光量", "阅读量", "观看量"},
    "conversionClicks": {"conversionclicks", "clicks", "点击", "转化点击", "链接点击", "主页点击", "私信点击"},
    "purchaseIntents": {"purchaseintents", "intents", "购买意向", "意向", "私信", "咨询", "留资", "线索"},
    "purchases": {"purchases", "成交", "购买", "外部成交", "已支付", "订单"},
    "bookClicks": {"bookclicks", "图书点击", "书目点击", "购书点击"},
    "publishTasks": {"publishtasks", "发布", "发布打卡", "发布数"},
    "reviews": {"reviews", "复盘", "复盘数"},
    "note": {"note", "备注", "说明"},
    "campaign": {"campaign", "活动", "推广批次"},
}

def canonical_manual_metric_field(header: str) -> str:
    normalized = normalize_header_name(header)
    for field, aliases in MANUAL_METRIC_FIELD_ALIASES.items():
        if normalized in {normalize_header_name(alias) for alias in aliases}:
            return field
    return header.strip()

def normalize_platform_value(value: str) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "小红书": "xhs",
        "xiaohongshu": "xhs",
        "red": "xhs",
        "xhs": "xhs",
        "抖音": "douyin",
        "douyin": "douyin",
        "tiktok": "douyin",
        "微信视频号": "wechat_channels",
        "视频号": "wechat_channels",
        "wechat": "wechat_channels",
        "wechat_channels": "wechat_channels",
        "channels": "wechat_channels",
    }
    return mapping.get(raw, raw if raw in {"xhs", "douyin", "wechat_channels"} else "xhs")

def parse_manual_metrics_rows(content: str) -> list:
    text = (content or "").strip().lstrip("\ufeff")
    if not text:
        return []
    raw_rows: list[dict] = []
    if text[0] in "[{":
        data = json.loads(text)
        if isinstance(data, list):
            raw_rows = [row for row in data if isinstance(row, dict)]
        elif isinstance(data, dict) and isinstance(data.get("rows"), list):
            raw_rows = [row for row in data.get("rows") if isinstance(row, dict)]
    else:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames:
            header_map = {header: canonical_manual_metric_field(header) for header in reader.fieldnames}
            for raw in reader:
                row = {}
                for header, value in (raw or {}).items():
                    field = header_map.get(header, header)
                    if value not in (None, ""):
                        row[field] = str(value).strip()
                if any(str(v).strip() for v in row.values()):
                    raw_rows.append(row)
    rows = []
    for raw in raw_rows:
        rows.append(ManualLaunchMetricsReq(
            date=str(raw.get("date") or ""),
            platform=normalize_platform_value(raw.get("platform") or raw.get("source") or ""),
            campaign=str(raw.get("campaign") or ""),
            views=manual_metric_count(raw.get("views"), 50000),
            conversionClicks=manual_metric_count(raw.get("conversionClicks"), 10000),
            purchaseIntents=manual_metric_count(raw.get("purchaseIntents"), 2000),
            purchases=manual_metric_count(raw.get("purchases"), 2000),
            bookClicks=manual_metric_count(raw.get("bookClicks"), 10000),
            publishTasks=manual_metric_count(raw.get("publishTasks"), 100),
            reviews=manual_metric_count(raw.get("reviews"), 100),
            note=str(raw.get("note") or ""),
        ))
    return rows

def insert_manual_launch_metrics_batch(rows: list, request: Request) -> dict:
    rows = rows[:300]
    inserted = 0
    details = []
    for row in rows:
        result = insert_manual_launch_metrics(row, request)
        inserted += int(result.get("inserted") or 0)
        details.append({
            "date": result.get("date"),
            "platform": result.get("platform"),
            "inserted": result.get("inserted"),
            "counts": result.get("counts"),
        })
    return {
        "success": True,
        "rows": len(rows),
        "inserted": inserted,
        "details": details[:20],
    }

def require_payment_admin_token(request: Request, message: str = "缺少运营后台权限") -> None:
    token = request.headers.get("X-Payment-Admin-Token", "")
    if not PAYMENT_ADMIN_TOKEN or token != PAYMENT_ADMIN_TOKEN:
        raise HTTPException(403, message)

def sensitive_file_check(path: str, executable: bool = False) -> dict:
    if not path:
        return {"pathConfigured": False, "exists": False, "isFile": False, "readable": False, "executable": None}
    file_path = Path(path)
    return {
        "pathConfigured": True,
        "path": path,
        "exists": file_path.exists(),
        "isFile": file_path.is_file(),
        "readable": os.access(path, os.R_OK),
        "executable": os.access(path, os.X_OK) if executable else None,
        "mode": oct(file_path.stat().st_mode & 0o777) if file_path.exists() else "",
    }

PAYMENT_ENV_KEYS = [
    "WECHAT_PAY_MCHID",
    "WECHAT_PAY_CERT_SERIAL_NO",
    "WECHAT_PAY_PRIVATE_KEY_PATH",
    "WECHAT_PAY_API_V3_KEY",
    "WECHAT_PAY_NOTIFY_URL",
]

def payment_env_values() -> dict:
    values = {key: os.getenv(key, "") for key in PAYMENT_ENV_KEYS if os.getenv(key, "")}
    values.update(parse_env_file(LEGACY_PAYMENT_ENV_PATH))
    values.update(parse_env_file(PAYMENT_ENV_PATH))
    return values

def payment_runtime_config() -> dict:
    values = payment_env_values()
    return {
        "mchid": values.get("WECHAT_PAY_MCHID", ""),
        "certSerialNo": values.get("WECHAT_PAY_CERT_SERIAL_NO", ""),
        "privateKeyPath": values.get("WECHAT_PAY_PRIVATE_KEY_PATH", ""),
        "apiV3Key": values.get("WECHAT_PAY_API_V3_KEY", ""),
        "notifyUrl": values.get("WECHAT_PAY_NOTIFY_URL", WECHAT_PAY_NOTIFY_URL),
        "envFile": str(PAYMENT_ENV_PATH),
        "legacyEnvFile": str(LEGACY_PAYMENT_ENV_PATH),
    }

def normalize_private_key_pem(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.replace("\\n", "\n")
    if "-----BEGIN" not in cleaned or "-----END" not in cleaned or "PRIVATE KEY" not in cleaned:
        raise HTTPException(400, "商户私钥必须是 PEM 格式，包含 BEGIN/END PRIVATE KEY")
    return cleaned.rstrip() + "\n"

def validate_payment_config_updates(updates: dict) -> dict:
    mchid = str(updates.get("WECHAT_PAY_MCHID") or "").strip()
    serial = str(updates.get("WECHAT_PAY_CERT_SERIAL_NO") or "").strip()
    key_path = str(updates.get("WECHAT_PAY_PRIVATE_KEY_PATH") or "").strip()
    api_v3_key = str(updates.get("WECHAT_PAY_API_V3_KEY") or "").strip()
    notify_url = str(updates.get("WECHAT_PAY_NOTIFY_URL") or "").strip()
    if mchid and not re.fullmatch(r"[0-9A-Za-z_-]{4,64}", mchid):
        raise HTTPException(400, "微信支付商户号格式不正确")
    if serial and len(serial) > 128:
        raise HTTPException(400, "API证书序列号过长")
    if key_path and len(key_path) > 300:
        raise HTTPException(400, "商户私钥路径过长")
    if api_v3_key and len(api_v3_key.encode("utf-8")) != 32:
        raise HTTPException(400, "微信支付 APIv3 Key 必须是 32 字节")
    if notify_url and not notify_url.startswith("https://"):
        raise HTTPException(400, "支付回调地址必须以 https:// 开头")
    return {
        "WECHAT_PAY_MCHID": mchid,
        "WECHAT_PAY_CERT_SERIAL_NO": serial,
        "WECHAT_PAY_PRIVATE_KEY_PATH": key_path,
        "WECHAT_PAY_API_V3_KEY": api_v3_key,
        "WECHAT_PAY_NOTIFY_URL": notify_url,
    }

def write_payment_config(payload: dict) -> dict:
    existing = payment_env_values()
    private_key_pem = normalize_private_key_pem(payload.get("privateKeyPem") or "")
    private_key_path = str(payload.get("privateKeyPath") or "").strip()
    if private_key_pem and not private_key_path:
        private_key_path = str(PAYMENT_PRIVATE_KEY_PATH)
    updates = {
        "WECHAT_PAY_MCHID": payload.get("mchid") or existing.get("WECHAT_PAY_MCHID", ""),
        "WECHAT_PAY_CERT_SERIAL_NO": payload.get("certSerialNo") or existing.get("WECHAT_PAY_CERT_SERIAL_NO", ""),
        "WECHAT_PAY_PRIVATE_KEY_PATH": private_key_path or existing.get("WECHAT_PAY_PRIVATE_KEY_PATH", ""),
        "WECHAT_PAY_API_V3_KEY": payload.get("apiV3Key") or existing.get("WECHAT_PAY_API_V3_KEY", ""),
        "WECHAT_PAY_NOTIFY_URL": payload.get("notifyUrl") or existing.get("WECHAT_PAY_NOTIFY_URL") or WECHAT_PAY_NOTIFY_URL,
    }
    if payload.get("clearPrivateKey"):
        updates["WECHAT_PAY_PRIVATE_KEY_PATH"] = ""
    updates = validate_payment_config_updates(updates)
    if private_key_pem and updates["WECHAT_PAY_PRIVATE_KEY_PATH"]:
        key_path = Path(updates["WECHAT_PAY_PRIVATE_KEY_PATH"])
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(private_key_pem, encoding="utf-8")
        os.chmod(key_path, 0o600)
    merged = dict(existing)
    merged.update(updates)
    lines = [
        "# Kangbo Academy WeChat Pay runtime configuration",
        "# Generated by protected /api/payment/config. Do not commit this file.",
    ]
    for key in PAYMENT_ENV_KEYS:
        if key in merged:
            lines.append(f"{key}={shell_single_quote(merged.get(key, ''))}")
    for key in sorted(set(merged) - set(PAYMENT_ENV_KEYS)):
        lines.append(f"{key}={shell_single_quote(merged.get(key, ''))}")
    PAYMENT_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    PAYMENT_ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.chmod(PAYMENT_ENV_PATH, 0o600)
    config = payment_runtime_config()
    return {
        "envFile": str(PAYMENT_ENV_PATH),
        "legacyEnvFile": str(LEGACY_PAYMENT_ENV_PATH),
        "mchidConfigured": bool(config["mchid"]),
        "serialConfigured": bool(config["certSerialNo"]),
        "privateKeyConfigured": bool(config["privateKeyPath"]),
        "privateKeyFileExists": Path(config["privateKeyPath"]).exists() if config["privateKeyPath"] else False,
        "apiV3KeyConfigured": bool(config["apiV3Key"]),
        "notifyUrl": config["notifyUrl"],
    }

def payment_config() -> dict:
    runtime = payment_runtime_config()
    private_key_path = runtime["privateKeyPath"]
    private_key_path_configured = bool(private_key_path)
    private_key_file_exists = Path(private_key_path).exists() if private_key_path else False
    ready = all([
        runtime["mchid"],
        runtime["certSerialNo"],
        private_key_path_configured,
        private_key_file_exists,
        runtime["apiV3Key"],
        runtime["notifyUrl"],
    ])
    missing = []
    if not runtime["mchid"]:
        missing.append("WECHAT_PAY_MCHID")
    if not runtime["certSerialNo"]:
        missing.append("WECHAT_PAY_CERT_SERIAL_NO")
    if not private_key_path_configured:
        missing.append("WECHAT_PAY_PRIVATE_KEY_PATH")
    elif not private_key_file_exists:
        missing.append("WECHAT_PAY_PRIVATE_KEY_FILE")
    if not runtime["apiV3Key"]:
        missing.append("WECHAT_PAY_API_V3_KEY")
    if not runtime["notifyUrl"]:
        missing.append("WECHAT_PAY_NOTIFY_URL")
    required = [
        {"key": "WECHAT_PAY_MCHID", "name": "微信支付商户号", "configured": bool(runtime["mchid"]), "sensitive": False},
        {"key": "WECHAT_PAY_CERT_SERIAL_NO", "name": "API证书序列号", "configured": bool(runtime["certSerialNo"]), "sensitive": False},
        {"key": "WECHAT_PAY_PRIVATE_KEY_PATH", "name": "商户API私钥文件路径", "configured": private_key_path_configured, "fileExists": private_key_file_exists, "sensitive": True},
        {"key": "WECHAT_PAY_API_V3_KEY", "name": "APIv3密钥", "configured": bool(runtime["apiV3Key"]), "sensitive": True},
        {"key": "WECHAT_PAY_NOTIFY_URL", "name": "支付回调地址", "configured": bool(runtime["notifyUrl"]), "sensitive": False},
    ]
    return {
        "provider": "wechat",
        "ready": bool(ready),
        "mchidConfigured": bool(runtime["mchid"]),
        "serialConfigured": bool(runtime["certSerialNo"]),
        "privateKeyConfigured": private_key_path_configured,
        "privateKeyFileExists": private_key_file_exists,
        "apiV3KeyConfigured": bool(runtime["apiV3Key"]),
        "notifyUrl": runtime["notifyUrl"],
        "envFile": runtime["envFile"],
        "legacyEnvFile": runtime["legacyEnvFile"],
        "privateKeyPath": private_key_path if private_key_path_configured else "",
        "missing": missing,
        "required": required,
        "docs": {
            "createOrder": "/api/payment/create",
            "notify": "/api/payment/wechat/notify",
            "status": "/api/payment/status/{order_no}",
            "plans": "/api/membership/plans",
        },
        "message": "微信支付商户配置完成后可直接发起 JSAPI 支付" if ready else "请配置微信支付商户号、API证书序列号、商户私钥和 APIv3 Key",
    }

def payment_service_commands() -> dict:
    return {
        "createFiles": "\n".join([
            "sudo install -d -m 750 -o ubuntu -g ubuntu /var/www/kangboacademy/data",
            "sudo nano /var/www/kangboacademy/data/apiclient_key.pem",
            "sudo chown ubuntu:ubuntu /var/www/kangboacademy/data/apiclient_key.pem",
            "sudo chmod 600 /var/www/kangboacademy/data/apiclient_key.pem",
            "sudo nano /var/www/kangboacademy/data/payment.env",
        ]),
        "envTemplate": "\n".join([
            "WECHAT_PAY_MCHID=填入微信支付商户号",
            "WECHAT_PAY_CERT_SERIAL_NO=填入API证书序列号",
            "WECHAT_PAY_PRIVATE_KEY_PATH=/var/www/kangboacademy/data/apiclient_key.pem",
            "WECHAT_PAY_API_V3_KEY=填入32位APIv3Key",
            "WECHAT_PAY_NOTIFY_URL=https://kangboacademy.cn/api/payment/wechat/notify",
        ]),
        "restart": "sudo systemctl restart kangboacademy",
        "status": "systemctl status kangboacademy --no-pager",
        "diagnostics": "curl -fsS https://kangboacademy.cn/api/payment/diagnostics",
        "plans": "curl -fsS https://kangboacademy.cn/api/membership/plans",
        "logs": "journalctl -u kangboacademy -n 80 --no-pager",
    }

def payment_recent_stats(days: int = 7) -> dict:
    days = max(1, min(int(days or 7), 180))
    since = f"-{days} days"
    conn = get_db()
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count, COALESCE(SUM(amount_fen), 0) AS amount_fen
        FROM payments
        WHERE created_at >= datetime('now', ?)
        GROUP BY status
        """,
        (since,),
    ).fetchall()
    conn.close()
    by_status = {row["status"] or "unknown": {"count": int(row["count"] or 0), "amountFen": int(row["amount_fen"] or 0)} for row in rows}
    return {"windowDays": days, "byStatus": by_status}

def payment_signature_probe() -> dict:
    runtime = payment_runtime_config()
    private_key_path = runtime["privateKeyPath"]
    if not private_key_path:
        return {"checked": False, "ok": False, "message": "未配置私钥路径"}
    if not Path(private_key_path).exists():
        return {"checked": False, "ok": False, "message": "私钥文件不存在"}
    try:
        signature = rsa_sign("kangbo-payment-diagnostics\n", private_key_path)
        return {"checked": True, "ok": bool(signature), "message": "私钥可读且可完成 RSA-SHA256 签名"}
    except Exception as exc:
        detail = getattr(exc, "detail", None) or str(exc)
        return {"checked": True, "ok": False, "message": str(detail)[:300]}

def payment_diagnostics(days: int = 7) -> dict:
    config = payment_config()
    runtime = payment_runtime_config()
    api_v3_len = len(runtime["apiV3Key"].encode("utf-8")) if runtime["apiV3Key"] else 0
    files = {
        "envFile": sensitive_file_check(str(PAYMENT_ENV_PATH)),
        "legacyEnvFile": sensitive_file_check(str(LEGACY_PAYMENT_ENV_PATH)),
        "privateKey": sensitive_file_check(runtime["privateKeyPath"]),
    }
    tools = {
        "openssl": command_check("openssl"),
        "cryptographyAESGCM": {"available": AESGCM is not None},
    }
    checks = [
        {"key": "mchid", "name": "商户号", "ok": bool(runtime["mchid"]), "message": "WECHAT_PAY_MCHID"},
        {"key": "serial", "name": "API证书序列号", "ok": bool(runtime["certSerialNo"]), "message": "WECHAT_PAY_CERT_SERIAL_NO"},
        {"key": "privateKeyPath", "name": "商户API私钥路径", "ok": bool(runtime["privateKeyPath"]), "message": "WECHAT_PAY_PRIVATE_KEY_PATH"},
        {"key": "privateKeyFile", "name": "商户API私钥文件", "ok": files["privateKey"].get("exists") and files["privateKey"].get("readable"), "message": "私钥文件存在且服务用户可读"},
        {"key": "apiV3Key", "name": "APIv3 Key", "ok": bool(runtime["apiV3Key"]), "message": "WECHAT_PAY_API_V3_KEY"},
        {"key": "apiV3KeyLength", "name": "APIv3 Key 长度", "ok": api_v3_len == 32 if runtime["apiV3Key"] else False, "message": "微信支付 APIv3 Key 应为 32 字节"},
        {"key": "notifyUrl", "name": "支付回调 URL", "ok": bool(runtime["notifyUrl"] and runtime["notifyUrl"].startswith("https://")), "message": runtime["notifyUrl"] or "WECHAT_PAY_NOTIFY_URL"},
        {"key": "openssl", "name": "OpenSSL 签名工具", "ok": tools["openssl"].get("available"), "message": tools["openssl"].get("path") or "openssl 不可用"},
        {"key": "cryptography", "name": "回调解密组件", "ok": AESGCM is not None, "message": "Python cryptography AESGCM"},
    ]
    signature_probe = payment_signature_probe()
    checks.append({"key": "signatureProbe", "name": "私钥签名探针", "ok": signature_probe.get("ok"), "message": signature_probe.get("message", "")})
    next_actions = []
    for item in checks:
        if not item.get("ok"):
            next_actions.append(f"{item['name']}：{item['message']}")
    if not config.get("ready"):
        next_actions.append("配置完成后重启 kangboacademy，再刷新 /api/payment/diagnostics")
    return {
        "config": config,
        "ready": config.get("ready"),
        "files": files,
        "tools": tools,
        "checks": checks,
        "signatureProbe": signature_probe,
        "recentPayments": payment_recent_stats(days),
        "commands": payment_service_commands(),
        "nextActions": list(dict.fromkeys(next_actions)),
        "routes": {
            "createOrder": "/api/payment/create",
            "notify": "/api/payment/wechat/notify",
            "status": "/api/payment/status/{order_no}",
            "plans": "/api/membership/plans",
        },
        "message": "诊断只返回配置状态和文件状态，不返回商户私钥、APIv3 Key 或推流密钥。",
    }

def systemd_service_status(name: str) -> dict:
    clean_name = re.sub(r"[^a-zA-Z0-9_.@:-]", "", (name or "").strip())
    if not clean_name:
        return {"name": "", "present": False, "active": False, "enabled": False, "state": "unknown"}
    result = {"name": clean_name, "present": False, "active": False, "enabled": False, "state": "unknown"}
    try:
        active = subprocess.run(["systemctl", "is-active", clean_name], capture_output=True, text=True, timeout=2)
        state = (active.stdout or active.stderr or "").strip()
        result["state"] = state or "unknown"
        result["present"] = active.returncode != 4 and state not in {"", "unknown"}
        result["active"] = state == "active"
    except Exception:
        result["state"] = "unavailable"
    try:
        enabled = subprocess.run(["systemctl", "is-enabled", clean_name], capture_output=True, text=True, timeout=2)
        enabled_state = (enabled.stdout or enabled.stderr or "").strip()
        result["enabled"] = enabled_state == "enabled"
        result["enabledState"] = enabled_state or "unknown"
    except Exception:
        result["enabledState"] = "unavailable"
    try:
        show = subprocess.run(
            [
                "systemctl",
                "show",
                clean_name,
                "--property=FragmentPath,MainPID,NRestarts,ExecMainStatus,ActiveEnterTimestamp,SubState",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        details = {}
        for line in (show.stdout or "").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                details[key] = value
        result["details"] = details
    except Exception:
        result["details"] = {}
    return result

def file_check(path: str, executable: bool = False) -> dict:
    file_path = Path(path)
    return {
        "path": path,
        "exists": file_path.exists(),
        "isFile": file_path.is_file(),
        "readable": os.access(path, os.R_OK),
        "executable": os.access(path, os.X_OK) if executable else None,
    }

def command_check(command: str) -> dict:
    try:
        result = subprocess.run(["bash", "-lc", f"command -v {command}"], capture_output=True, text=True, timeout=2)
        found = result.returncode == 0
        return {"command": command, "available": found, "path": (result.stdout or "").strip() if found else ""}
    except Exception:
        return {"command": command, "available": False, "path": ""}

def parse_env_file(path: Path) -> dict:
    values = {}
    if not path.exists() or not path.is_file():
        return values
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return values
    for line in lines:
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
            value = value[1:-1]
        if key:
            values[key] = value
    return values

def live_env_values() -> dict:
    keys = {
        "DOUYIN_RTMP_URL", "WECHAT_CHANNELS_RTMP_URL",
        "DOUYIN_LIVE_PERMISSION", "WECHAT_CHANNELS_LIVE_PERMISSION",
        "DIGITAL_HUMAN_SOURCE_URL", "DIGITAL_HUMAN_VIDEO_LOOP",
        "DIGITAL_HUMAN_VIDEO_BITRATE", "DIGITAL_HUMAN_VIDEO_MAXRATE",
        "DIGITAL_HUMAN_VIDEO_BUFSIZE", "DIGITAL_HUMAN_AUDIO_BITRATE",
    }
    values = {key: os.getenv(key, "") for key in keys if os.getenv(key, "")}
    values.update(parse_env_file(LEGACY_LIVE_ENV_PATH))
    values.update(parse_env_file(LIVE_ENV_PATH))
    return values

def env_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def shell_single_quote(value: str) -> str:
    return "'" + str(value or "").replace("'", "'\"'\"'") + "'"

def validate_rtmp_url(value: str, label: str) -> str:
    cleaned = str(value or "").strip()
    if cleaned and not (cleaned.startswith("rtmp://") or cleaned.startswith("rtmps://")):
        raise HTTPException(400, f"{label} 必须以 rtmp:// 或 rtmps:// 开头")
    if len(cleaned) > 1000:
        raise HTTPException(400, f"{label} 过长")
    return cleaned

def write_live_env_config(payload: dict) -> dict:
    existing = parse_env_file(LIVE_ENV_PATH)
    source_url = str(payload.get("sourceUrl") or "").strip()
    updates = {
        "DOUYIN_RTMP_URL": validate_rtmp_url(payload.get("douyinRtmpUrl") or existing.get("DOUYIN_RTMP_URL", ""), "抖音 RTMP"),
        "WECHAT_CHANNELS_RTMP_URL": validate_rtmp_url(payload.get("wechatChannelsRtmpUrl") or existing.get("WECHAT_CHANNELS_RTMP_URL", ""), "微信视频号 RTMP"),
        "DOUYIN_LIVE_PERMISSION": "true" if payload.get("douyinLivePermission") else "false",
        "WECHAT_CHANNELS_LIVE_PERMISSION": "true" if payload.get("wechatChannelsLivePermission") else "false",
        "DIGITAL_HUMAN_SOURCE_URL": source_url or existing.get("DIGITAL_HUMAN_SOURCE_URL") or public_url("digital-human-obs.html?layout=vertical&platform=both&muted=0&interval=900"),
    }
    for key, value in list(updates.items()):
        if value in (None, "") and key.endswith("_RTMP_URL"):
            updates[key] = existing.get(key, "")
    if payload.get("clearDouyin"):
        updates["DOUYIN_RTMP_URL"] = ""
    if payload.get("clearWechatChannels"):
        updates["WECHAT_CHANNELS_RTMP_URL"] = ""
    merged = dict(existing)
    merged.update(updates)
    ordered_keys = [
        "DOUYIN_RTMP_URL", "WECHAT_CHANNELS_RTMP_URL",
        "DOUYIN_LIVE_PERMISSION", "WECHAT_CHANNELS_LIVE_PERMISSION",
        "DIGITAL_HUMAN_SOURCE_URL",
        "DIGITAL_HUMAN_VIDEO_LOOP", "DIGITAL_HUMAN_VIDEO_BITRATE",
        "DIGITAL_HUMAN_VIDEO_MAXRATE", "DIGITAL_HUMAN_VIDEO_BUFSIZE",
        "DIGITAL_HUMAN_AUDIO_BITRATE",
    ]
    lines = [
        "# Kangbo Academy digital live runtime configuration",
        "# Generated by protected /api/live/config. Do not commit this file.",
    ]
    for key in ordered_keys:
        if key in merged:
            lines.append(f"{key}={shell_single_quote(merged.get(key, ''))}")
    for key in sorted(set(merged) - set(ordered_keys)):
        lines.append(f"{key}={shell_single_quote(merged.get(key, ''))}")
    LIVE_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.chmod(LIVE_ENV_PATH, 0o600)
    return {
        "envFile": str(LIVE_ENV_PATH),
        "douyinRtmpConfigured": bool(merged.get("DOUYIN_RTMP_URL")),
        "wechatChannelsRtmpConfigured": bool(merged.get("WECHAT_CHANNELS_RTMP_URL")),
        "douyinLivePermission": env_truthy(merged.get("DOUYIN_LIVE_PERMISSION")),
        "wechatChannelsLivePermission": env_truthy(merged.get("WECHAT_CHANNELS_LIVE_PERMISSION")),
        "sourceUrlConfigured": bool(merged.get("DIGITAL_HUMAN_SOURCE_URL")),
    }

def live_service_commands() -> dict:
    return {
        "install": "\n".join([
            "sudo install -m 0755 /var/www/kangboacademy/scripts/kangbo-digital-live-ffmpeg.sh /usr/local/bin/kangbo-digital-live-ffmpeg",
            "sudo install -m 0644 /var/www/kangboacademy/scripts/kangbo-digital-live-douyin.service /etc/systemd/system/kangbo-digital-live-douyin.service",
            "sudo install -m 0644 /var/www/kangboacademy/scripts/kangbo-digital-live-channels.service /etc/systemd/system/kangbo-digital-live-channels.service",
            "sudo systemctl daemon-reload",
            "sudo systemctl enable kangbo-digital-live-douyin kangbo-digital-live-channels",
        ]),
        "start": "sudo systemctl start kangbo-digital-live-douyin kangbo-digital-live-channels",
        "restart": "sudo systemctl restart kangbo-digital-live-douyin kangbo-digital-live-channels",
        "stop": "sudo systemctl stop kangbo-digital-live-douyin kangbo-digital-live-channels",
        "status": "systemctl status kangbo-digital-live-douyin kangbo-digital-live-channels --no-pager",
        "logs": "journalctl -u kangbo-digital-live-douyin -u kangbo-digital-live-channels -n 80 --no-pager",
    }

def live_platform_status(key: str, name: str, rtmp_configured: bool, permission_ready: bool, service: dict) -> dict:
    missing = []
    if not permission_ready:
        missing.append("直播或推流权限")
    if not rtmp_configured:
        missing.append("RTMP推流地址和密钥")
    if not service.get("active"):
        missing.append("24小时推流服务未运行")
    return {
        "key": key,
        "name": name,
        "rtmpConfigured": rtmp_configured,
        "livePermissionConfigured": permission_ready,
        "service": service,
        "readyForPush": rtmp_configured and permission_ready,
        "streamingActive": bool(service.get("active")),
        "missing": missing,
    }

def digital_live_config() -> dict:
    live_env = live_env_values()
    tracks = audio_playlist_tracks("all")
    counts = {
        "core": sum(1 for item in tracks if item.get("type") == "core"),
        "book": sum(1 for item in tracks if item.get("type") == "book"),
    }
    source_url = live_env.get("DIGITAL_HUMAN_SOURCE_URL") or DIGITAL_HUMAN_SOURCE_URL or public_url("digital-human-obs.html?layout=vertical&platform=both&muted=0&interval=900")
    service_names = [item.strip() for item in DIGITAL_HUMAN_STREAM_SERVICES.split(",") if item.strip()]
    while len(service_names) < 2:
        service_names.append("")
    services = {
        "douyin": systemd_service_status(service_names[0]),
        "wechat_channels": systemd_service_status(service_names[1]),
    }
    douyin_rtmp = live_env.get("DOUYIN_RTMP_URL") or DOUYIN_RTMP_URL
    channels_rtmp = live_env.get("WECHAT_CHANNELS_RTMP_URL") or WECHAT_CHANNELS_RTMP_URL
    douyin_permission = env_truthy(live_env.get("DOUYIN_LIVE_PERMISSION")) or DOUYIN_LIVE_PERMISSION
    channels_permission = env_truthy(live_env.get("WECHAT_CHANNELS_LIVE_PERMISSION")) or WECHAT_CHANNELS_LIVE_PERMISSION
    platforms = [
        live_platform_status("douyin", "抖音", bool(douyin_rtmp), douyin_permission, services["douyin"]),
        live_platform_status("wechat_channels", "微信视频号", bool(channels_rtmp), channels_permission, services["wechat_channels"]),
    ]
    missing = []
    if counts["core"] < 65:
        missing.append("65门主干课程音频未全部可用")
    if counts["book"] < 500:
        missing.append("500门书目课程音频未全部可用")
    if not any(item["readyForPush"] for item in platforms):
        missing.append("至少一个平台缺少直播权限或RTMP推流地址")
    if not any(item["streamingActive"] for item in platforms):
        missing.append("24小时推流服务未运行")
    return {
        "sourceUrl": source_url,
        "obsSourceReady": bool(source_url and tracks),
        "audio": {"total": len(tracks), "counts": counts, "expected": {"core": 65, "book": 500, "total": 565}},
        "platforms": platforms,
        "readyForObs": bool(source_url and tracks),
        "readyForPlatformPush": any(item["readyForPush"] for item in platforms),
        "streamingActive": any(item["streamingActive"] for item in platforms),
        "missing": missing,
        "envFile": str(LIVE_ENV_PATH),
        "legacyEnvFile": str(LEGACY_LIVE_ENV_PATH),
        "rtmpKeys": ["DOUYIN_RTMP_URL", "WECHAT_CHANNELS_RTMP_URL"],
        "permissionKeys": ["DOUYIN_LIVE_PERMISSION", "WECHAT_CHANNELS_LIVE_PERMISSION"],
        "scriptPath": "/var/www/kangboacademy/scripts/kangbo-digital-live-ffmpeg.sh",
    }

def digital_live_diagnostics() -> dict:
    readiness = digital_live_config()
    live_env = live_env_values()
    files = {
        "scriptTemplate": file_check("/var/www/kangboacademy/scripts/kangbo-digital-live-ffmpeg.sh", executable=True),
        "installedBinary": file_check("/usr/local/bin/kangbo-digital-live-ffmpeg", executable=True),
        "douyinUnit": file_check("/etc/systemd/system/kangbo-digital-live-douyin.service"),
        "wechatChannelsUnit": file_check("/etc/systemd/system/kangbo-digital-live-channels.service"),
        "envFile": file_check(str(LIVE_ENV_PATH)),
        "legacyEnvFile": file_check(str(LEGACY_LIVE_ENV_PATH)),
        "loopVideo": file_check(live_env.get("DIGITAL_HUMAN_VIDEO_LOOP") or os.getenv("DIGITAL_HUMAN_VIDEO_LOOP", "/var/www/kangboacademy/frontend/assets/xhs-week1-video.mp4")),
    }
    tools = {
        "ffmpeg": command_check("ffmpeg"),
        "systemctl": command_check("systemctl"),
    }
    env_keys = [
        {"key": "DOUYIN_RTMP_URL", "configured": bool(live_env.get("DOUYIN_RTMP_URL") or DOUYIN_RTMP_URL), "secret": True},
        {"key": "WECHAT_CHANNELS_RTMP_URL", "configured": bool(live_env.get("WECHAT_CHANNELS_RTMP_URL") or WECHAT_CHANNELS_RTMP_URL), "secret": True},
        {"key": "DOUYIN_LIVE_PERMISSION", "configured": env_truthy(live_env.get("DOUYIN_LIVE_PERMISSION")) or DOUYIN_LIVE_PERMISSION, "secret": False},
        {"key": "WECHAT_CHANNELS_LIVE_PERMISSION", "configured": env_truthy(live_env.get("WECHAT_CHANNELS_LIVE_PERMISSION")) or WECHAT_CHANNELS_LIVE_PERMISSION, "secret": False},
        {"key": "DIGITAL_HUMAN_SOURCE_URL", "configured": bool(live_env.get("DIGITAL_HUMAN_SOURCE_URL") or DIGITAL_HUMAN_SOURCE_URL), "secret": False},
    ]
    service_ready = files["installedBinary"]["exists"] and files["douyinUnit"]["exists"] and files["wechatChannelsUnit"]["exists"]
    next_actions = []
    if not tools["ffmpeg"]["available"]:
        next_actions.append("安装 ffmpeg：sudo apt install -y ffmpeg")
    if not service_ready:
        next_actions.append("安装推流脚本和 systemd unit，然后执行 daemon-reload")
    if not files["envFile"]["exists"]:
        next_actions.append(f"创建 {LIVE_ENV_PATH} 并写入平台 RTMP 与权限开关")
    for platform in readiness.get("platforms") or []:
        for missing in platform.get("missing") or []:
            next_actions.append(f"{platform.get('name')}：{missing}")
    return {
        "readiness": readiness,
        "server": {
            "files": files,
            "tools": tools,
            "envKeys": env_keys,
            "serviceInstallReady": bool(service_ready),
        },
        "commands": live_service_commands(),
        "nextActions": list(dict.fromkeys(next_actions)),
        "message": "诊断不返回任何 RTMP 密钥或私密配置值，只返回是否已配置。",
    }

def plan_public(plan_id: str, plan: dict) -> dict:
    payload = {
        "id": plan_id,
        "name": plan["name"],
        "price": plan["price"],
        "amountFen": plan.get("amount_fen", int(plan["price"] * 100)),
        "scope": plan.get("scope", "free"),
        "durationDays": plan.get("duration_days", 0),
        "features": plan.get("features", []),
        "highlight": bool(plan.get("highlight")),
    }
    if "courses" in plan:
        payload["courses"] = plan["courses"]
    if "book_courses" in plan:
        payload["bookCourses"] = plan["book_courses"]
    return payload

def order_no() -> str:
    return f"KB{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.randbelow(100000):05d}"

def rsa_sign(message: str, private_key_path: Optional[str] = None) -> str:
    private_key_path = private_key_path or payment_runtime_config()["privateKeyPath"]
    if not private_key_path:
        raise HTTPException(500, "微信支付商户私钥未配置")
    key_path = Path(private_key_path)
    if not key_path.exists():
        raise HTTPException(500, "微信支付商户私钥文件不存在")
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=message.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise HTTPException(500, f"微信支付签名失败: {proc.stderr.decode('utf-8', errors='ignore')}")
    return base64.b64encode(proc.stdout).decode("utf-8")

def wechat_pay_authorization(method: str, path: str, body: str, timestamp: str, nonce: str, config: Optional[dict] = None) -> str:
    config = config or payment_runtime_config()
    message = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}\n"
    signature = rsa_sign(message, config["privateKeyPath"])
    return (
        'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{config["mchid"]}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{config["certSerialNo"]}"'
    )

def wechat_pay_request(method: str, path: str, payload: Optional[dict] = None, timeout: int = 12) -> dict:
    config = payment_runtime_config()
    body = "" if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    auth = wechat_pay_authorization(method, path, body, timestamp, nonce, config)
    headers = {
        "Authorization": auth,
        "Accept": "application/json",
        "User-Agent": "kangboacademy-miniapp/1.0",
    }
    if body:
        headers["Content-Type"] = "application/json"
    req = urlrequest.Request(
        "https://api.mch.weixin.qq.com" + path,
        data=body.encode("utf-8") if body else None,
        headers=headers,
        method=method,
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"微信支付接口请求失败: {detail}")
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"微信支付服务暂不可用: {exc}")

def call_wechat_jsapi_order(payload: dict) -> dict:
    return wechat_pay_request("POST", "/v3/pay/transactions/jsapi", payload)

def query_wechat_order(out_trade_no: str) -> dict:
    config = payment_runtime_config()
    quoted_order = parse.quote(out_trade_no, safe="")
    quoted_mchid = parse.quote(config["mchid"], safe="")
    path = f"/v3/pay/transactions/out-trade-no/{quoted_order}?mchid={quoted_mchid}"
    return wechat_pay_request("GET", path)

def build_request_payment_params(prepay_id: str, config: Optional[dict] = None) -> dict:
    config = config or payment_runtime_config()
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    package = f"prepay_id={prepay_id}"
    sign_message = f"{WECHAT_MINIAPP_APPID}\n{timestamp}\n{nonce}\n{package}\n"
    return {
        "timeStamp": timestamp,
        "nonceStr": nonce,
        "package": package,
        "signType": "RSA",
        "paySign": rsa_sign(sign_message, config["privateKeyPath"]),
    }

def decrypt_wechat_resource(resource: dict) -> dict:
    if AESGCM is None:
        raise HTTPException(500, "服务器缺少 cryptography，无法解密微信支付回调")
    config = payment_runtime_config()
    api_v3_key = config["apiV3Key"]
    if not api_v3_key:
        raise HTTPException(500, "微信支付 APIv3 Key 未配置")
    associated_data = (resource.get("associated_data") or "").encode("utf-8")
    nonce = (resource.get("nonce") or "").encode("utf-8")
    ciphertext = base64.b64decode(resource.get("ciphertext") or "")
    aesgcm = AESGCM(api_v3_key.encode("utf-8"))
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
    return json.loads(plaintext.decode("utf-8"))

def has_active_entitlement(conn, user_id: int, scope: str) -> bool:
    scopes = [scope]
    if scope in ("core", "books"):
        scopes.append("bundle")
    placeholders = ",".join(["?"] * len(scopes))
    row = conn.execute(f"""
        SELECT id FROM user_entitlements
        WHERE user_id=? AND status='active' AND scope IN ({placeholders})
          AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
        LIMIT 1
    """, [user_id, *scopes]).fetchone()
    return bool(row)

def apply_paid_order(conn, payment: dict, transaction_id: str = "", notify_payload: Optional[dict] = None) -> dict:
    if payment["status"] == "paid":
        return {"alreadyPaid": True}
    plan = PLANS.get(payment["plan"])
    if not plan:
        raise HTTPException(400, "订单套餐已不存在")
    duration_days = int(plan.get("duration_days", 365) or 365)
    now = datetime.now()
    expires = (now + timedelta(days=duration_days)).isoformat()
    scope = plan.get("scope", payment.get("entitlement_scope") or "core")

    conn.execute("""
        UPDATE payments
        SET status='paid', paid_at=datetime('now'), updated_at=datetime('now'),
            transaction_id=COALESCE(NULLIF(?, ''), transaction_id),
            notify_payload=COALESCE(?, notify_payload)
        WHERE order_no=?
    """, (
        transaction_id,
        json.dumps(notify_payload, ensure_ascii=False) if notify_payload else None,
        payment["order_no"],
    ))
    if scope != "free":
        conn.execute("""
            INSERT INTO user_entitlements (user_id, scope, plan, order_no, starts_at, expires_at, status)
            VALUES (?, ?, ?, ?, datetime('now'), ?, 'active')
        """, (payment["user_id"], scope, payment["plan"], payment["order_no"], expires))
        conn.execute("""
            UPDATE users
            SET plan=?, plan_expires_at=?, updated_at=datetime('now')
            WHERE id=?
        """, (payment["plan"], expires, payment["user_id"]))
    return {"alreadyPaid": False, "scope": scope, "expiresAt": expires}

def user_has_scope(user: Optional[dict], scope: str) -> bool:
    if public_access_open():
        return True
    if not user:
        return False
    legacy_plan = user.get("plan") or "free"
    legacy_scope = PLANS.get(legacy_plan, {}).get("scope")
    if legacy_scope == "bundle" or legacy_scope == scope:
        expires = user.get("plan_expires_at")
        if not expires or expires > datetime.now().isoformat():
            return True
    if legacy_plan in ("starter", "pro", "premium") and scope == "core":
        return True
    conn = get_db()
    ok = has_active_entitlement(conn, user["id"], scope)
    conn.close()
    return ok

def can_access_core_course(user: Optional[dict], course_id: int) -> bool:
    if public_access_open():
        return True
    return course_id in FREE_CORE_COURSES or user_has_scope(user, "core")

def can_access_book_course(user: Optional[dict], book_id: int) -> bool:
    if public_access_open():
        return True
    return book_id in FREE_BOOK_COURSES or user_has_scope(user, "books")

def public_url(path_or_url: str) -> str:
    src = html.unescape((path_or_url or "").strip())
    if not src:
        return ""
    if src.startswith("http://") or src.startswith("https://"):
        return src
    if src.startswith("//"):
        return "https:" + src
    base = PUBLIC_BASE_URL.rstrip("/")
    if src.startswith("/"):
        return base + src
    return base + "/" + src.lstrip("./")

def frontend_audio_path(path_or_url: str) -> Optional[Path]:
    src = html.unescape((path_or_url or "").strip())
    if not src or src.startswith("http://") or src.startswith("https://") or src.startswith("//"):
        return None
    parsed = parse.urlparse(src)
    rel = parsed.path.lstrip("/")
    if not rel:
        return None
    return (FRONTEND_DIR / rel).resolve()

def audio_url_from_page(path: Path, fallback_candidates: List[str] = None, expected_path: str = "") -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    audio_blocks = re.findall(r"<audio\b[\s\S]*?</audio>|<audio\b[^>]*>", text, re.I)
    for block in audio_blocks:
        src_match = re.search(r"\bsrc=[\"']([^\"']+)[\"']", block, re.I)
        if not src_match:
            continue
        src = src_match.group(1)
        if expected_path:
            parsed = parse.urlparse(src)
            base = parse.urlparse(PUBLIC_BASE_URL)
            if parsed.path.lstrip('./') != expected_path or (parsed.netloc and parsed.netloc != base.netloc):
                continue
        local_path = frontend_audio_path(src)
        if not local_path or local_path.exists():
            return public_url(src)

    for src in fallback_candidates or []:
        local_path = frontend_audio_path(src)
        if local_path and local_path.exists():
            return public_url(src)
    return ""

def remove_audio_player_blocks(content: str) -> str:
    start_re = re.compile(r"<div\b[^>]*class=[\"'][^\"']*audio-player[^\"']*[\"'][^>]*>", re.I)
    tag_re = re.compile(r"</?div\b[^>]*>", re.I)
    chunks = []
    pos = 0
    while True:
        start = start_re.search(content, pos)
        if not start:
            chunks.append(content[pos:])
            break
        chunks.append(content[pos:start.start()])
        depth = 0
        end = start.end()
        for tag in tag_re.finditer(content, start.start()):
            if tag.group(0).startswith("</"):
                depth -= 1
                if depth <= 0:
                    end = tag.end()
                    break
            else:
                depth += 1
        pos = end
    return "".join(chunks)

def strip_audio_blocks(content: str) -> str:
    content = remove_audio_player_blocks(content)
    content = re.sub(r"<audio\b[\s\S]*?</audio>", "", content, flags=re.I)
    return content

def split_practice_from_html(content: str) -> tuple:
    markers = [
        r"[一二三四五六七八九十]+、\s*练习题",
        r"[一二三四五六七八九十]+、\s*练习",
        r"<h[23][^>]*>\s*[^<]*(练习题|课后练习|互动练习|练习与思考)[^<]*</h[23]>",
        r"(练习|问题)\s*1\s*[：:）)]",
    ]
    start = None
    for pattern in markers:
        match = re.search(pattern, content, re.I)
        if match and (start is None or match.start() < start):
            start = match.start()
    if start is None:
        return content, ""
    return content[:start], content[start:]

def html_to_text(fragment: str) -> str:
    text = re.sub(r"<script\b[\s\S]*?</script>", "", fragment, flags=re.I)
    text = re.sub(r"<style\b[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"</(h[1-6]|p|li|div|tr|section|article)>", "\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()

CORE_READING_FALLBACKS = {
    1: [
        {"title": "《经济生活中的长波》", "author": "康德拉季耶夫", "reason": "理解长波理论源头"},
        {"title": "《逃不开的经济周期》", "author": "拉斯·特维德", "reason": "建立周期观察框架"},
        {"title": "《周期》", "author": "霍华德·马克斯", "reason": "把周期意识用于投资决策"},
        {"title": "《周金涛周期论集》", "author": "周金涛", "reason": "理解中国语境下的康波研究"},
    ],
    2: [
        {"title": "《周金涛周期论集》", "author": "周金涛", "reason": "四周期嵌套框架核心文本"},
        {"title": "《涛动周期论》", "author": "周金涛", "reason": "理解人生财富机会与周期定位"},
        {"title": "《逃不开的经济周期》", "author": "拉斯·特维德", "reason": "补充全球经济周期视角"},
        {"title": "《周期》", "author": "霍华德·马克斯", "reason": "训练逆向和位置感"},
    ],
    3: [
        {"title": "《第二次机器革命》", "author": "布林约尔松 & 麦卡菲", "reason": "理解数字技术如何改变生产率"},
        {"title": "《技术的本质》", "author": "布莱恩·阿瑟", "reason": "理解技术组合和演化逻辑"},
        {"title": "《创新者的窘境》", "author": "克莱顿·克里斯坦森", "reason": "识别颠覆式创新路径"},
        {"title": "《人工智能：一种现代方法》", "author": "Russell & Norvig", "reason": "补齐 AI 基础框架"},
    ],
    4: [
        {"title": "《洛克菲勒传》", "author": "Ron Chernow", "reason": "观察家族财富与治理结构"},
        {"title": "《穷查理宝典》", "author": "查理·芒格", "reason": "学习跨周期的多元思维"},
        {"title": "《巴菲特致股东的信》", "author": "沃伦·巴菲特", "reason": "理解长期主义和资本配置"},
        {"title": "《基业长青》", "author": "柯林斯 & 波拉斯", "reason": "理解组织如何跨越周期"},
    ],
    5: [
        {"title": "《货币战争》", "author": "宋鸿兵", "reason": "理解货币体系与金融博弈叙事"},
        {"title": "《原则：应对变化中的世界秩序》", "author": "瑞·达里奥", "reason": "观察大国周期与货币秩序"},
        {"title": "《货币金融学》", "author": "米什金", "reason": "补齐货币银行学基础"},
        {"title": "《黄金与美元危机》", "author": "罗伯特·特里芬", "reason": "理解美元体系的结构性矛盾"},
    ],
    6: [
        {"title": "《投资最重要的事》", "author": "霍华德·马克斯", "reason": "训练风险、周期与逆向思维"},
        {"title": "《原则》", "author": "瑞·达里奥", "reason": "建立决策和资产配置原则"},
        {"title": "《聪明的投资者》", "author": "本杰明·格雷厄姆", "reason": "掌握安全边际"},
        {"title": "《漫步华尔街》", "author": "伯顿·马尔基尔", "reason": "理解有效市场与指数配置"},
    ],
    20: [
        {"title": "《原则》", "author": "瑞·达里奥", "reason": "把个人原则转化为决策系统"},
        {"title": "《投资最重要的事》", "author": "霍华德·马克斯", "reason": "整合周期、风险和逆向思维"},
        {"title": "《穷查理宝典》", "author": "查理·芒格", "reason": "建立多元思维模型"},
        {"title": "《思考，快与慢》", "author": "丹尼尔·卡尼曼", "reason": "识别决策偏差"},
    ],
}

def normalize_reading_item(item: dict) -> Optional[dict]:
    title = html_to_text(item.get("title", "")).strip()
    if not title or title in {"书籍", "书名"}:
        return None
    return {
        "title": title,
        "author": html_to_text(item.get("author", "")).strip(),
        "difficulty": html_to_text(item.get("difficulty", "")).strip(),
        "reason": html_to_text(item.get("reason", "")).strip(),
    }

def parse_recommendation_line(fragment: str) -> Optional[dict]:
    line = re.sub(r"\s+", " ", html_to_text(fragment)).strip()
    if "《" not in line or "》" not in line:
        return None
    title_match = re.search(r"《[^》]+》", line)
    if not title_match:
        return None
    title = title_match.group(0)
    before = line[:title_match.start()].strip(" ：:，,.-—")
    after = line[title_match.end():].strip()
    author = before if before and len(before) <= 32 else ""
    reason = ""
    sep_match = re.search(r"\s*(?:——|—|-)\s*", after)
    if sep_match:
        if not author:
            author = after[:sep_match.start()].strip(" ，,")
        reason = after[sep_match.end():].strip()
    elif not author:
        author = after.strip(" ，,")
    return normalize_reading_item({"title": title, "author": author, "reason": reason})

def parse_reference_books(fragment: str) -> list:
    text = re.sub(r"\s+", " ", html_to_text(fragment)).strip()
    text = re.sub(r"^\U0001f4d6\s*", "", text)
    text = re.sub(r"^(参考著作|延伸阅读|参考书目)\s*[：:]", "", text)
    matches = list(re.finditer(r"《[^》]+》", text))
    books = []
    for idx, match in enumerate(matches):
        title = match.group(0)
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        tail = text[match.end():next_start]
        tail = re.sub(r"^[（(][^）)]*[）)]", "", tail).strip(" ，,、;；")
        author = re.split(r"[，,、;；]", tail, 1)[0].strip()
        if len(author) > 24 or any(word in author for word in ["特别推荐", "综合", "所有课程", "本系列"]):
            author = ""
        item = normalize_reading_item({
            "title": title,
            "author": author,
            "reason": "本课参考著作",
        })
        if item:
            books.append(item)
    return books

def parse_recommendation_table(fragment: str) -> list:
    rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", fragment, flags=re.I)
    if not rows:
        return []
    headers = []
    books = []
    for row in rows:
        cells = [html_to_text(cell) for cell in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", row, flags=re.I)]
        cells = [cell for cell in cells if cell]
        if not cells:
            continue
        if re.search(r"<th\b", row, flags=re.I):
            headers = cells
            continue
        if cells[0] in {"书籍", "书名"}:
            continue
        item = {"title": cells[0], "author": "", "difficulty": "", "reason": ""}
        if headers:
            for idx, header in enumerate(headers[:len(cells)]):
                value = cells[idx]
                if "书" in header:
                    item["title"] = value
                elif "作者" in header:
                    item["author"] = value
                elif "难度" in header:
                    item["difficulty"] = value
                elif "价值" in header or "理由" in header:
                    item["reason"] = value
                elif "关联" in header and value:
                    item["reason"] = f"{item['reason']}；关联度：{value}" if item["reason"] else f"关联度：{value}"
        else:
            if len(cells) >= 2:
                item["author"] = cells[1]
            if len(cells) == 3:
                item["reason"] = cells[2]
            elif len(cells) >= 4:
                if re.search(r"[\u2605\u2606\U00002b50]", cells[2]):
                    item["difficulty"] = cells[2]
                    item["reason"] = cells[3]
                else:
                    item["reason"] = cells[2]
                    item["difficulty"] = cells[3] if re.search(r"[\u2605\u2606\U00002b50]", cells[3]) else ""
        normalized = normalize_reading_item(item)
        if normalized:
            books.append(normalized)
    return books

def recommended_books_from_page(path: Path, course_id: int) -> list:
    text = path.read_text(encoding="utf-8", errors="ignore")
    body_match = re.search(r"<article[^>]*>([\s\S]*?)</article>", text)
    if body_match:
        content = body_match.group(1)
    else:
        content_match = re.search(
            r'<div class="content">([\s\S]*?)\n\s*</div>\s*\n\s*<div class="bottom-nav">',
            text,
        )
        content = content_match.group(1) if content_match else text
    content = strip_audio_blocks(content)
    section_pattern = re.compile(
        r"<h[23][^>]*>[\s\S]*?(?:推荐阅读|延伸阅读|参考书目)[\s\S]*?</h[23]>([\s\S]*?)(?=<h2\b|<hr\b|<div\b[^>]*class=[\"'][^\"']*bottom-nav|</article>|</main>|$)",
        re.I,
    )
    recommend_div_pattern = re.compile(
        r"<div\b[^>]*class=[\"'][^\"']*recommend[^\"']*[\"'][^>]*>([\s\S]*?)</div>",
        re.I,
    )
    for match in list(section_pattern.finditer(content)) + list(recommend_div_pattern.finditer(content)):
        section = match.group(1)
        books = parse_recommendation_table(section)
        if not books:
            books = [
                item for item in (parse_recommendation_line(li) for li in re.findall(r"<li[^>]*>([\s\S]*?)</li>", section, flags=re.I))
                if item
            ]
        if books:
            return books[:8]
    reference_blocks = re.findall(
        r"<p>\s*(?:\U0001f4d6\s*)?<strong>\s*(?:参考著作|延伸阅读|参考书目)\s*</strong>\s*[：:]?([\s\S]*?)</p>",
        content,
        flags=re.I,
    )
    reference_blocks += re.findall(
        r"<blockquote>\s*<p>\s*(?:\U0001f4d6\s*)?<strong>\s*(?:参考著作|延伸阅读|参考书目)\s*</strong>\s*[：:]?([\s\S]*?)</p>\s*</blockquote>",
        content,
        flags=re.I,
    )
    for block in reference_blocks:
        books = parse_reference_books(block)
        if books:
            return books[:8]
    return CORE_READING_FALLBACKS.get(course_id, [])

def html_article_from_page(path: Path, strip_practice: bool = False) -> str:
    from html.parser import HTMLParser

    text = path.read_text(encoding="utf-8", errors="ignore")

    class ArticleParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.start = None
            self.end = None
            self.root = ""
            self.depth = 0
            self.offsets = [0]
            for line in text.splitlines(keepends=True):
                self.offsets.append(self.offsets[-1] + len(line))

        def source_offset(self):
            line, column = self.getpos()
            return self.offsets[line - 1] + column

        def handle_starttag(self, tag, attrs):
            classes = (dict(attrs).get("class") or "").split()
            if self.start is None and (tag == "article" or (tag == "div" and "content" in classes)):
                self.start = self.source_offset() + len(self.get_starttag_text())
                self.root = tag
                self.depth = 1
            elif self.depth and tag == self.root:
                self.depth += 1

        def handle_endtag(self, tag):
            if self.depth and tag == self.root:
                self.depth -= 1
                if self.depth == 0:
                    self.end = self.source_offset()

    parser = ArticleParser()
    parser.feed(text)
    if parser.start is not None:
        content = text[parser.start:parser.end]
    elif re.search(r"<(?:html|head|body)\b", text, re.I):
        # Never send a whole document into mini-program rich-text on extraction failure.
        content = ""
    else:
        content = text
    content = strip_audio_blocks(content)
    if strip_practice:
        content = split_practice_from_html(content)[0]
    from html import escape
    from urllib.parse import urljoin, urlsplit

    class ImageParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.replacements = []
            self.offsets = [0]
            for line in content.splitlines(keepends=True):
                self.offsets.append(self.offsets[-1] + len(line))

        def handle_starttag(self, tag, attrs):
            if tag != "img":
                return
            attributes = dict(attrs)
            src = (attributes.get("src") or "").strip()
            replacement = ""
            try:
                base = urlsplit(PUBLIC_BASE_URL)
                url = urlsplit(urljoin(PUBLIC_BASE_URL.rstrip("/") + "/", src))
                safe = (
                    src and not any(ord(char) <= 32 or ord(char) == 127 for char in src)
                    and "\\" not in src
                    and url.scheme in ("http", "https")
                    and (url.scheme, url.hostname, url.port) == (base.scheme, base.hostname, base.port)
                    and not url.username and not url.password
                )
                if safe:
                    kept = [('src', url.geturl())]
                    for name in ("alt", "title"):
                        if attributes.get(name) is not None:
                            kept.append((name, attributes[name]))
                    for name in ("width", "height"):
                        value = attributes.get(name) or ""
                        if re.fullmatch(r"[0-9]{1,4}", value) and 0 < int(value) <= 4096:
                            kept.append((name, value))
                    replacement = "<img " + " ".join(
                        f'{name}="{escape(value, quote=True)}"' for name, value in kept
                    ) + ">"
            except ValueError:
                pass
            line, column = self.getpos()
            start = self.offsets[line - 1] + column
            self.replacements.append((start, start + len(self.get_starttag_text()), replacement))

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

    images = ImageParser()
    images.feed(content)
    images.close()
    for start, end, replacement in reversed(images.replacements):
        content = content[:start] + replacement + content[end:]
    return content

# ============================================================
# MODELS
# ============================================================
class RegisterReq(BaseModel):
    email: str
    username: str
    password: str
    phone: Optional[str] = None

class LoginReq(BaseModel):
    email: str
    password: str

class UpdateProfileReq(BaseModel):
    username: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None

class ProgressReq(BaseModel):
    course_id: StrictInt
    status: Optional[str] = None
    progress_percent: Optional[StrictInt] = None

class QuizSubmitReq(BaseModel):
    course_id: int
    answers: List[int]

class NoteReq(BaseModel):
    course_id: int
    content: str

class BookmarkReq(BaseModel):
    course_id: int
    lesson: Optional[str] = ""
    title: Optional[str] = ""
    is_book_course: Optional[bool] = False

class PaymentReq(BaseModel):
    plan: str
    method: Optional[str] = "wechat"

class PaymentConfigReq(BaseModel):
    mchid: Optional[str] = ""
    certSerialNo: Optional[str] = ""
    privateKeyPath: Optional[str] = ""
    privateKeyPem: Optional[str] = ""
    apiV3Key: Optional[str] = ""
    notifyUrl: Optional[str] = ""
    clearPrivateKey: Optional[bool] = False

class ShopClickReq(BaseModel):
    book_id: int
    target: Optional[str] = ""
    source: Optional[str] = "miniapp"

class ShopResolveReq(BaseModel):
    book_id: int
    source: Optional[str] = "miniapp"

class AffiliateImportReq(BaseModel):
    products: dict
    replace: Optional[bool] = False

class AffiliateTemplateReq(BaseModel):
    template: str
    targetField: Optional[str] = "affiliateUrl"
    source: Optional[str] = "jd_union"
    channelName: Optional[str] = "京东联盟"
    settlementMode: Optional[str] = "cps"
    commissionRate: Optional[str] = "以联盟后台为准"
    productIdTemplate: Optional[str] = ""
    productPathTemplate: Optional[str] = ""
    miniProgramAppId: Optional[str] = ""
    appId: Optional[str] = ""
    businessType: Optional[str] = ""
    replace: Optional[bool] = False
    previewLimit: Optional[int] = 5

class AffiliateSmartImportReq(BaseModel):
    content: str
    source: Optional[str] = "jd_union"
    channelName: Optional[str] = "京东联盟"
    settlementMode: Optional[str] = "cps"
    commissionRate: Optional[str] = "以联盟后台为准"
    replace: Optional[bool] = False
    previewLimit: Optional[int] = 20

class WxLoginReq(BaseModel):
    code: str
    userInfo: Optional[dict] = None

class WxPhoneReq(BaseModel):
    code: Optional[str] = None
    phone: Optional[str] = None

class SearchReq(BaseModel):
    keyword: str

class PracticeSubmitReq(BaseModel):
    lesson: str
    answers: Dict[str, str]
    reflection: Optional[str] = ""

class AgentChatReq(BaseModel):
    prompt: str
    context: Optional[dict] = None
    source: Optional[str] = "miniapp_tools"
    max_tokens: Optional[int] = 900

class LaunchEventReq(BaseModel):
    event: str
    source: Optional[str] = ""
    channel: Optional[str] = ""
    campaign: Optional[str] = ""
    path: Optional[str] = ""
    referrer: Optional[str] = ""
    target: Optional[str] = ""
    plan: Optional[str] = ""
    book_id: Optional[int] = None
    order_no: Optional[str] = ""
    amount_fen: Optional[int] = None
    extra: Optional[dict] = None

class ManualLaunchMetricsReq(BaseModel):
    date: Optional[str] = ""
    platform: Optional[str] = "xhs"
    campaign: Optional[str] = ""
    views: Optional[int] = 0
    conversionClicks: Optional[int] = 0
    purchaseIntents: Optional[int] = 0
    purchases: Optional[int] = 0
    bookClicks: Optional[int] = 0
    publishTasks: Optional[int] = 0
    reviews: Optional[int] = 0
    note: Optional[str] = ""

class ManualLaunchMetricsBatchReq(BaseModel):
    rows: List[ManualLaunchMetricsReq]
    replace: Optional[bool] = False

class ManualLaunchMetricsImportReq(BaseModel):
    content: str

class LiveConfigReq(BaseModel):
    douyinRtmpUrl: Optional[str] = ""
    wechatChannelsRtmpUrl: Optional[str] = ""
    douyinLivePermission: Optional[bool] = False
    wechatChannelsLivePermission: Optional[bool] = False
    sourceUrl: Optional[str] = ""
    clearDouyin: Optional[bool] = False
    clearWechatChannels: Optional[bool] = False

# ============================================================
# APP
# ============================================================
app = FastAPI(title="康波研究院 API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Plans config
CORE_PHASE_FIRST_COURSES = [1, 7, 13, 17, 21, 25, 31, 40, 49, 58]
BOOK_WAVE_FIRST_COURSES = [1, 63, 93, 118, 148, 178, 208, 239, 269, 299, 329, 337, 364, 391, 419, 446, 473]
FREE_CORE_COURSES = set(CORE_PHASE_FIRST_COURSES)
FREE_BOOK_COURSES = set(BOOK_WAVE_FIRST_COURSES)

PLANS = {
    "free": {
        "name": "免费体验",
        "price": 0,
        "amount_fen": 0,
        "scope": "free",
        "duration_days": 0,
        "courses": sorted(FREE_CORE_COURSES),
        "book_courses": sorted(FREE_BOOK_COURSES),
        "features": ["每个主干课程阶段第一课免费", "每个书目课程波次第一本免费", "免费工具"],
    },
    "core_year": {
        "name": "主干课程年卡",
        "price": 399,
        "amount_fen": 39900,
        "scope": "core",
        "duration_days": 365,
        "courses": list(range(1, 66)),
        "features": ["65门主干课程", "课程进度记录", "后续课程更新"],
    },
    "books_year": {
        "name": "书目课程年卡",
        "price": 299,
        "amount_fen": 29900,
        "scope": "books",
        "duration_days": 365,
        "book_courses": list(range(1, 501)),
        "features": ["500本推荐书目课程", "17波系统精读", "19类知识领域"],
    },
    "bundle_year": {
        "name": "全库升级包",
        "price": 599,
        "amount_fen": 59900,
        "scope": "bundle",
        "duration_days": 365,
        "courses": list(range(1, 66)),
        "book_courses": list(range(1, 501)),
        "features": ["主干课程 + 书目课程", "升级打包优惠", "后续内容更新"],
        "highlight": True,
    },
}

BADGE_CATALOG = {
    "first_practice": {"name": "初试锋芒", "desc": "完成第一次互动练习", "icon": "badge-seed", "tier": "bronze"},
    "daily_refiner_1": {"name": "每日精进", "desc": "当天完成至少一次练习", "icon": "badge-daily", "tier": "bronze"},
    "sharp_80": {"name": "重点捕手", "desc": "单次练习得分达到 80 分", "icon": "badge-target", "tier": "silver"},
    "mastery_90": {"name": "体系掌握", "desc": "单次练习得分达到 90 分", "icon": "badge-medal", "tier": "gold"},
    "core_spark": {"name": "主干启航", "desc": "完成主干课程免费课练习", "icon": "badge-course", "tier": "bronze"},
    "book_spark": {"name": "书海开卷", "desc": "完成书目课程免费课练习", "icon": "badge-book", "tier": "bronze"},
    "three_practices": {"name": "连续打磨", "desc": "累计完成 3 次互动练习", "icon": "badge-loop", "tier": "silver"},
    "streak_3": {"name": "三日精进", "desc": "连续 3 天完成每日精进", "icon": "badge-streak", "tier": "silver"},
    "streak_7": {"name": "七日修炼", "desc": "连续 7 天完成每日精进", "icon": "badge-diamond", "tier": "gold"},
}

PRACTICE_KEYWORDS = [
    "康波", "周期", "春初", "冬末", "资产", "配置", "估值", "风险", "现金", "安全边际",
    "技术", "创新", "债务", "通胀", "利率", "泡沫", "人口", "政策", "AI", "黄金",
    "房地产", "股票", "复利", "现金流", "护城河", "反身性", "黑天鹅", "杠杆",
    "全球化", "地缘", "能源", "货币", "行动", "案例",
]

def resolve_lesson(lesson: str) -> dict:
    core_match = re.fullmatch(r"lesson(\d+)\.html", lesson or "")
    if core_match:
        course_id = int(core_match.group(1))
        return {
            "lesson": lesson,
            "id": course_id,
            "courseRef": course_id,
            "isBookCourse": False,
            "scope": "core",
            "requiredPlan": "core_year",
            "page": FRONTEND_DIR / lesson,
        }
    book_match = re.fullmatch(r"book(\d+)\.html", lesson or "")
    if book_match:
        book_id = int(book_match.group(1))
        return {
            "lesson": lesson,
            "id": book_id,
            "courseRef": 10000 + book_id,
            "isBookCourse": True,
            "scope": "books",
            "requiredPlan": "books_year",
            "page": FRONTEND_DIR / lesson,
        }
    raise HTTPException(400, "课程文件名不合法")

def can_access_lesson(user: Optional[dict], meta: dict) -> bool:
    if meta["isBookCourse"]:
        return can_access_book_course(user, meta["id"])
    return can_access_core_course(user, meta["id"])

def lesson_free(meta: dict) -> bool:
    if public_access_open():
        return True
    return meta["id"] in (FREE_BOOK_COURSES if meta["isBookCourse"] else FREE_CORE_COURSES)

def top_practice_keywords(text: str, limit: int = 8) -> List[str]:
    found = []
    for keyword in PRACTICE_KEYWORDS:
        if keyword in text and keyword not in found:
            found.append(keyword)
        if len(found) >= limit:
            break
    return found or ["周期", "资产", "风险", "行动"]

def compact_prompt(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:limit].rstrip() + ("..." if len(text) > limit else "")

def build_practice_questions(page: Path, lesson: str) -> dict:
    article = html_article_from_page(page, strip_practice=False)
    body_html, practice_html = split_practice_from_html(article)
    body_text = html_to_text(body_html)
    practice_text = html_to_text(practice_html)
    keywords = top_practice_keywords(body_text + "\n" + practice_text)

    answer_split = re.split(r"(参考答案|查看答案|答案与解析|延伸阅读|本课概要)", practice_text, maxsplit=1)
    prompt_text = (answer_split[0] if answer_split else practice_text).strip()
    segments = []
    if prompt_text:
        pattern = re.compile(r"((?:练习|问题)\s*\d+\s*[：:）)]?[\s\S]*?)(?=(?:练习|问题)\s*\d+\s*[：:）)]?|$)")
        segments = [m.group(1).strip() for m in pattern.finditer(prompt_text)]
        segments = [seg for seg in segments if len(seg) >= 12]

    if not segments:
        segments = [
            "练习1：用三句话总结本课最重要的逻辑，并说明它为什么重要。",
            "练习2：选择一个你正在关注的资产、职业或经营决策，用本课框架做一次判断。",
            "练习3：写下你接下来7天可以执行的一个行动，以及你要规避的一个风险。",
        ]

    questions = []
    for idx, segment in enumerate(segments[:4], 1):
        title_match = re.match(r"((?:练习|问题)\s*\d+\s*[：:）)]?\s*[^\n]{0,36})", segment)
        title = title_match.group(1).strip(" ：:") if title_match else f"练习{idx}"
        prompt = compact_prompt(segment, 260)
        questions.append({
            "id": f"q{idx}",
            "title": title,
            "prompt": prompt,
            "type": "text",
            "placeholder": "写下你的判断、理由、例子和行动方案。建议 80 字以上。",
            "keywords": keywords[:6],
            "maxScore": 100,
        })

    return {
        "lesson": lesson,
        "questions": questions,
        "keywords": keywords,
        "practiceText": prompt_text,
        "hasSourcePractice": bool(practice_text),
    }

def score_answer(answer: str, keywords: List[str]) -> dict:
    text = re.sub(r"\s+", " ", (answer or "").strip())
    if not text:
        return {"score": 0, "covered": [], "missing": keywords[:4], "comment": "这一题还没有作答。"}
    covered = [kw for kw in keywords if kw and kw in text]
    missing = [kw for kw in keywords if kw not in covered]
    length_score = min(35, len(text) // 4)
    keyword_score = round(40 * (len(covered) / max(1, min(5, len(keywords)))))
    specificity = 0
    if re.search(r"\d|20\d{2}|19\d{2}|A股|房产|黄金|美债|现金|AI", text):
        specificity += 8
    if any(word in text for word in ["因为", "所以", "导致", "如果", "但是", "风险", "策略", "行动"]):
        specificity += 9
    if any(word in text for word in ["我", "计划", "准备", "当前", "未来", "下周", "组合"]):
        specificity += 8
    score = max(10, min(100, length_score + keyword_score + specificity))
    if score >= 85:
        comment = "回答比较完整，已经把课程框架和自己的判断连接起来。"
    elif score >= 60:
        comment = "回答有基础判断，但还需要补充证据、风险和具体行动。"
    else:
        comment = "回答偏短，建议用“判断-理由-风险-行动”的结构重写。"
    return {"score": score, "covered": covered, "missing": missing[:4], "comment": comment}

def build_agent_feedback(score: int, results: List[dict], keywords: List[str]) -> str:
    covered = []
    missing = []
    for result in results:
        covered.extend(result.get("covered", []))
        missing.extend(result.get("missing", []))
    covered = list(dict.fromkeys(covered))[:5]
    missing = [kw for kw in dict.fromkeys(missing) if kw not in covered][:5]
    focus = "、".join(keywords[:5])
    if score >= 90:
        level = "你已经较好掌握了本课主线。"
    elif score >= 75:
        level = "你已经抓住了部分重点，但还需要把分析链条写得更完整。"
    elif score >= 60:
        level = "你有基本理解，下一步要把概念落到具体场景。"
    else:
        level = "你还需要先把本课关键词和基本框架补齐。"
    covered_text = "、".join(covered) if covered else "暂未明显覆盖"
    missing_text = "、".join(missing) if missing else "没有明显短板"
    return (
        f"康波学习Agent反馈：{level} 本课重点是 {focus}。"
        f"你的回答已经覆盖：{covered_text}；建议继续强化：{missing_text}。"
        " 下次练习请尽量按照“周期位置-资产影响-风险边界-下一步行动”的顺序作答。"
    )

def consecutive_practice_days(conn, user_id: int) -> int:
    rows = conn.execute(
        "SELECT date FROM daily_refinements WHERE user_id=? AND practice_count>0 ORDER BY date DESC",
        (user_id,)
    ).fetchall()
    dates = {row["date"] for row in rows}
    streak = 0
    day = datetime.now()
    while day.strftime("%Y-%m-%d") in dates:
        streak += 1
        day -= timedelta(days=1)
    return streak

def award_badges(conn, user_id: int, badge_keys: List[str]) -> List[dict]:
    earned = []
    for key in badge_keys:
        badge = BADGE_CATALOG.get(key)
        if not badge:
            continue
        try:
            conn.execute("""
                INSERT INTO user_badges (user_id, badge_key, badge_name, badge_desc, badge_icon)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, key, badge["name"], badge["desc"], badge["icon"]))
            earned.append({"key": key, **badge})
        except sqlite3.IntegrityError:
            continue
    return earned

# ============================================================
# AUTH ROUTES
# ============================================================
@app.post("/api/wx-login")
async def wx_login(req: WxLoginReq):
    if not req.code:
        raise HTTPException(400, "缺少微信登录 code")

    session = call_wechat_code2session(req.code)
    if session.get("errcode"):
        raise HTTPException(400, session.get("errmsg", "微信登录失败"))

    openid = session.get("openid")
    if not openid:
        raise HTTPException(400, "微信登录未返回 openid")

    unionid = session.get("unionid")
    session_key = session.get("session_key", "")
    profile = req.userInfo or {}
    username = profile.get("nickName") or profile.get("nickname") or "微信用户"
    avatar = profile.get("avatarUrl") or profile.get("avatar") or ""

    openid_hash = hashlib.sha256(openid.encode("utf-8")).hexdigest()
    synthetic_email = f"wx_{openid_hash[:24]}@wechat.local"

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE wechat_openid=?", (openid,)).fetchone()
    if user:
        conn.execute("""
            UPDATE users
            SET username=COALESCE(NULLIF(?, ''), username),
                avatar=COALESCE(NULLIF(?, ''), avatar),
                wechat_unionid=COALESCE(?, wechat_unionid),
                wechat_session_key=?,
                last_login=datetime('now'),
                updated_at=datetime('now')
            WHERE id=?
        """, (username, avatar, unionid, session_key, user["id"]))
        user_id = user["id"]
    else:
        password_hash, salt = hash_password(secrets.token_urlsafe(32))
        cursor = conn.execute("""
            INSERT INTO users (
                email, username, password_hash, salt, avatar,
                wechat_openid, wechat_unionid, wechat_session_key,
                wechat_bound_at, last_login
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (synthetic_email, username, password_hash, salt, avatar, openid, unionid, session_key))
        user_id = cursor.lastrowid

    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()

    token = create_token(user_id)
    return {
        "success": True,
        "token": token,
        "user": public_user(dict(user)),
        "userInfo": public_user(dict(user)),
    }

@app.post("/api/wx-phone")
async def bind_wx_phone(req: WxPhoneReq, user=Depends(get_current_user)):
    phone = ""
    if req.code:
        phone_info = call_wechat_phone_number(req.code)
        phone = phone_info.get("phoneNumber") or phone_info.get("purePhoneNumber") or ""
    elif req.phone:
        phone = req.phone
    phone = normalize_phone(phone)
    if not phone:
        raise HTTPException(400, "缺少手机号")

    conn = get_db()
    conn.execute(
        "UPDATE users SET phone=?, updated_at=datetime('now') WHERE id=?",
        (phone, user["id"])
    )
    conn.commit()
    fresh = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    conn.close()
    public = public_user(dict(fresh))
    return {"success": True, "phone": phone, "user": public, "userInfo": public}

@app.post("/api/auth/register")
async def register(req: RegisterReq):
    conn = get_db()
    existing = conn.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(400, "该邮箱已注册")
    
    password_hash, salt = hash_password(req.password)
    cursor = conn.execute(
        "INSERT INTO users (email, username, password_hash, salt, phone) VALUES (?,?,?,?,?)",
        (req.email, req.username, password_hash, salt, req.phone)
    )
    user_id = cursor.lastrowid
    token = create_token(user_id, conn)
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "token": token,
        "user": {"id": user_id, "email": req.email, "username": req.username, "plan": "free"}
    }

@app.post("/api/auth/login")
async def login(req: LoginReq):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=? AND is_active=1", (req.email,)).fetchone()
    if not user or not verify_password(req.password, user['password_hash'], user['salt']):
        conn.close()
        raise HTTPException(401, "邮箱或密码错误")
    
    conn.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user['id'],))
    token = create_token(user['id'], conn)
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user['id'], "email": user['email'], "username": user['username'],
            "plan": user['plan'], "avatar": user['avatar']
        }
    }

@app.post("/api/auth/logout")
async def logout(user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM user_tokens WHERE user_id=?", (user['id'],))
    conn.commit()
    conn.close()
    return {"success": True}

# ============================================================
# USER ROUTES
# ============================================================
@app.get("/api/user/profile")
async def get_profile(user=Depends(get_current_user)):
    conn = get_db()
    
    # Get stats
    completed = conn.execute(
        "SELECT COUNT(*) as c FROM course_progress WHERE user_id=? AND status='completed'",
        (user['id'],)
    ).fetchone()['c']
    
    total_progress = conn.execute(
        "SELECT AVG(progress_percent) as avg FROM course_progress WHERE user_id=?",
        (user['id'],)
    ).fetchone()['avg'] or 0
    
    streak = conn.execute(
        "SELECT COUNT(*) as c FROM learning_streaks WHERE user_id=? AND date >= date('now','-7 days')",
        (user['id'],)
    ).fetchone()['c']
    
    bookmarks = conn.execute(
        "SELECT COUNT(*) as c FROM user_bookmarks WHERE user_id=?", (user['id'],)
    ).fetchone()['c']
    
    conn.close()
    
    return {
        "id": user['id'], "email": user['email'], "username": user['username'],
        "phone": user['phone'], "avatar": user['avatar'], "plan": user['plan'],
        "plan_expires_at": user['plan_expires_at'], "created_at": user['created_at'],
        "stats": {
            "courses_completed": completed,
            "average_progress": round(total_progress, 1),
            "weekly_streak": streak,
            "bookmarks": bookmarks,
            "plan_name": PLANS.get(user['plan'], {}).get('name', '免费版')
        }
    }

@app.get("/api/user")
async def get_user_alias(user=Depends(get_current_user)):
    return await get_profile(user)

@app.put("/api/user/profile")
async def update_profile(req: UpdateProfileReq, user=Depends(get_current_user)):
    conn = get_db()
    updates = []
    params = []
    if req.username: updates.append("username=?"); params.append(req.username)
    if req.phone: updates.append("phone=?"); params.append(req.phone)
    if req.avatar is not None: updates.append("avatar=?"); params.append(req.avatar)
    if updates:
        params.append(user['id'])
        conn.execute(f"UPDATE users SET {','.join(updates)}, updated_at=datetime('now') WHERE id=?", params)
        conn.commit()
    conn.close()
    return {"success": True}

# ============================================================
# COURSE PROGRESS ROUTES
# ============================================================
@app.get("/api/progress")
async def get_all_progress(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM course_progress WHERE user_id=? ORDER BY course_id", (user['id'],)
    ).fetchall()
    conn.close()
    return {"progress": [dict(r) for r in rows]}

@app.get("/api/progress/{course_id}")
async def get_course_progress(course_id: int, user=Depends(get_current_user)):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM course_progress WHERE user_id=? AND course_id=?",
        (user['id'], course_id)
    ).fetchone()
    conn.close()
    if not row:
        return {"course_id": course_id, "status": "not_started", "progress_percent": 0}
    return dict(row)

@app.post("/api/progress")
async def update_progress(req: ProgressReq, user=Depends(get_current_user)):
    validate_progress_request(req)
    conn = get_db()
    try:
        # Serialize read/modify/write so concurrent completion retries count once.
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM course_progress WHERE user_id=? AND course_id=?",
            (user['id'], req.course_id)
        ).fetchone()
        status = req.status if req.status is not None else (existing['status'] if existing else 'in_progress')
        percent = req.progress_percent if req.progress_percent is not None else (existing['progress_percent'] if existing else 0)
        changed = not existing or existing['status'] != status or existing['progress_percent'] != percent
        repeated_completion = existing and existing['status'] == status == 'completed'
        if existing:
            if changed or (status == 'completed' and not existing['completed_at']):
                conn.execute("""
                    UPDATE course_progress SET status=?, progress_percent=?,
                    completed_at=CASE WHEN ?='completed' THEN COALESCE(completed_at, datetime('now')) ELSE completed_at END,
                    started_at=CASE WHEN ? IN ('in_progress','completed') THEN COALESCE(started_at, datetime('now')) ELSE started_at END,
                    updated_at=datetime('now') WHERE id=?
                """, (status, percent, status, status, existing['id']))
        else:
            conn.execute("""
                INSERT INTO course_progress (user_id, course_id, status, progress_percent, started_at, completed_at)
                VALUES (?, ?, ?, ?, CASE WHEN ? IN ('in_progress','completed') THEN datetime('now') END,
                        CASE WHEN ?='completed' THEN datetime('now') END)
            """, (user['id'], req.course_id, status, percent, status, status))
        if changed and not repeated_completion:
            today = datetime.now().strftime('%Y-%m-%d')
            conn.execute("""
                INSERT INTO learning_streaks (user_id, date, courses_viewed) VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) DO UPDATE SET courses_viewed = courses_viewed + 1
            """, (user['id'], today))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"success": True}

def validate_progress_request(req: ProgressReq) -> None:
    if type(req.course_id) is not int or req.course_id <= 0:
        raise HTTPException(422, "课程编号不合法")
    if req.status is not None and req.status not in ('not_started', 'in_progress', 'completed'):
        raise HTTPException(422, "学习状态不合法")
    if req.progress_percent is not None and (
        type(req.progress_percent) is not int or not 0 <= req.progress_percent <= 100
    ):
        raise HTTPException(422, "学习进度必须为0至100的整数")
    if req.course_id >= 10000:
        number = req.course_id - 10000
        exists = any(int(course['n']) == number for course in parse_book_courses())
        page = FRONTEND_DIR / f"book{number}.html"
    else:
        number = req.course_id
        exists = 1 <= number <= 65 and any(
            course_record_from_markdown(path) is not None
            for pattern in (f"{number:02d}-*.md", f"{number}-*.md")
            for path in COURSES_DIR.glob(pattern)
        )
        page = FRONTEND_DIR / f"lesson{number}.html"
    if not exists or not page.is_file():
        raise HTTPException(404, "课程不存在")

@app.get("/api/user/progress")
async def get_user_progress_alias(user=Depends(get_current_user)):
    return await get_all_progress(user)

@app.post("/api/user/progress")
async def update_user_progress_alias(req: ProgressReq, user=Depends(get_current_user)):
    return await update_progress(req, user)

# ============================================================
# QUIZ ROUTES
# ============================================================
@app.post("/api/quiz/submit")
async def submit_quiz(req: QuizSubmitReq, user=Depends(get_current_user)):
    conn = get_db()
    
    # Store answers
    for idx, answer in enumerate(req.answers):
        conn.execute(
            "INSERT INTO quiz_answers (user_id, course_id, question_idx, answer) VALUES (?,?,?,?)",
            (user['id'], req.course_id, idx, answer)
        )
    
    # Update progress
    conn.execute("""
        INSERT INTO course_progress (user_id, course_id, status, quiz_score, quiz_total, updated_at)
        VALUES (?, ?, 'in_progress', 0, ?, datetime('now'))
        ON CONFLICT(user_id, course_id) DO UPDATE SET quiz_total=?, updated_at=datetime('now')
    """, (user['id'], req.course_id, len(req.answers), len(req.answers)))
    
    # Update streak
    today = datetime.now().strftime('%Y-%m-%d')
    conn.execute("""
        INSERT INTO learning_streaks (user_id, date, quiz_taken) VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET quiz_taken = quiz_taken + 1
    """, (user['id'], today))
    
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "course_id": req.course_id,
        "total_questions": len(req.answers),
        "message": "答题已记录！参考答案可在课程页面查看。"
    }

# ============================================================
# NOTES & BOOKMARKS
# ============================================================
@app.get("/api/notes")
async def get_notes(course_id: int = None, user=Depends(get_current_user)):
    conn = get_db()
    if course_id:
        rows = conn.execute("SELECT * FROM user_notes WHERE user_id=? AND course_id=? ORDER BY created_at DESC", (user['id'], course_id)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM user_notes WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (user['id'],)).fetchall()
    conn.close()
    return {"notes": [dict(r) for r in rows]}

@app.post("/api/notes")
async def create_note(req: NoteReq, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("INSERT INTO user_notes (user_id, course_id, content) VALUES (?,?,?)",
                 (user['id'], req.course_id, req.content))
    conn.commit()
    conn.close()
    return {"success": True}

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("DELETE FROM user_notes WHERE id=? AND user_id=?", (note_id, user['id']))
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/bookmarks")
async def get_bookmarks(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM user_bookmarks WHERE user_id=? ORDER BY created_at DESC", (user['id'],)).fetchall()
    conn.close()
    bookmarks = []
    for row in rows:
        data = dict(row)
        course = course_public_from_ref(
            data["course_id"],
            data.get("title") or "",
            data.get("lesson") or "",
            bool(data.get("is_book_course")),
            user,
        )
        bookmarks.append({
            "id": data["id"],
            **course,
            "createdAt": data.get("created_at"),
            "updatedAt": data.get("updated_at") or data.get("created_at"),
        })
    return {"bookmarks": bookmarks, "total": len(bookmarks)}

@app.get("/api/bookmarks/status/{course_id}")
async def get_bookmark_status(course_id: int, user=Depends(get_current_user)):
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM user_bookmarks WHERE user_id=? AND course_id=?",
        (user['id'], course_id)
    ).fetchone()
    conn.close()
    return {"bookmarked": bool(existing), "courseRef": course_id}

@app.post("/api/bookmarks")
async def toggle_bookmark_payload(req: BookmarkReq, user=Depends(get_current_user)):
    course_ref = course_ref_from_payload(req.course_id, req.lesson or "", bool(req.is_book_course))
    course = course_public_from_ref(course_ref, req.title or "", req.lesson or "", bool(req.is_book_course), user)
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM user_bookmarks WHERE user_id=? AND course_id=?",
        (user['id'], course_ref)
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM user_bookmarks WHERE id=?", (existing['id'],))
        conn.commit()
        conn.close()
        return {"success": True, "bookmarked": False, "bookmark": course}
    conn.execute("""
        INSERT INTO user_bookmarks (user_id, course_id, lesson, title, is_book_course, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (
        user['id'], course_ref, course["lesson"], course["title"], 1 if course["isBookCourse"] else 0,
    ))
    conn.commit()
    conn.close()
    return {"success": True, "bookmarked": True, "bookmark": course}

@app.post("/api/bookmarks/{course_id}")
async def toggle_bookmark(course_id: int, user=Depends(get_current_user)):
    conn = get_db()
    existing = conn.execute("SELECT id FROM user_bookmarks WHERE user_id=? AND course_id=?", (user['id'], course_id)).fetchone()
    if existing:
        conn.execute("DELETE FROM user_bookmarks WHERE id=?", (existing['id'],))
        conn.commit(); conn.close()
        return {"success": True, "bookmarked": False}
    else:
        course = course_public_from_ref(course_id, user=user)
        conn.execute("""
            INSERT INTO user_bookmarks (user_id, course_id, lesson, title, is_book_course, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (user['id'], course_id, course["lesson"], course["title"], 1 if course["isBookCourse"] else 0))
        conn.commit(); conn.close()
        return {"success": True, "bookmarked": True}

@app.get("/api/study-notes")
async def get_study_notes(limit: int = 100, user=Depends(get_current_user)):
    safe_limit = max(1, min(limit, 200))
    conn = get_db()
    rows = conn.execute("""
        SELECT id, lesson, course_id, is_book_course, score, max_score,
               feedback, reflection_text, ai_analysis_json, ai_followups_json,
               ai_status, created_at
        FROM practice_attempts
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT ?
    """, (user["id"], safe_limit)).fetchall()
    conn.close()

    notes = []
    for row in rows:
        data = dict(row)
        ai_analysis = safe_json_loads(data.get("ai_analysis_json"), {})
        followups = safe_json_loads(data.get("ai_followups_json"), [])
        course = course_public_from_ref(
            data["course_id"],
            lesson=data.get("lesson") or "",
            is_book_course=bool(data.get("is_book_course")),
            user=user,
        )
        notes.append({
            "id": data["id"],
            **course,
            "score": data.get("score") or 0,
            "maxScore": data.get("max_score") or 100,
            "reflection": data.get("reflection_text") or "",
            "agentFeedback": data.get("feedback") or "",
            "aiStatus": data.get("ai_status") or ai_analysis.get("status", ""),
            "aiFeedback": ai_analysis.get("feedback") or ai_analysis.get("message") or "",
            "focusPoints": ai_analysis.get("focusPoints") or [],
            "followUps": followups if isinstance(followups, list) else [],
            "createdAt": data.get("created_at"),
        })
    return {"notes": notes, "total": len(notes)}

# ============================================================
# PAYMENT ROUTES
# ============================================================
@app.get("/api/plans")
async def get_plans():
    return {
        "plans": {plan_id: plan_public(plan_id, plan) for plan_id, plan in PLANS.items()},
        "payment": payment_config(),
    }

@app.get("/api/membership/plans")
async def get_membership_plans():
    grouped = [
        plan_public("core_year", PLANS["core_year"]),
        plan_public("books_year", PLANS["books_year"]),
        plan_public("bundle_year", PLANS["bundle_year"]),
    ]
    return {
        "plans": grouped,
        "free": plan_public("free", PLANS["free"]),
        "payment": payment_config(),
        "revenueModes": [
            {"key": "subscription", "name": "课程订阅", "desc": "主干课程、书目课程可单独订阅，也可升级打包"},
            {"key": "purchased_books", "name": "已购买的图书", "desc": "展示用户已购买和待同步的图书明细"},
        ],
    }

@app.get("/api/payment/config")
async def get_payment_config():
    return payment_config()

@app.get("/api/payment/diagnostics")
async def get_payment_diagnostics(days: int = 7):
    return payment_diagnostics(days)

@app.post("/api/payment/config")
async def save_payment_config(req: PaymentConfigReq, request: Request):
    require_payment_admin_token(request, "缺少微信支付配置权限")
    result = write_payment_config(req.dict())
    return {
        "success": True,
        "config": result,
        "diagnostics": payment_diagnostics(),
        "message": "微信支付配置已写入受保护的服务器文件，响应不会回显商户私钥或 APIv3 Key。配置完整后可进行小程序 JSAPI 支付测试。",
    }

@app.post("/api/payment/create")
async def create_payment(req: PaymentReq, user=Depends(get_current_user)):
    if req.plan not in PLANS:
        raise HTTPException(400, "无效的套餐")
    
    plan = PLANS[req.plan]
    if plan['price'] == 0:
        raise HTTPException(400, "免费套餐无需支付")

    provider = req.method or "wechat"
    out_trade_no = order_no()
    amount_fen = int(plan.get("amount_fen", int(plan["price"] * 100)))
    expires = (datetime.now() + timedelta(minutes=30)).isoformat()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO payments (
            user_id, order_no, plan, amount, amount_fen, method, provider,
            status, entitlement_scope, expires_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, datetime('now'))
        """,
        (user['id'], out_trade_no, req.plan, plan['price'], amount_fen, provider, provider, plan.get("scope"), expires)
    )
    conn.commit()

    base_resp = {
        "success": True,
        "order_no": out_trade_no,
        "plan": req.plan,
        "plan_name": plan['name'],
        "amount": plan['price'],
        "amountFen": amount_fen,
        "method": provider,
        "paymentReady": payment_config()["ready"],
        "expiresAt": expires,
    }

    if provider != "wechat":
        conn.close()
        return {**base_resp, "mode": "unsupported", "message": "当前小程序仅预置微信支付 JSAPI"}

    pay_config = payment_config()
    if not pay_config["ready"]:
        conn.close()
        return {
            **base_resp,
            "mode": "pending_config",
            "message": "订单已创建；请先配置微信支付商户号、证书序列号和商户私钥后再发起真实扣款",
        }

    if not user.get("wechat_openid"):
        conn.close()
        raise HTTPException(400, "当前账号缺少微信 openid，请在小程序内重新登录后支付")

    runtime = payment_runtime_config()
    payload = {
        "appid": WECHAT_MINIAPP_APPID,
        "mchid": runtime["mchid"],
        "description": f"康波研究院-{plan['name']}",
        "out_trade_no": out_trade_no,
        "notify_url": runtime["notifyUrl"],
        "amount": {"total": amount_fen, "currency": "CNY"},
        "payer": {"openid": user["wechat_openid"]},
        "attach": json.dumps({"plan": req.plan, "scope": plan.get("scope")}, ensure_ascii=False),
    }
    wx_order = call_wechat_jsapi_order(payload)
    prepay_id = wx_order.get("prepay_id")
    if not prepay_id:
        conn.close()
        raise HTTPException(502, "微信支付未返回 prepay_id")
    pay_params = build_request_payment_params(prepay_id, runtime)
    conn.execute(
        "UPDATE payments SET prepay_id=?, payment_payload=?, updated_at=datetime('now') WHERE order_no=?",
        (prepay_id, json.dumps(wx_order, ensure_ascii=False), out_trade_no)
    )
    conn.commit()
    conn.close()
    return {
        **base_resp,
        "mode": "wechat_jsapi",
        "prepayId": prepay_id,
        "payParams": pay_params,
    }

@app.post("/api/payment/wechat/notify")
async def wechat_payment_notify(request: Request):
    payload = await request.json()
    resource = payload.get("resource") or {}
    transaction = decrypt_wechat_resource(resource)
    out_trade_no = transaction.get("out_trade_no")
    trade_state = transaction.get("trade_state")
    transaction_id = transaction.get("transaction_id", "")
    if not out_trade_no:
        return JSONResponse(status_code=400, content={"code": "FAIL", "message": "缺少 out_trade_no"})

    conn = get_db()
    payment = conn.execute("SELECT * FROM payments WHERE order_no=?", (out_trade_no,)).fetchone()
    if not payment:
        conn.close()
        return JSONResponse(status_code=404, content={"code": "FAIL", "message": "订单不存在"})
    if trade_state == "SUCCESS":
        apply_paid_order(conn, dict(payment), transaction_id, transaction)
    else:
        conn.execute(
            "UPDATE payments SET status=?, notify_payload=?, updated_at=datetime('now') WHERE order_no=?",
            (trade_state.lower() if trade_state else "notified", json.dumps(transaction, ensure_ascii=False), out_trade_no)
        )
    conn.commit()
    conn.close()
    return {"code": "SUCCESS", "message": "成功"}

@app.get("/api/payment/status/{order_no}")
async def payment_status(order_no: str, user=Depends(get_current_user)):
    conn = get_db()
    payment = conn.execute("SELECT * FROM payments WHERE order_no=? AND user_id=?", (order_no, user['id'])).fetchone()
    if not payment:
        conn.close()
        raise HTTPException(404, "订单不存在")
    payment = dict(payment)
    sync_status = ""
    if payment["status"] != "paid" and payment_config()["ready"] and payment.get("provider") == "wechat":
        try:
            transaction = query_wechat_order(payment["order_no"])
            trade_state = transaction.get("trade_state") or ""
            sync_status = trade_state or "UNKNOWN"
            if trade_state == "SUCCESS":
                apply_paid_order(conn, payment, transaction.get("transaction_id", ""), transaction)
                conn.commit()
                payment = dict(conn.execute("SELECT * FROM payments WHERE order_no=?", (order_no,)).fetchone())
            elif trade_state and trade_state not in ("USERPAYING", "NOTPAY"):
                conn.execute(
                    "UPDATE payments SET status=?, notify_payload=?, updated_at=datetime('now') WHERE order_no=?",
                    (trade_state.lower(), json.dumps(transaction, ensure_ascii=False), order_no)
                )
                conn.commit()
                payment = dict(conn.execute("SELECT * FROM payments WHERE order_no=?", (order_no,)).fetchone())
        except HTTPException:
            sync_status = "QUERY_FAILED"
    conn.close()
    return {
        "order_no": payment["order_no"],
        "plan": payment["plan"],
        "status": payment["status"],
        "paid": payment["status"] == "paid",
        "paidAt": payment.get("paid_at"),
        "amount": payment["amount"],
        "amountFen": payment.get("amount_fen"),
        "syncStatus": sync_status,
    }

@app.post("/api/payment/confirm/{order_no}")
async def confirm_payment(order_no: str, request: Request, user=Depends(get_current_user)):
    """开发/运营后台手工确认。默认关闭，避免用户自行确认订单。"""
    token = request.headers.get("X-Payment-Admin-Token", "")
    if not PAYMENT_ADMIN_TOKEN or token != PAYMENT_ADMIN_TOKEN:
        raise HTTPException(403, "手工确认已关闭")
    conn = get_db()
    payment = conn.execute("SELECT * FROM payments WHERE order_no=? AND user_id=?", (order_no, user['id'])).fetchone()
    if not payment:
        conn.close()
        raise HTTPException(404, "订单不存在")
    result = apply_paid_order(conn, dict(payment), "manual-confirm")
    conn.commit()
    conn.close()
    return {"success": True, "message": "已手工确认", **result}

@app.get("/api/payment/history")
async def payment_history(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC", (user['id'],)).fetchall()
    conn.close()
    return {"payments": [dict(r) for r in rows]}

# ============================================================
# COURSE ACCESS CONTROL
# ============================================================
def can_access_course(user_plan: str, course_id: int) -> bool:
    if public_access_open():
        return True
    plan_courses = PLANS.get(user_plan, {}).get('courses', [])
    scope = PLANS.get(user_plan, {}).get("scope")
    return scope in ("core", "bundle") or course_id in plan_courses

@app.get("/api/courses")
async def get_courses(user_plan: str = "free", authorization: str = Header(None)):
    user = user_from_authorization(authorization)
    courses = []
    seen = set()
    if COURSES_DIR.exists():
        for f in sorted(COURSES_DIR.glob("*.md")):
            record = course_record_from_markdown(f)
            if not record:
                continue
            cid = record["id"]
            if cid < 1 or cid > 65 or cid in seen:
                continue
            seen.add(cid)
            accessible = can_access_core_course(user, cid) if user else can_access_course(user_plan, cid)
            free = public_access_open() or cid in FREE_CORE_COURSES
            record["accessible"] = accessible
            record["locked"] = not accessible
            record["free"] = free
            record["accessType"] = "free" if free else ("member" if accessible else "paid")
            record["requiredPlan"] = None if accessible else "core_year"
            courses.append(record)
    return {"courses": courses, "total": len(courses)}

@app.get("/api/courses/{course_id}")
async def get_course(course_id: int, authorization: str = Header(None)):
    user = user_from_authorization(authorization)
    
    candidates = list(COURSES_DIR.glob(f"{course_id:02d}-*.md")) + list(COURSES_DIR.glob(f"{course_id}-*.md"))
    if candidates:
        f = sorted(candidates)[0]
        accessible = can_access_core_course(user, course_id)
        free = public_access_open() or course_id in FREE_CORE_COURSES
        record = course_record_from_markdown(f) or {"id": course_id, "title": f.stem}
        record.update({
            "content": f.read_text(encoding="utf-8") if accessible else "",
            "filename": f.name,
            "accessible": accessible,
            "locked": not accessible,
            "free": free,
            "accessType": "free" if free else ("member" if accessible else "paid"),
            "requiredPlan": None if accessible else "core_year",
        })
        return record
    raise HTTPException(404, "课程不存在")

@app.get("/api/course-content/{lesson}")
async def get_course_content(lesson: str, authorization: str = Header(None)):
    match = re.fullmatch(r"lesson(\d+)\.html", lesson)
    if not match:
        raise HTTPException(400, "课程文件名不合法")
    course_id = int(match.group(1))
    user = user_from_authorization(authorization)
    accessible = can_access_core_course(user, course_id)
    if not accessible:
        return {
            "lesson": lesson,
            "courseId": course_id,
            "content": "",
            "accessible": False,
            "locked": True,
            "free": False,
            "accessType": "paid",
            "requiredPlan": "core_year",
            "message": "订阅主干课程年卡或全库升级包后可继续学习",
        }
    page = FRONTEND_DIR / lesson
    if not page.exists():
        raise HTTPException(404, "课程内容不存在")
    audio_url = audio_url_from_page(page, [f"audio/lesson{course_id}.mp3"])
    course_record = course_record_from_markdown(sorted(
        list(COURSES_DIR.glob(f"{course_id:02d}-*.md")) + list(COURSES_DIR.glob(f"{course_id}-*.md"))
    )[0]) if COURSES_DIR.exists() and (
        list(COURSES_DIR.glob(f"{course_id:02d}-*.md")) + list(COURSES_DIR.glob(f"{course_id}-*.md"))
    ) else None
    return {
        "lesson": lesson,
        "courseId": course_id,
        "title": (course_record or {}).get("title", ""),
        "content": html_article_from_page(page, strip_practice=True),
        "recommendedBooks": recommended_books_from_page(page, course_id),
        "audioUrl": audio_url,
        "audioAvailable": bool(audio_url),
        "practiceAvailable": True,
        "accessible": True,
        "locked": False,
        "free": public_access_open() or course_id in FREE_CORE_COURSES,
        "accessType": "free" if (public_access_open() or course_id in FREE_CORE_COURSES) else "member",
    }

@app.get("/api/book-course-content/{lesson}")
async def get_book_course_content(lesson: str, authorization: str = Header(None)):
    match = re.fullmatch(r"book(\d+)\.html", lesson)
    if not match:
        raise HTTPException(400, "书目课程文件名不合法")
    book_id = int(match.group(1))
    user = user_from_authorization(authorization)
    accessible = can_access_book_course(user, book_id)
    if not accessible:
        return {
            "lesson": lesson,
            "bookId": book_id,
            "content": "",
            "accessible": False,
            "locked": True,
            "free": False,
            "accessType": "paid",
            "requiredPlan": "books_year",
            "message": "订阅书目课程年卡或全库升级包后可继续学习",
        }
    page = FRONTEND_DIR / lesson
    if not page.exists():
        raise HTTPException(404, "书目课程内容不存在")
    audio_url = audio_url_from_page(page, [f"audio/books/lesson{book_id}.mp3"], expected_path=f"audio/books/lesson{book_id}.mp3")
    return {
        "lesson": lesson,
        "bookId": book_id,
        "content": html_article_from_page(page, strip_practice=True),
        "title": book_course_title(book_id),
        "audioUrl": audio_url,
        "audioAvailable": bool(audio_url),
        "practiceAvailable": True,
        "accessible": True,
        "locked": False,
        "free": public_access_open() or book_id in FREE_BOOK_COURSES,
        "accessType": "free" if (public_access_open() or book_id in FREE_BOOK_COURSES) else "member",
    }

@app.get("/api/practice/{lesson}")
async def get_lesson_practice(lesson: str, authorization: str = Header(None)):
    meta = resolve_lesson(lesson)
    user = user_from_authorization(authorization)
    if not can_access_lesson(user, meta):
        return {
            "lesson": lesson,
            "locked": True,
            "accessible": False,
            "requiredPlan": meta["requiredPlan"],
            "message": "订阅后可完成互动练习并记录每日精进",
        }
    page = meta["page"]
    if not page.exists():
        raise HTTPException(404, "课程内容不存在")
    practice = build_practice_questions(page, lesson)
    return {
        **practice,
        "locked": False,
        "accessible": True,
        "free": lesson_free(meta),
        "isBookCourse": meta["isBookCourse"],
        "badgeSystem": BADGE_CATALOG,
    }

@app.post("/api/practice/submit")
async def submit_practice(req: PracticeSubmitReq, user=Depends(get_current_user)):
    meta = resolve_lesson(req.lesson)
    if not can_access_lesson(user, meta):
        raise HTTPException(403, "订阅后可提交练习")
    page = meta["page"]
    if not page.exists():
        raise HTTPException(404, "课程内容不存在")

    practice = build_practice_questions(page, req.lesson)
    questions = practice["questions"]
    keywords = practice["keywords"]
    answers = req.answers or {}
    reflection = (req.reflection or "").strip()[:2000]
    results = []
    for question in questions:
        answer = answers.get(question["id"], "")
        scored = score_answer(answer, question.get("keywords") or keywords)
        results.append({
            "questionId": question["id"],
            "title": question["title"],
            "answer": answer,
            **scored,
        })
    overall = round(sum(item["score"] for item in results) / max(1, len(results)))
    feedback = build_agent_feedback(overall, results, keywords)
    ai_analysis = build_practice_ai_analysis(user, meta, practice, results, overall, reflection)
    today = datetime.now().strftime("%Y-%m-%d")
    minutes = max(5, len(questions) * 4)

    conn = get_db()
    attempts_before = conn.execute(
        "SELECT COUNT(*) AS c FROM practice_attempts WHERE user_id=?",
        (user["id"],)
    ).fetchone()["c"]
    cursor = conn.execute("""
        INSERT INTO practice_attempts (
            user_id, lesson, course_id, is_book_course, score, max_score,
            answers_json, results_json, feedback, reflection_text,
            ai_analysis_json, ai_followups_json, ai_status
        )
        VALUES (?, ?, ?, ?, ?, 100, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user["id"], req.lesson, meta["courseRef"], 1 if meta["isBookCourse"] else 0,
        overall, json.dumps(answers, ensure_ascii=False),
        json.dumps(results, ensure_ascii=False), feedback, reflection,
        json.dumps(ai_analysis, ensure_ascii=False),
        json.dumps(ai_analysis.get("followUps", []), ensure_ascii=False),
        ai_analysis.get("status", ""),
    ))
    attempt_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO course_progress (
            user_id, course_id, status, progress_percent, quiz_score, quiz_total, started_at, updated_at
        )
        VALUES (?, ?, 'in_progress', 100, ?, 100, datetime('now'), datetime('now'))
        ON CONFLICT(user_id, course_id) DO UPDATE SET
            progress_percent=MAX(progress_percent, 100),
            quiz_score=?,
            quiz_total=100,
            updated_at=datetime('now')
    """, (user["id"], meta["courseRef"], overall, overall))
    conn.execute("""
        INSERT INTO learning_streaks (user_id, date, quiz_taken)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET quiz_taken = quiz_taken + 1
    """, (user["id"], today))
    conn.execute("""
        INSERT INTO daily_refinements (user_id, date, practice_count, score_total, minutes, updated_at)
        VALUES (?, ?, 1, ?, ?, datetime('now'))
        ON CONFLICT(user_id, date) DO UPDATE SET
            practice_count = practice_count + 1,
            score_total = score_total + excluded.score_total,
            minutes = minutes + excluded.minutes,
            updated_at = datetime('now')
    """, (user["id"], today, overall, minutes))

    total_attempts = attempts_before + 1
    streak = consecutive_practice_days(conn, user["id"])
    badge_keys = ["daily_refiner_1"]
    if attempts_before == 0:
        badge_keys.append("first_practice")
    if overall >= 80:
        badge_keys.append("sharp_80")
    if overall >= 90:
        badge_keys.append("mastery_90")
    if lesson_free(meta):
        badge_keys.append("book_spark" if meta["isBookCourse"] else "core_spark")
    if total_attempts >= 3:
        badge_keys.append("three_practices")
    if streak >= 3:
        badge_keys.append("streak_3")
    if streak >= 7:
        badge_keys.append("streak_7")

    badges_earned = award_badges(conn, user["id"], badge_keys)
    if badges_earned:
        conn.execute(
            "UPDATE daily_refinements SET badges_earned = badges_earned + ? WHERE user_id=? AND date=?",
            (len(badges_earned), user["id"], today)
        )
        conn.execute(
            "UPDATE practice_attempts SET badges_json=? WHERE id=?",
            (json.dumps(badges_earned, ensure_ascii=False), attempt_id)
        )
    daily = conn.execute(
        "SELECT * FROM daily_refinements WHERE user_id=? AND date=?",
        (user["id"], today)
    ).fetchone()
    conn.commit()
    conn.close()

    return {
        "success": True,
        "attemptId": attempt_id,
        "lesson": req.lesson,
        "score": overall,
        "maxScore": 100,
        "results": results,
        "feedback": feedback,
        "reflection": reflection,
        "aiAnalysis": ai_analysis,
        "aiAnalysisStatus": ai_analysis.get("status"),
        "aiAnalysisMessage": ai_analysis.get("message", ""),
        "aiFollowUps": ai_analysis.get("followUps", []),
        "badgesEarned": badges_earned,
        "dailyRefinement": dict(daily) if daily else None,
        "streakDays": streak,
    }

@app.get("/api/daily-refinement")
async def get_daily_refinement(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM daily_refinements
        WHERE user_id=?
        ORDER BY date DESC
        LIMIT 14
    """, (user["id"],)).fetchall()
    attempts = conn.execute("""
        SELECT lesson, score, max_score, feedback, created_at
        FROM practice_attempts
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT 10
    """, (user["id"],)).fetchall()
    streak = consecutive_practice_days(conn, user["id"])
    conn.close()
    return {
        "days": [dict(row) for row in rows],
        "recentAttempts": [dict(row) for row in attempts],
        "streakDays": streak,
    }

@app.get("/api/badges")
async def get_badges(user=Depends(get_current_user)):
    conn = get_db()
    earned_rows = conn.execute(
        "SELECT * FROM user_badges WHERE user_id=? ORDER BY earned_at DESC",
        (user["id"],)
    ).fetchall()
    conn.close()
    earned_map = {row["badge_key"]: dict(row) for row in earned_rows}
    catalog = []
    for key, badge in BADGE_CATALOG.items():
        earned = earned_map.get(key)
        catalog.append({
            "key": key,
            **badge,
            "earned": bool(earned),
            "earnedAt": earned.get("earned_at") if earned else None,
        })
    return {
        "catalog": catalog,
        "earned": [dict(row) for row in earned_rows],
        "totalEarned": len(earned_rows),
    }

@app.get("/api/book-courses")
async def get_book_courses(category: str = "all", wave: int = 0, limit: int = 500, authorization: str = Header(None)):
    user = user_from_authorization(authorization)
    courses = parse_book_courses()
    if category != "all":
        courses = [c for c in courses if c["category"] == category]
    if wave:
        courses = [c for c in courses if get_wave(c["n"]) == wave]
    for course in courses:
        accessible = can_access_book_course(user, course["n"])
        free = public_access_open() or course["n"] in FREE_BOOK_COURSES
        course["accessible"] = accessible
        course["locked"] = not accessible
        course["free"] = free
        course["accessType"] = "free" if free else ("member" if accessible else "paid")
        course["requiredPlan"] = None if accessible else "books_year"
    return {
        "courses": courses[:max(1, min(limit, 500))],
        "total": len(courses),
        "categories": {
            "period": "周期理论", "invest": "投资策略", "risk": "风险管理", "money": "货币金融",
            "demo": "人口经济", "tech": "科技创新", "china": "中国经济", "behavior": "行为经济",
            "wealth": "财富管理", "inequality": "贫富分化", "history": "历史传记", "global": "全球格局",
            "future": "未来趋势", "ai": "AI与认知", "bio": "生物科技", "energy": "能源气候",
            "geo": "地缘安全", "science": "前沿科学", "east": "东方智慧"
        },
        "waves": [
            {"w": idx, "range": [start, end]}
            for idx, (start, end) in enumerate([
                (1, 62), (63, 92), (93, 117), (118, 147), (148, 177),
                (178, 207), (208, 238), (239, 268), (269, 298), (299, 328),
                (329, 336), (337, 363), (364, 390), (391, 418), (419, 445),
                (446, 472), (473, 500)
            ], 1)
        ]
    }

@app.get("/api/knowledge-graph")
async def get_knowledge_graph():
    if KNOWLEDGE_GRAPH_JSON.exists():
        return json.loads(KNOWLEDGE_GRAPH_JSON.read_text(encoding="utf-8"))
    fallback = FRONTEND_DIR / "knowledge-base.json"
    if fallback.exists():
        return json.loads(fallback.read_text(encoding="utf-8"))
    raise HTTPException(404, "知识图谱数据不存在")

@app.post("/api/search")
async def search(req: SearchReq):
    keyword = req.keyword.strip().lower()
    if not keyword:
        return {"results": [], "total": 0}

    results = []
    for course in (await get_courses()).get("courses", []):
        haystack = f"{course['title']} {course.get('filename', '')}".lower()
        if keyword in haystack:
            results.append({"type": "course", **course})

    for book in parse_book_courses():
        haystack = f"{book['title']} {book['author']} {book['category']}".lower()
        if keyword in haystack:
            results.append({"type": "book_course", **book})

    return {"results": results[:50], "total": len(results)}

@app.get("/api/recommendations")
async def get_recommendations():
    courses = (await get_courses()).get("courses", [])
    books = parse_book_courses()
    return {
        "courses": courses[:6],
        "book_courses": books[:12],
        "tools": [
            {"name": "康波计算器", "path": "/pages/tools/calculator"},
            {"name": "资产轮动", "path": "/pages/tools/asset-rotation"},
            {"name": "四维评分", "path": "/pages/tools/radar"},
            {"name": "排名榜", "path": "/pages/tools/ranking"},
        ]
    }

def audio_playlist_tracks(scope: str = "all") -> list[dict]:
    scope = (scope or "all").strip().lower()
    tracks: list[dict] = []
    include_core = scope in ("all", "core", "main")
    include_books = scope in ("all", "book", "books")

    if include_core and COURSES_DIR.exists():
        seen = set()
        for f in sorted(COURSES_DIR.glob("*.md")):
            record = course_record_from_markdown(f)
            if not record:
                continue
            cid = int(record["id"])
            if cid < 1 or cid > 65 or cid in seen:
                continue
            seen.add(cid)
            audio_rel = f"audio/lesson{cid}.mp3"
            if not (FRONTEND_DIR / audio_rel).exists():
                continue
            tracks.append({
                "id": f"core-{cid}",
                "type": "core",
                "typeLabel": "主干课程",
                "courseId": cid,
                "title": record.get("title") or f"第 {cid} 课",
                "lesson": f"lesson{cid}.html",
                "audio": audio_rel,
                "audioUrl": public_url(audio_rel),
                "audioAvailable": True,
            })

    if include_books:
        for course in parse_book_courses():
            book_id = int(course.get("n") or course.get("id") or 0)
            if not book_id:
                continue
            audio_rel = f"audio/books/lesson{book_id}.mp3"
            if not (FRONTEND_DIR / audio_rel).exists():
                continue
            tracks.append({
                "id": f"book-{book_id}",
                "type": "book",
                "typeLabel": "书目课程",
                "courseId": book_id,
                "title": course.get("title") or course.get("t") or f"书目课程 {book_id}",
                "author": course.get("author") or course.get("a") or "",
                "lesson": f"book{book_id}.html",
                "audio": audio_rel,
                "audioUrl": public_url(audio_rel),
                "audioAvailable": True,
                "wave": get_wave(book_id),
                "category": course.get("category") or course.get("c") or "",
            })
    return tracks

@app.get("/api/audio-playlist")
async def get_audio_playlist(scope: str = "all", limit: int = 0):
    all_tracks = audio_playlist_tracks(scope)
    total = len(all_tracks)
    counts = {
        "core": sum(1 for item in all_tracks if item["type"] == "core"),
        "book": sum(1 for item in all_tracks if item["type"] == "book"),
    }
    tracks = all_tracks
    if limit and limit > 0:
        tracks = tracks[:min(limit, 565)]
    return {
        "scope": scope,
        "tracks": tracks,
        "total": total,
        "returned": len(tracks),
        "counts": counts,
        "message": "连续播放清单已包含可用的主干课程和书目课程音频",
    }

@app.get("/api/live/readiness")
async def get_live_readiness():
    return digital_live_config()

@app.get("/api/live/diagnostics")
async def get_live_diagnostics():
    return digital_live_diagnostics()

@app.post("/api/live/config")
async def save_live_config(req: LiveConfigReq, request: Request):
    require_payment_admin_token(request, "缺少数字人推流配置权限")
    result = write_live_env_config(req.model_dump())
    return {
        "success": True,
        "config": result,
        "diagnostics": digital_live_diagnostics(),
        "message": "RTMP 密钥已写入受保护的服务器环境文件，响应不会回显任何密钥值。启动或重启推流服务后生效。",
        "commands": live_service_commands(),
    }


PROMO_THEMES = [
    {"focus": "认知入口", "headline": "普通人如何看懂下一轮财富周期", "hook": "别先问买什么，先问自己处在什么周期位置。"},
    {"focus": "方法论入口", "headline": "别只问涨跌，先问周期在哪里", "hook": "同一个资产，在不同周期里风险收益完全不同。"},
    {"focus": "课程入口", "headline": "65门主干课程如何学", "hook": "每天15分钟，把宏观判断拆成可以复述的观察清单。"},
    {"focus": "书目入口", "headline": "500本书目精读怎么用", "hook": "一本书给洞见，一组书给结构，书目课程给你知识地图。"},
    {"focus": "购买入口", "headline": "适合系统学习康波框架的3类人", "hook": "长期投资者、知识服务者、宏观学习者，都需要稳定框架。"},
    {"focus": "互动入口", "headline": "用100字判断你现在的周期位置", "hook": "写下周期位置、关键证据、反方信号和下一步行动。"},
    {"focus": "转化入口", "headline": "7天试学后，下一步怎么选", "hook": "免费课看兴趣，主干课建框架，书目课补底层，全库包适合系统学。"},
]

def promo_china_today() -> datetime:
    return datetime.utcnow() + timedelta(hours=8)

def parse_promo_date(value: str = "") -> datetime:
    if not value:
        return promo_china_today()
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except Exception:
        return promo_china_today()

def promo_week_start() -> datetime:
    raw = os.getenv("LAUNCH_WEEK_START", "2026-05-28")
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    except Exception:
        return promo_china_today()

def promo_url(path: str, source: str, campaign: str, content: str = "") -> str:
    query = {"utm_source": source, "utm_campaign": campaign}
    if content:
        query["utm_content"] = content
    return f"{PUBLIC_BASE_URL.rstrip('/')}/{path.lstrip('/')}?{parse.urlencode(query)}"

def cn_book_title(value: str) -> str:
    clean = str(value or "").strip()
    if clean.startswith("《") and clean.endswith("》"):
        return clean
    return f"《{clean}》" if clean else "《推荐书目》"

def promo_item_for_day(day_date: datetime, day_number: int, core_tracks: list[dict], book_tracks: list[dict]) -> dict:
    theme = PROMO_THEMES[(day_number - 1) % len(PROMO_THEMES)]
    core = core_tracks[(day_number - 1) % len(core_tracks)] if core_tracks else {
        "title": "康波理论基础",
        "courseId": 1,
        "lesson": "lesson1.html",
        "audioUrl": public_url("audio/lesson1.mp3"),
    }
    book = book_tracks[((day_number - 1) * 17) % len(book_tracks)] if book_tracks else {
        "title": "推荐书目课程",
        "courseId": 1,
        "lesson": "book1.html",
        "author": "",
    }
    campaign = f"week{((day_number - 1) // 7) + 1}_day{((day_number - 1) % 7) + 1}"
    focus_key = parse.quote(theme["focus"])
    landing = promo_url("xhs.html", "xhs", campaign, theme["focus"])
    purchase = promo_url("purchase-intent.html", "xhs", campaign, "bundle")
    book_shop = promo_url("book-shop.html", "xhs", campaign, "books")
    digital_live = promo_url("digital-human-obs.html", "digital_human", campaign, "live")
    core_url = promo_url(core.get("lesson") or "lesson1.html", "xhs", campaign, "core")
    book_url = promo_url(book.get("lesson") or "book1.html", "xhs", campaign, "book")
    title = theme["headline"]
    core_title = core.get("title") or "主干课程"
    book_title = book.get("title") or "书目课程"
    core_name = cn_book_title(core_title)
    book_name = cn_book_title(book_title)
    post_copy = (
        f"{title}\n\n"
        f"{theme['hook']}\n\n"
        f"今天主干课建议听：{core_name}。\n"
        f"配套书目建议看：{book_name}。\n\n"
        "学习顺序很简单：先听一节课，再写下一个判断，再用一本书补证据。\n\n"
        "康波研究院已经整理好65门主干课程、500门书目课程和565节连续音频，适合每天15分钟系统学习。\n\n"
        f"今日行动：打开试学入口，听完第一课后登记全库升级包购买意向。\n\n"
        f"试学入口：{landing}\n"
        f"购买意向：{purchase}\n"
        "评论关键词：康波"
    )
    video_script = (
        f"开头3秒：{theme['hook']}\n\n"
        f"正文：今天用{core_name}这节课建立一个判断框架，再用{book_name}补充底层知识。"
        "不要只看短期价格，要同时看技术扩散、信用周期、人口结构和政策方向。"
        "能把证据和反方信号讲清楚，才是真正开始建立周期判断力。\n\n"
        "结尾：康波研究院已经把65门主干课程和500门书目课程做成连续音频，先试学，再决定是否系统学习。"
    )
    dm_script = (
        f"你好，今天的康波试学路线在这里：{landing} 。"
        f"建议先听{core_name}，再看{book_name}。"
        f"如果你想系统学习，可以在这里留下全库升级包购买意向：{purchase}"
    )
    live_script = (
        f"欢迎来到康波研究院数字人课堂。今天主题是“{title}”。"
        f"本小时先讲主干课{core_name}，再推荐书目{book_name}。"
        "请在评论区写下四句话：周期位置、关键证据、反方信号、下一步行动。"
    )
    douyin_url = promo_url("xhs.html", "douyin", campaign, theme["focus"])
    douyin_purchase = promo_url("purchase-intent.html", "douyin", campaign, "bundle")
    channels_url = promo_url("xhs.html", "wechat_channels", campaign, theme["focus"])
    channels_purchase = promo_url("purchase-intent.html", "wechat_channels", campaign, "bundle")
    platform_contents = {
        "xhs": {
            "name": "小红书",
            "primaryCopy": post_copy,
            "videoScript": video_script,
            "dmScript": dm_script,
            "liveScript": live_script,
            "landingUrl": landing,
            "purchaseIntentUrl": purchase,
            "bookShopUrl": book_shop,
            "hashtags": ["康波周期", "读书方法", "长期主义", "资产配置"],
            "publishHint": "图文用3张素材图，标题保留问题感，评论区引导关键词“康波”。",
        },
        "douyin": {
            "name": "抖音",
            "primaryCopy": (
                f"{theme['hook']}\n\n"
                f"今天用{core_name}讲一个判断框架，再用{book_name}补一条证据链。"
                "别把康波当成玄学，它本质上是长期经济、技术和信用周期的观察工具。\n\n"
                f"完整试学入口：{douyin_url}\n"
                "评论区写“周期位置”，我给你四句话练习模板。"
            ),
            "videoScript": (
                "开场：你以为投资难在选标的，其实难在不知道自己站在哪个周期位置。\n"
                f"中段：今天这条视频，用{core_name}把框架讲清楚，再用{book_name}补底层阅读。"
                "看技术扩散、信用周期、人口结构和政策方向四个变量，少听情绪，多看结构。\n"
                "结尾：康波研究院有65门主干课程和500门书目课程，先试学，再决定是否系统学习。"
            ),
            "dmScript": f"这是今天的康波试学入口：{douyin_url}。如果你想系统学习，全库升级包购买意向页是：{douyin_purchase}",
            "liveScript": (
                f"抖音直播间的朋友，今天主题是“{title}”。"
                f"我会用{core_name}解释周期判断，再用{book_name}补充阅读。"
                "请在评论区写下你的周期位置判断，我用四句话模板帮你拆。"
            ),
            "landingUrl": douyin_url,
            "purchaseIntentUrl": douyin_purchase,
            "bookShopUrl": promo_url("book-shop.html", "douyin", campaign, "books"),
            "hashtags": ["康波周期", "宏观学习", "投资认知", "读书成长"],
            "publishHint": "短视频前3秒直接抛问题，标题用反差句，置顶评论放试学入口。",
        },
        "wechat_channels": {
            "name": "微信视频号",
            "primaryCopy": (
                f"{title}\n\n"
                f"今天建议先听{core_name}，再读{book_name}。"
                "康波研究院把长期周期判断拆成课程、音频、练习和书目，适合每天固定学习。\n\n"
                f"试学入口：{channels_url}\n"
                f"全库升级意向：{channels_purchase}"
            ),
            "videoScript": (
                f"今天分享{core_name}。"
                "这不是预测明天涨跌，而是训练长期判断力。"
                f"如果你想继续补底层知识，配套书目是{book_name}。"
                "欢迎收藏，按30天推广日历每天学一节。"
            ),
            "dmScript": f"今天的视频号试学入口：{channels_url}。先听课程，再按页面填写购买意向或查看书目。",
            "liveScript": (
                f"视频号直播间欢迎大家。今天讲“{title}”，主线课程是{core_name}，延伸书目是{book_name}。"
                "本直播只做教育研究，不承诺收益，不做个股建议。"
            ),
            "landingUrl": channels_url,
            "purchaseIntentUrl": channels_purchase,
            "bookShopUrl": promo_url("book-shop.html", "wechat_channels", campaign, "books"),
            "hashtags": ["康波研究院", "长期学习", "书目精读", "周期框架"],
            "publishHint": "视频号适合更稳的知识型口吻，正文强调教育研究和系统学习。",
        },
    }
    return {
        "date": day_date.strftime("%Y-%m-%d"),
        "dayNumber": day_number,
        "focus": theme["focus"],
        "headline": title,
        "hook": theme["hook"],
        "course": {
            "id": core.get("courseId"),
            "title": core_title,
            "lesson": core.get("lesson"),
            "url": core_url,
            "audioUrl": core.get("audioUrl"),
        },
        "book": {
            "id": book.get("courseId"),
            "title": book_title,
            "author": book.get("author", ""),
            "lesson": book.get("lesson"),
            "url": book_url,
        },
        "urls": {
            "landing": landing,
            "purchaseIntent": purchase,
            "bookShop": book_shop,
            "digitalLive": digital_live,
        },
        "postCopy": post_copy,
        "videoScript": video_script,
        "dmScript": dm_script,
        "liveScript": live_script,
        "platformContents": platform_contents,
        "assets": {
            "cards": [
                public_url("assets/xhs-card-01.png"),
                public_url("assets/xhs-card-02.png"),
                public_url("assets/xhs-card-03.png"),
            ],
            "video": public_url("assets/xhs-week1-video.mp4"),
        },
        "checklist": [
            "发布图文或短视频时使用当天 landing 链接，保留 utm 参数。",
            "评论区引导关键词“康波”，私信发送当天试学入口。",
            "直播间口播使用 liveScript，并把购买意向页放到简介或评论置顶。",
            "发布后2小时查看上线看板，重点看浏览量、购买意向和图书点击。",
        ],
        "shareTags": ["康波周期", "长期主义", "资产配置", "读书方法", "宏观学习"],
        "safeNote": "内容定位为教育研究，不承诺收益，不做个股买卖建议。",
        "focusKey": focus_key,
    }

def promo_item_for_date(date: str = "") -> dict:
    target_date = parse_promo_date(date)
    start = promo_week_start()
    raw_offset = (target_date.date() - start.date()).days
    day_number = raw_offset + 1 if raw_offset >= 0 else 1
    tracks = audio_playlist_tracks("all")
    core_tracks = [item for item in tracks if item.get("type") == "core"]
    book_tracks = [item for item in tracks if item.get("type") == "book"]
    return promo_item_for_day(start + timedelta(days=day_number - 1), day_number, core_tracks, book_tracks)

def promo_csv_response(items: list[dict], generated_at: str) -> Response:
    output = io.StringIO()
    fieldnames = [
        "日期", "第几天", "平台", "主题入口", "主标题", "开场钩子",
        "主干课程ID", "主干课程", "书目ID", "书目", "书目作者",
        "主文案", "短视频口播", "直播口播", "私信话术", "发布建议",
        "标签", "落地页", "购买意向页", "书目购买页", "数字人直播源",
        "安全提示", "生成时间",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in items:
        platform_contents = item.get("platformContents") or {}
        for platform_key in ["xhs", "douyin", "wechat_channels"]:
            content = platform_contents.get(platform_key) or {}
            tags = " ".join(f"#{tag}" for tag in content.get("hashtags", []))
            writer.writerow({
                "日期": item.get("date", ""),
                "第几天": item.get("dayNumber", ""),
                "平台": content.get("name", platform_key),
                "主题入口": item.get("focus", ""),
                "主标题": item.get("headline", ""),
                "开场钩子": item.get("hook", ""),
                "主干课程ID": (item.get("course") or {}).get("id", ""),
                "主干课程": (item.get("course") or {}).get("title", ""),
                "书目ID": (item.get("book") or {}).get("id", ""),
                "书目": (item.get("book") or {}).get("title", ""),
                "书目作者": (item.get("book") or {}).get("author", ""),
                "主文案": content.get("primaryCopy", ""),
                "短视频口播": content.get("videoScript", ""),
                "直播口播": content.get("liveScript", ""),
                "私信话术": content.get("dmScript", ""),
                "发布建议": content.get("publishHint", ""),
                "标签": tags,
                "落地页": content.get("landingUrl", ""),
                "购买意向页": content.get("purchaseIntentUrl", ""),
                "书目购买页": content.get("bookShopUrl", ""),
                "数字人直播源": (item.get("urls") or {}).get("digitalLive", ""),
                "安全提示": item.get("safeNote", ""),
                "生成时间": generated_at,
            })
    csv_text = "\ufeff" + output.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kangbo-promo-30days.csv"'},
    )

def promo_calendar_payload(items: list[dict], generated_at: str) -> dict:
    platform_plan = [
        {
            "key": "xhs",
            "name": "小红书",
            "publishTime": "08:30",
            "format": "图文4卡或50秒短视频",
            "goal": {"views": 70, "clicks": 8, "purchaseIntents": 3},
        },
        {
            "key": "douyin",
            "name": "抖音",
            "publishTime": "12:30",
            "format": "50秒短视频和直播切片",
            "goal": {"views": 50, "clicks": 5, "purchaseIntents": 2},
        },
        {
            "key": "wechat_channels",
            "name": "微信视频号",
            "publishTime": "20:30",
            "format": "知识型短视频和直播预告",
            "goal": {"views": 25, "clicks": 3, "purchaseIntents": 2},
        },
    ]
    rows = []
    for item in items:
        platform_contents = item.get("platformContents") or {}
        day_goal = {
            "views": 145 if item.get("dayNumber", 1) <= 7 else 100,
            "conversionClicks": 22 if item.get("dayNumber", 1) <= 7 else 15,
            "purchaseIntents": 8 if item.get("dayNumber", 1) <= 7 else 5,
            "posts": 3,
        }
        task_rows = []
        for platform in platform_plan:
            content = platform_contents.get(platform["key"]) or {}
            task_rows.append({
                "platform": platform["key"],
                "platformName": platform["name"],
                "publishTime": platform["publishTime"],
                "format": platform["format"],
                "headline": item.get("headline", ""),
                "primaryCopy": content.get("primaryCopy", ""),
                "videoScript": content.get("videoScript", ""),
                "liveScript": content.get("liveScript", ""),
                "dmScript": content.get("dmScript", ""),
                "publishHint": content.get("publishHint", ""),
                "hashtags": content.get("hashtags", []),
                "landingUrl": content.get("landingUrl", ""),
                "purchaseIntentUrl": content.get("purchaseIntentUrl", ""),
                "bookShopUrl": content.get("bookShopUrl", ""),
                "goal": platform["goal"],
            })
        rows.append({
            "date": item.get("date", ""),
            "dayNumber": item.get("dayNumber", ""),
            "focus": item.get("focus", ""),
            "headline": item.get("headline", ""),
            "hook": item.get("hook", ""),
            "course": item.get("course") or {},
            "book": item.get("book") or {},
            "goal": day_goal,
            "tasks": task_rows,
            "assets": item.get("assets") or {},
            "links": item.get("urls") or {},
            "checklist": item.get("checklist") or [],
            "safeNote": item.get("safeNote", ""),
        })
    return {
        "generatedAt": generated_at,
        "weekStart": rows[0]["date"] if rows else promo_week_start().strftime("%Y-%m-%d"),
        "goals": {"weekViews": 1000, "weekPurchases": 50, "dailyPosts": 3},
        "platforms": platform_plan,
        "items": rows,
        "exports": {
            "csv": "/api/promo/calendar?days=30&format=csv",
            "dailyCsv": "/api/promo/daily?days=30&format=csv",
            "todayPack": "/api/promo/publish-pack",
        },
    }

def promo_calendar_csv_response(calendar: dict) -> Response:
    output = io.StringIO()
    fieldnames = [
        "日期", "第几天", "发布时间", "平台", "形式", "主题", "标题", "钩子",
        "主干课程", "书目课程", "目标浏览", "目标点击", "目标意向",
        "文案摘要", "短视频脚本", "直播口播", "私信话术", "发布建议",
        "落地页", "购买意向页", "书目购买页", "标签",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in calendar.get("items") or []:
        course = item.get("course") or {}
        book = item.get("book") or {}
        for task in item.get("tasks") or []:
            goal = task.get("goal") or {}
            writer.writerow({
                "日期": item.get("date", ""),
                "第几天": item.get("dayNumber", ""),
                "发布时间": task.get("publishTime", ""),
                "平台": task.get("platformName", ""),
                "形式": task.get("format", ""),
                "主题": item.get("focus", ""),
                "标题": task.get("headline", ""),
                "钩子": item.get("hook", ""),
                "主干课程": course.get("title", ""),
                "书目课程": book.get("title", ""),
                "目标浏览": goal.get("views", ""),
                "目标点击": goal.get("clicks", ""),
                "目标意向": goal.get("purchaseIntents", ""),
                "文案摘要": task.get("primaryCopy", ""),
                "短视频脚本": task.get("videoScript", ""),
                "直播口播": task.get("liveScript", ""),
                "私信话术": task.get("dmScript", ""),
                "发布建议": task.get("publishHint", ""),
                "落地页": task.get("landingUrl", ""),
                "购买意向页": task.get("purchaseIntentUrl", ""),
                "书目购买页": task.get("bookShopUrl", ""),
                "标签": " ".join(f"#{tag}" for tag in task.get("hashtags", [])),
            })
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kangbo-promo-calendar-30days.csv"'},
    )

def promo_items_for_range(date: str = "", days: int = 30) -> list[dict]:
    days = max(1, min(int(days or 30), 30))
    launch_start = promo_week_start()
    start_date = parse_promo_date(date) if date else launch_start
    raw_offset = (start_date.date() - launch_start.date()).days
    first_day_number = raw_offset + 1 if raw_offset >= 0 else 1
    tracks = audio_playlist_tracks("all")
    core_tracks = [item for item in tracks if item.get("type") == "core"]
    book_tracks = [item for item in tracks if item.get("type") == "book"]
    return [
        promo_item_for_day(launch_start + timedelta(days=first_day_number - 1 + i), first_day_number + i, core_tracks, book_tracks)
        for i in range(days)
    ]

def split_script_lines(script: str, max_lines: int = 8) -> list[str]:
    clean = re.sub(r"\s+", " ", str(script or "").replace("\n", " ")).strip()
    if not clean:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[。！？；.!?])", clean) if part.strip()]
    if not parts:
        parts = [clean]
    lines = []
    current = ""
    for part in parts:
        if len(current) + len(part) <= 34:
            current = (current + part).strip()
        else:
            if current:
                lines.append(current)
            current = part
    if current:
        lines.append(current)
    compact = []
    for line in lines:
        if len(line) <= 72:
            compact.append(line)
        else:
            chunks = [part.strip() for part in re.split(r"(?<=[，、：])", line) if part.strip()]
            if len(chunks) > 1:
                compact.extend(chunks)
            else:
                for i in range(0, len(line), 42):
                    compact.append(line[i:i + 42])
    if len(compact) > max_lines:
        compact = compact[:max_lines]
        compact[-1] = re.sub(r"[，。；,.\\s]+$", "", compact[-1]) + "。"
    return compact

def srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def lines_to_srt(lines: list[str], total_seconds: int = 50) -> str:
    if not lines:
        return ""
    duration = max(2.5, total_seconds / max(1, len(lines)))
    blocks = []
    for idx, line in enumerate(lines, 1):
        start = (idx - 1) * duration
        end = min(total_seconds, idx * duration - 0.12)
        blocks.append(f"{idx}\n{srt_time(start)} --> {srt_time(end)}\n{line}\n")
    return "\n".join(blocks).strip() + "\n"

def promo_video_task(item: dict, platform_key: str) -> dict:
    platform_key = platform_key if platform_key in {"xhs", "douyin", "wechat_channels"} else "douyin"
    content = (item.get("platformContents") or {}).get(platform_key) or {}
    pack = promo_publish_pack(item)
    platform_names = {"xhs": "小红书", "douyin": "抖音", "wechat_channels": "微信视频号"}
    script = content.get("videoScript") or item.get("videoScript") or ""
    captions = split_script_lines(script)
    srt = lines_to_srt(captions)
    links = {
        "landing": content.get("landingUrl", ""),
        "purchaseIntent": content.get("purchaseIntentUrl", ""),
        "bookShop": content.get("bookShopUrl", ""),
        "digitalLive": (item.get("urls") or {}).get("digitalLive", ""),
    }
    teleprompter = "\n\n".join([
        f"{platform_names.get(platform_key, platform_key)}短视频提词稿",
        f"日期：{item.get('date', '')}",
        f"标题：{item.get('headline', '')}",
        f"主干课程：{(item.get('course') or {}).get('title', '')}",
        f"书目课程：{(item.get('book') or {}).get('title', '')}",
        script,
        "发布后动作：复制落地页到正文或置顶评论，评论区引导关键词“康波”。",
        f"落地页：{links['landing']}",
        f"购买意向：{links['purchaseIntent']}",
        f"书目购买：{links['bookShop']}",
        item.get("safeNote", ""),
    ]).strip() + "\n"
    return {
        "date": item.get("date", ""),
        "dayNumber": item.get("dayNumber", ""),
        "platform": platform_key,
        "platformName": platform_names.get(platform_key, platform_key),
        "headline": item.get("headline", ""),
        "hook": item.get("hook", ""),
        "course": item.get("course") or {},
        "book": item.get("book") or {},
        "videoScript": script,
        "teleprompter": teleprompter,
        "captions": captions,
        "srt": srt,
        "storyboard": (pack.get("video") or {}).get("storyboard", []),
        "links": links,
        "hashtags": content.get("hashtags", []),
        "publishHint": content.get("publishHint", ""),
        "safeNote": item.get("safeNote", ""),
        "filenames": {
            "srt": f"kangbo-{item.get('date', '')}-{platform_key}.srt",
            "txt": f"kangbo-{item.get('date', '')}-{platform_key}-teleprompter.txt",
        },
    }

def promo_video_kit_payload(items: list[dict], platform: str = "all") -> dict:
    platforms = ["xhs", "douyin", "wechat_channels"] if platform == "all" else [platform if platform in {"xhs", "douyin", "wechat_channels"} else "douyin"]
    tasks = []
    for item in items:
        for platform_key in platforms:
            tasks.append(promo_video_task(item, platform_key))
    return {
        "generatedAt": promo_china_today().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(tasks),
        "platforms": platforms,
        "items": tasks,
        "exports": {
            "csv": "/api/promo/video-kit?days=30&format=csv",
            "srt": "/api/promo/video-kit?date=YYYY-MM-DD&platform=douyin&format=srt",
            "txt": "/api/promo/video-kit?date=YYYY-MM-DD&platform=douyin&format=txt",
        },
    }

def promo_video_kit_csv_response(kit: dict) -> Response:
    output = io.StringIO()
    fieldnames = [
        "日期", "第几天", "平台", "标题", "主干课程", "书目课程",
        "短视频脚本", "字幕文本", "SRT文件名", "提词稿文件名",
        "落地页", "购买意向页", "书目购买页", "发布建议", "标签",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for task in kit.get("items") or []:
        writer.writerow({
            "日期": task.get("date", ""),
            "第几天": task.get("dayNumber", ""),
            "平台": task.get("platformName", ""),
            "标题": task.get("headline", ""),
            "主干课程": (task.get("course") or {}).get("title", ""),
            "书目课程": (task.get("book") or {}).get("title", ""),
            "短视频脚本": task.get("videoScript", ""),
            "字幕文本": "\n".join(task.get("captions") or []),
            "SRT文件名": (task.get("filenames") or {}).get("srt", ""),
            "提词稿文件名": (task.get("filenames") or {}).get("txt", ""),
            "落地页": (task.get("links") or {}).get("landing", ""),
            "购买意向页": (task.get("links") or {}).get("purchaseIntent", ""),
            "书目购买页": (task.get("links") or {}).get("bookShop", ""),
            "发布建议": task.get("publishHint", ""),
            "标签": " ".join(f"#{tag}" for tag in task.get("hashtags", [])),
        })
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kangbo-video-kit-30days.csv"'},
    )

@app.get("/api/promo/daily")
async def get_daily_promo(date: str = "", days: int = 7, format: str = "json"):
    days = max(1, min(int(days or 7), 30))
    target_date = parse_promo_date(date)
    start = promo_week_start()
    raw_offset = (target_date.date() - start.date()).days
    today_number = raw_offset + 1 if raw_offset >= 0 else 1
    tracks = audio_playlist_tracks("all")
    core_tracks = [item for item in tracks if item.get("type") == "core"]
    book_tracks = [item for item in tracks if item.get("type") == "book"]
    items = [
        promo_item_for_day(start + timedelta(days=i), i + 1, core_tracks, book_tracks)
        for i in range(days)
    ]
    today_index = min(max(today_number - 1, 0), len(items) - 1)
    generated_at = promo_china_today().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "today": items[today_index],
        "items": items,
        "todayIndex": today_index,
        "weekStart": start.strftime("%Y-%m-%d"),
        "generatedAt": generated_at,
        "goals": {"views": 1000, "purchases": 50},
        "audioCounts": {
            "core": len(core_tracks),
            "book": len(book_tracks),
            "total": len(tracks),
        },
        "platforms": ["xhs", "douyin", "wechat_channels"],
    }
    if (format or "").lower() == "csv":
        return promo_csv_response(items, generated_at)
    return payload

@app.get("/api/promo/calendar")
async def get_promo_calendar(date: str = "", days: int = 30, format: str = "json"):
    promo = await get_daily_promo(date=date, days=days)
    calendar = promo_calendar_payload(promo.get("items") or [], promo.get("generatedAt") or promo_china_today().strftime("%Y-%m-%d %H:%M:%S"))
    if (format or "").lower() == "csv":
        return promo_calendar_csv_response(calendar)
    return calendar

@app.get("/api/promo/video-kit")
async def get_promo_video_kit(date: str = "", days: int = 30, platform: str = "all", format: str = "json"):
    fmt = (format or "json").strip().lower()
    platform_key = (platform or "all").strip().lower()
    if fmt in {"srt", "txt"}:
        task = promo_video_task(promo_item_for_date(date), platform_key if platform_key != "all" else "douyin")
        if fmt == "srt":
            return Response(
                content=task.get("srt", ""),
                media_type="application/x-subrip; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{(task.get("filenames") or {}).get("srt", "kangbo-video.srt")}"'},
            )
        return Response(
            content=task.get("teleprompter", ""),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{(task.get("filenames") or {}).get("txt", "kangbo-video.txt")}"'},
        )
    items = promo_items_for_range(date, days)
    kit = promo_video_kit_payload(items, platform_key)
    if fmt == "csv":
        return promo_video_kit_csv_response(kit)
    return kit

def promo_publish_pack(item: dict) -> dict:
    headline = item.get("headline", "")
    hook = item.get("hook", "")
    course = item.get("course") or {}
    book = item.get("book") or {}
    urls = item.get("urls") or {}
    course_title = course.get("title", "主干课程")
    book_title = book.get("title", "书目课程")
    xhs = (item.get("platformContents") or {}).get("xhs") or {}
    douyin = (item.get("platformContents") or {}).get("douyin") or {}
    channels = (item.get("platformContents") or {}).get("wechat_channels") or {}
    xhs_titles = [
        headline,
        "别先问买什么，先判断周期位置",
        "普通人也能学会的康波判断框架",
        f"今天听{cn_book_title(course_title)}",
        "用一节课和一本书重建长期判断力",
    ]
    image_cards = [
        {
            "sequence": 1,
            "title": headline,
            "body": hook,
            "footer": "康波研究院 · 每天15分钟",
            "asset": public_url("assets/xhs-card-01.png"),
        },
        {
            "sequence": 2,
            "title": "今天先听一节课",
            "body": f"主干课程：{cn_book_title(course_title)}\n先建立判断框架，再写下自己的周期位置。",
            "footer": "65门主干课程",
            "asset": public_url("assets/xhs-card-02.png"),
        },
        {
            "sequence": 3,
            "title": "再用一本书补证据",
            "body": f"书目课程：{cn_book_title(book_title)}\n用经典阅读补充证据链，避免只凭情绪判断。",
            "footer": "500门书目课程",
            "asset": public_url("assets/xhs-card-03.png"),
        },
        {
            "sequence": 4,
            "title": "今日行动",
            "body": "听完第一课，写下四句话：周期位置、关键证据、反方信号、下一步行动。",
            "footer": "评论关键词：康波",
            "asset": public_url("assets/xhs-card-03.png"),
        },
    ]
    video_shots = [
        {"time": "0-3秒", "visual": "人物正面或课程标题卡", "caption": hook, "voice": f"先别问买什么，先问：{hook}"},
        {"time": "3-12秒", "visual": "课程页和知识图谱快速切换", "caption": course_title, "voice": f"今天用{cn_book_title(course_title)}建立判断框架。"},
        {"time": "12-24秒", "visual": "书目封面式文字卡", "caption": book_title, "voice": f"再用{cn_book_title(book_title)}补一条底层证据链。"},
        {"time": "24-38秒", "visual": "四象限文字卡", "caption": "技术扩散 · 信用周期 · 人口结构 · 政策方向", "voice": "真正的周期判断，要同时看四个变量，而不是只看短期涨跌。"},
        {"time": "38-50秒", "visual": "落地页和购买意向页", "caption": "先试学，再决定是否系统学习", "voice": "康波研究院已经整理好65门主干课程和500门书目课程，先试学，再决定是否系统学习。"},
    ]
    pinned_comment = (
        f"今日试学入口：{xhs.get('landingUrl') or urls.get('landing', '')}\n"
        f"全库升级购买意向：{xhs.get('purchaseIntentUrl') or urls.get('purchaseIntent', '')}\n"
        "评论区写“康波”，我发你四句话练习模板。"
    )
    return {
        "date": item.get("date", ""),
        "dayNumber": item.get("dayNumber", 1),
        "headline": headline,
        "focus": item.get("focus", ""),
        "course": course,
        "book": book,
        "links": {
            "landing": urls.get("landing", ""),
            "purchaseIntent": urls.get("purchaseIntent", ""),
            "bookShop": urls.get("bookShop", ""),
            "digitalLive": urls.get("digitalLive", ""),
            "xhsLanding": xhs.get("landingUrl", ""),
            "douyinLanding": douyin.get("landingUrl", ""),
            "wechatChannelsLanding": channels.get("landingUrl", ""),
        },
        "xhs": {
            "titles": xhs_titles,
            "hashtags": xhs.get("hashtags", []),
            "primaryCopy": xhs.get("primaryCopy", ""),
            "pinnedComment": pinned_comment,
            "dmScript": xhs.get("dmScript", ""),
            "imageCards": image_cards,
        },
        "video": {
            "sourceAsset": public_url("assets/xhs-week1-video.mp4"),
            "douyinScript": douyin.get("videoScript", ""),
            "wechatChannelsScript": channels.get("videoScript", ""),
            "storyboard": video_shots,
            "caption": f"{headline}\n\n{hook}\n\n先试学，再决定是否系统学习。",
        },
        "live": {
            "source": urls.get("digitalLive", ""),
            "xhsScript": xhs.get("liveScript", ""),
            "douyinScript": douyin.get("liveScript", ""),
            "wechatChannelsScript": channels.get("liveScript", ""),
            "interaction": "请在评论区写下四句话：周期位置、关键证据、反方信号、下一步行动。",
        },
        "checklist": [
            "小红书发布4张图文卡，标题用问题句，评论区置顶试学入口。",
            "抖音发布50秒短视频，前3秒直接抛周期问题。",
            "微信视频号发布稳健知识型版本，正文加入教育研究免责声明。",
            "发布后回到首周增长冲刺台录入平台后台浏览、点击、私信意向和外部成交。",
        ],
    }

def publish_pack_markdown(pack: dict) -> str:
    lines = [
        "# 康波研究院今日发布包",
        "",
        f"- 日期：{pack.get('date', '')}",
        f"- 主题：{pack.get('headline', '')}",
        f"- 主干课程：{(pack.get('course') or {}).get('title', '')}",
        f"- 书目课程：{(pack.get('book') or {}).get('title', '')}",
        "",
        "## 小红书图文",
        "",
        "备选标题：",
    ]
    lines.extend([f"- {title}" for title in (pack.get("xhs") or {}).get("titles", [])])
    lines.extend(["", "图文卡片："])
    for card in (pack.get("xhs") or {}).get("imageCards", []):
        lines.extend(["", f"### 第{card.get('sequence')}张：{card.get('title')}", card.get("body", ""), f"素材：{card.get('asset', '')}"])
    lines.extend([
        "",
        "正文：",
        "",
        (pack.get("xhs") or {}).get("primaryCopy", ""),
        "",
        "置顶评论：",
        "",
        (pack.get("xhs") or {}).get("pinnedComment", ""),
        "",
        "## 短视频分镜",
    ])
    for shot in (pack.get("video") or {}).get("storyboard", []):
        lines.append(f"- {shot.get('time')}：{shot.get('visual')}｜{shot.get('voice')}")
    lines.extend([
        "",
        "## 直播口播",
        "",
        (pack.get("live") or {}).get("douyinScript", ""),
        "",
        "## 链接",
        "",
    ])
    for key, value in (pack.get("links") or {}).items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"

def publish_pack_csv(pack: dict) -> Response:
    output = io.StringIO()
    fieldnames = ["type", "platform", "sequence", "title", "body", "asset", "link"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for card in (pack.get("xhs") or {}).get("imageCards", []):
        writer.writerow({
            "type": "image_card",
            "platform": "小红书",
            "sequence": card.get("sequence", ""),
            "title": card.get("title", ""),
            "body": card.get("body", ""),
            "asset": card.get("asset", ""),
            "link": (pack.get("links") or {}).get("xhsLanding", ""),
        })
    for shot in (pack.get("video") or {}).get("storyboard", []):
        writer.writerow({
            "type": "video_shot",
            "platform": "抖音/微信视频号",
            "sequence": shot.get("time", ""),
            "title": shot.get("caption", ""),
            "body": shot.get("voice", ""),
            "asset": shot.get("visual", ""),
            "link": (pack.get("links") or {}).get("purchaseIntent", ""),
        })
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kangbo-today-publish-pack.csv"'},
    )

@app.get("/api/promo/publish-pack")
async def get_promo_publish_pack(date: str = "", format: str = "json"):
    pack = promo_publish_pack(promo_item_for_date(date))
    fmt = (format or "json").strip().lower()
    if fmt in {"md", "markdown"}:
        return Response(
            content=publish_pack_markdown(pack),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="kangbo-today-publish-pack.md"'},
        )
    if fmt == "csv":
        return publish_pack_csv(pack)
    return pack


def affiliate_template_rows() -> list[dict]:
    rows = []
    product_map = load_shop_product_map()
    config = shop_config()
    for course in parse_book_courses():
        detail = shop_book_detail(int(course["n"]))
        product = detail["product"]
        rows.append({
            "bookId": int(course["n"]),
            "title": detail["title"],
            "author": detail["author"],
            "category": course.get("category", ""),
            "affiliateUrl": product.get("affiliateUrl", ""),
            "externalUrl": product.get("externalUrl", ""),
            "productId": product.get("productId", ""),
            "path": product.get("path", ""),
            "source": product_channel(product),
            "channelName": product.get("channelName", ""),
            "settlementMode": product.get("settlementMode", ""),
            "commissionRate": product.get("commissionRate", ""),
            "commissionReady": product_has_direct_commission(product, config),
            "configured": str(course["n"]) in product_map,
        })
    return rows

def affiliate_workbook_spec(channel: str) -> dict:
    channel = (channel or "wechat_shop").strip().lower()
    specs = {
        "wechat_shop": {
            "name": "微信小店商品映射表",
            "filename": "kangbo-wechat-shop-book-map.csv",
            "source": "wechat_shop",
            "channelName": "微信小店",
            "settlementMode": "wechat_shop",
            "commissionRate": "微信小店后台结算",
            "openType": "mini_program",
            "targetFields": "productId/path/miniProgramAppId/businessType",
            "notes": "填写微信小店商品ID或商品路径；若使用交易组件，请填写businessType。",
        },
        "jd_union": {
            "name": "京东联盟CPS链接表",
            "filename": "kangbo-jd-union-book-map.csv",
            "source": "jd_union",
            "channelName": "京东联盟",
            "settlementMode": "cps",
            "commissionRate": "以京东联盟后台为准",
            "openType": "clipboard",
            "targetFields": "affiliateUrl/shortUrl/productId",
            "notes": "填写京东联盟生成的推广链接；小程序内默认复制链接或走站内中转。",
        },
        "dangdang_affiliate": {
            "name": "当当图书联盟链接表",
            "filename": "kangbo-dangdang-affiliate-book-map.csv",
            "source": "dangdang_affiliate",
            "channelName": "当当图书联盟",
            "settlementMode": "cps",
            "commissionRate": "以联盟后台为准",
            "openType": "clipboard",
            "targetFields": "affiliateUrl/shortUrl/productId",
            "notes": "填写当当或图书联盟的可追踪推广链接。",
        },
        "custom": {
            "name": "出版社或书商直连分成表",
            "filename": "kangbo-custom-book-map.csv",
            "source": "custom",
            "channelName": "出版社/书商直连",
            "settlementMode": "commission",
            "commissionRate": "按协议",
            "openType": "web_view",
            "targetFields": "externalUrl/affiliateUrl/productId",
            "notes": "填写出版社、书店或知识服务商提供的专属分成链接。",
        },
    }
    return specs.get(channel, specs["wechat_shop"])

def affiliate_workbook_rows(channel: str = "wechat_shop") -> tuple[dict, list[dict]]:
    spec = affiliate_workbook_spec(channel)
    rows = []
    for row in affiliate_template_rows():
        clean_title = re.sub(r"^《|》$", "", row.get("title") or "").strip()
        keyword = " ".join(x for x in [clean_title, row.get("author", "")] if x).strip()
        rows.append({
            "bookId": row.get("bookId", ""),
            "title": row.get("title", ""),
            "author": row.get("author", ""),
            "category": row.get("category", ""),
            "keyword": keyword,
            "currentReady": "yes" if row.get("commissionReady") else "no",
            "currentChannel": row.get("channelName", ""),
            "currentAffiliateUrl": row.get("affiliateUrl", ""),
            "currentProductId": row.get("productId", ""),
            "currentPath": row.get("path", ""),
            "affiliateUrl": "" if spec["source"] == "wechat_shop" else "",
            "externalUrl": "" if spec["source"] != "wechat_shop" else "",
            "shortUrl": "",
            "productId": "",
            "shopProductId": "",
            "path": "",
            "shopPath": "",
            "miniProgramAppId": "",
            "appId": "",
            "businessType": "",
            "source": spec["source"],
            "channel": spec["source"],
            "channelName": spec["channelName"],
            "settlementMode": spec["settlementMode"],
            "commissionRate": spec["commissionRate"],
            "openType": spec["openType"],
            "targetFields": spec["targetFields"],
            "notes": spec["notes"],
        })
    return spec, rows

def affiliate_csv_response(rows: list[dict], filename: str) -> Response:
    output = io.StringIO()
    fieldnames = [
        "bookId", "title", "author", "category", "keyword",
        "currentReady", "currentChannel", "currentAffiliateUrl", "currentProductId", "currentPath",
        "affiliateUrl", "externalUrl", "shortUrl", "productId", "shopProductId",
        "path", "shopPath", "miniProgramAppId", "appId", "businessType",
        "source", "channel", "channelName", "settlementMode", "commissionRate",
        "openType", "targetFields", "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def shop_commission_report(days: int = 7) -> dict:
    days = max(1, min(int(days or 7), 180))
    since = f"-{days} days"
    config = shop_config()
    click_by_book: dict[int, dict] = {}
    source_totals: dict[str, int] = {}
    purchase_by_book: dict[int, dict] = {}
    conn = get_db()
    click_rows = conn.execute(
        """
        SELECT book_id,
               COALESCE(NULLIF(source,''), 'direct') AS source,
               COUNT(*) AS clicks,
               MAX(created_at) AS last_click_at
        FROM shop_clicks
        WHERE created_at >= datetime('now', ?)
        GROUP BY book_id, COALESCE(NULLIF(source,''), 'direct')
        """,
        (since,),
    ).fetchall()
    # Historical book status='paid' has no trusted merchant verification yet.
    purchase_rows = conn.execute(
        """
        SELECT book_id,
               0 AS paid,
               COUNT(*) AS pending,
               MAX(COALESCE(updated_at, purchased_at)) AS last_purchase_at
        FROM book_purchases
        WHERE COALESCE(updated_at, purchased_at) >= datetime('now', ?)
        GROUP BY book_id
        """,
        (since,),
    ).fetchall()
    conn.close()
    for row in click_rows:
        book_id = int(row["book_id"] or 0)
        if book_id <= 0:
            continue
        source = row["source"] or "direct"
        clicks = int(row["clicks"] or 0)
        item = click_by_book.setdefault(book_id, {"clicks": 0, "sources": {}, "lastClickAt": ""})
        item["clicks"] += clicks
        item["sources"][source] = item["sources"].get(source, 0) + clicks
        if row["last_click_at"] and row["last_click_at"] > item["lastClickAt"]:
            item["lastClickAt"] = row["last_click_at"]
        source_totals[source] = source_totals.get(source, 0) + clicks
    for row in purchase_rows:
        book_id = int(row["book_id"] or 0)
        if book_id <= 0:
            continue
        purchase_by_book[book_id] = {
            "paid": int(row["paid"] or 0),
            "pending": int(row["pending"] or 0),
            "lastPurchaseAt": row["last_purchase_at"] or "",
        }

    rows = []
    for course in parse_book_courses():
        book_id = int(course["n"])
        detail = shop_book_detail(book_id)
        product = detail["product"]
        action = book_open_action(book_id, product, config)
        click = click_by_book.get(book_id, {"clicks": 0, "sources": {}, "lastClickAt": ""})
        purchase = purchase_by_book.get(book_id, {"paid": 0, "pending": 0, "lastPurchaseAt": ""})
        commission_ready = product_has_direct_commission(product, config)
        link_fields = [key for key in ("affiliateUrl", "externalUrl", "shortUrl", "productId", "path", "shopPath") if product.get(key)]
        rows.append({
            "bookId": book_id,
            "title": detail["title"],
            "author": detail["author"],
            "category": course.get("category", ""),
            "channel": product_channel(product),
            "channelName": product.get("channelName", ""),
            "settlementMode": product.get("settlementMode", ""),
            "commissionRate": product.get("commissionRate", ""),
            "commissionReady": commission_ready,
            "openType": action.get("type", "none"),
            "canBuy": action.get("canBuy", False),
            "canOpen": action.get("canOpen", False),
            "entryKind": action.get("entryKind", "unavailable"),
            "configuredFields": "/".join(link_fields),
            "clicks": int(click.get("clicks") or 0),
            "sources": click.get("sources") or {},
            "lastClickAt": click.get("lastClickAt") or "",
            "pendingPurchases": int(purchase.get("pending") or 0),
            "paidPurchases": int(purchase.get("paid") or 0),
            "lastPurchaseAt": purchase.get("lastPurchaseAt") or "",
            "redirectUrl": public_url(f"/api/shop/redirect/{book_id}?source=book_report&campaign=commission_review"),
        })
    total_books = len(rows)
    direct_ready = sum(1 for row in rows if row["commissionReady"])
    linked = sum(1 for row in rows if row["canOpen"])
    clicked_books = sum(1 for row in rows if row["clicks"] > 0)
    total_clicks = sum(int(row["clicks"] or 0) for row in rows)
    paid_purchases = sum(int(row["paidPurchases"] or 0) for row in rows)
    pending_purchases = sum(int(row["pendingPurchases"] or 0) for row in rows)
    priority_missing = sorted(
        [row for row in rows if not row["commissionReady"]],
        key=lambda row: (-int(row["clicks"] or 0), int(row["bookId"])),
    )[:30]
    top_books = sorted(rows, key=lambda row: (-int(row["clicks"] or 0), int(row["bookId"])))[:30]
    return {
        "windowDays": days,
        "generatedAt": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "totalBooks": total_books,
            "linkedBooks": linked,
            "directCommissionBooks": direct_ready,
            "missingDirectCommission": max(0, total_books - direct_ready),
            "directCommissionReady": total_books > 0 and direct_ready >= total_books,
            "totalClicks": total_clicks,
            "clickedBooks": clicked_books,
            "pendingPurchases": pending_purchases,
            "paidPurchases": paid_purchases,
        },
        "sourceTotals": [{"source": source, "clicks": clicks} for source, clicks in sorted(source_totals.items(), key=lambda x: -x[1])],
        "topBooks": top_books,
        "priorityMissing": priority_missing,
        "rows": rows,
    }

def shop_commission_report_csv(report: dict) -> Response:
    output = io.StringIO()
    fieldnames = [
        "bookId", "title", "author", "category", "channelName", "settlementMode",
        "commissionRate", "commissionReady", "openType", "canBuy", "canOpen", "entryKind", "configuredFields",
        "clicks", "pendingPurchases", "paidPurchases", "lastClickAt", "lastPurchaseAt", "redirectUrl",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in report.get("rows") or []:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    filename = f"kangbo-book-commission-report-{report.get('windowDays', 7)}d.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def shop_commission_gap_rows(channel: str = "wechat_shop", days: int = 7) -> tuple[dict, list[dict]]:
    spec = affiliate_workbook_spec(channel)
    report = shop_commission_report(days)
    missing = [row for row in report.get("rows") or [] if not row.get("commissionReady")]
    missing.sort(key=lambda row: (-int(row.get("clicks") or 0), int(row.get("bookId") or 0)))
    rows = []
    for index, row in enumerate(missing, 1):
        clean_title = re.sub(r"^《|》$", "", row.get("title") or "").strip()
        keyword = " ".join(x for x in [clean_title, row.get("author", "")] if x).strip()
        rows.append({
            "priority": index,
            "bookId": row.get("bookId", ""),
            "title": row.get("title", ""),
            "author": row.get("author", ""),
            "category": row.get("category", ""),
            "keyword": keyword,
            "clicks": row.get("clicks", 0),
            "lastClickAt": row.get("lastClickAt", ""),
            "currentChannel": row.get("channelName", ""),
            "currentSettlementMode": row.get("settlementMode", ""),
            "currentConfiguredFields": row.get("configuredFields", ""),
            "affiliateUrl": "" if spec["source"] == "wechat_shop" else "",
            "externalUrl": "" if spec["source"] != "wechat_shop" else "",
            "shortUrl": "",
            "productId": "",
            "shopProductId": "",
            "path": "",
            "shopPath": "",
            "miniProgramAppId": "",
            "appId": "",
            "businessType": "",
            "source": spec["source"],
            "channel": spec["source"],
            "channelName": spec["channelName"],
            "settlementMode": spec["settlementMode"],
            "commissionRate": spec["commissionRate"],
            "openType": spec["openType"],
            "targetFields": spec["targetFields"],
            "notes": spec["notes"],
        })
    return spec, rows

def shop_commission_gap_csv(rows: list[dict], spec: dict, days: int) -> Response:
    output = io.StringIO()
    fieldnames = [
        "priority", "bookId", "title", "author", "category", "keyword", "clicks",
        "lastClickAt", "currentChannel", "currentSettlementMode", "currentConfiguredFields",
        "affiliateUrl", "externalUrl", "shortUrl", "productId", "shopProductId",
        "path", "shopPath", "miniProgramAppId", "appId", "businessType",
        "source", "channel", "channelName", "settlementMode", "commissionRate",
        "openType", "targetFields", "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    filename = f"kangbo-book-commission-gap-{spec['source']}-{days}d.csv"
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def normalize_import_products(products: dict) -> dict:
    normalized = {}
    for key, value in (products or {}).items():
        try:
            book_id = int(key)
        except (TypeError, ValueError):
            if isinstance(value, dict):
                try:
                    book_id = int(value.get("bookId") or value.get("id"))
                except (TypeError, ValueError):
                    continue
            else:
                continue
        if book_id < 1 or book_id > 500 or not isinstance(value, dict):
            continue
        allowed = {
            "title", "author", "price", "productId", "shopProductId", "path", "shopPath",
            "affiliateUrl", "externalUrl", "shortUrl", "url", "commissionRate", "settlementMode",
            "source", "channel", "channelName", "openType", "businessType", "queryString",
            "miniProgramAppId", "appId", "productPathTemplate"
        }
        item = {k: v for k, v in value.items() if k in allowed and v not in (None, "", [], {})}
        if item:
            normalized[str(book_id)] = item
    return normalized

CSV_FIELD_ALIASES = {
    "bookId": {
        "bookid", "id", "编号", "序号", "书号", "课程编号", "图书编号", "book_id",
    },
    "title": {
        "title", "book", "booktitle", "书名", "图书", "商品名称", "商品标题", "商品名",
        "标题", "name", "productname", "sku名称", "sku名",
    },
    "author": {"author", "作者"},
    "affiliateUrl": {
        "affiliateurl", "推广链接", "联盟链接", "cps链接", "转链链接", "推广url",
        "推广地址", "购买链接", "商品链接", "链接", "url", "link",
    },
    "externalUrl": {"externalurl", "外部链接", "直连链接", "出版社链接", "书商链接"},
    "shortUrl": {"shorturl", "短链", "短链接"},
    "productId": {"productid", "skuid", "sku", "商品id", "商品编号", "产品id"},
    "path": {"path", "路径", "小程序路径", "微信小店路径", "商品路径"},
    "shopProductId": {"shopproductid", "小店商品id", "微信商品id"},
    "commissionRate": {"commissionrate", "佣金", "佣金比例", "分佣比例", "佣金率"},
    "price": {"price", "价格", "券后价", "售价"},
    "source": {"source", "渠道", "来源"},
    "channelName": {"channelname", "渠道名称", "平台"},
    "settlementMode": {"settlementmode", "结算方式", "分成方式"},
}

def normalize_header_name(value: str) -> str:
    return re.sub(r"[\s_\-:/()（）【】\\[\\]]+", "", str(value or "").strip().lower())

def canonical_import_field(header: str) -> str:
    normalized = normalize_header_name(header)
    for field, aliases in CSV_FIELD_ALIASES.items():
        if normalized in {normalize_header_name(alias) for alias in aliases}:
            return field
    return header.strip()

def parse_import_content_rows(content: str) -> list[dict]:
    text = (content or "").strip().lstrip("\ufeff")
    if not text:
        raise HTTPException(400, "导入内容为空")
    if text[0] in "[{":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"JSON 解析失败：{exc.msg}") from exc
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            return [row for row in data["rows"] if isinstance(row, dict)]
        if isinstance(data, dict) and isinstance(data.get("products"), dict):
            return [
                {"bookId": book_id, **(value or {})}
                for book_id, value in data["products"].items()
                if isinstance(value, dict)
            ]
        if isinstance(data, dict):
            return [
                {"bookId": book_id, **(value or {})}
                for book_id, value in data.items()
                if isinstance(value, dict)
            ]
        return []

    sample = io.StringIO(text)
    reader = csv.DictReader(sample)
    if not reader.fieldnames:
        return []
    headers = {header: canonical_import_field(header) for header in reader.fieldnames}
    rows = []
    for raw in reader:
        row = {}
        for header, value in (raw or {}).items():
            field = headers.get(header, header)
            if value not in (None, ""):
                row[field] = str(value).strip()
        if any(str(v).strip() for v in row.values()):
            rows.append(row)
    return rows

def normalize_match_text(value: str) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[《》<>「」『』()（）\[\]【】]", "", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)
    return text

def book_match_index() -> list[dict]:
    index = []
    for course in parse_book_courses():
        book_id = int(course["n"])
        title = course.get("title") or course.get("t") or ""
        clean_title = re.sub(r"^《|》$", "", title).strip()
        author = course.get("author") or course.get("a") or ""
        index.append({
            "bookId": book_id,
            "title": title,
            "cleanTitle": clean_title,
            "author": author,
            "key": normalize_match_text(clean_title or title),
        })
    return index

def match_book_from_import_row(row: dict, index: list[dict]) -> tuple[Optional[dict], str, list[dict]]:
    raw_id = row.get("bookId") or row.get("id") or row.get("编号")
    if raw_id:
        try:
            book_id = int(str(raw_id).strip())
        except ValueError:
            book_id = 0
        match = next((item for item in index if item["bookId"] == book_id), None)
        if match:
            return match, "bookId", []
    title = row.get("title") or row.get("bookTitle") or row.get("商品名称") or row.get("name") or ""
    title_key = normalize_match_text(title)
    if not title_key:
        return None, "missing_title", []
    exact = [item for item in index if item["key"] and item["key"] == title_key]
    if len(exact) == 1:
        return exact[0], "exact_title", []
    contains = [
        item for item in index
        if item["key"] and (item["key"] in title_key or title_key in item["key"])
    ]
    contains = sorted(contains, key=lambda item: len(item["key"]), reverse=True)
    if len(contains) == 1:
        return contains[0], "title_contains", []
    if len(contains) > 1 and len(contains[0]["key"]) > len(contains[1]["key"]):
        return contains[0], "best_title_contains", contains[1:4]
    return None, "ambiguous" if contains else "unmatched", contains[:5]

def row_import_url(row: dict) -> tuple[str, str]:
    for field in ("affiliateUrl", "externalUrl", "shortUrl", "url"):
        value = str(row.get(field) or "").strip()
        if value:
            target = "affiliateUrl" if field in {"url", "shortUrl"} else field
            return target, value
    return "", ""

def smart_affiliate_products(req: AffiliateSmartImportReq) -> dict:
    rows = parse_import_content_rows(req.content)
    index = book_match_index()
    products: dict[str, dict] = {}
    preview = []
    unmatched = []
    ambiguous = []
    for row_no, row in enumerate(rows, 1):
        match, method, candidates = match_book_from_import_row(row, index)
        target_field, target_url = row_import_url(row)
        if not target_url and not (row.get("productId") or row.get("shopProductId") or row.get("path") or row.get("shopPath")):
            unmatched.append({"row": row_no, "reason": "missing_link", "title": row.get("title", "")})
            continue
        if not match:
            item = {"row": row_no, "reason": method, "title": row.get("title", "")}
            if candidates:
                item["candidates"] = [{"bookId": c["bookId"], "title": c["title"]} for c in candidates]
                ambiguous.append(item)
            else:
                unmatched.append(item)
            continue
        product = {
            "source": row.get("source") or req.source or "affiliate",
            "channel": row.get("source") or req.source or "affiliate",
            "channelName": row.get("channelName") or req.channelName or req.source or "affiliate",
            "settlementMode": row.get("settlementMode") or req.settlementMode or "cps",
            "commissionRate": row.get("commissionRate") or req.commissionRate or "以联盟后台为准",
        }
        if target_field and target_url:
            product[target_field] = target_url
        for field in ("productId", "shopProductId", "path", "shopPath", "miniProgramAppId", "appId", "businessType", "price"):
            if row.get(field):
                product[field] = row[field]
        products[str(match["bookId"])] = product
        if len(preview) < max(1, min(int(req.previewLimit or 20), 50)):
            preview.append({
                "row": row_no,
                "bookId": match["bookId"],
                "title": match["title"],
                "sourceTitle": row.get("title", ""),
                "matchMethod": method,
                "targetField": target_field or "product/path",
                "target": target_url or row.get("productId") or row.get("path") or "",
            })
    normalized = normalize_import_products(products)
    return {
        "parsedRows": len(rows),
        "matchedBooks": len(normalized),
        "products": normalized,
        "preview": preview,
        "unmatchedRows": unmatched[:50],
        "ambiguousRows": ambiguous[:50],
        "unmatchedCount": len(unmatched),
        "ambiguousCount": len(ambiguous),
    }

def build_affiliate_products_from_template(req: AffiliateTemplateReq) -> dict:
    target_field = (req.targetField or "affiliateUrl").strip()
    allowed_targets = {"affiliateUrl", "externalUrl", "path", "shopPath", "productId", "shopProductId"}
    if target_field not in allowed_targets:
        raise HTTPException(400, "写入字段不支持")
    template = (req.template or "").strip()
    if not template:
        raise HTTPException(400, "请填写真实分成链接模板")
    source = (req.source or "affiliate").strip()
    settlement_mode = (req.settlementMode or ("wechat_shop" if target_field in {"path", "shopPath", "productId", "shopProductId"} else "cps")).strip()
    commission_rate = (req.commissionRate or "以联盟后台为准").strip()
    channel_name = (req.channelName or source).strip()
    products = {}
    for course in parse_book_courses():
        book_id = int(course["n"])
        title = course.get("title") or course.get("t") or f"图书 {book_id}"
        author = course.get("author") or course.get("a") or ""
        product_id = render_affiliate_template(req.productIdTemplate or "", book_id, title, author)
        target = render_affiliate_template(template, book_id, title, author, product_id)
        if not target:
            continue
        item = {
            target_field: target,
            "source": source,
            "channel": source,
            "channelName": channel_name,
            "settlementMode": settlement_mode,
            "commissionRate": commission_rate,
        }
        if product_id and target_field not in {"productId", "shopProductId"}:
            item["productId"] = product_id
        if req.productPathTemplate:
            item["productPathTemplate"] = req.productPathTemplate
        if req.miniProgramAppId:
            item["miniProgramAppId"] = req.miniProgramAppId.strip()
        if req.appId:
            item["appId"] = req.appId.strip()
        if req.businessType:
            item["businessType"] = req.businessType.strip()
        products[str(book_id)] = item
    if not products:
        raise HTTPException(400, "模板没有生成有效链接，请检查占位符和链接格式")
    return products

def affiliate_template_preview_payload(req: AffiliateTemplateReq, products: dict) -> dict:
    config = shop_config()
    preview_limit = max(1, min(int(req.previewLimit or 5), 20))
    rows = []
    ready = 0
    for course in parse_book_courses():
        book_id = int(course["n"])
        generated = products.get(str(book_id), {})
        detail = shop_book_detail(book_id)
        merged = merge_product_config(generated_book_product(book_id, detail["title"], detail["author"]), generated)
        is_ready = product_has_direct_commission(merged, config)
        ready += 1 if is_ready else 0
        if len(rows) < preview_limit:
            action = book_open_action(book_id, merged, config)
            rows.append({
                "bookId": book_id,
                "title": detail["title"],
                "author": detail["author"],
                "targetField": req.targetField or "affiliateUrl",
                "target": generated.get(req.targetField or "affiliateUrl", ""),
                "channel": product_channel(merged),
                "settlementMode": merged.get("settlementMode", ""),
                "commissionRate": merged.get("commissionRate", ""),
                "commissionReady": is_ready,
                "openType": action.get("type", "none"),
            })
    return {
        "total": len(products),
        "commissionReadyAfterImport": ready,
        "missingDirectCommissionAfterImport": max(0, len(parse_book_courses()) - ready),
        "preview": rows,
    }

def affiliate_smart_preview_payload(req: AffiliateSmartImportReq) -> dict:
    parsed = smart_affiliate_products(req)
    product_map = {} if req.replace else load_shop_product_map()
    merged_map = dict(product_map or {})
    merged_map.update(parsed["products"])
    config = shop_config()
    ready = 0
    for course in parse_book_courses():
        book_id = int(course["n"])
        detail = shop_book_detail(book_id)
        base = generated_book_product(book_id, detail["title"], detail["author"])
        product = merge_product_config(base, merged_map.get(str(book_id), {}))
        if product_has_direct_commission(product, config):
            ready += 1
    total_books = len(parse_book_courses())
    return {
        **{key: value for key, value in parsed.items() if key != "products"},
        "commissionReadyAfterImport": ready,
        "missingDirectCommissionAfterImport": max(0, total_books - ready),
        "totalBooks": total_books,
        "importEndpoint": "/api/shop/affiliate-smart-import",
    }

@app.get("/api/shop/config")
async def get_shop_config():
    return shop_config()

@app.get("/api/shop/affiliate-programs")
async def get_shop_affiliate_programs():
    return {"programs": affiliate_programs()}

@app.get("/api/shop/affiliate-workbook")
async def get_shop_affiliate_workbook(channel: str = "wechat_shop", format: str = "json"):
    spec, rows = affiliate_workbook_rows(channel)
    ready = sum(1 for row in rows if row.get("currentReady") == "yes")
    payload = {
        "channel": spec["source"],
        "name": spec["name"],
        "total": len(rows),
        "currentCommissionReady": ready,
        "missingDirectCommission": len(rows) - ready,
        "downloadUrl": f"/api/shop/affiliate-workbook?channel={parse.quote(spec['source'])}&format=csv",
        "importEndpoint": "/api/shop/affiliate-import",
        "requiredHeader": "X-Payment-Admin-Token",
        "instructions": {
            "targetFields": spec["targetFields"],
            "notes": spec["notes"],
            "importableFields": [
                "affiliateUrl", "externalUrl", "shortUrl", "productId", "shopProductId",
                "path", "shopPath", "miniProgramAppId", "appId", "businessType",
                "source", "channel", "channelName", "settlementMode", "commissionRate", "openType",
            ],
        },
        "rows": rows,
    }
    if (format or "").lower() == "csv":
        return affiliate_csv_response(rows, spec["filename"])
    return payload

@app.get("/api/shop/affiliate-template")
async def get_shop_affiliate_template(format: str = "json"):
    rows = affiliate_template_rows()
    if format.lower() == "csv":
        output = io.StringIO()
        fieldnames = [
            "bookId", "title", "author", "category", "affiliateUrl", "externalUrl",
            "productId", "path", "source", "channelName", "settlementMode",
            "commissionRate", "commissionReady", "configured"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return JSONResponse({"csv": output.getvalue(), "total": len(rows)})
    ready = sum(1 for row in rows if row["commissionReady"])
    return {
        "total": len(rows),
        "commissionReady": ready,
        "missingDirectCommission": len(rows) - ready,
        "rows": rows,
        "instructions": {
            "jsonImportEndpoint": "/api/shop/affiliate-import",
            "requiredHeader": "X-Payment-Admin-Token",
            "fields": ["affiliateUrl", "productId", "path", "settlementMode", "commissionRate", "source"],
        },
    }

@app.get("/api/shop/commission-report")
async def get_shop_commission_report(days: int = 7, format: str = "json"):
    report = shop_commission_report(days)
    if (format or "").lower() == "csv":
        return shop_commission_report_csv(report)
    return report

@app.get("/api/shop/commission-gap")
async def get_shop_commission_gap(channel: str = "wechat_shop", days: int = 7, format: str = "json"):
    days = max(1, min(int(days or 7), 180))
    spec, rows = shop_commission_gap_rows(channel, days)
    if (format or "").lower() == "csv":
        return shop_commission_gap_csv(rows, spec, days)
    return {
        "channel": spec["source"],
        "name": spec["name"],
        "windowDays": days,
        "totalMissing": len(rows),
        "downloadUrl": f"/api/shop/commission-gap?channel={parse.quote(spec['source'])}&days={days}&format=csv",
        "importEndpoint": "/api/shop/affiliate-import",
        "rows": rows,
    }

@app.post("/api/shop/affiliate-import")
async def import_shop_affiliate_links(req: AffiliateImportReq, request: Request):
    token = request.headers.get("X-Payment-Admin-Token", "")
    if not PAYMENT_ADMIN_TOKEN or token != PAYMENT_ADMIN_TOKEN:
        raise HTTPException(403, "缺少运营导入权限")
    incoming = normalize_import_products(req.products or {})
    if not incoming:
        raise HTTPException(400, "没有可导入的图书链接")
    existing = {} if req.replace else load_shop_product_map()
    existing.update(incoming)
    SHOP_PRODUCTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SHOP_PRODUCTS_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = affiliate_template_rows()
    ready = sum(1 for row in rows if row["commissionReady"])
    return {
        "success": True,
        "imported": len(incoming),
        "totalConfigured": len(existing),
        "commissionReady": ready,
        "missingDirectCommission": len(rows) - ready,
    }

@app.post("/api/shop/affiliate-template-preview")
async def preview_shop_affiliate_template(req: AffiliateTemplateReq):
    products = build_affiliate_products_from_template(req)
    return affiliate_template_preview_payload(req, products)

@app.post("/api/shop/affiliate-smart-preview")
async def preview_shop_affiliate_smart(req: AffiliateSmartImportReq):
    return affiliate_smart_preview_payload(req)

@app.post("/api/shop/affiliate-template-import")
async def import_shop_affiliate_template(req: AffiliateTemplateReq, request: Request):
    require_payment_admin_token(request, "缺少运营导入权限")
    incoming = normalize_import_products(build_affiliate_products_from_template(req))
    if not incoming:
        raise HTTPException(400, "没有可导入的图书链接")
    existing = {} if req.replace else load_shop_product_map()
    existing.update(incoming)
    SHOP_PRODUCTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SHOP_PRODUCTS_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = affiliate_template_rows()
    ready = sum(1 for row in rows if row["commissionReady"])
    return {
        "success": True,
        "imported": len(incoming),
        "totalConfigured": len(existing),
        "commissionReady": ready,
        "missingDirectCommission": len(rows) - ready,
        "preview": affiliate_template_preview_payload(req, incoming)["preview"],
    }

@app.post("/api/shop/affiliate-smart-import")
async def import_shop_affiliate_smart(req: AffiliateSmartImportReq, request: Request):
    require_payment_admin_token(request, "缺少运营导入权限")
    parsed = smart_affiliate_products(req)
    incoming = parsed["products"]
    if not incoming:
        raise HTTPException(400, "没有匹配到可导入的图书分成链接")
    existing = {} if req.replace else load_shop_product_map()
    existing.update(incoming)
    SHOP_PRODUCTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SHOP_PRODUCTS_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = affiliate_template_rows()
    ready = sum(1 for row in rows if row["commissionReady"])
    return {
        "success": True,
        "parsedRows": parsed["parsedRows"],
        "matchedBooks": parsed["matchedBooks"],
        "imported": len(incoming),
        "totalConfigured": len(existing),
        "commissionReady": ready,
        "missingDirectCommission": len(rows) - ready,
        "unmatchedCount": parsed["unmatchedCount"],
        "ambiguousCount": parsed["ambiguousCount"],
        "preview": parsed["preview"],
        "unmatchedRows": parsed["unmatchedRows"],
        "ambiguousRows": parsed["ambiguousRows"],
    }

@app.get("/api/shop/books")
async def get_shop_books(limit: int = 24):
    # Reuse request-local snapshots for both readiness totals and individual rows.
    courses = parse_book_courses()
    product_map = load_shop_product_map()
    config = shop_config(courses=courses, product_map=product_map)
    books = []
    max_limit = max(1, min(limit, 500))
    for course in courses[:max_limit]:
        detail = shop_book_detail(int(course["n"]), course=course, product_map=product_map)
        product = detail["product"]
        price = detail["price"] or "去渠道查看"
        price_text = detail["price_text"]
        action = book_open_action(int(course["n"]), product, config)
        books.append({
            "id": course["n"],
            "title": detail["title"],
            "author": detail["author"],
            "price": price if action.get('canBuy') else "",
            "priceText": price_text if action.get('canBuy') else "价格以渠道页面为准",
            "priceEvidence": "configured" if action.get('canBuy') else "unknown",
            "cat": course["category"],
            "category": course["category"],
            "shopProductId": product.get("productId", ""),
            "shopPath": action.get("path", ""),
            "affiliateUrl": action.get("url", ""),
            "externalUrl": action.get("url", ""),
            "commissionRate": product.get("commissionRate", ""),
            "settlementMode": product.get("settlementMode", "cps"),
            "commissionReady": product_has_direct_commission(product, config),
            "purchaseEntryReady": product_has_purchase_entry(product, config),
            "purchaseEntryType": action.get("entryKind", "unavailable"),
            "channel": product_channel(product),
            "channelName": product.get("channelName", ""),
            "source": product.get("source", product_channel(product)),
            "openType": action["type"],
            "canBuy": action.get("canBuy", False),
            "canOpen": action.get("canOpen", False),
            "entryKind": action.get("entryKind", "unavailable"),
            "action": action,
            "paymentEvidence": "none",
            "purchaseStatus": "ready" if action.get('canBuy') else (
                "authorization_or_service_missing" if action.get('entryKind') == 'configured_product'
                else action.get('entryKind', 'unavailable')),
            **public_merchant_info(product),
        })
    return {"books": books, "total": len(books), "shop": config}

@app.get("/api/books")
async def get_books(limit: int = 24):
    return await get_shop_books(limit)

@app.post("/api/shop/click")
async def record_shop_click(req: ShopClickReq, authorization: str = Header(None)):
    user = user_from_authorization(authorization)
    record_shop_lead(user, req.book_id, req.source or "miniapp", req.target or "")
    return {"success": True}

@app.post("/api/shop/resolve")
async def resolve_shop_book(req: ShopResolveReq, authorization: str = Header(None)):
    if req.book_id <= 0:
        raise HTTPException(400, "图书 ID 不合法")
    detail = shop_book_detail(req.book_id)
    product = detail["product"]
    action = book_open_action(req.book_id, product, shop_config())
    user = user_from_authorization(authorization)
    if action.get("target"):
        record_shop_lead(user, req.book_id, req.source or "miniapp", action["target"])
    return {
        "success": True,
        "book": {
            "bookId": req.book_id,
            "title": detail["title"],
            "author": detail["author"],
            "priceText": detail["price_text"] if action.get('canBuy') else "价格以渠道页面为准",
            "entryKind": action.get('entryKind', 'unavailable'),
            "paymentEvidence": "none",
            **public_merchant_info(product),
            "channel": product_channel(product),
            "commissionRate": product.get("commissionRate", ""),
            "settlementMode": product.get("settlementMode", "cps"),
            "commissionReady": product_has_direct_commission(product, shop_config()),
            "purchaseEntryReady": product_has_purchase_entry(product, shop_config()),
        },
        "action": action,
    }


@app.get("/api/shop/redirect/{book_id}")
async def redirect_shop_book(
    book_id: int,
    request: Request,
    source: str = "xhs",
    campaign: str = "",
    channel: str = "book_redirect",
    authorization: str = Header(None),
):
    if book_id <= 0:
        raise HTTPException(400, "图书 ID 不合法")
    detail = shop_book_detail(book_id)
    product = detail["product"]
    action = book_open_action(book_id, product, shop_config())
    target = safe_commerce_url(action.get("url") or "")
    if action.get('type') in ('mini_program', 'business_view'):
        return JSONResponse(status_code=200, content={"success": True, "action": action})
    user = user_from_authorization(authorization)
    if target:
        record_shop_lead(user, book_id, source or "web", target)
        record_launch_event(
            LaunchEventReq(
                event="book_click",
                source=source or "web",
                channel=channel or "book_redirect",
                campaign=campaign or "",
                path=str(request.url),
                referrer=request.headers.get("referer", ""),
                target=target,
                book_id=book_id,
                extra={
                    "redirect": True,
                    "commissionReady": product_has_direct_commission(product, shop_config()),
                    "shopChannel": product_channel(product),
                },
            ),
            request,
            user,
        )
        return RedirectResponse(target, status_code=302)
    return JSONResponse(status_code=404, content={"success": False, "message": action.get("message") or "该图书尚未配置购买链接"})

@app.get("/api/shop/purchases")
async def get_shop_purchases(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM book_purchases
        WHERE user_id=?
        ORDER BY CASE WHEN status='paid' THEN 0 ELSE 1 END, purchased_at DESC
    """, (user["id"],)).fetchall()
    conn.close()
    purchases = [purchase_public(row) for row in rows]
    return {
        "purchases": purchases,
        "summary": {
            "total": len(purchases),
            "paid": sum(1 for item in purchases if item["status"] == "paid" and item["paymentVerified"] is True),
            "pending": sum(1 for item in purchases if item["paymentVerified"] is not True),
        }
    }

@app.get("/api/wechat/config")
async def get_wechat_config():
    config = shop_config()
    return {
        "miniappAppId": WECHAT_MINIAPP_APPID,
        "officialAppId": WECHAT_OFFICIAL_APPID,
        "shopConfigured": config["enabled"],
        "shopMode": config["mode"],
        "paymentConfigured": payment_config()["ready"],
    }

# ============================================================
# AGENT COPILOT
# ============================================================
AGENT_SYSTEM_PROMPT = """你是康波研究院小程序里的投资学习Agent。你的任务是把用户在工具页得到的周期、资产、评分或排名结果，转成可执行的学习和决策复盘建议。

要求：
1. 只提供教育和研究用途的信息，不承诺收益，不构成个性化投资建议。
2. 先指出还需要补充的关键约束，例如年龄、现金流、负债、投资期限、已有持仓、最大回撤。
3. 用中文回答，结构清晰，尽量短句。
4. 默认输出四段：初步判断、需要追问、行动清单、风险提醒。
5. 如果用户要求直接买卖某个资产，必须先提醒风险边界和验证条件。"""

def call_deepseek_agent(req: AgentChatReq, user: dict) -> dict:
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=503, detail="DeepSeek API Key 未配置，请先在服务器环境变量 DEEPSEEK_API_KEY 中设置")

    prompt = (req.prompt or "").strip()
    if len(prompt) < 4:
        raise HTTPException(status_code=400, detail="Agent问题太短，请先选择或输入一个具体问题")

    context_text = ""
    if isinstance(req.context, dict):
        context_text = json.dumps(req.context, ensure_ascii=False)[:2500]

    user_prompt = "\n".join([
        f"用户ID：{user.get('id')}",
        f"来源：{(req.source or 'miniapp_tools')[:80]}",
        f"工具上下文：{context_text}" if context_text else "工具上下文：无",
        f"用户问题：{prompt[:1800]}",
    ])
    max_tokens = max(300, min(int(req.max_tokens or 900), 1500))
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.35,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if DEEPSEEK_THINKING in {"enabled", "disabled"}:
        payload["thinking"] = {"type": DEEPSEEK_THINKING}
    endpoint = f"{DEEPSEEK_BASE_URL}/chat/completions"
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    upstream_req = urlrequest.Request(
        endpoint,
        data=request_body,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(upstream_req, timeout=DEEPSEEK_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")[:800]
        raise HTTPException(status_code=502, detail=f"DeepSeek服务返回错误({exc.code})：{raw}")
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek服务暂不可用：{exc}")

    answer = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not answer:
        raise HTTPException(status_code=502, detail="DeepSeek未返回有效回答")

    return {
        "answer": answer,
        "model": data.get("model", DEEPSEEK_MODEL),
        "provider": "deepseek",
        "usage": data.get("usage", {}),
    }

def user_has_paid_agent_access(user: Optional[dict]) -> bool:
    if public_access_open():
        return bool(user)
    if not user:
        return False

    legacy_plan = user.get("plan") or "free"
    if legacy_plan not in ("", "free"):
        expires = user.get("plan_expires_at")
        if not expires or expires > datetime.now().isoformat():
            return True

    conn = get_db()
    try:
        return (
            has_active_entitlement(conn, user["id"], "core")
            or has_active_entitlement(conn, user["id"], "books")
            or has_active_entitlement(conn, user["id"], "bundle")
        )
    finally:
        conn.close()

def require_paid_agent_access(user: dict) -> None:
    if public_access_open():
        return
    if not user_has_paid_agent_access(user):
        raise HTTPException(
            status_code=403,
            detail="Agent API沟通功能仅限已付费会员使用，请先订阅主干课程年卡、书目课程年卡或全库升级包"
        )

PRACTICE_AGENT_SYSTEM_PROMPT = """你是康波研究院课程学习Agent，负责分析用户完成课程练习后的答案和课后反思。

请严格按 JSON 输出，不要输出 Markdown，不要输出额外解释：
{
  "feedback": "给用户的个性化反馈，包含优势、误区、下一步学习建议，180-260字",
  "focusPoints": ["课程重点1", "课程重点2", "课程重点3"],
  "followUps": ["追问1", "追问2", "追问3"]
}

要求：
1. 结合用户答案、得分、反思内容和课程关键词。
2. 反馈要具体，不能只说“继续努力”。
3. 追问要推动用户把概念和自己的决策、现金流、风险边界联系起来。
4. 只做教育和学习反馈，不承诺收益，不给直接买卖指令。"""

def call_deepseek_completion(system_prompt: str, user_prompt: str, max_tokens: int = 900) -> str:
    if not DEEPSEEK_API_KEY:
        raise HTTPException(status_code=503, detail="DeepSeek API Key 未配置")
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.35,
        "max_tokens": max(300, min(int(max_tokens or 900), 1500)),
        "stream": False,
    }
    if DEEPSEEK_THINKING in {"enabled", "disabled"}:
        payload["thinking"] = {"type": DEEPSEEK_THINKING}
    upstream_req = urlrequest.Request(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlrequest.urlopen(upstream_req, timeout=DEEPSEEK_TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )

def parse_agent_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except Exception:
        data = {"feedback": raw, "focusPoints": [], "followUps": []}
    data["feedback"] = str(data.get("feedback") or raw or "").strip()
    data["focusPoints"] = [str(item).strip() for item in (data.get("focusPoints") or []) if str(item).strip()][:5]
    data["followUps"] = [str(item).strip() for item in (data.get("followUps") or []) if str(item).strip()][:5]
    return data

def build_practice_ai_analysis(user: dict, meta: dict, practice: dict, results: list, score: int, reflection: str) -> dict:
    if not user_has_paid_agent_access(user):
        return {
            "status": "locked",
            "message": "AI个性化分析暂未开放，请先登录后再试",
            "feedback": "",
            "focusPoints": [],
            "followUps": [],
        }
    if not DEEPSEEK_API_KEY:
        return {
            "status": "not_configured",
            "message": "DeepSeek API Key 未配置，暂时无法生成AI个性化分析",
            "feedback": "",
            "focusPoints": [],
            "followUps": [],
        }

    lesson_type = "书目课程" if meta["isBookCourse"] else "主干课程"
    prompt = {
        "lesson": meta["lesson"],
        "lessonType": lesson_type,
        "score": score,
        "keywords": practice.get("keywords", [])[:10],
        "results": [
            {
                "title": item.get("title"),
                "score": item.get("score"),
                "covered": item.get("covered", []),
                "missing": item.get("missing", []),
                "answer": (item.get("answer") or "")[:600],
            }
            for item in results
        ],
        "reflection": reflection[:1600],
    }
    try:
        raw = call_deepseek_completion(
            PRACTICE_AGENT_SYSTEM_PROMPT,
            json.dumps(prompt, ensure_ascii=False),
            900
        )
        parsed = parse_agent_json(raw)
        return {"status": "ready", "message": "", **parsed}
    except Exception as exc:
        return {
            "status": "error",
            "message": f"AI分析暂时不可用：{exc}",
            "feedback": "",
            "focusPoints": [],
            "followUps": [],
        }

@app.get("/api/agent/config")
async def get_agent_config(authorization: str = Header(None)):
    user = user_from_authorization(authorization)
    open_mode = public_access_open()
    return {
        "provider": "deepseek",
        "ready": bool(DEEPSEEK_API_KEY),
        "model": DEEPSEEK_MODEL,
        "accessMode": "open" if open_mode else "paid",
        "requiresLogin": True,
        "requiresPaid": not open_mode,
        "loggedIn": bool(user),
        "hasAccess": user_has_paid_agent_access(user),
    }

@app.post("/api/agent/chat")
async def agent_chat(req: AgentChatReq, user=Depends(get_current_user)):
    require_paid_agent_access(user)
    return call_deepseek_agent(req, user)


# ============================================================
# LAUNCH TRACKING
# ============================================================
@app.post("/api/launch/event")
async def launch_event(req: LaunchEventReq, request: Request, authorization: str = Header(None)):
    user = user_from_authorization(authorization)
    return record_launch_event(req, request, user)

@app.post("/api/launch/manual-metrics")
async def launch_manual_metrics(req: ManualLaunchMetricsReq, request: Request):
    require_payment_admin_token(request, "缺少运营数据录入权限")
    return insert_manual_launch_metrics(req, request)

@app.post("/api/launch/manual-metrics-batch")
async def launch_manual_metrics_batch(req: ManualLaunchMetricsBatchReq, request: Request):
    require_payment_admin_token(request, "缺少运营数据录入权限")
    return insert_manual_launch_metrics_batch(req.rows or [], request)

@app.post("/api/launch/manual-metrics-import-preview")
async def launch_manual_metrics_import_preview(req: ManualLaunchMetricsImportReq):
    rows = parse_manual_metrics_rows(req.content or "")
    return {
        "success": True,
        "rows": len(rows),
        "preview": [row.model_dump() for row in rows[:20]],
    }

@app.post("/api/launch/manual-metrics-import")
async def launch_manual_metrics_import(req: ManualLaunchMetricsImportReq, request: Request):
    require_payment_admin_token(request, "缺少运营数据录入权限")
    rows = parse_manual_metrics_rows(req.content or "")
    if not rows:
        raise HTTPException(400, "没有解析到可导入的平台数据")
    return insert_manual_launch_metrics_batch(rows, request)

@app.get("/api/launch/stats")
async def launch_stats(days: int = 7):
    days = max(1, min(int(days or 7), 90))
    since = f"-{days} days"
    conn = get_db()
    row = conn.execute(
        """
        SELECT
            COUNT(CASE WHEN event_type='view' THEN 1 END) AS views,
            COUNT(DISTINCT CASE WHEN event_type='view' THEN ip_hash END) AS unique_visitors,
            COUNT(CASE WHEN event_type IN ('cta_click','subscribe_click','book_click','purchase_intent','manual_purchase') THEN 1 END) AS conversion_clicks,
            COUNT(CASE WHEN event_type='purchase_intent' THEN 1 END) AS purchase_intents,
            COUNT(CASE WHEN event_type='manual_purchase' THEN 1 END) AS manual_purchases
        FROM launch_events
        WHERE created_at >= datetime('now', ?)
        """,
        (since,),
    ).fetchone()
    by_source_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(source,''), 'direct') AS source,
               COUNT(CASE WHEN event_type='view' THEN 1 END) AS views,
               COUNT(CASE WHEN event_type IN ('cta_click','subscribe_click','book_click','purchase_intent','manual_purchase') THEN 1 END) AS conversion_clicks
        FROM launch_events
        WHERE created_at >= datetime('now', ?)
        GROUP BY COALESCE(NULLIF(source,''), 'direct')
        ORDER BY views DESC
        LIMIT 12
        """,
        (since,),
    ).fetchall()
    paid = conn.execute(
        """
        SELECT COUNT(*) AS orders, COALESCE(SUM(amount_fen), 0) AS revenue_fen
        FROM payments
        WHERE status='paid' AND COALESCE(paid_at, created_at) >= datetime('now', ?)
        """,
        (since,),
    ).fetchone()
    pending = conn.execute(
        """
        SELECT COUNT(*) AS orders
        FROM payments
        WHERE status='pending' AND created_at >= datetime('now', ?)
        """,
        (since,),
    ).fetchone()
    shop_clicks = conn.execute(
        "SELECT COUNT(*) AS c FROM shop_clicks WHERE created_at >= datetime('now', ?)",
        (since,),
    ).fetchone()["c"]
    book_paid = conn.execute(
        "SELECT COUNT(*) AS c FROM book_purchases WHERE status='paid' AND purchased_at >= datetime('now', ?)",
        (since,),
    ).fetchone()["c"]
    conn.close()
    manual_purchases = int(row["manual_purchases"] or 0)
    # Book rows are legacy claims until a trusted merchant callback is integrated.
    paid_orders = int(paid["orders"] or 0)
    return {
        "windowDays": days,
        "goal": {"views": 1000, "purchases": 50},
        "views": int(row["views"] or 0),
        "uniqueVisitors": int(row["unique_visitors"] or 0),
        "conversionClicks": int(row["conversion_clicks"] or 0),
        "purchaseIntents": int(row["purchase_intents"] or 0),
        "manualPurchases": manual_purchases,
        "unverifiedBookPaid": int(book_paid or 0),
        "paidPurchases": paid_orders,
        "paidRevenueFen": int(paid["revenue_fen"] or 0),
        "pendingOrders": int(pending["orders"] or 0),
        "bookSalesClicks": int(shop_clicks or 0),
        "bySource": [dict(r) for r in by_source_rows],
        "readiness": {
            "payment": payment_config(),
            "shop": shop_config(),
        },
    }

@app.get("/api/launch/sprint")
async def launch_sprint(days: int = 7):
    days = max(1, min(int(days or 7), 30))
    goal = {"views": 1000, "purchases": 50, "conversionClicks": 150}
    daily_targets = {
        "views": (goal["views"] + days - 1) // days,
        "purchases": (goal["purchases"] + days - 1) // days,
        "conversionClicks": (goal["conversionClicks"] + days - 1) // days,
        "publishTasks": 3,
    }
    start = promo_week_start().date()
    date_keys = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    day_map = {
        key: {
            "date": key,
            "dayNumber": idx + 1,
            "target": {
                "views": min(goal["views"], daily_targets["views"] * (idx + 1)),
                "purchases": min(goal["purchases"], daily_targets["purchases"] * (idx + 1)),
                "conversionClicks": min(goal["conversionClicks"], daily_targets["conversionClicks"] * (idx + 1)),
                "publishTasks": daily_targets["publishTasks"],
            },
            "actual": {
                "views": 0,
                "uniqueVisitors": 0,
                "conversionClicks": 0,
                "purchaseIntents": 0,
                "paidPurchases": 0,
                "paidRevenueFen": 0,
                "bookSalesClicks": 0,
                "publishTasks": 0,
                "reviews": 0,
            },
            "platforms": {},
        }
        for idx, key in enumerate(date_keys)
    }
    totals = {
        "views": 0,
        "uniqueVisitors": 0,
        "conversionClicks": 0,
        "purchaseIntents": 0,
        "paidPurchases": 0,
        "paidRevenueFen": 0,
        "bookSalesClicks": 0,
        "publishTasks": 0,
        "reviews": 0,
    }
    since = f"-{days} days"
    platform_keys = {"xhs", "douyin", "wechat_channels"}
    conn = get_db()
    event_rows = conn.execute(
        """
        SELECT
            date(created_at, '+8 hours') AS day,
            COALESCE(NULLIF(source,''), 'direct') AS source,
            COALESCE(NULLIF(channel,''), '') AS channel,
            event_type,
            COUNT(*) AS count,
            COUNT(DISTINCT CASE WHEN event_type='view' THEN ip_hash END) AS unique_visitors
        FROM launch_events
        WHERE created_at >= datetime('now', ?)
        GROUP BY date(created_at, '+8 hours'), source, channel, event_type
        """,
        (since,),
    ).fetchall()
    paid_rows = conn.execute(
        """
        SELECT date(COALESCE(paid_at, created_at), '+8 hours') AS day,
               COUNT(*) AS orders,
               COALESCE(SUM(amount_fen), 0) AS revenue_fen
        FROM payments
        WHERE status='paid' AND COALESCE(paid_at, created_at) >= datetime('now', ?)
        GROUP BY date(COALESCE(paid_at, created_at), '+8 hours')
        """,
        (since,),
    ).fetchall()
    book_paid_rows = conn.execute(
        """
        SELECT date(purchased_at, '+8 hours') AS day, COUNT(*) AS orders
        FROM book_purchases
        WHERE status='paid' AND purchased_at >= datetime('now', ?)
        GROUP BY date(purchased_at, '+8 hours')
        """,
        (since,),
    ).fetchall()
    shop_click_rows = conn.execute(
        """
        SELECT date(created_at, '+8 hours') AS day, COUNT(*) AS clicks
        FROM shop_clicks
        WHERE created_at >= datetime('now', ?)
        GROUP BY date(created_at, '+8 hours')
        """,
        (since,),
    ).fetchall()
    conn.close()

    for row in event_rows:
        day = row["day"]
        if day not in day_map:
            continue
        count = int(row["count"] or 0)
        event_type = row["event_type"] or ""
        source = row["source"] or "direct"
        channel = row["channel"] or ""
        platform = source if source in platform_keys else channel if channel in platform_keys else source
        platform_map = day_map[day]["platforms"]
        if platform not in platform_map:
            platform_map[platform] = {
                "views": 0,
                "uniqueVisitors": 0,
                "conversionClicks": 0,
                "purchaseIntents": 0,
                "paidPurchases": 0,
                "publishTasks": 0,
                "reviews": 0,
            }
        target = platform_map[platform]
        if event_type == "view":
            day_map[day]["actual"]["views"] += count
            totals["views"] += count
            unique_count = int(row["unique_visitors"] or 0)
            day_map[day]["actual"]["uniqueVisitors"] += unique_count
            totals["uniqueVisitors"] += unique_count
            target["views"] += count
            target["uniqueVisitors"] += unique_count
        if event_type in {"cta_click", "subscribe_click", "book_click", "purchase_intent", "manual_purchase"}:
            day_map[day]["actual"]["conversionClicks"] += count
            totals["conversionClicks"] += count
            target["conversionClicks"] += count
        if event_type == "purchase_intent":
            day_map[day]["actual"]["purchaseIntents"] += count
            totals["purchaseIntents"] += count
            target["purchaseIntents"] += count
        if event_type == "manual_purchase":
            for bucket in (day_map[day]["actual"], totals, target):
                bucket["manualPurchases"] = bucket.get("manualPurchases", 0) + count
        if event_type == "publish_task":
            day_map[day]["actual"]["publishTasks"] += count
            totals["publishTasks"] += count
            target["publishTasks"] += count
        if event_type == "promo_review":
            day_map[day]["actual"]["reviews"] += count
            totals["reviews"] += count
            target["reviews"] += count

    for row in paid_rows:
        day = row["day"]
        if day in day_map:
            orders = int(row["orders"] or 0)
            revenue = int(row["revenue_fen"] or 0)
            day_map[day]["actual"]["paidPurchases"] += orders
            day_map[day]["actual"]["paidRevenueFen"] += revenue
            totals["paidPurchases"] += orders
            totals["paidRevenueFen"] += revenue
    for row in book_paid_rows:
        day = row["day"]
        if day in day_map:
            orders = int(row["orders"] or 0)
            for bucket in (day_map[day]["actual"], totals):
                bucket['unverifiedBookPaid'] = bucket.get('unverifiedBookPaid', 0) + orders
    for row in shop_click_rows:
        day = row["day"]
        if day in day_map:
            clicks = int(row["clicks"] or 0)
            day_map[day]["actual"]["bookSalesClicks"] += clicks
            totals["bookSalesClicks"] += clicks
    platform_totals = {}
    for day_data in day_map.values():
        actual = day_data["actual"]
        actual["purchaseLike"] = max(actual["paidPurchases"], actual["purchaseIntents"])
        actual["publishRate"] = round(actual["publishTasks"] / max(1, daily_targets["publishTasks"]) * 100)
        actual["viewRate"] = round(actual["views"] / max(1, daily_targets["views"]) * 100)
        actual["purchaseRate"] = round(actual["purchaseLike"] / max(1, daily_targets["purchases"]) * 100)
        for platform, pdata in day_data["platforms"].items():
            if platform not in platform_totals:
                platform_totals[platform] = {
                    "views": 0,
                    "uniqueVisitors": 0,
                    "conversionClicks": 0,
                    "purchaseIntents": 0,
                    "paidPurchases": 0,
                    "manualPurchases": 0,
                    "publishTasks": 0,
                    "reviews": 0,
                }
            for key in platform_totals[platform]:
                platform_totals[platform][key] += int(pdata.get(key) or 0)
    purchase_like = max(totals["paidPurchases"], totals["purchaseIntents"])
    funnel = [
        {"key": "publishTasks", "name": "发布打卡", "value": totals["publishTasks"], "target": days * daily_targets["publishTasks"]},
        {"key": "views", "name": "浏览量", "value": totals["views"], "target": goal["views"]},
        {"key": "conversionClicks", "name": "转化点击", "value": totals["conversionClicks"], "target": goal["conversionClicks"]},
        {"key": "purchaseLike", "name": "购买或意向", "value": purchase_like, "target": goal["purchases"]},
    ]
    completion = {
        "publishRate": round(totals["publishTasks"] / max(1, days * daily_targets["publishTasks"]) * 100),
        "viewRate": round(totals["views"] / max(1, goal["views"]) * 100),
        "conversionRate": round(totals["conversionClicks"] / max(1, goal["conversionClicks"]) * 100),
        "purchaseRate": round(purchase_like / max(1, goal["purchases"]) * 100),
    }

    return {
        "windowDays": days,
        "weekStart": start.isoformat(),
        "goal": goal,
        "dailyTargets": daily_targets,
        "totals": totals,
        "completion": completion,
        "funnel": funnel,
        "platformTotals": platform_totals,
        "gap": {
            "views": max(0, goal["views"] - totals["views"]),
            "purchases": max(0, goal["purchases"] - purchase_like),
            "conversionClicks": max(0, goal["conversionClicks"] - totals["conversionClicks"]),
        },
        "days": [day_map[key] for key in date_keys],
    }

@app.get("/api/launch/purchase-intents")
async def launch_purchase_intents(request: Request, days: int = 30, limit: int = 200):
    require_payment_admin_token(request, "缺少购买意向查看权限")
    days = max(1, min(int(days or 30), 180))
    limit = max(1, min(int(limit or 200), 500))
    since = f"-{days} days"
    conn = get_db()
    total_row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM launch_events
        WHERE event_type='purchase_intent' AND created_at >= datetime('now', ?)
        """,
        (since,),
    ).fetchone()
    rows = conn.execute(
        """
        SELECT id, user_id, event_type, source, channel, campaign, path, referrer,
               target, plan, book_id, order_no, amount_fen, raw_json, created_at
        FROM launch_events
        WHERE event_type='purchase_intent' AND created_at >= datetime('now', ?)
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (since, limit),
    ).fetchall()
    summary_rows = conn.execute(
        """
        SELECT
            COALESCE(NULLIF(plan,''), 'unknown') AS plan,
            COALESCE(NULLIF(source,''), 'direct') AS source,
            COUNT(*) AS count
        FROM launch_events
        WHERE event_type='purchase_intent' AND created_at >= datetime('now', ?)
        GROUP BY COALESCE(NULLIF(plan,''), 'unknown'), COALESCE(NULLIF(source,''), 'direct')
        ORDER BY count DESC
        """,
        (since,),
    ).fetchall()
    conn.close()
    intents = []
    for row in rows:
        raw = json.loads(row["raw_json"] or "{}")
        extra = raw.get("extra") if isinstance(raw, dict) else {}
        if not isinstance(extra, dict):
            extra = {}
        intents.append({
            "id": row["id"],
            "createdAt": row["created_at"],
            "source": row["source"],
            "channel": row["channel"],
            "campaign": row["campaign"],
            "plan": row["plan"],
            "planName": extra.get("planName", ""),
            "price": extra.get("price", ""),
            "contact": extra.get("contact", ""),
            "note": extra.get("note", ""),
            "target": row["target"],
            "path": row["path"],
            "referrer": row["referrer"],
            "bookId": row["book_id"],
            "amountFen": row["amount_fen"],
        })
    return {
        "windowDays": days,
        "total": int(total_row["total"] or 0),
        "returned": len(intents),
        "intents": intents,
        "summary": [dict(row) for row in summary_rows],
    }

@app.get("/api/launch/readiness")
async def launch_readiness():
    payment = payment_config()
    shop = shop_config()
    live = digital_live_config()
    priority_blockers = []
    deferred_blockers = []
    if not payment.get("ready"):
        deferred_blockers.append("微信支付缺少证书序列号、商户私钥或 APIv3 Key，课程订阅暂先用购买意向承接")
    if not shop.get("purchaseEntryReady"):
        priority_blockers.append("图书尚未全部配置商品入口；搜索链接不计入商品，配置不代表成交")
    elif not shop.get("directCommissionReady"):
        deferred_blockers.append("500本图书已有购买入口，但尚未全部替换为微信小店或联盟分成链接")
    if not live.get("readyForPlatformPush"):
        deferred_blockers.append("数字人直播缺少抖音或视频号推流权限/RTMP地址，后续再处理")
    blockers = priority_blockers + deferred_blockers
    return {
        "domain": PUBLIC_BASE_URL,
        "miniappAppId": WECHAT_MINIAPP_APPID,
        "weeklyGoal": {"views": 1000, "purchases": 50},
        "payment": payment,
        "shop": shop,
        "live": live,
        "blockers": blockers,
        "priorityBlockers": priority_blockers,
        "deferredBlockers": deferred_blockers,
        "readyForWechatPromotion": not priority_blockers,
        "readyForTrafficTest": True,
        "readyForPaidLaunch": payment.get("ready") and shop.get("directCommissionReady"),
    }

@app.get("/api/launch/audit")
async def launch_audit(days: int = 7):
    days = max(1, min(int(days or 7), 30))
    stats = await launch_stats(days)
    sprint = await launch_sprint(min(days, 7))
    readiness = await launch_readiness()
    promo = await get_daily_promo(days=7)
    payment = readiness.get("payment") or {}
    shop = readiness.get("shop") or {}
    live = readiness.get("live") or {}
    link_coverage = shop.get("linkCoverage") or {}
    audio = live.get("audio") or {}
    audio_counts = audio.get("counts") or {}
    paid_or_intent = max(int(stats.get("paidPurchases") or 0), int(stats.get("purchaseIntents") or 0))
    requirements = [
        {
            "key": "miniapp_backend",
            "name": "微信小程序后端域名",
            "status": "ready",
            "summary": f"小程序 AppID {WECHAT_MINIAPP_APPID}，接口域名 {PUBLIC_BASE_URL}",
            "evidence": "/api/launch/readiness",
            "actionUrl": "launch-dashboard.html",
        },
        {
            "key": "miniapp_content",
            "name": "小程序课程内容",
            "status": "ready" if audio_counts.get("core") == 65 and audio_counts.get("book") == 500 else "attention",
            "summary": f"{audio_counts.get('core', 0)}/65 主干课程音频，{audio_counts.get('book', 0)}/500 书目课程音频",
            "evidence": "/api/audio-playlist?scope=all&limit=1",
            "actionUrl": "digital-human.html",
        },
        {
            "key": "wechat_payment",
            "name": "微信支付课程订阅",
            "status": "ready" if payment.get("ready") else "attention",
            "summary": "可真实扣款" if payment.get("ready") else "暂缓配置，先用购买意向页承接微信推广",
            "evidence": "/api/payment/diagnostics",
            "actionUrl": "payment-runbook.html",
            "missing": payment.get("missing") or [],
        },
        {
            "key": "book_links",
            "name": "500本书购买链接",
            "status": "ready" if shop.get("purchaseEntryReady") else "attention",
            "summary": f"{shop.get('purchaseEntryBooks', 0)}/{link_coverage.get('total', 500)} 本已配置商品入口，非成交证明",
            "evidence": "/api/shop/books?limit=500",
            "actionUrl": "book-shop.html",
        },
        {
            "key": "book_commission",
            "name": "500本书直接分成",
            "status": "ready" if shop.get("directCommissionReady") else "attention",
            "summary": f"{shop.get('directCommissionBooks', 0)}/{link_coverage.get('total', 500)} 本接入真实分成，购买入口可先推广",
            "evidence": "/api/shop/affiliate-workbook?channel=wechat_shop&format=json",
            "actionUrl": "affiliate-admin.html",
        },
        {
            "key": "daily_promo",
            "name": "每日推广文案",
            "status": "ready" if len(promo.get("items") or []) >= 7 else "attention",
            "summary": f"已生成 {len(promo.get('items') or [])} 天，小红书、抖音、微信视频号三平台可用",
            "evidence": "/api/promo/daily?days=7",
            "actionUrl": "xhs-promo.html",
        },
        {
            "key": "weekly_growth",
            "name": "首周1000浏览和50购买",
            "status": "ready" if stats.get("views", 0) >= 1000 and paid_or_intent >= 50 else "attention",
            "summary": f"当前 {stats.get('views', 0)}/1000 浏览，{paid_or_intent}/50 购买或意向",
            "evidence": "/api/launch/sprint?days=7",
            "actionUrl": "growth-sprint.html",
            "gap": sprint.get("gap") or {},
        },
        {
            "key": "digital_human_obs",
            "name": "数字人讲课画面",
            "status": "ready" if live.get("readyForObs") else "attention",
            "summary": "OBS源可用，565节课程可连续播放" if live.get("readyForObs") else "后续处理，当前先不依赖数字人直播",
            "evidence": "/api/live/readiness",
            "actionUrl": "digital-human-obs.html?layout=vertical&platform=both&muted=0",
        },
        {
            "key": "platform_live_push",
            "name": "抖音和微信视频号24小时推流",
            "status": "ready" if live.get("readyForPlatformPush") and live.get("streamingActive") else "attention",
            "summary": "平台推流运行中" if live.get("streamingActive") else "后续处理，当前先做微信图文和小程序传播",
            "evidence": "/api/live/readiness",
            "actionUrl": "live-control.html",
            "missing": live.get("missing") or [],
        },
    ]
    ready_count = sum(1 for item in requirements if item["status"] == "ready")
    blocked_count = sum(1 for item in requirements if item["status"] == "blocked")
    attention_count = sum(1 for item in requirements if item["status"] == "attention")
    return {
        "generatedAt": promo_china_today().strftime("%Y-%m-%d %H:%M:%S"),
        "domain": PUBLIC_BASE_URL,
        "miniappAppId": WECHAT_MINIAPP_APPID,
        "windowDays": days,
        "score": {
            "ready": ready_count,
            "attention": attention_count,
            "blocked": blocked_count,
            "total": len(requirements),
            "percent": round(ready_count / max(1, len(requirements)) * 100),
        },
        "requirements": requirements,
        "stats": stats,
        "sprint": sprint,
        "readiness": readiness,
        "todayPromo": promo.get("today"),
        "links": {
            "launchDashboard": "launch-dashboard.html",
            "paymentRunbook": "payment-runbook.html",
            "affiliateAdmin": "affiliate-admin.html",
            "growthSprint": "growth-sprint.html",
            "promoDesk": "xhs-promo.html",
            "liveControl": "live-control.html",
            "miniappDomain": "https://mp.weixin.qq.com/",
        },
    }

def daily_report_markdown(payload: dict) -> str:
    promo = payload.get("promo") or {}
    gaps = payload.get("gap") or {}
    stats = payload.get("stats") or {}
    lines = [
        f"# 康波研究院每日推广执行报告",
        "",
        f"- 日期：{payload.get('date', '')}",
        f"- 今日主题：{promo.get('headline', '')}",
        f"- 主干课程：{((promo.get('course') or {}).get('title') or '')}",
        f"- 书目课程：{((promo.get('book') or {}).get('title') or '')}",
        f"- 首周目标缺口：浏览 {gaps.get('views', 0)}，购买或意向 {gaps.get('purchases', 0)}，转化点击 {gaps.get('conversionClicks', 0)}",
        f"- 当前数据：浏览 {stats.get('views', 0)}，购买意向 {stats.get('purchaseIntents', 0)}，已支付 {stats.get('paidPurchases', 0)}，图书点击 {stats.get('bookSalesClicks', 0)}",
        "",
        "## 发布链接",
        "",
        f"- 购买意向页：{((promo.get('urls') or {}).get('purchaseIntent') or '')}",
        f"- 书目购买页：{((promo.get('urls') or {}).get('bookShop') or '')}",
        f"- 数字人直播源：{((promo.get('urls') or {}).get('digitalLive') or '')}",
        "",
        "## 平台发布内容",
    ]
    platform_contents = promo.get("platformContents") or {}
    for key in ["xhs", "douyin", "wechat_channels"]:
        content = platform_contents.get(key) or {}
        lines.extend([
            "",
            f"### {content.get('name', key)}",
            "",
            "主文案：",
            "",
            content.get("primaryCopy", ""),
            "",
            "短视频口播：",
            "",
            content.get("videoScript", ""),
            "",
            "直播口播：",
            "",
            content.get("liveScript", ""),
            "",
            f"购买意向链接：{content.get('purchaseIntentUrl', '')}",
            f"书目购买链接：{content.get('bookShopUrl', '')}",
            f"发布建议：{content.get('publishHint', '')}",
        ])
    blockers = payload.get("blockers") or []
    if blockers:
        lines.extend(["", "## 仍需处理", ""])
        lines.extend([f"- {item}" for item in blockers])
    lines.append("")
    return "\n".join(lines)

def daily_report_csv(payload: dict) -> Response:
    output = io.StringIO()
    fieldnames = [
        "date", "platform", "headline", "course", "book", "primaryCopy",
        "videoScript", "liveScript", "landingUrl", "purchaseIntentUrl",
        "bookShopUrl", "digitalLiveUrl", "viewsGap", "purchasesGap",
        "conversionClicksGap", "blockers",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    promo = payload.get("promo") or {}
    urls = promo.get("urls") or {}
    gaps = payload.get("gap") or {}
    blockers = "；".join(payload.get("blockers") or [])
    for key in ["xhs", "douyin", "wechat_channels"]:
        content = (promo.get("platformContents") or {}).get(key) or {}
        writer.writerow({
            "date": payload.get("date", ""),
            "platform": content.get("name", key),
            "headline": promo.get("headline", ""),
            "course": (promo.get("course") or {}).get("title", ""),
            "book": (promo.get("book") or {}).get("title", ""),
            "primaryCopy": content.get("primaryCopy", ""),
            "videoScript": content.get("videoScript", ""),
            "liveScript": content.get("liveScript", ""),
            "landingUrl": content.get("landingUrl", ""),
            "purchaseIntentUrl": content.get("purchaseIntentUrl", ""),
            "bookShopUrl": content.get("bookShopUrl", ""),
            "digitalLiveUrl": urls.get("digitalLive", ""),
            "viewsGap": gaps.get("views", 0),
            "purchasesGap": gaps.get("purchases", 0),
            "conversionClicksGap": gaps.get("conversionClicks", 0),
            "blockers": blockers,
        })
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kangbo-daily-promo-report.csv"'},
    )

@app.get("/api/launch/daily-report")
async def launch_daily_report(date: str = "", format: str = "json"):
    promo_data = await get_daily_promo(date=date, days=7)
    sprint = await launch_sprint(7)
    stats = await launch_stats(7)
    readiness = await launch_readiness()
    today = promo_data.get("today") or {}
    payload = {
        "date": today.get("date") or parse_promo_date(date).strftime("%Y-%m-%d"),
        "generatedAt": promo_china_today().strftime("%Y-%m-%d %H:%M:%S"),
        "promo": today,
        "stats": stats,
        "gap": sprint.get("gap") or {},
        "blockers": readiness.get("blockers") or [],
        "links": {
            "launchAudit": public_url("launch-audit.html"),
            "growthSprint": public_url("growth-sprint.html"),
            "promoDesk": public_url("xhs-promo.html"),
            "purchaseIntent": (today.get("urls") or {}).get("purchaseIntent", ""),
            "bookShop": (today.get("urls") or {}).get("bookShop", ""),
            "digitalLive": (today.get("urls") or {}).get("digitalLive", ""),
        },
    }
    fmt = (format or "json").strip().lower()
    if fmt in {"md", "markdown"}:
        return Response(
            content=daily_report_markdown(payload),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="kangbo-daily-promo-report.md"'},
        )
    if fmt == "csv":
        return daily_report_csv(payload)
    return payload

# ============================================================
# STATS & LEADERBOARD
# ============================================================
@app.get("/api/stats")
async def get_stats():
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_active=1").fetchone()['c']
    total_completions = conn.execute("SELECT COUNT(*) as c FROM course_progress WHERE status='completed'").fetchone()['c']
    conn.close()
    
    total_courses = len((await get_courses()).get("courses", []))
    
    return {
        "total_courses": total_courses,
        "total_users": total_users,
        "total_completions": total_completions,
        "phases": 10,
        "books": len(parse_book_courses())
    }

@app.get("/api/leaderboard")
async def get_leaderboard():
    conn = get_db()
    rows = conn.execute("""
        SELECT u.username, u.avatar, 
               COUNT(CASE WHEN cp.status='completed' THEN 1 END) as completed,
               AVG(cp.progress_percent) as avg_progress
        FROM users u
        LEFT JOIN course_progress cp ON u.id = cp.user_id
        WHERE u.is_active = 1
        GROUP BY u.id
        ORDER BY completed DESC, avg_progress DESC
        LIMIT 20
    """).fetchall()
    conn.close()
    
    return {"leaderboard": [
        {"rank": i+1, "username": r['username'], "avatar": r['avatar'],
         "completed": r['completed'], "progress": round(r['avg_progress'] or 0, 1)}
        for i, r in enumerate(rows)
    ]}

# ============================================================
# HEALTH
# ============================================================
@app.get("/api/health")
async def health():
    conn = get_db()
    users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    conn.close()
    return {
        "status": "healthy",
        "service": "康波研究院 API",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "registered_users": users
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)

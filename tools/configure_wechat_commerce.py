#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen


ENV_PATH = Path("/etc/kangboacademy/wechat.env")
CERT_DIR = Path("/etc/kangboacademy/certs")
PAY_KEY_PATH = CERT_DIR / "apiclient_key.pem"
SHOP_PRODUCTS_PATH = Path("/var/www/kangboacademy/data/shop-products.json")
SHOP_PRODUCTS_EXAMPLE = Path("/var/www/kangboacademy/data/shop-products.example.json")


def run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_text, text=True, check=True)


def sudo_write(path: Path, content: str, mode: str = "600", owner: str = "root:root") -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        run(["sudo", "install", "-o", owner.split(":", 1)[0], "-g", owner.split(":", 1)[1], "-m", mode, tmp_path, str(path)])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def sudo_mkdir(path: Path, mode: str = "700", owner: str = "root:root") -> None:
    run(["sudo", "mkdir", "-p", str(path)])
    run(["sudo", "chown", owner, str(path)])
    run(["sudo", "chmod", mode, str(path)])


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except PermissionError:
        text = subprocess.check_output(["sudo", "cat", str(path)], text=True)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = shlex.split(value.strip())[0] if value.strip() else ""
    return values


def render_env(values: dict[str, str]) -> str:
    lines = [
        "# Kangbo Academy runtime secrets.",
        "# Managed by tools/configure_wechat_commerce.py. Do not commit this file.",
    ]
    for key in sorted(values):
        lines.append(f"{key}={shlex.quote(str(values[key]))}")
    return "\n".join(lines) + "\n"


def update_env(args: argparse.Namespace) -> None:
    existing = read_env(ENV_PATH)
    updates = {
        "WECHAT_PAY_NOTIFY_URL": args.pay_notify_url,
        "WECHAT_PAY_PRIVATE_KEY_PATH": str(PAY_KEY_PATH) if args.pay_private_key else existing.get("WECHAT_PAY_PRIVATE_KEY_PATH", ""),
        "BOOK_AFFILIATE_MODE": args.book_affiliate_mode,
    }
    optional = {
        "WECHAT_PAY_MCHID": args.pay_mchid,
        "WECHAT_PAY_CERT_SERIAL_NO": args.pay_cert_serial,
        "WECHAT_PAY_API_V3_KEY": args.pay_api_v3_key,
        "WECHAT_SHOP_APPID": args.shop_appid,
        "WECHAT_SHOP_HOME_PATH": args.shop_home_path,
        "WECHAT_SHOP_PRODUCT_PATH_TEMPLATE": args.shop_product_path_template,
        "WECHAT_SHOP_BUSINESS_TYPE": args.shop_business_type,
        "WECHAT_SHOP_QUERY_STRING": args.shop_query_string,
    }
    for key, value in optional.items():
        if value:
            updates[key] = value
    merged = {**existing, **{k: v for k, v in updates.items() if v is not None}}
    sudo_write(ENV_PATH, render_env(merged), mode="600", owner="root:root")


def install_private_key(source: str) -> None:
    src = Path(source).expanduser()
    if not src.exists():
        raise SystemExit(f"商户私钥不存在：{src}")
    text = src.read_text(encoding="utf-8", errors="ignore")
    if "BEGIN" not in text or "PRIVATE KEY" not in text:
        raise SystemExit("商户私钥格式不正确，应该是 PEM 格式的 apiclient_key.pem")
    sudo_mkdir(CERT_DIR, mode="700", owner="ubuntu:ubuntu")
    sudo_write(PAY_KEY_PATH, text, mode="600", owner="ubuntu:ubuntu")


def install_shop_products(source: str | None) -> None:
    if source:
        src = Path(source).expanduser()
        if not src.exists():
            raise SystemExit(f"商品映射文件不存在：{src}")
        data = json.loads(src.read_text(encoding="utf-8"))
    elif SHOP_PRODUCTS_PATH.exists():
        return
    elif SHOP_PRODUCTS_EXAMPLE.exists():
        data = json.loads(SHOP_PRODUCTS_EXAMPLE.read_text(encoding="utf-8"))
    else:
        data = {}
    SHOP_PRODUCTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHOP_PRODUCTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def restart_and_verify() -> None:
    run(["sudo", "systemctl", "restart", "kangboacademy"])
    print("kangboacademy service restarted")
    for url in [
        "http://127.0.0.1:8088/api/health",
        "http://127.0.0.1:8088/api/membership/plans",
        "http://127.0.0.1:8088/api/shop/config",
    ]:
        try:
            with urlopen(url, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if url.endswith("/api/membership/plans"):
                print("payment:", json.dumps(payload.get("payment"), ensure_ascii=False))
            elif url.endswith("/api/shop/config"):
                print("shop:", json.dumps(payload, ensure_ascii=False))
            else:
                print("health:", json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            print(f"verify failed for {url}: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Kangbo WeChat Pay and book sales settings.")
    parser.add_argument("--pay-mchid", default="")
    parser.add_argument("--pay-cert-serial", default="")
    parser.add_argument("--pay-api-v3-key", default="")
    parser.add_argument("--pay-private-key", default="", help="Path to apiclient_key.pem")
    parser.add_argument("--pay-notify-url", default="https://kangboacademy.cn/api/payment/wechat/notify")
    parser.add_argument("--shop-appid", default="")
    parser.add_argument("--shop-home-path", default="pages/index/index")
    parser.add_argument("--shop-product-path-template", default="")
    parser.add_argument("--shop-business-type", default="")
    parser.add_argument("--shop-query-string", default="")
    parser.add_argument("--book-affiliate-mode", default="wechat_shop")
    parser.add_argument("--shop-products", default="", help="JSON mapping file for book_id -> shop product metadata")
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_args()

    if args.pay_private_key:
        install_private_key(args.pay_private_key)
    update_env(args)
    install_shop_products(args.shop_products or None)
    if not args.no_restart:
        restart_and_verify()
    else:
        print("configuration written; restart skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

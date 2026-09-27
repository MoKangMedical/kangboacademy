#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib import parse, request


DEFAULT_API_BASE = "https://kangboacademy.cn/api"
DEFAULT_TEMPLATE = "https://search.jd.com/Search?keyword={encodedTitle}"


def fetch_book_courses(api_base: str) -> list[dict]:
    url = f"{api_base.rstrip('/')}/book-courses?limit=500"
    with request.urlopen(url, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    courses = payload.get("courses") or []
    if len(courses) < 500:
        raise SystemExit(f"expected 500 book courses, got {len(courses)} from {url}")
    return courses[:500]


def clean_title(title: str) -> str:
    return str(title or "").strip().removeprefix("《").removesuffix("》").strip()


def render_template(template: str, course: dict) -> str:
    title = clean_title(course.get("title") or course.get("t") or "")
    author = str(course.get("author") or course.get("a") or "").strip()
    book_id = str(course.get("id") or course.get("n") or "")
    values = {
        "bookId": book_id,
        "id": book_id,
        "title": title,
        "rawTitle": course.get("title") or course.get("t") or "",
        "author": author,
        "encodedTitle": parse.quote(title),
        "encodedAuthor": parse.quote(author),
    }
    return template.format(**values)


def build_mapping(args: argparse.Namespace, courses: list[dict]) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for course in courses:
        book_id = int(course.get("id") or course.get("n"))
        target = render_template(args.template, course)
        item = {
            "title": course.get("title") or course.get("t") or f"图书 {book_id}",
            "author": course.get("author") or course.get("a") or "",
            "price": args.price,
            "channel": args.source,
            "channelName": args.channel_name,
            "source": args.source,
            "settlementMode": args.settlement_mode,
            "commissionRate": args.commission_rate,
            "openType": args.open_type,
            "purchaseEntryReady": True,
            "purchaseEntryType": args.purchase_entry_type,
        }
        if args.target_field in {"affiliateUrl", "externalUrl", "shortUrl", "url", "path", "shopPath"}:
            item[args.target_field] = target
        elif args.target_field in {"productId", "shopProductId"}:
            item[args.target_field] = target
        else:
            raise SystemExit(f"unsupported target field: {args.target_field}")
        mapping[str(book_id)] = item
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a 500-book purchase-entry mapping for Kangbo Academy.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, help="URL/path template. Supports {bookId}, {title}, {encodedTitle}, {author}, {encodedAuthor}.")
    parser.add_argument("--output", default="data/shop-products.purchase-entry.json")
    parser.add_argument("--target-field", default="externalUrl")
    parser.add_argument("--source", default="jd_search")
    parser.add_argument("--channel-name", default="京东搜索购买入口")
    parser.add_argument("--settlement-mode", default="purchase_entry")
    parser.add_argument("--commission-rate", default="")
    parser.add_argument("--open-type", default="clipboard")
    parser.add_argument("--purchase-entry-type", default="search")
    parser.add_argument("--price", default="去渠道查看")
    args = parser.parse_args()

    courses = fetch_book_courses(args.api_base)
    mapping = build_mapping(args, courses)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ready = sum(1 for item in mapping.values() if item.get(args.target_field))
    print(json.dumps({"output": str(output), "books": len(mapping), "purchaseEntries": ready}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

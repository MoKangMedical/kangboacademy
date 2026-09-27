#!/usr/bin/env python3
"""Offline, fail-closed partner product validation; never installs products."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "shared/content-contract.json"
REQUIRED = {
    "bookId", "title", "author", "channel", "channelName", "settlementMode",
    "productId", "merchantName", "merchantId", "authorizationBasis",
    "authorizationReference", "afterSales", "afterSalesContact",
    "targetEvidence",
}
OPTIONAL = {
    "price", "priceEvidence", "commissionRate", "commissionEvidence",
    "externalUrl", "affiliateUrl", "miniProgramAppId", "path", "businessType",
    "queryString", "source", "openType",
}
FIELDS = REQUIRED | OPTIONAL
PLACEHOLDERS = {"待配置", "待提供", "待确认", "示例", "未知", "todo", "tbd", "n/a", "null", "none", "test", "example"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)


def load_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)) or not REQUIRED <= set(headers):
                raise ValueError("CSV requires unique headers and all required fields")
            if set(headers) - FIELDS:
                raise ValueError(f"unknown CSV headers: {sorted(set(headers) - FIELDS)}")
            rows = list(reader)
            if any(None in row or None in row.values() for row in rows):
                raise ValueError("CSV row width differs from header")
            return rows
    if path.suffix.lower() != ".json":
        raise ValueError("input must be .csv or .json")
    data = read_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        rows = []
        for key, value in data.items():
            if not isinstance(value, dict):
                raise ValueError(f"mapping value must be an object: {key}")
            if "bookId" in value and value["bookId"] != key:
                raise ValueError(f"bookId conflicts with mapping key: {key}")
            rows.append({**value, "bookId": key})
        return rows
    raise ValueError("JSON must be a row array or book ID mapping")


def load_catalog(path: Path) -> dict:
    contract = read_json(path)
    if not isinstance(contract, dict) or not isinstance(contract.get("courses"), list):
        raise ValueError("catalog must be a content contract with a courses array")
    catalog = {}
    for book in contract["courses"]:
        if not isinstance(book, dict):
            raise ValueError("content contract courses must be objects")
        if book.get("kind") != "book":
            continue
        number = book.get("number")
        if type(number) is not int or not 1 <= number <= 500:
            raise ValueError("book number must be an integer in 1..500")
        key = str(number)
        if book.get("key") != f"book:{key}" or key in catalog:
            raise ValueError(f"duplicate or inconsistent book key: {key}")
        if any(not isinstance(book.get(f), str) or not book[f].strip() for f in ("title", "author")):
            raise ValueError(f"catalog lacks canonical title/author: {key}")
        catalog[key] = {field: book[field] for field in ("title", "author")}
    if set(catalog) != {str(i) for i in range(1, 501)}:
        raise ValueError("catalog must contain exactly book IDs 1..500")
    return catalog


def decoded(value: str) -> str:
    for _ in range(4):
        new = unquote(value)
        if new == value:
            break
        value = new
    return value


def concrete_target(value: str, product_id: str, *, url: bool) -> bool:
    value = decoded(value)
    if re.search(r"[\s\\{}<>\x00-\x1f\x7f]", value):
        return False
    parsed = urlsplit(value)
    if parsed.fragment or parsed.username or parsed.password:
        return False
    if url:
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or "." not in host or parsed.port not in (None, 443):
            return False
        if host in {"localhost", "example.com", "example.org", "example.net"} or host.endswith((".example", ".invalid", ".test", ".local")):
            return False
        if host == "jd.com" or host.endswith(".jd.com"):
            return host == "item.jd.com" and parsed.path == f"/{product_id}.html" and not parsed.query and product_id.isdigit()
    else:
        if parsed.scheme or parsed.netloc or not re.fullmatch(r"/?pages/[A-Za-z0-9_/-]+(?:\?[^\s{}\\#]+)?", value) or ".." in value:
            return False
    if re.search(r"search|keyword|query=|redirect|returnurl|callback", value, re.I):
        return False
    # Require an ID as a complete path/query token, not a substring of a shop URL.
    tokens = re.split(r"[/?.]", parsed.path) + [value for _, value in parse_qsl(parsed.query)]
    return product_id in tokens and parsed.path not in {"", "/"}


def validate(rows: list[dict], catalog: dict, *, allow_partial: bool = False, authorization_reviewed: bool = False):
    errors = []
    products = {}
    seen = set()
    if not rows or len(rows) > 500:
        errors.append("batch must contain 1..500 rows")
    for number, raw in enumerate(rows, 1):
        issues = []
        if not isinstance(raw, dict):
            errors.append(f"row {number}: must be an object")
            continue
        if set(raw) - FIELDS:
            issues.append(f"unknown fields: {sorted(set(raw) - FIELDS)}")
        if any(not isinstance(value, str) for value in raw.values()):
            errors.append(f"row {number}: all values must be strings (including IDs/prices)")
            continue
        row = {key: value.strip() for key, value in raw.items()}
        for key in REQUIRED:
            if not row.get(key) or row[key].lower() in PLACEHOLDERS:
                issues.append(f"required non-placeholder field: {key}")
        for key, value in row.items():
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                issues.append(f"control character in {key}")
            if value and value.lower() in PLACEHOLDERS:
                issues.append(f"placeholder in {key}")
        reference = row.get("authorizationReference", "")
        for key, limit in (("merchantName", 200), ("afterSalesContact", 200), ("afterSales", 500)):
            value = row.get(key, "")
            if len(value) > limit or (reference and reference in value) or re.search(
                r"file:|(?:^|\s)(?:~[/\\]|[A-Za-z]:\\|/(?:Users|home|root|var|tmp|etc|private|mnt)/)", value, re.I
            ):
                issues.append(f"{key} must be public text without private document references (max {limit} characters)")
        if reference and any(reference in row.get(key, "") for key in ("externalUrl", "affiliateUrl", "path")):
            issues.append("product targets must not contain the private authorizationReference")
        book_id = row.get("bookId", "")
        if book_id not in catalog:
            issues.append("bookId must be a catalog ID 1..500 without leading zeros")
        else:
            for field in ("title", "author"):
                if row.get(field) != catalog[book_id][field]:
                    issues.append(f"{field} does not match catalog")
        if book_id in seen:
            issues.append("duplicate bookId")
        seen.add(book_id)
        channel = row.get("channel")
        if channel not in {"wechat_shop", "jd_union", "custom"}:
            issues.append("channel must be wechat_shop, jd_union or custom; search is not a product")
        if row.get("source") and row["source"] != channel:
            issues.append("source must equal channel")
        mode = row.get("settlementMode")
        if mode not in {"agreement", "direct", "wechat_shop", "cps", "commission", "affiliate"}:
            issues.append("unsupported settlementMode")
        product_id = row.get("productId", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", product_id):
            issues.append("invalid productId")
        for field, evidence in (("price", "priceEvidence"), ("commissionRate", "commissionEvidence")):
            value = row.get(field, "")
            if value:
                if not re.fullmatch(r"(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,2})?", value):
                    issues.append(f"{field} must be a nonnegative decimal with at most two decimal places")
                elif field == "commissionRate" and float(value) > 100:
                    issues.append("commissionRate must be in 0..100 percent")
                if not row.get(evidence):
                    issues.append(f"{evidence} required when {field} is supplied")
        if mode in {"cps", "commission", "affiliate"} and not row.get("commissionRate"):
            issues.append("commission settlement requires documented commissionRate")
        urls = [row.get(f, "") for f in ("externalUrl", "affiliateUrl") if row.get(f)]
        if len(set(urls)) > 1:
            issues.append("externalUrl and affiliateUrl must identify the same target")
        for value in urls:
            try:
                valid = concrete_target(value, product_id, url=True)
            except ValueError:
                valid = False
            if not valid:
                issues.append("URL must be a concrete HTTPS product target containing productId; no search/short/redirect URL")
        if row.get("businessType") or row.get("queryString") or row.get("openType") == "business_view":
            issues.append("business_view is unsupported; businessType and queryString must remain blank")
        if channel == "wechat_shop":
            app_id = row.get("miniProgramAppId", "")
            path = row.get("path", "")
            if urls:
                issues.append("wechat_shop requires a mini-program target without URLs")
            try:
                valid_path = concrete_target(path, product_id, url=False)
            except ValueError:
                valid_path = False
            if not re.fullmatch(r"wx[0-9a-f]{16}", app_id) or not valid_path:
                issues.append("requires valid miniProgramAppId and concrete product path containing productId")
            expected_open = "mini_program"
        else:
            if not urls or any(row.get(k) for k in ("miniProgramAppId", "path", "businessType", "queryString")):
                issues.append("external channel requires only a concrete product URL")
            if channel == "jd_union":
                try:
                    jd_host = urlsplit(urls[0]).hostname if urls else None
                except ValueError:
                    jd_host = None
                if jd_host != "item.jd.com":
                    issues.append("jd_union requires canonical item.jd.com product URL; opaque affiliate links need manual review")
            expected_open = "clipboard"
        if row.get("openType") and row["openType"] != expected_open:
            issues.append(f"openType must be {expected_open}")
        if issues:
            errors.extend(f"row {number} (bookId={book_id}): {issue}" for issue in issues)
            continue
        product = {key: value for key, value in row.items() if key not in {"bookId", "afterSalesContact"} and value}
        product["afterSales"] = {"description": row["afterSales"], "contact": row["afterSalesContact"]}
        product["authorizationStatus"] = "confirmed" if authorization_reviewed else "unverified"
        if row.get("commissionRate"):
            product["commissionRate"] = row["commissionRate"] + "%"
        product.update(source=channel, openType=expected_open)
        products[book_id] = product
    missing = sorted(set(catalog) - set(products), key=int)
    if not allow_partial and missing:
        errors.append(f"complete batch requires all 500 books; missing or invalid: {','.join(missing)}")
    return products, errors, missing


def check_output_path(path: Path, suffix: str) -> None:
    resolved = path.expanduser().resolve()
    if not resolved.name.endswith(suffix):
        raise ValueError(f"output filename must end with {suffix}")
    if any(resolved.is_relative_to(root.resolve()) for root in (Path("/var/www"), Path("/etc"))):
        raise ValueError("production/config output directories are forbidden")


def write_candidate(path: Path, products: dict) -> None:
    check_output_path(path, ".candidate.json")
    # Exclusive creation rejects existing files, including symlinks, without overwrite.
    with path.expanduser().open("x", encoding="utf-8") as stream:
        json.dump(products, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def write_matching_csv(path: Path, catalog: dict) -> None:
    """Create an unfilled matching worksheet, not a product import or readiness claim."""
    check_output_path(path, ".csv")
    with (ROOT / "data/partner-products.template.csv").open(encoding="utf-8", newline="") as stream:
        headers = next(csv.reader(stream))
    if len(headers) != len(set(headers)) or set(headers) != FIELDS:
        raise ValueError("template header differs from import schema")
    with path.expanduser().open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        for key in sorted(catalog, key=int):
            writer.writerow({"bookId": key, "title": catalog[key]["title"], "author": catalog[key]["author"]})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--allow-partial", action="store_true", help="validate an explicitly incomplete batch")
    parser.add_argument("--output", type=Path, help="create a NEW *.candidate.json only if the entire batch passes")
    parser.add_argument("--dry-run", action="store_true", help="explicit validation only; incompatible with --output")
    parser.add_argument("--generate-matching-csv", type=Path, metavar="NEW.csv", help="create a NEW 500-row unfilled worksheet from the content contract")
    parser.add_argument("--authorization-reviewed", action="store_true", help="explicit human attestation that every row's actual authorization has been reviewed; emit confirmed, never infer it")
    args = parser.parse_args(argv)
    if args.dry_run and args.output:
        parser.error("--dry-run and --output are mutually exclusive")
    if args.generate_matching_csv:
        if args.input or args.output or args.dry_run or args.allow_partial or args.authorization_reviewed:
            parser.error("--generate-matching-csv cannot be combined with import options")
    elif args.input is None:
        parser.error("input is required unless --generate-matching-csv is specified")
    try:
        catalog = load_catalog(args.catalog)
        if args.generate_matching_csv:
            write_matching_csv(args.generate_matching_csv, catalog)
            print(json.dumps({"status": "UNFILLED_MATCHING_WORKSHEET_NOT_PRODUCTS", "rows": len(catalog), "output": str(args.generate_matching_csv.resolve())}, ensure_ascii=False))
            return 0
        products, errors, missing = validate(load_rows(args.input), catalog, allow_partial=args.allow_partial,
                                            authorization_reviewed=args.authorization_reviewed)
        report = {
            "status": "REJECTED" if errors else "OFFLINE_VALIDATED_NOT_VERIFIED_NOT_DEPLOYED",
            "dryRun": not bool(args.output), "qualified": len(products), "total": 500,
            "complete": not missing, "missingBookIds": missing, "errors": errors,
            "authorizationStatus": "confirmed" if args.authorization_reviewed else "unverified",
            "warning": "Offline checks cannot prove merchant identity, authorization, stock, price or target ownership. Human review and real-device verification are required.",
        }
        if args.output and not errors:
            write_candidate(args.output, products)
            report["candidate"] = str(args.output.resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if errors else 0
    except (OSError, ValueError, csv.Error) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Synthetic fixtures only. Never use these merchants/products in production."""
import ast
import contextlib
import csv
import io
import json
import re
from pathlib import Path
import tempfile
import unittest
from typing import Optional
from urllib import parse

import import_partner_products as importer


def catalog():
    return {str(i): {"title": f"SYNTHETIC book {i}", "author": "SYNTHETIC author"} for i in range(1, 501)}


def contract():
    return {"courses": [{"kind": "book", "number": int(key), "key": f"book:{key}",
                         "displayTitle": "NOT canonical", **book} for key, book in catalog().items()]
            + [{"kind": "core", "number": 1, "title": "NOT a book"}]}


def fixture(book_id="1", **changes):
    row = {
        "bookId": book_id, "title": f"SYNTHETIC book {book_id}",
        "author": "SYNTHETIC author", "channel": "wechat_shop",
        "channelName": "SYNTHETIC shop", "settlementMode": "agreement",
        "productId": f"sku-{book_id}", "merchantName": "SYNTHETIC merchant",
        "merchantId": "SYNTHETIC-merchant-1", "authorizationBasis": "SYNTHETIC agreement",
        "authorizationReference": "SYNTHETIC agreement ref 1",
        "afterSales": "SYNTHETIC return policy; SYNTHETIC service desk",
        "afterSalesContact": "SYNTHETIC public customer service",
        "targetEvidence": "SYNTHETIC target inspection record",
        "miniProgramAppId": "wx0000000000000000", "path": f"pages/product/detail?productId=sku-{book_id}",
    }
    row.update(changes)
    return row


class ValidationTests(unittest.TestCase):
    def validate(self, rows, partial=True):
        return importer.validate(rows, catalog(), allow_partial=partial)

    def test_complete_500(self):
        products, errors, missing = self.validate([fixture(str(i)) for i in range(1, 501)], False)
        self.assertEqual(errors, [])
        self.assertEqual(missing, [])
        self.assertEqual(len(products), 500)
        self.assertNotIn("price", products["1"])
        self.assertNotIn("commissionReady", products["1"])

    def test_partial_explicit(self):
        self.assertTrue(self.validate([fixture()], False)[1])
        self.assertEqual(self.validate([fixture()])[1], [])
        self.assertEqual(len(self.validate([fixture()])[2]), 499)

    def test_missing_required_and_placeholders(self):
        for field in importer.REQUIRED:
            for value in ("", "待配置", "TODO"):
                with self.subTest(field=field, value=value):
                    self.assertTrue(self.validate([fixture(**{field: value})])[1])

    def test_invalid_ids_identity_duplicates_and_types(self):
        for row in (fixture("0"), fixture("501"), fixture("01"), fixture(title="Different book"),
                    fixture(author="Wrong author"), fixture(bookId=1), fixture(price=12),
                    fixture(sales="999"), fixture(wechatContact="invented"), fixture(commissionReady="true"),
                    fixture(purchaseEntryReady="true"), fixture(canBuy="true"),
                    fixture(afterSalesPolicy="legacy"), fixture(authorizationStatus="confirmed")):
            with self.subTest(row=row):
                self.assertTrue(self.validate([row])[1])
        self.assertTrue(self.validate([fixture(), fixture()])[1])
        self.assertTrue(self.validate([])[1])
        self.assertTrue(self.validate([None])[1])

    def test_search_and_non_products(self):
        for url in (
            "https://search.jd.com/Search?keyword=123", "https://search.jd.com/search?productId=123",
            "https://item.jd.com.evil.test/123.html", "https://item.jd.com/123.html?keyword=x",
            "https://item.jd.com/1234.html", "http://item.jd.com/123.html",
            "https://item.jd.com/123.html#fragment", "https://user:pass@item.jd.com/123.html",
            "https://item.jd.com/%53earch?keyword=123", "https://u.jd.com/123",
            "https://[broken/123", "https://item.jd.com/123.html?redirect=https://search.jd.com",
        ):
            with self.subTest(url=url):
                self.assertTrue(self.validate([fixture(channel="jd_union", productId="123", miniProgramAppId="", path="", externalUrl=url)])[1])
        self.assertTrue(self.validate([fixture(channel="jd_search")])[1])

    def test_valid_jd_and_rejected_business_view(self):
        self.assertEqual(self.validate([fixture(channel="jd_union", productId="123", miniProgramAppId="", path="", externalUrl="https://item.jd.com/123.html")])[1], [])
        for changes in ({"miniProgramAppId": "", "path": "", "businessType": "SYNTHETIC", "queryString": "productId=sku-1"},
                        {"businessType": "SYNTHETIC"}, {"queryString": "productId=sku-1"}, {"openType": "business_view"}):
            with self.subTest(changes=changes):
                self.assertTrue(self.validate([fixture(**changes)])[1])

    def test_target_conflicts_and_home_pages(self):
        for changes in (
            {"path": "pages/index/index"}, {"path": "pages/search?productId=sku-1"},
            {"path": "pages/product?productId=sku-11"}, {"miniProgramAppId": "bad"},
            {"businessType": "SYNTHETIC", "queryString": "productId=sku-1"},
            {"miniProgramAppId": "", "path": "", "businessType": "SYNTHETIC", "queryString": "productId=sku-1&productId=sku-2"},
            {"externalUrl": "https://item.jd.com/123.html"}, {"openType": "web_view"},
            {"source": "jd_search"}, {"afterSales": "bad\x00data"},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(self.validate([fixture(**changes)])[1])

    def test_prices_and_commissions(self):
        for price in ("NaN", "Infinity", "-1", "1.234", "1e2", "￥12", "待配置"):
            self.assertTrue(self.validate([fixture(price=price, priceEvidence="SYNTHETIC evidence")])[1])
        self.assertTrue(self.validate([fixture(price="1.00")])[1])
        self.assertTrue(self.validate([fixture(settlementMode="cps")])[1])
        self.assertTrue(self.validate([fixture(commissionRate="101", commissionEvidence="SYNTHETIC evidence")])[1])
        self.assertEqual(self.validate([fixture(price="0.00", priceEvidence="SYNTHETIC evidence", settlementMode="cps", commissionRate="2.50", commissionEvidence="SYNTHETIC evidence")])[1], [])


class InputAndOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.json"
        self.source.write_text(json.dumps([fixture()]), encoding="utf-8")
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps(contract()), encoding="utf-8")
        self.output = self.root / "new.candidate.json"

    def run_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = importer.main([str(self.source), "--catalog", str(self.catalog), *args])
        return code, out.getvalue()

    def test_dry_run_and_explicit_new_output(self):
        before = set(self.root.iterdir())
        self.assertEqual(self.run_cli("--allow-partial")[0], 0)
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertEqual(self.run_cli("--allow-partial", "--output", str(self.output))[0], 0)
        products = json.loads(self.output.read_text())
        self.assertEqual(set(products), {"1"})
        self.assertEqual(products["1"]["productId"], "sku-1")
        self.assertNotIn("bookId", products["1"])

    def test_reject_batch_without_partial_write(self):
        self.source.write_text(json.dumps([fixture(), fixture("2", merchantName="")]))
        self.assertEqual(self.run_cli("--allow-partial", "--output", str(self.output))[0], 2)
        self.assertFalse(self.output.exists())
        self.source.write_text(json.dumps([fixture()]))
        self.assertEqual(self.run_cli("--output", str(self.output))[0], 2)
        self.assertFalse(self.output.exists())

    def test_no_overwrite_symlinks_or_production_path(self):
        self.output.write_text("KEEP")
        self.assertEqual(self.run_cli("--allow-partial", "--output", str(self.output))[0], 2)
        self.assertEqual(self.output.read_text(), "KEEP")
        link = self.root / "link.candidate.json"
        link.symlink_to(self.output)
        with self.assertRaises(FileExistsError):
            importer.write_candidate(link, {})
        for name in ("shop-products.json", "/var/www/kangboacademy/data/new.candidate.json", "/etc/new.candidate.json"):
            with self.assertRaises(ValueError):
                importer.write_candidate(Path(name), {})

    def test_duplicate_json_keys_and_conflicting_mapping_id(self):
        for text in ('{"1":{},"1":{}}', '{"1":{"title":"a","title":"b"}}', '{"1":{"bookId":"2"}}', 'null'):
            self.source.write_text(text)
            with self.assertRaises(ValueError):
                importer.load_rows(self.source)

    def test_input_mapping_and_candidate_not_trusted_as_input(self):
        row = fixture()
        row.pop("bookId")
        self.source.write_text(json.dumps({"1": row}))
        self.assertEqual(importer.validate(importer.load_rows(self.source), catalog(), allow_partial=True)[1], [])
        products = importer.validate([fixture()], catalog(), allow_partial=True, authorization_reviewed=True)[0]
        self.source.write_text(json.dumps(products))
        self.assertTrue(importer.validate(importer.load_rows(self.source), catalog(), allow_partial=True)[1])

    def test_csv_bom_quotes_and_bad_headers(self):
        source = self.root / "input.csv"
        row = fixture(afterSales='SYNTHETIC policy, "quoted"; SYNTHETIC service desk')
        with source.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        self.assertEqual(importer.load_rows(source), [row])
        original = source.read_text(encoding="utf-8-sig")
        for text in ("bookId,bookId\n1,1\n", original.replace("bookId", "unknown", 1), original + "1,2\n"):
            source.write_text(text)
            with self.assertRaises(ValueError):
                importer.load_rows(source)

    def test_template_empty_and_catalog_integrity(self):
        self.assertEqual(importer.load_rows(importer.ROOT / "data/partner-products.template.csv"), [])
        with (importer.ROOT / "data/partner-products.template.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), importer.FIELDS)
        self.catalog.write_text('{"1":{"title":"x","author":"y"}}')
        with self.assertRaises(ValueError):
            importer.load_catalog(self.catalog)

    def test_backend_evidence_contract(self):
        products, errors, _ = importer.validate([fixture()], catalog(), allow_partial=True)
        self.assertEqual(errors, [])
        product = products["1"]
        for key in ("authorizationReference", "merchantName"):
            self.assertEqual(product[key], fixture()[key])
        self.assertEqual(product["afterSales"], {"description": fixture()["afterSales"], "contact": fixture()["afterSalesContact"]})
        self.assertEqual(product["authorizationStatus"], "unverified")
        for key in ("afterSalesPolicy", "afterSalesContact", "purchaseEntryReady", "canBuy", "commissionReady"):
            self.assertNotIn(key, product)

    def test_canonical_contract_and_invalid_books(self):
        self.assertEqual(importer.load_catalog(self.catalog), catalog())
        variants = []
        for field, value in (("number", True), ("number", "1"), ("key", "book:2"), ("author", "")):
            data = contract()
            data["courses"][0][field] = value
            variants.append(data)
        duplicate = contract()
        duplicate["courses"].append(duplicate["courses"][0])
        variants.append(duplicate)
        missing = contract()
        missing["courses"].pop(0)
        variants.extend((missing, catalog()))
        for data in variants:
            self.catalog.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                importer.load_catalog(self.catalog)

    def test_matching_csv_cli_is_unfilled_and_exclusive(self):
        output = self.root / "matching.csv"
        template = importer.ROOT / "data/partner-products.template.csv"
        original = template.read_bytes()
        args = ["--catalog", str(self.catalog), "--generate-matching-csv", str(output)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(importer.main(args), 0)
            before = output.read_bytes()
            self.assertEqual(importer.main(args), 2)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(template.read_bytes(), original)
        rows = importer.load_rows(output)
        self.assertEqual(len(rows), 500)
        for number, row in enumerate(rows, 1):
            self.assertEqual(row["bookId"], str(number))
            self.assertEqual(row["title"], catalog()[str(number)]["title"])
            self.assertEqual(row["author"], catalog()[str(number)]["author"])
            self.assertTrue(all(not value for key, value in row.items() if key not in {"bookId", "title", "author"}))
            self.assertNotIn("purchaseEntryReady", row)
        products, errors, _ = importer.validate(rows, catalog())
        self.assertFalse(products)
        self.assertTrue(errors)
        with self.assertRaises(FileExistsError):
            importer.write_matching_csv(template, catalog())
        with self.assertRaises(ValueError):
            importer.write_matching_csv(Path("/var/www/matching.csv"), catalog())

    def test_matching_cli_conflicts(self):
        for flags in ([str(self.source)], ["--dry-run"], ["--allow-partial"], ["--output", str(self.output)], ["--authorization-reviewed"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
                importer.main(["--generate-matching-csv", str(self.root / "unused.csv"), *flags])
            self.assertEqual(result.exception.code, 2)
        self.assertFalse((self.root / "unused.csv").exists())

    def test_live_shared_contract_matching(self):
        self.assertEqual(importer.CATALOG, importer.ROOT / "shared/content-contract.json")
        books = importer.load_catalog(importer.CATALOG)
        self.assertEqual(len(books), 500)
        output = self.root / "canonical.csv"
        importer.write_matching_csv(output, books)
        rows = importer.load_rows(output)
        self.assertEqual({row["bookId"]: {key: row[key] for key in ("title", "author")} for row in rows}, books)

    def test_dry_run_output_conflict(self):
        with self.assertRaises(SystemExit) as result:
            self.run_cli("--dry-run", "--output", str(self.output))
        self.assertEqual(result.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_dangling_symlink_and_aliased_production_directory(self):
        link = self.root / "link.candidate.json"
        target = self.root / "absent.candidate.json"
        link.symlink_to(target)
        with self.assertRaises(FileExistsError):
            importer.write_candidate(link, {})
        self.assertFalse(target.exists())
        alias = self.root / "production"
        alias.symlink_to(Path("/etc").resolve(), target_is_directory=True)
        with self.assertRaises(ValueError):
            importer.write_candidate(alias / "new.candidate.json", {})


class BackendIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Execute actual backend functions only, never server imports/startup/DB/network.
        backend_path = importer.ROOT / "server_patch/backend/main.py"
        tree = ast.parse(backend_path.read_text(encoding="utf-8"), filename=str(backend_path))
        names = {
            "product_channel", "product_target_url", "safe_commerce_url", "commerce_link_kind",
            "public_merchant_info", "commerce_authorization_ready", "book_open_action",
            "product_has_purchase_entry", "product_has_direct_commission", "merge_product_config",
        }
        nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        if {node.name for node in nodes} != names:
            raise AssertionError("real backend commerce function contract changed")
        cls.backend = {"re": re, "parse": parse, "Optional": Optional}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(backend_path), "exec"), cls.backend)

    def candidate(self, row, reviewed=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            source.write_text(json.dumps([row]), encoding="utf-8")
            contract_path = root / "contract.json"
            contract_path.write_text(json.dumps(contract()), encoding="utf-8")
            output = root / "review.candidate.json"
            args = [str(source), "--catalog", str(contract_path), "--allow-partial", "--output", str(output)]
            if reviewed:
                args.append("--authorization-reviewed")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(importer.main(args), 0)
            return json.loads(output.read_text(encoding="utf-8"))["1"]

    def test_real_backend_unverified_and_reviewed_targets(self):
        rows = [fixture(settlementMode="cps", commissionRate="2.50", commissionEvidence="SYNTHETIC rate record"),
                fixture(channel="jd_union", miniProgramAppId="", path="", productId="123",
                        externalUrl="https://item.jd.com/123.html", settlementMode="cps",
                        commissionRate="2.50", commissionEvidence="SYNTHETIC rate record")]
        search_base = {"channel": "jd_search", "source": "jd_search", "purchaseEntryType": "search",
                       "externalUrl": "https://search.jd.com/Search?keyword=SYNTHETIC",
                       "affiliateUrl": "https://search.jd.com/Search?keyword=SYNTHETIC", "openType": "clipboard"}
        for row in rows:
            for reviewed in (False, True):
                with self.subTest(channel=row["channel"], reviewed=reviewed):
                    candidate = self.candidate(row, reviewed)
                    self.assertEqual(candidate["authorizationStatus"], "confirmed" if reviewed else "unverified")
                    self.assertEqual(candidate["commissionRate"], "2.50%")
                    self.assertEqual(self.backend["commerce_authorization_ready"](candidate), reviewed)
                    product = self.backend["merge_product_config"](search_base, candidate)
                    action = self.backend["book_open_action"](1, product, {})
                    self.assertEqual(action["type"], "mini_program" if row["channel"] == "wechat_shop" else "clipboard")
                    self.assertEqual(action["entryKind"], "configured_product")
                    self.assertIs(action["canBuy"], reviewed)
                    self.assertIs(product["purchaseEntryReady"], reviewed)
                    self.assertIs(product["commissionReady"], reviewed)
                    self.assertNotIn("search.jd.com", action["target"])
                    public = self.backend["public_merchant_info"](product)
                    self.assertEqual(public["afterSales"]["contact"], row["afterSalesContact"])
                    self.assertNotIn(candidate["authorizationReference"], json.dumps(public))

    def test_real_backend_fails_closed_without_authorization_requirements(self):
        candidate = self.candidate(fixture(), True)
        for replacement in ({"authorizationStatus": "unverified"}, {"authorizationReference": ""},
                            {"merchantName": ""}, {"afterSales": {"description": "SYNTHETIC description only"}}):
            with self.subTest(replacement=replacement):
                product = {**candidate, **replacement}
                self.assertFalse(self.backend["commerce_authorization_ready"](product))
                self.assertFalse(self.backend["book_open_action"](1, product, {})["canBuy"])

    def test_real_backend_commission_percentage_boundaries(self):
        for rate in ("0", "100", "0.01"):
            with self.subTest(rate=rate):
                candidate = self.candidate(fixture(settlementMode="cps", commissionRate=rate,
                                                   commissionEvidence="SYNTHETIC rate record"), True)
                self.assertEqual(candidate["commissionRate"], rate + "%")
                self.assertTrue(self.backend["product_has_direct_commission"](candidate))
        candidate = self.candidate(fixture(), True)
        self.assertNotIn("commissionRate", candidate)
        self.assertFalse(self.backend["product_has_direct_commission"](candidate))

    def test_review_flag_does_not_bypass_validation(self):
        for changes in ({"afterSalesContact": ""}, {"authorizationReference": ""},
                        {"afterSalesContact": "/Users/internal/authorization.pdf"},
                        {"afterSalesContact": "SYNTHETIC agreement ref 1"},
                        {"merchantName": "/tmp/private-merchant"},
                        {"commissionRate": "2.50%"}, {"authorizationStatus": "confirmed"},
                        {"path": "pages/detail?sku-1=wrong"}, {"path": "pages/../detail?productId=sku-1"}):
            with self.subTest(changes=changes):
                products, errors, _ = importer.validate([fixture(**changes)], catalog(), allow_partial=True, authorization_reviewed=True)
                self.assertTrue(errors)
                self.assertFalse(products)


if __name__ == "__main__":
    unittest.main()

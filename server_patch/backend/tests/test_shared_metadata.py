import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('public_content_contract', ROOT / 'server_patch/backend/content_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SharedMetadataTests(unittest.TestCase):
    def test_all_server_titles_match_the_clients_without_entitlements(self):
        data = json.loads((ROOT / 'shared/content-contract.json').read_text())
        for course in data['courses']:
            actual = module.catalog_metadata(ROOT / 'server_patch/frontend', course['kind'], course['number'])
            self.assertEqual(actual['title'], course['title'])
            self.assertEqual(actual['desc'], course['description'])
            self.assertFalse({'free', 'locked', 'accessible', 'price', 'token'} & set(actual))

    def test_missing_manifest_or_identity_is_safe(self):
        self.assertEqual(module.catalog_metadata(ROOT / 'not-a-frontend', 'core', 1), {})
        self.assertEqual(module.catalog_metadata(ROOT / 'server_patch/frontend', 'book', 900000), {})


if __name__ == '__main__':
    unittest.main()

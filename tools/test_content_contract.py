import copy
import json
import unittest
from build_content_contract import MASTER, LiteralParser, validate, build


class ContractTests(unittest.TestCase):
    def test_parser_only_accepts_literals(self):
        self.assertEqual(LiteralParser("[{n:1,title:'hello',},]").value(), [{'n': 1, 'title': 'hello'}])
        for text in ["[run()]", "[{n:process.env.SECRET}]", "{a:1,a:2}"]:
            with self.assertRaises(ValueError):
                LiteralParser(text).value()

    def test_generated_artifacts_do_not_drift(self):
        build(check=True)

    def test_invalid_cross_kind_audio_and_progress_rejected(self):
        data = json.loads(MASTER.read_text())
        for field, value in [('audioPath', 'audio/lesson1.mp3'), ('legacyCourseRef', 1), ('free', True)]:
            bad = copy.deepcopy(data)
            row = next(item for item in bad['courses'] if item['kind'] == 'book')
            row[field] = value
            with self.assertRaises(ValueError):
                validate(bad)


if __name__ == '__main__':
    unittest.main()

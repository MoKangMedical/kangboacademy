import unittest
from pathlib import Path

from audio_narration import title_first
from regenerate_long_course_audio import CourseJob, build_script
from generate_core_audio_neural import normalize_script
from generate_book_audio_neural import build_script as book_script


class NarrationTests(unittest.TestCase):
    def test_exact_old_opening(self):
        old = '康波研究院主干课程第1课，长波理论。这段音频不是简单复述页面，而是带你抓住本课最值得反复听的主线、变量和练习动作。技术扩散影响长期增长。'
        self.assertEqual(title_first(old, '长波理论'), '长波理论。技术扩散影响长期增长。')

    def test_copy_variant(self):
        self.assertEqual(title_first('不是简单复制页面，而是讲解重点。正文内容。', '标题'), '标题。正文内容。')

    def test_preserves_substantive_contrast(self):
        text = '风险。风险不是波动，而是永久损失。'
        self.assertEqual(title_first(text, '风险'), text)

    def test_idempotent(self):
        text = title_first('正文。', '标题')
        self.assertEqual(title_first(text, '标题'), text)

    def test_rejects_missing_title(self):
        with self.assertRaises(ValueError):
            title_first('正文。', '')

    def test_new_generator_starts_with_title_and_content(self):
        job = CourseJob('core', 1, Path('x'), Path('x'), Path('x'), '主干课程')
        content = '技术扩散影响长期增长，信用条件改变企业的投资行为和融资决策。'
        script = build_script(job, '长波理论', [content] * 3, 100, 780)
        self.assertTrue(script.startswith('长波理论。' + content))
        self.assertNotIn('复述页面', script)
        self.assertNotIn('先看核心问题', script)

    def test_core_generator_title_first(self):
        script = normalize_script(1, '长波理论', '技术扩散影响长期增长。' * 25,
                                  '康波研究院主干课程第1课，长波理论。' + '技术扩散影响长期增长。' * 20)
        self.assertTrue(script.startswith('长波理论。技术扩散'))

    def test_book_generator_title_first(self):
        script = book_script(1, {'title': '示例书名', 'author': '示例作者'}, '<p>示例正文</p>')
        self.assertTrue(script.startswith('《示例书名》。作者是示例作者。'))


if __name__ == '__main__':
    unittest.main()

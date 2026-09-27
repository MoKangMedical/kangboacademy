"""Remove production commentary without deleting genuine course arguments."""
import re

META_SENTENCE = re.compile(
    r"[^。！？\n]*不是简单(?:地)?(?:复述|复制)(?:页面|网页)[^。！？\n]*(?:[。！？]|$)"
)
BRANDED_PREFIX = re.compile(
    r"^康波研究院(?:主干课程|书目精读|书目课程)[，,\s]*第\d+课[，,：:、\s]*"
)


def title_first(script: str, title: str) -> str:
    title = title.strip().rstrip("。！？")
    if not title:
        raise ValueError("A verified course title is required")
    text = META_SENTENCE.sub("", script).strip()
    text = BRANDED_PREFIX.sub("", text).strip()
    if text.startswith(title):
        text = text[len(title):].lstrip("。！？，,:： \n")
    return title + "。" + text

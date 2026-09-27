#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


RECOMMEND_RE = re.compile(r"推荐阅读|延伸阅读|参考书目|推荐书目")
PRACTICE_RE = re.compile(r"练习题|课后练习|互动练习|练习与思考|思考题")
PLACEHOLDER_RE = re.compile(r"待完善|TODO|占位|暂无内容|敬请期待|待补充", re.I)

BOOK_TEMPLATE_PATTERNS = [
    "这门课不把",
    "当作孤立的读书笔记",
    "观察第六轮康波",
    "当新闻每天改变叙事",
    "提供一个稳定的观察坐标",
    "重要著作从来不是凭空出现",
    "旧解释失效、新秩序尚未成形",
    "原书观点、现实证据、资产映射、反方证据",
    "不是读完就遗忘的知识消费",
]


def strip_html(fragment: str) -> str:
    fragment = re.sub(r"<script\b[\s\S]*?</script>", "", fragment, flags=re.I)
    fragment = re.sub(r"<style\b[\s\S]*?</style>", "", fragment, flags=re.I)
    fragment = re.sub(r"<audio\b[\s\S]*?</audio>", "", fragment, flags=re.I)
    fragment = re.sub(r"</(h[1-6]|p|li|div|tr|section|article|blockquote)>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(fragment)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def article_html(page_html: str) -> str:
    match = re.search(r"<article[^>]*>([\s\S]*?)</article>", page_html, flags=re.I)
    if match:
        return match.group(1)
    match = re.search(
        r'<div\s+class=["\'][^"\']*content[^"\']*["\'][^>]*>([\s\S]*?)'
        r'\n\s*</div>\s*\n\s*<div\s+class=["\'][^"\']*bottom-nav',
        page_html,
        flags=re.I,
    )
    if match:
        return match.group(1)
    return page_html


def extract_title(page_html: str, fallback: str) -> str:
    for tag in ("h1", "title"):
        match = re.search(rf"<{tag}[^>]*>([\s\S]*?)</{tag}>", page_html, flags=re.I)
        if match:
            return strip_html(match.group(1))[:160]
    return fallback


def audio_sources(page_html: str) -> list[str]:
    sources = re.findall(r"<source[^>]+src=[\"']([^\"']+)[\"']", page_html, flags=re.I)
    sources += re.findall(r"<audio[^>]+src=[\"']([^\"']+)[\"']", page_html, flags=re.I)
    return sources


def resolve_audio(frontend: Path, kind: str, idx: int, sources: list[str]) -> Path | None:
    candidates = []
    for src in sources:
        if re.match(r"^https?://", src) or src.startswith("//"):
            continue
        rel = src.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        candidates.append(frontend / rel)
    if kind == "core":
        candidates.append(frontend / f"audio/lesson{idx}.mp3")
    else:
        candidates.append(frontend / f"audio/books/lesson{idx}.mp3")
        candidates.append(frontend / f"audio/lesson{idx}.mp3")
    for path in candidates:
        if path.exists():
            return path
    return candidates[0] if candidates else None


def ffprobe(path: Path) -> dict:
    if not path or not path.exists():
        return {}
    try:
        raw = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,bit_rate",
                "-show_entries",
                "stream=codec_name,sample_rate,channels",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
        data = json.loads(raw)
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        return {
            "audio_codec": stream.get("codec_name", ""),
            "audio_sample_rate": int(stream.get("sample_rate") or 0),
            "audio_channels": int(stream.get("channels") or 0),
            "audio_duration": round(float(fmt.get("duration") or 0), 3),
            "audio_bit_rate": int(fmt.get("bit_rate") or 0),
        }
    except Exception as exc:
        return {"audio_probe_error": str(exc)[:180]}


def normalized_sentences(text: str) -> list[str]:
    sentences = []
    for part in re.split(r"[。！？!?]\s*", text):
        value = re.sub(r"\s+", "", part)
        if 20 <= len(value) <= 160:
            sentences.append(value)
    return sentences


def inspect_page(frontend: Path, kind: str, idx: int) -> dict:
    filename = f"lesson{idx}.html" if kind == "core" else f"book{idx}.html"
    path = frontend / filename
    fallback = f"第{idx}课" if kind == "core" else f"书目课程{idx}"
    record = {
        "kind": kind,
        "id": idx,
        "filename": filename,
        "exists": path.exists(),
        "title": fallback,
        "content_chars": 0,
        "han_chars": 0,
        "h2_count": 0,
        "h3_count": 0,
        "p_count": 0,
        "has_recommended": False,
        "has_practice": False,
        "placeholder_hits": 0,
        "template_hits": 0,
        "title_mentions": 0,
        "repeated_sentence_ratio": 0.0,
        "audio_path": "",
        "audio_exists": False,
        "audio_size": 0,
        "_text": "",
        "_sentences": [],
    }
    if not path.exists():
        return record

    raw = path.read_text(encoding="utf-8", errors="replace")
    article = article_html(raw)
    text = strip_html(article)
    title = extract_title(raw, fallback)
    sources = audio_sources(raw)
    audio = resolve_audio(frontend, kind, idx, sources)
    sentences = normalized_sentences(text)
    counts = Counter(sentences)
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    book_title = re.sub(r"^.*?《|》.*$", "", title)
    if "《" in title and "》" in title:
        book_title = title.split("《", 1)[1].split("》", 1)[0]

    record.update(
        {
            "title": title,
            "content_chars": len(text),
            "han_chars": len(re.findall(r"[\u4e00-\u9fff]", text)),
            "h2_count": len(re.findall(r"<h2\b", article, flags=re.I)),
            "h3_count": len(re.findall(r"<h3\b", article, flags=re.I)),
            "p_count": len(re.findall(r"<p\b", article, flags=re.I)),
            "has_recommended": bool(RECOMMEND_RE.search(raw)),
            "has_practice": bool(PRACTICE_RE.search(raw)),
            "placeholder_hits": len(PLACEHOLDER_RE.findall(text)),
            "template_hits": sum(text.count(p) for p in BOOK_TEMPLATE_PATTERNS),
            "title_mentions": text.count(book_title) if book_title else 0,
            "repeated_sentence_ratio": round(repeated / max(1, len(sentences)), 4),
            "audio_path": str(audio.relative_to(frontend)) if audio and audio.is_absolute() is False else str(audio or ""),
            "audio_exists": bool(audio and audio.exists()),
            "audio_size": audio.stat().st_size if audio and audio.exists() else 0,
            "_text": text,
            "_sentences": sentences,
        }
    )
    if audio and audio.exists():
        record.update(ffprobe(audio))
    return record


def classify_content(record: dict, benchmark: dict) -> tuple[str, list[str]]:
    flags = []
    if not record["exists"]:
        return "D", ["MISSING_PAGE"]
    if record["content_chars"] < 1000:
        flags.append("VERY_SHORT")
    if record["kind"] == "core" and record["content_chars"] < benchmark["content_chars"] * 0.85:
        flags.append("BELOW_LESSON1_DEPTH")
    if record["kind"] == "book" and record["content_chars"] < 3600:
        flags.append("BOOK_CONTENT_THIN")
    if record["h2_count"] < 5:
        flags.append("WEAK_STRUCTURE")
    if not record["has_recommended"]:
        flags.append("NO_RECOMMENDED_READING")
    if not record["has_practice"]:
        flags.append("NO_PRACTICE")
    if record["placeholder_hits"]:
        flags.append("PLACEHOLDER")
    if record["kind"] == "book" and record["template_hits"] >= 5:
        flags.append("BOOK_TEMPLATE_GENERATED")
    if record["kind"] == "book" and record["title_mentions"] >= 35:
        flags.append("BOOK_TITLE_STUFFING")
    if record["repeated_sentence_ratio"] >= 0.12:
        flags.append("INTERNAL_REPETITION")

    severe = {"VERY_SHORT", "PLACEHOLDER"}
    if any(flag in severe for flag in flags):
        return "D", flags
    if "BOOK_TEMPLATE_GENERATED" in flags or "BOOK_TITLE_STUFFING" in flags:
        return "C", flags
    if "BELOW_LESSON1_DEPTH" in flags or "BOOK_CONTENT_THIN" in flags or "WEAK_STRUCTURE" in flags:
        return "C", flags
    if flags:
        return "B", flags
    return "A", flags


def classify_audio(record: dict, benchmark: dict) -> tuple[str, list[str]]:
    flags = []
    if not record.get("audio_exists"):
        return "D", ["MISSING_AUDIO"]
    if record.get("audio_duration", 0) < 10:
        return "D", ["AUDIO_UNREADABLE_OR_TOO_SHORT"]
    if record.get("audio_duration", 0) < benchmark["audio_duration"] * 0.85:
        flags.append("SHORTER_THAN_LESSON1")
    if record.get("audio_sample_rate") != benchmark.get("audio_sample_rate"):
        flags.append("SAMPLE_RATE_DIFFERS_FROM_LESSON1")
    if record.get("audio_channels") != benchmark.get("audio_channels"):
        flags.append("CHANNELS_DIFFER_FROM_LESSON1")
    if record.get("audio_size", 0) < benchmark.get("audio_size", 0) * 0.75:
        flags.append("SMALLER_THAN_LESSON1")
    if record.get("audio_duration", 0) > benchmark["audio_duration"] * 1.8:
        flags.append("MUCH_LONGER_THAN_LESSON1")
    if flags:
        if {"SAMPLE_RATE_DIFFERS_FROM_LESSON1", "SHORTER_THAN_LESSON1"} & set(flags):
            return "C", flags
        return "B", flags
    return "A", flags


def public_record(record: dict) -> dict:
    return {k: v for k, v in record.items() if not k.startswith("_")}


def write_reports(records: list[dict], benchmark: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "kind",
        "id",
        "filename",
        "title",
        "content_grade",
        "audio_grade",
        "content_flags",
        "audio_flags",
        "content_chars",
        "h2_count",
        "h3_count",
        "p_count",
        "has_recommended",
        "has_practice",
        "template_hits",
        "title_mentions",
        "repeated_sentence_ratio",
        "audio_exists",
        "audio_duration",
        "audio_sample_rate",
        "audio_channels",
        "audio_bit_rate",
        "audio_size",
        "audio_path",
    ]
    with (out_dir / "lesson1_benchmark_audit.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})
    (out_dir / "lesson1_benchmark_audit.json").write_text(
        json.dumps({"benchmark": benchmark, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    content_counts = Counter((r["kind"], r["content_grade"]) for r in records)
    audio_counts = Counter((r["kind"], r["audio_grade"]) for r in records)
    content_flags = Counter(flag for r in records for flag in r["content_flags"].split("|") if flag)
    audio_flags = Counter(flag for r in records for flag in r["audio_flags"].split("|") if flag)
    worst_content = [r for r in records if r["content_grade"] in ("C", "D")][:60]
    worst_audio = [r for r in records if r["audio_grade"] in ("C", "D")][:60]

    lines = [
        "# 第一课标杆质量审计",
        "",
        "## 第 1 课标杆",
        "",
        f"- 正文字符数：{benchmark['content_chars']}",
        f"- 二级标题：{benchmark['h2_count']}，三级标题：{benchmark['h3_count']}，段落：{benchmark['p_count']}",
        f"- 音频：{benchmark['audio_duration']} 秒，{benchmark['audio_sample_rate']}Hz，{benchmark['audio_channels']} 声道，{benchmark['audio_bit_rate']}bps，{benchmark['audio_size']} bytes",
        "",
        "## 总览",
        "",
        f"- 总课程：{len(records)}",
        f"- 内容等级：{dict(content_counts)}",
        f"- 音频等级：{dict(audio_counts)}",
        f"- 内容主要问题：{dict(content_flags.most_common(12))}",
        f"- 音频主要问题：{dict(audio_flags.most_common(12))}",
        "",
        "## 内容需优先处理",
        "",
    ]
    for r in worst_content:
        lines.append(
            f"- {r['kind']} {r['id']} {r['title']}：{r['content_grade']}，{r['content_flags']}，chars={r['content_chars']}"
        )
    lines += ["", "## 音频需优先处理", ""]
    for r in worst_audio:
        lines.append(
            f"- {r['kind']} {r['id']} {r['title']}：{r['audio_grade']}，{r['audio_flags']}，duration={r.get('audio_duration', '')}，path={r.get('audio_path', '')}"
        )
    (out_dir / "lesson1_benchmark_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", default="/var/www/kangboacademy/frontend")
    parser.add_argument("--out-dir", default="/tmp/kangbo_lesson1_benchmark")
    args = parser.parse_args()
    frontend = Path(args.frontend)
    benchmark_raw = inspect_page(frontend, "core", 1)
    benchmark = public_record(benchmark_raw)
    if not benchmark.get("audio_exists"):
        raise SystemExit("第 1 课音频不存在，不能建立标杆")

    records = []
    for kind, end in (("core", 65), ("book", 500)):
        for idx in range(1, end + 1):
            record = inspect_page(frontend, kind, idx)
            content_grade, content_flags = classify_content(record, benchmark)
            audio_grade, audio_flags = classify_audio(record, benchmark)
            row = public_record(record)
            row["content_grade"] = content_grade
            row["audio_grade"] = audio_grade
            row["content_flags"] = "|".join(content_flags)
            row["audio_flags"] = "|".join(audio_flags)
            records.append(row)
    write_reports(records, benchmark, Path(args.out_dir))
    print(f"wrote {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

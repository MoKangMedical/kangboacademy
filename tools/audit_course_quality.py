#!/usr/bin/env python3
import argparse
import csv
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError


GENERIC_PHRASES = [
    "这个概念的深层含义需要我们仔细理解",
    "在当前第六轮康波春初阶段",
    "当你真正内化这个概念之后",
    "你看待市场的方式会发生根本变化",
    "不再被每日的波动所困扰",
    "这段话之所以经典",
    "前人已经犯过无数次了",
    "不再被每日电市场波动牵着走",
    "在混乱中看到秩序",
]

PLACEHOLDER_PHRASES = [
    "待完善",
    "TODO",
    "占位内容",
    "内容占位",
    "示例内容",
    "本课程内容正在",
    "暂无内容",
    "敬请期待",
    "待补充",
]

RECOMMEND_RE = re.compile(r"推荐阅读|延伸阅读|参考书目|推荐书目")
PRACTICE_RE = re.compile(r"练习题|课后练习|互动练习|练习与思考|思考题")


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
        r'<div\s+class=["\']content["\'][^>]*>([\s\S]*?)\n\s*</div>\s*\n\s*<div\s+class=["\']bottom-nav["\']',
        page_html,
        flags=re.I,
    )
    if match:
        return match.group(1)
    match = re.search(r'<div[^>]+class=["\'][^"\']*content[^"\']*["\'][^>]*>([\s\S]*?)</div>', page_html, flags=re.I)
    return match.group(1) if match else page_html


def normalized_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?]\s*", text)
    out = []
    for part in parts:
        value = re.sub(r"\s+", "", part)
        if 20 <= len(value) <= 180:
            out.append(value)
    return out


def extract_title(page_html: str, fallback: str) -> str:
    h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", page_html, flags=re.I)
    if h1:
        return strip_html(h1.group(1))[:120]
    title = re.search(r"<title[^>]*>([\s\S]*?)</title>", page_html, flags=re.I)
    if title:
        return strip_html(title.group(1))[:120]
    return fallback


def audio_sources(page_html: str) -> list[str]:
    sources = re.findall(r"<source[^>]+src=[\"']([^\"']+)[\"']", page_html, flags=re.I)
    sources += re.findall(r"<audio[^>]+src=[\"']([^\"']+)[\"']", page_html, flags=re.I)
    return sources


def local_audio_exists(frontend: Path, src: str) -> bool:
    if not src or re.match(r"^https?://", src) or src.startswith("//"):
        return True
    rel = src.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    return (frontend / rel).exists()


def fetch_json(url: str, timeout: int = 10) -> tuple[int, dict | None, str]:
    try:
        with urlrequest.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw), ""
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return exc.code, None, detail
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return 0, None, str(exc)[:300]


def inspect_static(frontend: Path, kind: str, idx: int) -> dict:
    filename = f"lesson{idx}.html" if kind == "core" else f"book{idx}.html"
    path = frontend / filename
    fallback = f"第 {idx} 课" if kind == "core" else f"书目课程 {idx}"
    if not path.exists():
        return {
            "kind": kind,
            "id": idx,
            "filename": filename,
            "exists": False,
            "title": fallback,
            "website_text_chars": 0,
            "h2_count": 0,
            "h3_count": 0,
            "p_count": 0,
            "has_recommended": False,
            "has_practice": False,
            "has_audio": False,
            "audio_files_exist": False,
            "doctype": False,
            "charset": False,
            "viewport": False,
            "generic_hits": 0,
            "placeholder_hits": 0,
            "repeated_sentence_ratio": 0,
            "common_sentence_ratio": 0,
            "_sentences": [],
            "_text": "",
        }
    raw = path.read_text(encoding="utf-8", errors="replace")
    article = article_html(raw)
    text = strip_html(article)
    sources = audio_sources(raw)
    return {
        "kind": kind,
        "id": idx,
        "filename": filename,
        "exists": True,
        "title": extract_title(raw, fallback),
        "html_bytes": path.stat().st_size,
        "website_text_chars": len(text),
        "han_chars": len(re.findall(r"[\u4e00-\u9fff]", text)),
        "h2_count": len(re.findall(r"<h2\b", article, flags=re.I)),
        "h3_count": len(re.findall(r"<h3\b", article, flags=re.I)),
        "p_count": len(re.findall(r"<p\b", article, flags=re.I)),
        "has_recommended": bool(RECOMMEND_RE.search(raw)),
        "has_practice": bool(PRACTICE_RE.search(raw)),
        "has_audio": bool(sources),
        "audio_files_exist": bool(sources) and all(local_audio_exists(frontend, src) for src in sources),
        "doctype": "<!doctype html" in raw[:300].lower(),
        "charset": bool(re.search(r"<meta[^>]+charset=", raw, flags=re.I)),
        "viewport": bool(re.search(r"<meta[^>]+name=[\"']viewport[\"']", raw, flags=re.I)),
        "generic_hits": sum(text.count(phrase) for phrase in GENERIC_PHRASES),
        "placeholder_hits": sum(text.count(phrase) for phrase in PLACEHOLDER_PHRASES),
        "repeated_sentence_ratio": 0,
        "common_sentence_ratio": 0,
        "_sentences": normalized_sentences(text),
        "_text": text,
    }


def add_api_metrics(record: dict, api_base: str | None) -> None:
    if not api_base:
        record.update({
            "api_status": "",
            "api_locked": "",
            "miniapp_text_chars": "",
            "api_recommended_count": "",
            "api_audio_available": "",
            "api_error": "",
        })
        return
    kind = record["kind"]
    idx = record["id"]
    endpoint = (
        f"/api/course-content/lesson{idx}.html"
        if kind == "core"
        else f"/api/book-course-content/book{idx}.html"
    )
    status, data, error = fetch_json(api_base.rstrip("/") + endpoint)
    content = data.get("content", "") if isinstance(data, dict) else ""
    record.update({
        "api_status": status,
        "api_locked": bool(data.get("locked")) if isinstance(data, dict) else "",
        "miniapp_text_chars": len(strip_html(content)) if content else 0,
        "api_recommended_count": len(data.get("recommendedBooks") or []) if isinstance(data, dict) else 0,
        "api_audio_available": bool(data.get("audioAvailable")) if isinstance(data, dict) else False,
        "api_error": error,
    })


def classify(record: dict) -> tuple[str, list[str]]:
    flags = []
    kind = record["kind"]
    min_web = 4500 if kind == "core" else 3000
    min_api = 3500 if kind == "core" else 2500

    if not record["exists"]:
        flags.append("FAIL_MISSING_FILE")
    if record["website_text_chars"] < min_web:
        flags.append("FAIL_WEBSITE_TEXT_SHORT")
    if record["h2_count"] < 4:
        flags.append("FAIL_STRUCTURE_THIN")
    if record["placeholder_hits"]:
        flags.append("FAIL_PLACEHOLDER_TEXT")
    if record["generic_hits"] >= 6:
        flags.append("FAIL_GENERIC_TEMPLATE_PHRASES")
    if record["common_sentence_ratio"] >= 0.18:
        flags.append("FAIL_CROSS_COURSE_TEMPLATE")
    if record["repeated_sentence_ratio"] >= 0.18:
        flags.append("FAIL_INTERNAL_REPETITION")
    if record.get("api_status") not in ("", 200):
        flags.append("FAIL_MINIAPP_API")
    if record.get("api_locked") is True:
        flags.append("FAIL_MINIAPP_LOCKED")
    if record.get("miniapp_text_chars") != "" and record.get("miniapp_text_chars", 0) < min_api:
        flags.append("FAIL_MINIAPP_TEXT_SHORT")

    if not record["has_recommended"]:
        flags.append("WARN_NO_RECOMMENDED_READING")
    if kind == "core" and record.get("api_recommended_count") == 0:
        flags.append("WARN_MINIAPP_NO_RECOMMENDED_DATA")
    if not record["has_practice"]:
        flags.append("WARN_NO_WEBSITE_PRACTICE_SECTION")
    if not record["has_audio"] or not record["audio_files_exist"]:
        flags.append("WARN_AUDIO_MISSING_OR_BROKEN")
    if not (record["doctype"] and record["charset"] and record["viewport"]):
        flags.append("WARN_HTML_META")

    status = "FAIL" if any(f.startswith("FAIL_") for f in flags) else ("WARN" if flags else "PASS")
    return status, flags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", default="/var/www/kangboacademy/frontend")
    parser.add_argument("--api-base", default="http://127.0.0.1:8088")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    frontend = Path(args.frontend)
    records = []
    for i in range(1, 66):
        records.append(inspect_static(frontend, "core", i))
    for i in range(1, 501):
        records.append(inspect_static(frontend, "book", i))

    sentence_counter = Counter()
    for record in records:
        sentence_counter.update(set(record["_sentences"]))

    for record in records:
        sentences = record["_sentences"]
        if sentences:
            counts = Counter(sentences)
            repeated = sum(count - 1 for count in counts.values() if count > 1)
            common = sum(1 for sentence in sentences if sentence_counter[sentence] >= 20)
            record["repeated_sentence_ratio"] = round(repeated / len(sentences), 4)
            record["common_sentence_ratio"] = round(common / len(sentences), 4)
        add_api_metrics(record, args.api_base)
        status, flags = classify(record)
        record["status"] = status
        record["flags"] = flags
        record.pop("_sentences", None)
        record.pop("_text", None)

    fieldnames = [
        "kind", "id", "filename", "title", "status", "flags", "exists",
        "website_text_chars", "han_chars", "miniapp_text_chars", "h2_count", "h3_count", "p_count",
        "has_recommended", "api_recommended_count", "has_practice", "has_audio", "audio_files_exist",
        "doctype", "charset", "viewport", "generic_hits", "placeholder_hits",
        "repeated_sentence_ratio", "common_sentence_ratio",
        "api_status", "api_locked", "api_audio_available", "api_error", "html_bytes",
    ]
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            row["flags"] = "|".join(record["flags"])
            writer.writerow(row)

    payload = {"records": records}
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    counts = Counter(record["status"] for record in records)
    flag_counts = Counter(flag for record in records for flag in record["flags"])
    fail_records = [r for r in records if r["status"] == "FAIL"]
    warn_records = [r for r in records if r["status"] == "WARN"]
    by_kind = {
        kind: Counter(r["status"] for r in records if r["kind"] == kind)
        for kind in ("core", "book")
    }
    with open(args.summary, "w", encoding="utf-8") as f:
        f.write("# 康波研究院课程正文质量审计\n\n")
        f.write("## 判定标准\n\n")
        f.write("- 核心课正文不少于 4500 字；书目课正文不少于 3000 字。\n")
        f.write("- 至少 4 个二级标题，避免正文只有薄弱提纲。\n")
        f.write("- 不应出现占位文本、明显模板套话、跨课程大段重复。\n")
        f.write("- 小程序 API 应能返回正文且未锁定；核心课应返回推荐阅读数据。\n")
        f.write("- 推荐阅读、练习、音频、HTML 基础 meta 缺失按警告处理。\n\n")
        f.write("## 总览\n\n")
        f.write(f"- 总课程：{len(records)} 门\n")
        f.write(f"- PASS：{counts.get('PASS', 0)}\n")
        f.write(f"- WARN：{counts.get('WARN', 0)}\n")
        f.write(f"- FAIL：{counts.get('FAIL', 0)}\n")
        f.write(f"- 核心课：{dict(by_kind['core'])}\n")
        f.write(f"- 书目课：{dict(by_kind['book'])}\n\n")
        f.write("## 主要问题计数\n\n")
        for flag, count in flag_counts.most_common():
            f.write(f"- {flag}: {count}\n")
        f.write("\n## 必须重写或修复的课程\n\n")
        for r in fail_records:
            f.write(
                f"- {r['kind']} {r['id']:03d} `{r['filename']}` "
                f"{r['title']}：{', '.join(r['flags'])}; "
                f"web={r['website_text_chars']}字, mini={r['miniapp_text_chars']}字, "
                f"common={r['common_sentence_ratio']}\n"
            )
        f.write("\n## 仅警告课程\n\n")
        for r in warn_records:
            f.write(
                f"- {r['kind']} {r['id']:03d} `{r['filename']}` "
                f"{r['title']}：{', '.join(r['flags'])}\n"
            )
    print(json.dumps({
        "total": len(records),
        "counts": dict(counts),
        "by_kind": {k: dict(v) for k, v in by_kind.items()},
        "top_flags": flag_counts.most_common(12),
        "csv": args.csv,
        "json": args.json,
        "summary": args.summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

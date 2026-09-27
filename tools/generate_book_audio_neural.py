#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import edge_tts
from bs4 import BeautifulSoup


API_BASE = "https://kangboacademy.cn/api"
DEFAULT_OUT = "generated_audio_neural/books"
PROBLEM_IDS = (
    list(range(204, 231))
    + list(range(301, 309))
    + list(range(337, 501))
)


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def strip_book_marks(title: str) -> str:
    title = clean_space(title)
    title = re.sub(r"^《|》$", "", title)
    return title or "书目课程"


def read_json(url: str, retries: int = 4) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(url, timeout=30) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"读取接口失败：{url}") from last_error


def load_course_index(api_base: str) -> dict[int, dict]:
    data = read_json(f"{api_base.rstrip('/')}/book-courses")
    return {
        int(item.get("n") or item.get("id")): item
        for item in data.get("courses", [])
        if item.get("n") or item.get("id")
    }


def html_to_text(content: str) -> str:
    soup = BeautifulSoup(content or "", "html.parser")
    for tag in soup(["script", "style", "audio", "table"]):
        tag.decompose()
    pieces = []
    for tag in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        text = clean_space(tag.get_text(" ", strip=True))
        if text:
            pieces.append(text)
    return "\n".join(pieces)


def find_first(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.S)
    return clean_space(match.group(1)) if match else default


def clip_sentence(text: str, limit: int) -> str:
    text = clean_space(re.sub(r"[。；;]+$", "", text))
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in "。；，、":
        idx = cut.rfind(mark)
        if idx >= limit * 0.55:
            return cut[:idx]
    return cut.rstrip()


def build_script(n: int, meta: dict, content: str) -> str:
    title = strip_book_marks(meta.get("title") or meta.get("t") or f"书目课程{n}")
    author = clean_space(meta.get("author") or meta.get("a") or "作者")
    text = html_to_text(content)

    core_problem = find_first(r"核心问题[:：]\s*([^。\n]+)", text)
    lens = find_first(r"所在的[^，。]{2,12}为例，([^。]+)", text)
    assets = find_first(r"本课重点关注的资产包括([^。]+)", text)
    risk = find_first(r"最容易出现的误用是([^。]+)", text)
    opening_point = find_first(
        rf"《{re.escape(title)}》的价值正在于([^。]+)",
        text,
    )
    if not opening_point:
        opening_point = find_first(r"这门课不把[^。]+，而是([^。]+)", text)

    parts = [
        f"《{title}》。作者是{author}。",
    ]
    if opening_point:
        parts.append(f"这本书的价值，在于{clip_sentence(opening_point, 70)}。")
    if core_problem:
        parts.append(f"本课的核心问题是：{clip_sentence(core_problem, 58)}。")

    parts.append("听这一课，请抓住三个层次。")
    if lens:
        parts.append(f"第一，分析镜头。{clip_sentence(lens, 72)}。")
    else:
        parts.append("第一，分析镜头。先把作者的观点写成可以检验的因果链，而不是只记住结论。")
    if assets:
        parts.append(f"第二，资产映射。重点观察{clip_sentence(assets, 72)}。")
    else:
        parts.append("第二，资产映射。把书里的判断翻译成仓位、期限、现金流和风险预算。")
    if risk:
        parts.append(f"第三，风险边界。最容易误用的地方是{clip_sentence(risk, 70)}。")
    else:
        parts.append("第三，风险边界。任何经典都不是免检结论，关键是写出它可能失效的条件。")

    parts.append(
        "最后做一个练习：请用四列笔记复盘这本书，分别写下原书观点、现实证据、资产映射和反方证据。"
    )
    parts.append(
        "如果一个观点不能改变你的观察清单、仓位上限或行动节奏，就先不要把它当成真正掌握。"
    )

    return "\n".join(parts)


def parse_ids(value: str) -> list[int]:
    if not value:
        return PROBLEM_IDS
    ids: list[int] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, end = [int(x) for x in chunk.split("-", 1)]
            ids.extend(range(start, end + 1))
        else:
            ids.append(int(chunk))
    return sorted(dict.fromkeys(ids))


async def synthesize_edge(text: str, out: Path, voice: str, rate: str, pitch: str) -> None:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
            await communicate.save(str(out))
            return
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError("Edge TTS 生成失败") from last_error


def normalize_mp3(src: Path, dst: Path, ffmpeg: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "64k",
            str(dst),
        ],
        check=True,
    )


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="", help="例如 204,337,500 或 204-230；默认重制 199 个问题音频")
    parser.add_argument("--api-base", default=API_BASE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--script-out", default="generated_audio_neural/scripts")
    parser.add_argument("--voice", default="zh-CN-YunyangNeural")
    parser.add_argument("--rate", default="-6%")
    parser.add_argument("--pitch", default="-2Hz")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if not Path(ffmpeg).exists() and shutil.which(ffmpeg) is None:
        raise SystemExit("需要 ffmpeg")

    ids = parse_ids(args.ids)
    if args.limit:
        ids = ids[: args.limit]

    out_dir = Path(args.out)
    script_dir = Path(args.script_out)
    out_dir.mkdir(parents=True, exist_ok=True)
    script_dir.mkdir(parents=True, exist_ok=True)

    course_index = load_course_index(args.api_base)
    generated = 0
    skipped = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for n in ids:
            target = out_dir / f"lesson{n}.mp3"
            script_path = script_dir / f"lesson{n}.txt"
            if target.exists() and target.stat().st_size > 20_000 and not args.force:
                skipped += 1
                continue

            meta = course_index.get(n, {"title": f"书目课程{n}", "author": "康波研究院"})
            lesson = quote(f"book{n}.html")
            detail = read_json(f"{args.api_base.rstrip('/')}/book-course-content/{lesson}")
            script = build_script(n, meta, detail.get("content", ""))
            script_path.write_text(script, encoding="utf-8")

            raw = tmp_dir / f"lesson{n}.raw.mp3"
            await synthesize_edge(script, raw, args.voice, args.rate, args.pitch)
            normalize_mp3(raw, target, ffmpeg)

            generated += 1
            duration = subprocess.check_output(
                [
                    ffmpeg.replace("ffmpeg", "ffprobe"),
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    str(target),
                ],
                text=True,
            ).strip()
            print(f"generated lesson{n}.mp3 duration={duration}s")

    print(f"generated={generated} skipped={skipped} out={out_dir}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

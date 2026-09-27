#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html
import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import edge_tts
from bs4 import BeautifulSoup
from audio_narration import title_first


ROOT = Path("/var/www/kangboacademy")
FRONTEND = ROOT / "frontend"
DATA_ROOT = ROOT / "data"
BACKUP_ROOT = ROOT / "backups"

DEFAULT_MIN_CHARS = 500
DEFAULT_MAX_CHARS = 780


@dataclass(frozen=True)
class CourseJob:
    kind: str
    idx: int
    page: Path
    audio: Path
    script: Path
    label: str


def clean_space(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_ids(value: str, start: int, end: int) -> list[int]:
    if not value:
        return list(range(start, end + 1))
    ids: list[int] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            left, right = [int(part.strip()) for part in chunk.split("-", 1)]
            ids.extend(range(left, right + 1))
        else:
            ids.append(int(chunk))
    return [idx for idx in sorted(dict.fromkeys(ids)) if start <= idx <= end]


def title_from_soup(soup: BeautifulSoup, fallback: str) -> str:
    for selector in ["h1", "title"]:
        tag = soup.select_one(selector)
        if not tag:
            continue
        title = clean_space(tag.get_text(" ", strip=True))
        title = re.sub(r"\s*[—|-].*$", "", title).strip()
        if title:
            return title
    return fallback


def strip_page_noise(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style", "audio", "video", "iframe", "nav", "footer", "canvas", "svg"]):
        tag.decompose()
    selectors = [
        ".audio-player",
        ".bottom-nav",
        ".nav",
        ".progress-bar",
        ".purchase-card",
        ".buy-row",
        ".footer",
        ".lesson-nav",
        ".share-panel",
    ]
    for tag in soup.select(",".join(selectors)):
        tag.decompose()


def useful_fragment(text: str) -> bool:
    if len(text) < 12:
        return False
    skip_words = [
        "上一课",
        "下一课",
        "返回",
        "您的浏览器不支持音频",
        "康波研究院 ©",
        "立即购买",
        "京东",
        "当当",
        "豆瓣",
        "点击播放",
        "播放中",
        "微信小程序",
        "开始学习",
    ]
    return not any(word in text for word in skip_words)


def extract_page_text(job: CourseJob) -> tuple[str, list[str]]:
    raw = job.page.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    strip_page_noise(soup)
    title = title_from_soup(soup, f"{job.label}第{job.idx}课")
    container = (
        soup.select_one("article")
        or soup.select_one(".content")
        or soup.select_one("main")
        or soup.body
        or soup
    )
    fragments: list[str] = []
    for tag in container.find_all(["h2", "h3", "p", "li", "blockquote", "td"]):
        text = clean_space(tag.get_text(" ", strip=True))
        if useful_fragment(text):
            fragments.append(text)
    deduped = list(dict.fromkeys(fragments))
    return title, deduped


def split_sentences(fragments: list[str]) -> list[str]:
    sentences: list[str] = []
    for fragment in fragments:
        parts = re.split(r"(?<=[。！？；])\s*", fragment)
        if len(parts) <= 1 and len(fragment) > 120:
            parts = re.split(r"[，,]\s*", fragment)
        for part in parts:
            sentence = clean_space(part)
            if not sentence:
                continue
            if not re.search(r"[。！？；]$", sentence):
                sentence = sentence.rstrip("，,、；") + "。"
            if 18 <= len(sentence) <= 180 and useful_fragment(sentence):
                sentences.append(sentence)
    return list(dict.fromkeys(sentences))


def clip_sentence(text: str, limit: int) -> str:
    text = clean_space(text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in "。！？；，":
        pos = cut.rfind(mark)
        if pos >= int(limit * 0.6):
            return cut[: pos + 1]
    return cut.rstrip("，；、") + "。"


def build_script(job: CourseJob, title: str, fragments: list[str], min_chars: int, max_chars: int) -> str:
    sentences = split_sentences(fragments)
    intro = f"{title.rstrip('。！？')}。"
    body: list[str] = [intro]

    if sentences:
        body.append(clip_sentence(sentences[0], 120))
    if len(sentences) > 1:
        body.append(clip_sentence(sentences[1], 130))

    for sentence in sentences[2:]:
        current = clean_space("".join(body))
        if len(current) >= min_chars:
            break
        if title in sentence and current.count(title) >= 2:
            sentence = sentence.replace(title, "这一课")
        body.append(clip_sentence(sentence, 150))

    closing = (
        "听课时请把内容拆成三列：第一列写本课真正讨论的问题，第二列写可以观察的证据，第三列写会让你修正判断的反方信号。"
        "最后完成一次每日精进：用一百字写下一个新概念、一个风险边界和一个下一步行动。"
    )
    body.append(closing)
    script = clean_space("".join(body))

    if len(script) < min_chars:
        script += (
            "如果这一课涉及周期，就把它放回技术扩散、债务成本、人口结构、制度变化和行为偏差这五个慢变量中检查；"
            "如果这一课涉及一本书，就先区分作者的时代问题、核心洞见和今天仍然可迁移的方法。"
            "学习目标不是记住一句结论，而是形成一张可以复盘的观察清单。"
        )
    script = clean_space(script)

    if len(script) > max_chars:
        clipped = script[:max_chars]
        for mark in "。！？；":
            pos = clipped.rfind(mark)
            if pos >= min_chars:
                return clipped[: pos + 1]
        return clipped[:max_chars].rstrip("，；、") + "。"
    return script


def make_jobs(frontend: Path, kind: str, ids: str) -> list[CourseJob]:
    jobs: list[CourseJob] = []
    script_root = DATA_ROOT / "long_audio_scripts"
    if kind in ("all", "core"):
        for idx in parse_ids(ids, 1, 65):
            jobs.append(
                CourseJob(
                    kind="core",
                    idx=idx,
                    page=frontend / f"lesson{idx}.html",
                    audio=frontend / "audio" / f"lesson{idx}.mp3",
                    script=script_root / "core" / f"lesson{idx:03d}.txt",
                    label="主干课程",
                )
            )
    if kind in ("all", "books"):
        for idx in parse_ids(ids, 1, 500):
            jobs.append(
                CourseJob(
                    kind="books",
                    idx=idx,
                    page=frontend / f"book{idx}.html",
                    audio=frontend / "audio" / "books" / f"lesson{idx}.mp3",
                    script=script_root / "books" / f"lesson{idx:03d}.txt",
                    label="书目精读",
                )
            )
    return jobs


def ffprobe(path: Path) -> dict:
    try:
        raw = subprocess.check_output(
            [
                shutil.which("ffprobe") or "/usr/bin/ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "stream=codec_name,sample_rate,channels,bit_rate:format=duration",
                "-of",
                "json",
                str(path),
            ],
            text=True,
        )
        data = json.loads(raw or "{}")
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        return {
            "codec_name": stream.get("codec_name", ""),
            "sample_rate": str(stream.get("sample_rate", "")),
            "channels": int(stream.get("channels") or 0),
            "bit_rate": str(stream.get("bit_rate") or ""),
            "duration": round(float(fmt.get("duration") or 0), 3),
        }
    except Exception as exc:
        return {"error": str(exc)}


def standard_audio(meta: dict) -> bool:
    if meta.get("error"):
        return False
    bit_rate = int(meta.get("bit_rate") or 0)
    return (
        meta.get("codec_name") == "mp3"
        and str(meta.get("sample_rate")) == "24000"
        and int(meta.get("channels") or 0) == 1
        and 45000 <= bit_rate <= 52000
    )


def safe_relative(path: Path, base: Path) -> Path:
    try:
        return path.relative_to(base)
    except ValueError:
        return Path(path.parent.name) / path.name


async def synthesize_audio(text: str, target: Path, voice: str, rate: str, pitch: str, backup_dir: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup_target = backup_dir / safe_relative(target, FRONTEND)
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_target)

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp3"
        for attempt in range(4):
            try:
                communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
                await communicate.save(str(raw))
                break
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(1.5 * (attempt + 1))
        subprocess.run(
            [
                shutil.which("ffmpeg") or "/usr/bin/ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(raw),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=9",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                "48k",
                str(target),
            ],
            check=True,
        )


def write_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


async def process_job(job: CourseJob, args: argparse.Namespace, backup_dir: Path, log_path: Path) -> tuple[bool, str]:
    started = time.time()
    try:
        if not job.page.exists():
            raise FileNotFoundError(job.page)
        title, fragments = extract_page_text(job)
        if job.script.exists() and not args.force:
            script = clean_space(job.script.read_text(encoding="utf-8", errors="ignore"))
            if len(script) < args.min_chars:
                script = build_script(job, title, fragments, args.min_chars, args.max_chars)
        else:
            script = build_script(job, title, fragments, args.min_chars, args.max_chars)
        script = title_first(script, title)
        if len(script) < args.min_chars:
            raise RuntimeError(f"script too short: {len(script)} chars")
        job.script.parent.mkdir(parents=True, exist_ok=True)
        job.script.write_text(script + "\n", encoding="utf-8")

        if not args.skip_audio and not args.verify_only:
            await synthesize_audio(script, job.audio, args.voice, args.rate, args.pitch, backup_dir)
        meta = ffprobe(job.audio) if job.audio.exists() else {"error": "missing audio"}
        row = {
            "status": "ok" if standard_audio(meta) else "audio_mismatch",
            "kind": job.kind,
            "id": job.idx,
            "title": title,
            "scriptChars": len(script),
            "audio": str(safe_relative(job.audio, FRONTEND)),
            "meta": meta,
            "seconds": round(time.time() - started, 3),
        }
        write_jsonl(log_path, row)
        return row["status"] == "ok", f"{job.kind} {job.idx} chars={len(script)} duration={meta.get('duration')}"
    except Exception as exc:
        row = {
            "status": "failed",
            "kind": job.kind,
            "id": job.idx,
            "error": str(exc),
            "seconds": round(time.time() - started, 3),
        }
        write_jsonl(log_path, row)
        return False, f"{job.kind} {job.idx} FAIL {exc}"


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["all", "core", "books"], default="all")
    parser.add_argument("--ids", default="", help="例如 1,9,151 或 1-50；all 同时用于主干和书目")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--frontend", default=str(FRONTEND))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--min-chars", type=int, default=DEFAULT_MIN_CHARS)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--voice", default="zh-CN-YunyangNeural")
    parser.add_argument("--rate", default="-8%")
    parser.add_argument("--pitch", default="-2Hz")
    args = parser.parse_args()

    frontend = Path(args.frontend)
    jobs = make_jobs(frontend, args.kind, args.ids)
    if args.limit:
        jobs = jobs[: args.limit]
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_dir = BACKUP_ROOT / f"long-audio-before-{run_id}"
    log_path = DATA_ROOT / "long_audio_logs" / f"run-{run_id}.jsonl"

    ok = 0
    failed = 0
    for job in jobs:
        status, message = await process_job(job, args, backup_dir, log_path)
        print(("OK " if status else "FAIL ") + message, flush=True)
        ok += 1 if status else 0
        failed += 0 if status else 1

    print(f"done ok={ok} fail={failed} log={log_path} backup={backup_dir}")
    return 0 if failed == 0 else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

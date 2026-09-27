#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib import request as urlrequest

import edge_tts
from bs4 import BeautifulSoup
from audio_narration import title_first


ROOT = Path("/var/www/kangboacademy")
FRONTEND = ROOT / "frontend"
CACHE_ROOT = ROOT / "data" / "generated_core_audio"
BACKUP_ROOT = ROOT / "backups"


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def parse_ids(value: str) -> list[int]:
    if not value:
        return list(range(2, 66))
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
    return [idx for idx in sorted(dict.fromkeys(ids)) if 1 <= idx <= 65]


def process_environ() -> dict[str, str]:
    values = dict(os.environ)
    try:
        pid = subprocess.check_output(
            ["systemctl", "show", "kangboacademy", "-p", "MainPID", "--value"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if pid and pid != "0":
            for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
                if b"=" not in item:
                    continue
                key, value = item.split(b"=", 1)
                values.setdefault(key.decode(), value.decode(errors="ignore"))
    except Exception:
        pass
    return values


def deepseek_config() -> tuple[str, str, str]:
    env = process_environ()
    key = env.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not available")
    base_url = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = env.get("DEEPSEEK_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
    return key, base_url, model


def call_deepseek(system_prompt: str, user_prompt: str, max_tokens: int = 500, retries: int = 4) -> str:
    key, base_url, model = deepseek_config()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.35,
        "top_p": 0.88,
        "max_tokens": max_tokens,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urlrequest.Request(
                f"{base_url}/chat/completions",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlrequest.urlopen(req, timeout=80) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return content.strip()
        except Exception as exc:
            last_error = exc
            time.sleep(1.8 * (attempt + 1))
    raise RuntimeError(f"DeepSeek request failed: {last_error}")


def extract_json(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text, strict=False)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0), strict=False)
    raise ValueError("Cannot parse JSON response")


def title_from_soup(soup: BeautifulSoup, idx: int) -> str:
    for selector in ["h1", "title"]:
        tag = soup.select_one(selector)
        if tag:
            title = clean_space(tag.get_text(" ", strip=True))
            title = re.sub(r"\s*—.*$", "", title)
            if title:
                return title
    return f"第{idx}课"


def extract_lesson_text(frontend: Path, idx: int) -> tuple[str, str]:
    page = frontend / f"lesson{idx}.html"
    raw = page.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "audio", "video", "iframe", "nav"]):
        tag.decompose()
    for tag in soup.select(".audio-player, .bottom-nav, .progress-bar, .nav"):
        tag.decompose()
    title = title_from_soup(soup, idx)
    container = soup.select_one("article") or soup.select_one(".content") or soup.select_one("main") or soup.body or soup
    pieces: list[str] = []
    for tag in container.find_all(["h2", "h3", "p", "li", "blockquote"]):
        text = clean_space(tag.get_text(" ", strip=True))
        if not text:
            continue
        if any(skip in text for skip in ["您的浏览器不支持音频", "上一课", "下一课", "主干课程", "推荐书目"]):
            continue
        pieces.append(text)
    lesson_text = "\n".join(dict.fromkeys(pieces))
    return title, lesson_text


def clip_sentence(text: str, limit: int) -> str:
    text = clean_space(re.sub(r"[。！？；,，]+$", "", text))
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in "。！？；，、":
        idx = cut.rfind(mark)
        if idx >= limit * 0.62:
            return cut[:idx]
    return cut.rstrip("，；、") + "。"


def fallback_script(idx: int, title: str, lesson_text: str) -> str:
    first = ""
    for sentence in re.split(r"[。！？]\s*", lesson_text):
        sentence = clean_space(sentence)
        if 25 <= len(sentence) <= 120 and title not in sentence:
            first = sentence
            break
    if not first:
        first = "本课帮助你把概念、周期位置、资产含义和风险边界放到同一张观察清单里。"
    return (
        f"{title}。"
        f"这一课的核心，是{clip_sentence(first, 68)}"
        "学习时请抓住三个层次：先理解问题，再写出因果链，最后把它转成自己的观察指标和复盘动作。"
        "听完后，请用一条反方证据检查你的判断。"
    )


def normalize_script(idx: int, title: str, lesson_text: str, raw: str) -> str:
    script = clean_space(raw)
    script = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", script)
    script = re.sub(r"[#*`<>]", "", script)
    if len(script) < 170:
        script = fallback_script(idx, title, lesson_text)
    script = title_first(script, title)
    if len(script) < 190:
        script += "请把本课内容写进每日精进，用一个指标、一个风险边界和一个行动来完成复盘。"
    if len(script) <= 240:
        return script
    cut = script[:240]
    for mark in "。！？；，":
        pos = cut.rfind(mark)
        if pos >= 190:
            return cut[: pos + 1]
    return cut[:239].rstrip("，；、") + "。"


def generate_script(idx: int, title: str, lesson_text: str, cache_dir: Path, force: bool) -> str:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"lesson{idx}.json"
    if cache_path.exists() and not force:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        script = clean_space(cached.get("audioScript", ""))
        if 170 <= len(script) <= 260:
            return title_first(script, title)

    system_prompt = (
        "你是康波研究院的课程音频主笔。请把课程正文压缩成一段自然、沉稳、像真人老师导入课程的中文口播稿。"
        "必须输出严格 JSON，不要 Markdown。不要给买卖建议，不承诺收益。"
    )
    payload = {
        "courseId": idx,
        "title": title,
        "sourceText": lesson_text[:2600],
        "rules": [
            "只输出 JSON：{\"audioScript\":\"...\"}",
            "audioScript 190 到 230 个中文字符，适合慢速朗读 35 到 50 秒。",
            "必须具体对应本课主题，不能写成通用学习提示。",
            "直接以课程标题开头，接着讲正文；不加欢迎语、制作说明或不是简单复述页面之类的开场白。",
            "包含本课核心问题、一个关键词、一个练习或复盘动作。",
            "不要使用列表符号、括号、HTML、舞台说明。",
        ],
    }
    previous_error = ""
    for _ in range(4):
        if previous_error:
            payload["previousError"] = previous_error
        try:
            data = extract_json(call_deepseek(system_prompt, json.dumps(payload, ensure_ascii=False)))
            script = normalize_script(idx, title, lesson_text, str(data.get("audioScript") or ""))
            if 170 <= len(script) <= 260:
                cache_path.write_text(
                    json.dumps({"title": title, "audioScript": script, "generatedAt": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return script
            previous_error = f"音频稿长度不合格：{len(script)}"
        except Exception as exc:
            previous_error = f"输出不可解析：{exc}"
    script = normalize_script(idx, title, lesson_text, "")
    cache_path.write_text(
        json.dumps({"title": title, "audioScript": script, "generatedAt": datetime.now().isoformat(timespec="seconds"), "fallback": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return script


async def synthesize_audio(text: str, target: Path, voice: str, rate: str, pitch: str, ffmpeg: str, backup_dir: Path) -> float:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, backup_dir / target.name)
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
                ffmpeg,
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
    return ffprobe_duration(target)


def ffprobe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        [
            shutil.which("ffprobe") or "/usr/bin/ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
    ).strip()
    return round(float(raw), 3)


async def main_async() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="", help="默认 2-65，例如 7,11,42-50")
    parser.add_argument("--frontend", default=str(FRONTEND))
    parser.add_argument("--cache-dir", default=str(CACHE_ROOT))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--voice", default="zh-CN-YunyangNeural")
    parser.add_argument("--rate", default="-8%")
    parser.add_argument("--pitch", default="-2Hz")
    args = parser.parse_args()

    frontend = Path(args.frontend)
    cache_dir = Path(args.cache_dir)
    script_dir = cache_dir / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = BACKUP_ROOT / f"core-ai-audio-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"

    ok = 0
    failed = 0
    for idx in parse_ids(args.ids):
        try:
            title, lesson_text = extract_lesson_text(frontend, idx)
            script = generate_script(idx, title, lesson_text, cache_dir, args.force)
            (script_dir / f"lesson{idx:03d}.txt").write_text(script + "\n", encoding="utf-8")
            target = frontend / "audio" / f"lesson{idx}.mp3"
            duration = await synthesize_audio(script, target, args.voice, args.rate, args.pitch, ffmpeg, backup_dir)
            print(f"OK lesson{idx} {title} chars={len(script)} audio={duration}s")
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"FAIL lesson{idx}: {exc}")
    print(f"done ok={ok} fail={failed} backup={backup_dir} cache={cache_dir}")
    return 0 if failed == 0 else 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())

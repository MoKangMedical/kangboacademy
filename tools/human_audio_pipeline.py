#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString


FRONTEND = Path("/var/www/kangboacademy/frontend")
OUT_DIR = Path("/var/www/kangboacademy/data/human_audio")
BACKUP_ROOT = Path("/var/www/kangboacademy/backups")
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".aac", ".flac", ".aiff")


@dataclass
class CourseAudioJob:
    kind: str
    id: int
    title: str
    page: str
    script_path: str
    final_audio_path: str
    inbox_candidates: list[str]
    chars: int
    estimated_minutes: float
    status: str = "script_ready"


def clean_space(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\u3000", " ")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n+", "\n", value)
    return value.strip()


def text_of(tag) -> str:
    return clean_space(tag.get_text(" ", strip=True))


def strip_book_marks(value: str) -> str:
    value = clean_space(value)
    value = re.sub(r"\s*—.*$", "", value)
    value = value.replace("《《", "《").replace("》》", "》")
    return value


def parse_ids(value: str, start: int, end: int) -> list[int]:
    if not value:
        return list(range(start, end + 1))
    ids: list[int] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, b = [int(x) for x in chunk.split("-", 1)]
            ids.extend(range(a, b + 1))
        else:
            ids.append(int(chunk))
    return [i for i in sorted(dict.fromkeys(ids)) if start <= i <= end]


def get_content_container(soup: BeautifulSoup):
    for selector in [
        "article",
        "div.content",
        "main .content",
        "main",
        "body",
    ]:
        node = soup.select_one(selector)
        if node:
            return node
    return soup


def remove_non_lesson_nodes(container) -> None:
    for tag in container.select(
        "script, style, audio, video, iframe, nav, .nav, .bottom-nav, "
        ".purchase-card, .buy-row, .progress-bar, .audio-player"
    ):
        tag.decompose()
    for tag in container.find_all(["table"]):
        rows = []
        for tr in tag.find_all("tr"):
            cells = [text_of(cell) for cell in tr.find_all(["th", "td"])]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append("；".join(cells))
        tag.replace_with(BeautifulSoup("\n".join(f"<p>{html.escape(row)}</p>" for row in rows), "html.parser"))


def extract_title(soup: BeautifulSoup, fallback: str) -> str:
    for selector in ["h1", "title"]:
        tag = soup.select_one(selector)
        if tag:
            title = strip_book_marks(text_of(tag))
            if title:
                return title
    return fallback


def skip_text(value: str) -> bool:
    if not value:
        return True
    banned = [
        "您的浏览器不支持音频播放",
        "京东",
        "当当",
        "豆瓣",
        "购买与延伸学习",
        "课程音频",
        "上一课",
        "下一课",
        "主干课程",
        "推荐书目",
    ]
    return any(item in value for item in banned)


def sentence_pause(value: str) -> str:
    value = clean_space(value)
    if not value:
        return ""
    if value[-1] not in "。！？；：":
        value += "。"
    return value


def narration_from_page(frontend: Path, kind: str, idx: int) -> tuple[str, str, int, float]:
    page_name = f"lesson{idx}.html" if kind == "core" else f"book{idx}.html"
    page = frontend / page_name
    raw = page.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    title = extract_title(soup, f"第{idx}课")
    container = get_content_container(soup)
    remove_non_lesson_nodes(container)

    lines = [
        f"康波研究院，{'主干课程' if kind == 'core' else '推荐书目课程'}第{idx}课。",
        f"本课标题：{title}。",
        "以下为完整课程口播稿，录制时请保持自然、沉稳、留出段落停顿。",
        "",
    ]
    seen = set()
    for tag in container.find_all(["h2", "h3", "h4", "p", "li", "blockquote"]):
        value = text_of(tag)
        if skip_text(value):
            continue
        if value in seen:
            continue
        seen.add(value)
        if tag.name == "h2":
            lines.append("")
            lines.append(f"【{value}】")
        elif tag.name == "h3":
            lines.append("")
            lines.append(f"{value}。")
        else:
            lines.append(sentence_pause(value))

    text = clean_space("\n".join(lines)) + "\n"
    chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))
    # Conservative Mandarin audiobook pace: about 240 Chinese chars/minute.
    estimated_minutes = round(chars / 240, 1)
    return title, text, chars, estimated_minutes


def final_audio_path(frontend: Path, kind: str, idx: int) -> Path:
    if kind == "core":
        return frontend / "audio" / f"lesson{idx}.mp3"
    return frontend / "audio" / "books" / f"lesson{idx}.mp3"


def inbox_candidates(kind: str, idx: int) -> list[str]:
    names = []
    if kind == "core":
        bases = [f"core/lesson{idx}", f"core/lesson{idx:03d}", f"lesson{idx}", f"lesson{idx:03d}"]
    else:
        bases = [f"book/book{idx}", f"book/book{idx:03d}", f"book/lesson{idx}", f"book/lesson{idx:03d}"]
    for base in bases:
        names.extend(base + ext for ext in AUDIO_EXTS)
    return names


def write_manifest(jobs: list[CourseAudioJob], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "manifest.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(jobs[0]).keys()))
        writer.writeheader()
        for job in jobs:
            row = asdict(job)
            row["inbox_candidates"] = "|".join(job.inbox_candidates)
            writer.writerow(row)
    (out_dir / "manifest.json").write_text(
        json.dumps([asdict(job) for job in jobs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_minutes = round(sum(job.estimated_minutes for job in jobs), 1)
    lines = [
        "# 真人音频录制包",
        "",
        f"- 课程数：{len(jobs)}",
        f"- 预计录制时长：约 {total_minutes} 分钟",
        "- 录音建议：安静房间，48kHz/24bit WAV 或高码率 MP3，单人稳定口播。",
        "- 交付方式：把录好的文件放入 `inbox/`，文件名按 manifest 的候选路径命名。",
        "- 发布方式：运行 `human_audio_pipeline.py install --inbox ...`，脚本会自动备份旧音频并转成 24kHz 单声道 48kbps MP3。",
        "",
        "## 文件命名示例",
        "",
        "- 主干第 7 课：`inbox/core/lesson7.wav`",
        "- 书目第 151 课：`inbox/book/book151.wav` 或 `inbox/book/lesson151.wav`",
        "",
        "## 质检标准",
        "",
        "- 不要有明显底噪、爆音、截断、左右声道异常。",
        "- 录音开头和结尾各保留 0.3 到 0.8 秒自然静音。",
        "- 不读页面导航、购买链接、按钮文字。",
        "- 不加入投资承诺或买卖指令。",
    ]
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare(frontend: Path, out_dir: Path, kind: str, ids: str) -> None:
    jobs: list[CourseAudioJob] = []
    kinds = ["core", "book"] if kind == "all" else [kind]
    for course_kind in kinds:
        end = 65 if course_kind == "core" else 500
        script_dir = out_dir / "scripts" / course_kind
        script_dir.mkdir(parents=True, exist_ok=True)
        for idx in parse_ids(ids, 1, end):
            page = frontend / (f"lesson{idx}.html" if course_kind == "core" else f"book{idx}.html")
            if not page.exists():
                continue
            title, text, chars, estimated_minutes = narration_from_page(frontend, course_kind, idx)
            script_name = f"lesson{idx:03d}.txt" if course_kind == "core" else f"book{idx:03d}.txt"
            script_path = script_dir / script_name
            script_path.write_text(text, encoding="utf-8")
            jobs.append(
                CourseAudioJob(
                    kind=course_kind,
                    id=idx,
                    title=title,
                    page=page.name,
                    script_path=str(script_path.relative_to(out_dir)),
                    final_audio_path=str(final_audio_path(frontend, course_kind, idx).relative_to(frontend)),
                    inbox_candidates=inbox_candidates(course_kind, idx),
                    chars=chars,
                    estimated_minutes=estimated_minutes,
                )
            )
    if not jobs:
        raise SystemExit("没有找到可准备的课程页面")
    write_manifest(jobs, out_dir)
    print(f"prepared={len(jobs)} out={out_dir}")


def ffmpeg_bin() -> str:
    return shutil.which("ffmpeg") or "/usr/bin/ffmpeg"


def ffprobe(path: Path) -> dict:
    try:
        raw = subprocess.check_output(
            [
                shutil.which("ffprobe") or "/usr/bin/ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration,bit_rate",
                "-show_entries",
                "stream=sample_rate,channels",
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
            "duration": round(float(fmt.get("duration") or 0), 3),
            "bit_rate": int(fmt.get("bit_rate") or 0),
            "sample_rate": int(stream.get("sample_rate") or 0),
            "channels": int(stream.get("channels") or 0),
            "size": path.stat().st_size if path.exists() else 0,
        }
    except Exception as exc:
        return {"error": str(exc)[:180]}


def load_manifest(out_dir: Path) -> list[dict]:
    path = out_dir / "manifest.json"
    if not path.exists():
        raise SystemExit(f"缺少 manifest：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def find_inbox_file(inbox: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = inbox / rel
        if path.exists():
            return path
    return None


def normalize_audio(src: Path, dst: Path, backup_dir: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.copy2(dst, backup_dir / dst.name)
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=10,aresample=24000",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "48k",
            str(dst),
        ],
        check=True,
    )


def install(frontend: Path, out_dir: Path, inbox: Path, kind: str, ids: str) -> None:
    manifest = load_manifest(out_dir)
    allowed = set()
    if ids:
        for course_kind in (["core", "book"] if kind == "all" else [kind]):
            end = 65 if course_kind == "core" else 500
            for idx in parse_ids(ids, 1, end):
                allowed.add((course_kind, idx))
    backup_dir = BACKUP_ROOT / f"audio-before-human-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    installed = []
    missing = []
    for row in manifest:
        row_kind = row["kind"]
        row_id = int(row["id"])
        if kind != "all" and row_kind != kind:
            continue
        if allowed and (row_kind, row_id) not in allowed:
            continue
        candidates = row["inbox_candidates"]
        src = find_inbox_file(inbox, candidates)
        if not src:
            missing.append(f"{row_kind}{row_id}")
            continue
        dst = frontend / row["final_audio_path"]
        normalize_audio(src, dst, backup_dir / row_kind)
        meta = ffprobe(dst)
        installed.append({**row, "source": str(src), **meta})
        print(f"installed {row_kind}{row_id} {src} -> {dst} duration={meta.get('duration')}")
    report = out_dir / "install_report.json"
    report.write_text(
        json.dumps({"installed": installed, "missing": missing, "backup_dir": str(backup_dir)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"installed={len(installed)} missing={len(missing)} report={report}")


def audit(frontend: Path, out_dir: Path, kind: str, ids: str) -> None:
    manifest = load_manifest(out_dir)
    rows = []
    for row in manifest:
        row_kind = row["kind"]
        row_id = int(row["id"])
        if kind != "all" and row_kind != kind:
            continue
        end = 65 if row_kind == "core" else 500
        if ids and row_id not in set(parse_ids(ids, 1, end)):
            continue
        audio = frontend / row["final_audio_path"]
        meta = ffprobe(audio) if audio.exists() else {"error": "missing"}
        status = "ok"
        if meta.get("error"):
            status = "missing_or_broken"
        elif meta.get("sample_rate") != 24000 or meta.get("channels") != 1:
            status = "format_warning"
        rows.append({**row, **meta, "audio_status": status})
    report_json = out_dir / "audit_report.json"
    report_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    report_csv = out_dir / "audit_report.csv"
    fields = [
        "kind",
        "id",
        "title",
        "final_audio_path",
        "chars",
        "estimated_minutes",
        "duration",
        "sample_rate",
        "channels",
        "bit_rate",
        "size",
        "audio_status",
        "error",
    ]
    with report_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    print(f"audited={len(rows)} report={report_csv}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare", "install", "audit"])
    parser.add_argument("--frontend", default=str(FRONTEND))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--kind", choices=["all", "core", "book"], default="all")
    parser.add_argument("--ids", default="")
    parser.add_argument("--inbox", default="")
    args = parser.parse_args()

    frontend = Path(args.frontend)
    out_dir = Path(args.out_dir)
    if args.mode == "prepare":
        prepare(frontend, out_dir, args.kind, args.ids)
    elif args.mode == "install":
        if not args.inbox:
            raise SystemExit("install 需要 --inbox")
        install(frontend, out_dir, Path(args.inbox), args.kind, args.ids)
    else:
        audit(frontend, out_dir, args.kind, args.ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from audio_narration import title_first


def clean_title(value: str) -> str:
    value = re.sub(r"\s*—.*$", "", value or "").strip()
    value = value.replace("《《", "《").replace("》》", "》")
    return value or "书目课程"


def missing_audio_rows(report: Path) -> list[dict]:
    rows = []
    with report.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("kind") != "book":
                continue
            if "WARN_AUDIO_MISSING_OR_BROKEN" not in row.get("flags", ""):
                continue
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="reports/kangbo_course_audit.csv")
    parser.add_argument("--out", default="generated_audio/books")
    parser.add_argument("--voice", default="Tingting")
    parser.add_argument("--rate", default="155")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--script-dir", required=True, help="Verified narration files named lesson<ID>.txt")
    args = parser.parse_args()

    report = Path(args.report)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    say = shutil.which("say")
    if not ffmpeg or not say:
        raise SystemExit("需要本机安装 say 和 ffmpeg")

    rows = missing_audio_rows(report)
    if args.limit:
        rows = rows[:args.limit]

    generated = 0
    skipped = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for row in rows:
            idx = int(row["id"])
            title = clean_title(row["title"])
            target = out_dir / f"lesson{idx}.mp3"
            if target.exists() and target.stat().st_size > 1024:
                skipped += 1
                continue
            source = Path(args.script_dir) / f"lesson{idx}.txt"
            narration = source.read_text(encoding="utf-8").strip()
            if len(narration) < 100:
                raise ValueError(f"Narration is missing substantive content: {source}")
            text = title_first(narration, title)
            aiff = tmp_dir / f"lesson{idx}.aiff"
            subprocess.run(
                [say, "-v", args.voice, "-r", str(args.rate), "-o", str(aiff), text],
                check=True,
            )
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(aiff),
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "64k",
                    str(target),
                ],
                check=True,
            )
            generated += 1
            if generated % 25 == 0:
                print(f"generated={generated}")

    print(f"generated={generated} skipped={skipped} out={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Prepare title-first audio in a new directory; never overwrite live audio."""
import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from audio_narration import META_SENTENCE, title_first
from regenerate_long_course_audio import CourseJob, extract_page_text, ffprobe, synthesize_audio


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def prepare(args):
    root = Path(args.root)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for kind, count in [('core', 65), ('books', 500)]:
        for idx in range(1, count + 1):
            if args.ids and idx not in args.ids:
                continue
            page = root / 'frontend' / f'{"lesson" if kind == "core" else "book"}{idx}.html'
            source_audio = root / 'frontend/audio' / ('' if kind == 'core' else 'books') / f'lesson{idx}.mp3'
            source_script = root / 'data/long_audio_scripts' / kind / f'lesson{idx:03d}.txt'
            row = {'kind': kind, 'id': idx, 'status': 'unverified'}
            try:
                # Missing authoritative narration must not be replaced with a new summary.
                if not source_script.is_file() or not source_audio.is_file() or not page.is_file():
                    raise FileNotFoundError('Missing page, existing narration or audio; manual source matching required')
                job = CourseJob(kind, idx, page, source_audio, source_script, '')
                title, _ = extract_page_text(job)
                original = source_script.read_text(encoding='utf-8').strip()
                cleaned = title_first(original, title)
                row.update(title=title, sourceScriptSHA256=sha256(source_script),
                           sourceAudioSHA256=sha256(source_audio),
                           boilerplateMatches=len(META_SENTENCE.findall(original)),
                           changed=cleaned != original)
                if cleaned == original:
                    row['status'] = 'unchanged_script_audio_not_transcribed'
                else:
                    folder = output / kind
                    folder.mkdir(exist_ok=True)
                    backup = folder / 'originals'
                    backup.mkdir(exist_ok=True)
                    shutil.copy2(source_script, backup / source_script.name)
                    shutil.copy2(source_audio, backup / source_audio.name)
                    (folder / source_script.name).write_text(cleaned + '\n', encoding='utf-8')
                    row['status'] = 'script_prepared'
                    if args.render:
                        target = folder / source_audio.name
                        await synthesize_audio(cleaned, target, args.voice, '-8%', '-2Hz', output / 'render_backup')
                        meta = ffprobe(target)
                        if meta.get('error') or meta.get('duration', 0) <= 0:
                            raise RuntimeError('Generated audio metadata check failed')
                        subprocess.run([shutil.which('ffmpeg') or 'ffmpeg', '-v', 'error', '-xerror',
                                        '-i', str(target), '-f', 'null', '-'], check=True)
                        row.update(status='rendered_not_published', audioSHA256=sha256(target), meta=meta)
            except Exception as exc:
                row.update(status='blocked', error=str(exc))
            rows.append(row)
            with (output / 'manifest.jsonl').open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            print(f'{kind}/{idx}: {row["status"]}', flush=True)
    summary = {'processed': len(rows), 'blocked': sum(r['status'] == 'blocked' for r in rows),
               'changed': sum(bool(r.get('changed')) for r in rows), 'published': False}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary['blocked'] else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='/var/www/kangboacademy')
    parser.add_argument('--output', required=True, help='New staging directory, must not exist')
    parser.add_argument('--ids', type=lambda v: [int(x) for x in v.split(',')], default=[])
    parser.add_argument('--render', action='store_true', help='Synthesize staged files, never publish')
    parser.add_argument('--voice', default='zh-CN-YunyangNeural')
    raise SystemExit(asyncio.run(prepare(parser.parse_args())))

#!/usr/bin/env python3
"""Read-only production narration inventory; sample metadata is not a listening review."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    args = parser.parse_args()
    root = Path(args.root)
    missing_audio, missing_scripts, unwanted_intro, old_prefix, samples = [], [], [], [], []
    pattern = re.compile(r'不是简单(?:地)?(?:复述|复制)(?:页面|网页)')
    for kind, size in [('core', 65), ('books', 500)]:
        for number in range(1, size + 1):
            key = f'{kind}:{number}'
            audio = root / 'frontend/audio' / (f'books/lesson{number}.mp3' if kind == 'books' else f'lesson{number}.mp3')
            script = root / f'data/long_audio_scripts/{kind}/lesson{number:03d}.txt'
            if not audio.is_file() or audio.stat().st_size < 1024:
                missing_audio.append(key)
            elif number in {1, size // 2, size}:
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration,size',
                                        '-of', 'json', str(audio)], capture_output=True, text=True, timeout=30)
                samples.append({'course': key, 'probePassed': probe.returncode == 0,
                                'metadata': json.loads(probe.stdout) if probe.returncode == 0 else {}})
            if not script.is_file():
                missing_scripts.append(key)
                continue
            text = script.read_text(encoding='utf-8')
            if pattern.search(text):
                unwanted_intro.append(key)
            if re.match(r'^\s*康波研究院(?:主干课程|书目精读|书目课程)', text):
                old_prefix.append(key)
    print(json.dumps({'scope': 'production-files-readonly-not-audio-listening-or-regeneration',
                      'expectedCourses': 565, 'missingAudio': missing_audio, 'missingScripts': missing_scripts,
                      'unwantedIntroScripts': unwanted_intro, 'brandedPrefixScripts': old_prefix,
                      'sampleMetadata': samples, 'audioOpeningContentVerified': False,
                      'productionModified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()

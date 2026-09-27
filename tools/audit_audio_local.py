#!/usr/bin/env python3
"""Inventory existing local narration/audio without changing or rendering it."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from audio_narration import META_SENTENCE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root, output = Path(args.root), Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    scripts = []
    for source in sorted((root / 'generated_audio_neural/scripts').glob('*.txt')):
        text = source.read_text(encoding='utf-8')
        scripts.append({'path': str(source.relative_to(root)), 'chars': len(text),
                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'targetedIntroMatches': len(META_SENTENCE.findall(text))})
    samples = []
    files = sorted((root / 'generated_audio_neural/books').glob('*.mp3'))
    for source in files[:1] + files[-1:]:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                 'format=duration,size:stream=codec_name,sample_rate,channels',
                                 '-of', 'json', str(source)], capture_output=True, text=True, timeout=20)
        decoded = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(source),
                                  '-f', 'null', '-'], capture_output=True, text=True, timeout=30)
        samples.append({'path': str(source.relative_to(root)),
                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'probe': json.loads(result.stdout) if result.returncode == 0 else {},
                        'decoded': decoded.returncode == 0})
    summary = {'localScripts': len(scripts), 'localMp3s': len(files),
               'scriptsWithTargetedIntro': sum(row['targetedIntroMatches'] > 0 for row in scripts),
               'localSamplesDecoded': sum(row['decoded'] for row in samples),
               'onlineOpeningVerified': False, 'onlinePublishedByThisRun': False,
               'scope': 'Local historical short-audio assets only; not the authoritative online long-audio narration.'}
    (output / 'local-audio-audit.json').write_text(json.dumps({'summary': summary, 'scripts': scripts, 'samples': samples}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()

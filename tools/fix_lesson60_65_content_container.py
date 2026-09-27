#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


FRONTEND_DIR = Path("/var/www/kangboacademy/frontend")
BACKUP_ROOT = Path("/var/www/kangboacademy/backups")
LESSONS = range(60, 66)

EXACT_CONTENT_RE = re.compile(
    r'<div\s+class=["\']content["\'][^>]*>[\s\S]*?\n\s*</div>\s*\n\s*<div\s+class=["\']bottom-nav["\']',
    re.I,
)


def fix_container(source: str) -> tuple[str, bool]:
    if EXACT_CONTENT_RE.search(source):
        return source, False

    content_match = re.search(r'<div\s+class=["\']content["\'][^>]*>', source, flags=re.I)
    bottom_match = re.search(r'<div\s+class=["\']bottom-nav["\']', source, flags=re.I)
    if not content_match or not bottom_match or content_match.end() >= bottom_match.start():
        return source, False

    first_close = source.find("</div>", content_match.end(), bottom_match.start())
    if first_close == -1:
        return source, False

    # Remove the premature close of .content, then add the real close immediately
    # before bottom-nav. Existing recommendation/exercise divs keep their own closes.
    without_premature = source[:first_close] + source[first_close + len("</div>"):]
    bottom_match = re.search(r'<div\s+class=["\']bottom-nav["\']', without_premature, flags=re.I)
    if not bottom_match:
        return source, False
    updated = without_premature[:bottom_match.start()] + "</div>\n" + without_premature[bottom_match.start():]
    return updated, True


def main() -> int:
    backup_dir = BACKUP_ROOT / f"lesson60-65-container-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    changed = []
    for lesson_id in LESSONS:
        path = FRONTEND_DIR / f"lesson{lesson_id}.html"
        original = path.read_text(encoding="utf-8", errors="ignore")
        updated, did = fix_container(original)
        if did and updated != original:
            shutil.copy2(path, backup_dir / path.name)
            path.write_text(updated, encoding="utf-8")
            changed.append(path.name)
    print(f"backup_dir={backup_dir}")
    print(f"changed={','.join(changed) if changed else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Public catalog metadata only. Entitlements always remain in the API layer."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4)
def _read(path, modified, size):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schemaVersion') != 1 or not isinstance(data.get('courses'), list):
        raise ValueError('Invalid content contract')
    lookup = {}
    for row in data['courses']:
        kind, number = row['kind'], row['number']
        key = f'{kind}:{number}'
        lesson = f'{"lesson" if kind == "core" else "book"}{number}.html'
        if kind not in ('core', 'book') or type(number) is not int or number < 1 or row['key'] != key or row['lesson'] != lesson or key in lookup:
            raise ValueError('Invalid catalog identity')
        lookup[key] = row
    return data.get('contentVersion', ''), lookup


def catalog_metadata(frontend, kind, number):
    source = Path(frontend) / 'content-manifest.json'
    try:
        stat = source.stat()
        version, lookup = _read(str(source), stat.st_mtime_ns, stat.st_size)
        row = lookup.get(f'{kind}:{number}')
        if not row:
            return {}
        result = {'title': row['title'], 'desc': row.get('description', ''),
                  'diffLabel': row.get('difficulty', ''), 'time': row.get('durationLabel', ''),
                  'contentVersion': version}
        if kind == 'book':
            result.update(t=row['title'], author=row.get('author', ''), a=row.get('author', ''),
                          category=row.get('category', ''), c=row.get('category', ''))
        return result
    except (OSError, ValueError, KeyError, TypeError):
        # Existing releases without a manifest remain readable during migration.
        return {}

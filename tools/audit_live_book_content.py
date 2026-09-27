#!/usr/bin/env python3
"""Read-only audit of public book pages and free mini-program responses."""
import argparse
import csv
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


class ContentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.found = False
        self.text = []
        self.headings = []
        self.heading = None
        self.paragraphs = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.found and (tag == 'article' or
                (tag == 'div' and 'content' in attrs.get('class', '').split())):
            self.found = True
            self.root = tag
            self.depth = 1
        elif self.depth and tag == self.root:
            self.depth += 1
        if self.depth:
            if tag in ('h2', 'h3'):
                self.heading = []
            if tag == 'p':
                self.paragraphs += 1

    def handle_endtag(self, tag):
        if self.depth:
            if tag in ('h2', 'h3') and self.heading is not None:
                self.headings.append(''.join(self.heading).strip())
                self.heading = None
            if tag == self.root:
                self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.text.append(data)
            if self.heading is not None:
                self.heading.append(data)


def fetch(url):
    req = Request(url, headers={'User-Agent': 'Kangbo-Content-Audit/1.0'})
    with urlopen(req, timeout=25) as response:
        return response.read().decode('utf-8')


def inspect(base, n):
    for attempt in range(2):
        try:
            raw = fetch(f'{base}/book{n}.html')
            parser = ContentParser()
            parser.feed(raw)
            text = ''.join(parser.text)
            title = re.search(r'<h1[^>]*>(.*?)</h1>', raw, re.S | re.I)
            return {
                'id': n, 'title': re.sub('<[^>]+>', '', title[1]) if title else '',
                'content_found': parser.found, 'text_chars': len(re.sub(r'\s+', '', text)),
                'paragraphs': parser.paragraphs, 'headings': parser.headings,
                'legacy_template': '这门课不把' in text and '当作孤立的读书笔记' in text,
                'enhanced_template': '这一点决定了读者不能只停在摘录层面' in text,
                'source_links': len(re.findall(r'href=["\']https?://', raw)),
                'error': '',
            }
        except Exception as exc:
            if attempt == 0:
                time.sleep(1)
            else:
                return {'id': n, 'error': str(exc)}


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--base', default='https://kangboacademy.cn')
    cli.add_argument('--output', required=True)
    args = cli.parse_args()
    base = args.base.rstrip('/')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for row in pool.map(lambda n: inspect(base, n), range(1, 501)):
            rows.append(row)
            if len(rows) % 50 == 0:
                print(f'Inspected {len(rows)}/500 static pages', flush=True)
    api_rows = []
    # Free entries from each wave; do not bypass subscription access controls.
    for n in [1, 63, 93, 118, 148, 178, 208, 239, 269, 299, 329, 337, 364, 391, 419, 446, 473]:
        try:
            data = json.loads(fetch(f'{base}/api/book-course-content/book{n}.html'))
            content = data.get('content', '')
            api_rows.append({'id': n, 'locked': data.get('locked'),
                             'content_chars': len(content),
                             'full_document': bool(re.search(r'<(?:html|head|body)\b', content, re.I)),
                             'error': ''})
            (output / f'api-book{n}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as exc:
            api_rows.append({'id': n, 'error': str(exc)})
        time.sleep(2.1)
    valid = [r for r in rows if not r['error']]
    result = {
        'checked_at': datetime.now().astimezone().isoformat(), 'base': base,
        'scope': '500 public static pages; 17 free API entries. No content factual verification.',
        'summary': {
            'static_requested': 500, 'static_ok': len(valid),
            'content_found': sum(r['content_found'] for r in valid),
            'median_text_chars': statistics.median(r['text_chars'] for r in valid) if valid else 0,
            'legacy_template': sum(r['legacy_template'] for r in valid),
            'enhanced_template': sum(r['enhanced_template'] for r in valid),
            'api_checked': len(api_rows),
            'api_full_document': sum(r.get('full_document', False) for r in api_rows),
        }, 'pages': rows, 'api': api_rows,
    }
    (output / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'book-content-audit.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        fields = ['id', 'title', 'content_found', 'text_chars', 'paragraphs', 'legacy_template', 'enhanced_template', 'error']
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(result['summary'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

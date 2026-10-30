#!/usr/bin/env python3
"""Check actual image bytes and the image links in the published catalogue/TXT files."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'


class ImageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'img' and attrs.get('src'):
            self.links.append(attrs['src'])
        if tag in ('img', 'source') and attrs.get('srcset'):
            self.links.extend(part.strip().split()[0] for part in attrs['srcset'].split(',') if part.strip())


def main():
    manifest = json.loads((ROOT / 'asset-manifest.json').read_text())
    expected = {item['path']: item for item in manifest['files']}
    errors = []
    if len(expected) != len(manifest['files']):
        errors.append('Duplicate paths in asset-manifest.json')
    total = 0
    for path, record in expected.items():
        file = DOCS / path
        if file.resolve().parent != DOCS.resolve() and DOCS.resolve() not in file.resolve().parents:
            errors.append('Invalid asset path: ' + path)
            continue
        if not file.is_file():
            errors.append('Missing image: ' + path)
            continue
        data = file.read_bytes()
        total += len(data)
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            errors.append('Image bytes changed: ' + path)
        if record['format'] == 'WEBP':
            if file.suffix != '.webp' or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
                errors.append('Invalid WebP file: ' + path)
        elif record['format'] == 'AVIF':
            if file.suffix != '.avif' or data[4:8] != b'ftyp' or not any(brand in data[:64] for brand in (b'avif', b'avis')):
                errors.append('Invalid AVIF file: ' + path)
        else:
            errors.append('Unexpected public image format: ' + path)
    actual = {str(file.relative_to(DOCS)) for file in DOCS.rglob('*') if file.is_file() and file.suffix.lower() in ('.webp', '.avif', '.jpg', '.jpeg', '.png')}
    if actual != set(expected):
        errors.append('Unlisted or missing images: ' + repr(sorted(actual.symmetric_difference(expected))))
    if total >= 1_000_000_000:
        errors.append('Public images exceed the GitHub Pages size limit')
    for url, path in manifest['url_aliases'].items():
        if path not in expected:
            errors.append('Alias points to a missing image: ' + url)

    publishing = ROOT / 'publishing.json'
    public_base = json.loads(publishing.read_text())['public_base_url'] if publishing.is_file() else None
    base = urlsplit(public_base) if public_base else None
    checked_links = 0
    files = [DOCS / 'index.html'] + sorted((ROOT / 'clicksites').glob('*.txt')) + sorted((DOCS / 'preview').glob('*.html'))
    for file in files:
        source = file.read_text()
        parser = ImageLinks()
        parser.feed(source)
        if file.suffix == '.txt' and not all(tag in source.lower() for tag in ('<!doctype html>', '<html', '<head', '<body', '</html>')):
            errors.append('ClickSites file is not a complete HTML document: ' + file.name)
        for url in parser.links:
            parsed = urlsplit(url)
            if not parsed.scheme and not parsed.netloc:
                path = unquote(str((file.parent / parsed.path).relative_to(DOCS))) if file.is_relative_to(DOCS) else None
            elif base and parsed.netloc == base.netloc and parsed.path.startswith(base.path):
                path = unquote(parsed.path[len(base.path):])
            else:
                errors.append('Image is outside the published image library: ' + str(file.relative_to(ROOT)) + ' ' + url)
                continue
            checked_links += 1
            if path not in expected:
                errors.append('Broken image link: ' + str(file.relative_to(ROOT)) + ' ' + url)
        if file.parent.name == 'clicksites':
            for url in re.findall(r'https://(?:lead\.b-cdn\.net|cdn\.nyverden\.no|nyverden\.b-cdn\.net)[^\s\"\'<>\\)]+', source):
                if re.search(r'\.(?:png|jpe?g|webp|avif)(?:\?|$)', url, re.I):
                    errors.append('Old image host remains in ' + file.name + ': ' + url)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'OK: {len(expected)} image files, {total:,} bytes, {len(manifest["url_aliases"])} aliases, {checked_links} HTML image links.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

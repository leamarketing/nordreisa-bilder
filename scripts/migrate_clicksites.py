#!/usr/bin/env python3
"""Build complete ClickSites documents from the preserved published sources."""
from __future__ import annotations

import argparse
import html
import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = self.skip = 0
        self.parts = []
        self.h1 = []
        self.in_h1 = False

    def handle_starttag(self, tag, attrs):
        if tag in ('main', 'footer'):
            self.capture += 1
        if tag in ('script', 'style'):
            self.skip += 1
        if tag == 'h1':
            self.in_h1 = True

    def handle_endtag(self, tag):
        if tag in ('main', 'footer'):
            self.capture -= 1
        if tag in ('script', 'style'):
            self.skip -= 1
        if tag == 'h1':
            self.in_h1 = False

    def handle_data(self, data):
        if self.capture > 0 and self.skip == 0:
            self.parts.append(data)
        if self.in_h1:
            self.h1.append(data)

    def text(self):
        return ' '.join(' '.join(self.parts).split())


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag in ('a', 'form', 'input', 'select', 'textarea', 'option', 'button'):
            keep = {'href', 'action', 'method', 'onsubmit', 'onclick', 'id', 'name', 'type', 'required', 'checked', 'disabled', 'value', 'min', 'max', 'step', 'pattern', 'autocomplete'}
            self.items.append((tag, sorted((k, v) for k, v in attrs if k in keep)))


def visible(source):
    parsed = VisibleText()
    parsed.feed(source)
    return parsed


def controls(source):
    parsed = Controls()
    parsed.feed(source)
    return parsed.items


def complete_document(source, page_url):
    if re.search(r'<html\b', source, re.I):
        return source
    assert not re.search(r'</?(?:head|body)\b', source, re.I), 'Unexpected partial document wrapper'
    position = 0
    while position < len(source):
        remaining = source[position:]
        whitespace = re.match(r'\s+', remaining)
        if whitespace:
            position += whitespace.end()
            continue
        comment = re.match(r'<!--[\s\S]*?-->', remaining)
        if comment:
            position += comment.end()
            continue
        void = re.match(r'<(?:meta|link)\b[^>]*>', remaining, re.I)
        if void:
            position += void.end()
            continue
        paired = re.match(r'<(style|title)\b[^>]*>[\s\S]*?</\1\s*>', remaining, re.I)
        if paired:
            position += paired.end()
            continue
        structured = re.match(r'<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>[\s\S]*?</script\s*>', remaining, re.I)
        if structured:
            position += structured.end()
            continue
        break
    head, body = source[:position], source[position:]
    if not re.search(r'<meta\b[^>]*charset', head, re.I):
        head = '<meta charset="utf-8">\n' + head
    if not re.search(r'<meta\b[^>]*name=[\"\']viewport[\"\']', head, re.I):
        head += '\n<meta name="viewport" content="width=device-width,initial-scale=1">'
    if not re.search(r'<title\b', head, re.I):
        title = ' '.join(' '.join(visible(source).h1).split()) or 'Nordreisa PALT'
        head += '\n<title>' + html.escape(title) + ' | Nordreisa PALT</title>'
    if not re.search(r'<link\b[^>]*rel=[\"\']canonical[\"\']', head, re.I):
        head += '\n<link rel="canonical" href="' + html.escape(page_url, quote=True) + '">'
    return '<!DOCTYPE html>\n<html lang="en">\n<head>\n' + head + '\n</head>\n<body>\n' + body + '\n</body>\n</html>\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip('/') + '/'
    parsed_base = urlsplit(base)
    if parsed_base.scheme != 'https' or not parsed_base.netloc:
        parser.error('Use the verified HTTPS address of the published library')
    manifest = json.loads((ROOT / 'asset-manifest.json').read_text())
    aliases = {}
    for old, path in manifest['url_aliases'].items():
        new = base + quote(path, safe='/.-_~')
        aliases[old] = new
        aliases[unquote(old)] = new
    ordered = sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)

    def replace_urls(source):
        for old, new in ordered:
            source = source.replace(old, new)
        # Connection hints now refer to the published image origin.
        source = re.sub(r'(<link\b[^>]*rel=[\"\'](?:preconnect|dns-prefetch)[\"\'][^>]*href=[\"\'])https://(?:lead\.b-cdn\.net|cdn\.nyverden\.no|nyverden\.b-cdn\.net)/?([\"\'])', lambda match: match[1] + parsed_base.scheme + '://' + parsed_base.netloc + match[2], source, flags=re.I)
        return source

    out = ROOT / 'clicksites'
    preview = ROOT / 'docs' / 'preview'
    downloads = ROOT / 'docs' / 'sidefiler'
    for directory in (out, preview, downloads):
        directory.mkdir(exist_ok=True)
    validation = []
    documents = {}
    routes = {urlsplit(page['url']).path.rstrip('/') or '/': page['slug'] for page in manifest['pages']}
    for page in manifest['pages']:
        slug = page['slug']
        original = (ROOT / 'source' / 'original' / (slug + '.txt')).read_text()
        baseline = (ROOT / 'source' / 'prepared-p02.txt').read_text() if slug == 'p02-spa-sauna-waterpark' else original
        changed = replace_urls(baseline)
        document = complete_document(changed, page['url'])
        assert visible(original).text() == visible(document).text(), 'Visible project text changed: ' + slug
        assert controls(changed) == controls(document), 'Navigation or form changed: ' + slug
        # URL substitutions are the only changes made to executable scripts.
        expected_scripts = re.findall(r'<script\b[^>]*>[\s\S]*?</script\s*>', changed, re.I)
        actual_scripts = re.findall(r'<script\b[^>]*>[\s\S]*?</script\s*>', document, re.I)
        assert expected_scripts == actual_scripts, 'Script content/order changed: ' + slug
        for url in re.findall(r'https://(?:lead\.b-cdn\.net|cdn\.nyverden\.no|nyverden\.b-cdn\.net)[^\s\"\'<>\\)]+', document):
            assert not re.search(r'\.(?:png|jpe?g|webp|avif)(?:\?|$)', url, re.I), 'Unmapped image: ' + url
        (out / (slug + '.txt')).write_text(document)
        (downloads / (slug + '.txt')).write_text(document)
        documents[slug] = document
        shown = re.sub(r'<meta\b[^>]*name=[\"\']robots[\"\'][^>]*>', '', document, flags=re.I)
        shown = shown.replace('</head>', '<meta name="robots" content="noindex,nofollow">\n</head>', 1)

        # Prevent source SEO scripts from re-enabling indexing in the preview.
        shown = shown.replace('["name", "robots", "index, follow"]', '["name", "robots", "noindex,nofollow"]')

        def preview_link(match):
            value = html.unescape(match[2])
            address = urlsplit(value)
            if address.netloc in ('nordreisa.eu', 'www.nordreisa.eu') or (not address.netloc and value.startswith('/')):
                route = address.path.rstrip('/') or '/'
                if route in routes:
                    replacement = './' + routes[route] + '.html'
                    if address.fragment:
                        replacement += '#' + address.fragment
                    return match[1] + replacement + match[3]
                if not address.netloc:
                    return match[1] + 'https://nordreisa.eu' + value + match[3]
            return match[0]

        shown = re.sub(r'(<a\b[^>]*\bhref=[\"\'])([^\"\']+)([\"\'])', preview_link, shown, flags=re.I)
        (preview / (slug + '.html')).write_text(shown)
        validation.append({'page': page['url'], 'txt': slug + '.txt', 'visible_text_preserved': True, 'controls_preserved': True, 'scripts_preserved': True})
    instructions = '''NORDREISA – FERDIGE SIDEFILER MED GITHUB-BILDER

Bildene ligger nå i et eget Nordreisa-bibliotek på GitHub Pages.
Hver TXT-fil inneholder hele HTML-dokumentet for én side.

1. Åpne riktig side i ClickSites.
2. Ta en kopi av sidens eksisterende HTML.
3. Erstatt hele HTML-koden med innholdet i TXT-filen med samme sidenavn.
4. Lagre og publiser siden.
5. Kontroller den publiserte siden.

Begynn gjerne med p02-spa-sauna-waterpark.txt. Alle P02-bildene er allerede lagt inn i bildelageret.
forside.txt gjelder førstesiden. ap01–ap10 gjelder områdepakkene. p01–p25 gjelder prosjektsidene.
overview.txt, calculations.txt og why-nordreisa.txt er de tre øvrige sidene.

TXT-filene er klargjort. Dette betyr ikke at de er limt inn eller publisert på nordreisa.eu.
Selve bildeleveringen er flyttet; ClickSites-sidene må få de nye adressene ved publisering av disse filene.
'''
    (out / '00_START_HER.txt').write_text(instructions)
    package = ROOT / 'docs' / 'Nordreisa_CLICKSITES_GITHUB_2026-10-30.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(out.glob('*.txt')):
            archive.write(file, file.name)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
    catalogue = ROOT / 'docs' / 'index.html'
    index = catalogue.read_text()

    def catalogue_card(match):
        card = match[0]
        paths = re.findall(r'data-copy="([^"]+)"', card)
        pages = sorted(slug for slug, document in documents.items() if any(base + path in document for path in paths))
        key = html.unescape(re.search(r'data-search="([^"]+)"', card)[1]).split()[0]
        labels = [slug.split('-')[0].upper() if re.match(r'^(?:ap|p)\d+', slug) else slug for slug in pages]
        card = re.sub(r'data-search="[^"]+"', 'data-search="' + html.escape(key + ' ' + ' '.join(pages), quote=True) + '"', card, count=1)
        card = re.sub(r'<p class="pages">.*?</p>', '<p class="pages">' + html.escape(', '.join(labels) if labels else 'Prosjektbilde') + '</p>', card, count=1)
        return card

    index = re.sub(r'<article class="card"[\s\S]*?</article>', catalogue_card, index)
    index = index.replace("+' bildemotiv'", "+' bildegrupper'")
    page_links = []
    for page in sorted(manifest['pages'], key=lambda item: (item['slug'] != 'forside', item['slug'])):
        slug = page['slug']
        label = 'Førstesiden' if slug == 'forside' else slug.replace('-', ' ')
        page_links.append('<li><a href="preview/' + slug + '.html">Forhåndsvis: ' + html.escape(label) + '</a><a href="sidefiler/' + slug + '.txt" download>Hent TXT-fil</a></li>')
    section = '<section id="migration-downloads"><h2>Oppdater nettsidene</h2><p>Sidefilene er klare med de nye bildene. De må fortsatt legges inn og publiseres i ClickSites.</p><p><a href="Nordreisa_CLICKSITES_GITHUB_2026-10-30.zip" download>Last ned alle 39 sidefiler som TXT</a></p><details><summary>Forhåndsvis en side eller hent én TXT-fil</summary><ul>' + ''.join(page_links) + '</ul></details></section>'
    if 'id="migration-downloads"' in index:
        index = re.sub(r'<section id="migration-downloads">[\s\S]*?</section>', section, index)
    else:
        index = index.replace('<footer>', section + '<footer>', 1)
    catalogue.write_text(index)
    (ROOT / 'publishing.json').write_text(json.dumps({'public_base_url': base}, indent=2) + '\n')
    (ROOT / 'migration-validation.json').write_text(json.dumps(validation, indent=2) + '\n')
    print(json.dumps({'pages': len(validation), 'public_base_url': base, 'download': str(package), 'zip_bytes': package.stat().st_size}))


if __name__ == '__main__':
    main()

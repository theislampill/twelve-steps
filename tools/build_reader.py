#!/usr/bin/env python3
"""Build the offline reader from Markdown while preserving the supplied design.

Usage: python tools/build_reader.py [--output _site]
SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Tag
import mistune

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    'README.md', 'THESIS.md', 'ISLAMIC_APPLICATION.md', 'OBJECTIONS.md',
    'APPENDIX.md', 'NOTICE.md', 'CONTRIBUTING.md', 'CHANGELOG.md',
)
GROUPS = (
    ('Read the argument', (
        ('README.md', 'Start here'), ('THESIS.md', 'The essay'),
        ('ISLAMIC_APPLICATION.md', 'The Way of the Messengers'),
        ('OBJECTIONS.md', 'Objections and replies'))),
    ('Further detail', (('APPENDIX.md', 'Notes on grounds and evidence'),)),
    ('About this edition', (
        ('NOTICE.md', 'Scope, sources and rights'),
        ('CONTRIBUTING.md', 'Contributing'), ('CHANGELOG.md', 'Changelog'))),
)
SITE_URL = 'https://theislampill.github.io/twelve-steps/'


def slug(text: str) -> str:
    """The existing reader's Unicode-aware, GitHub-style heading convention."""
    return re.sub(r'\s', '-', re.sub(r'[^\w\s-]', '', text.strip().lower()))


def document_id(name: str) -> str:
    return 'doc-' + Path(name).stem.lower().replace('_', '-')


def render_document(path: Path) -> Tag:
    source = path.read_text(encoding='utf-8')
    md = mistune.create_markdown(escape=False, plugins=['table', 'footnotes', 'strikethrough'])
    rendered, state = md.parse(source)
    soup = BeautifulSoup(rendered, 'html.parser')
    prefix = document_id(path.name)
    note_keys = {i: slug(key) for i, key in enumerate(state.env.get('footnotes', []), 1)}
    counts: Counter[int] = Counter()
    footnotes = soup.select_one('section.footnotes')

    for ref in soup.select('sup.footnote-ref'):
        number = int(ref.a.get_text())
        counts[number] += 1
        key = note_keys[number]
        ref['id'] = f'{prefix}-ref-{key}-{counts[number]}'
        ref.a['href'] = f'#{prefix}-note-{key}'
        ref.a['role'] = 'doc-noteref'
        ref.a['aria-label'] = f'Note {number}'

    if footnotes:
        footnotes['role'] = 'doc-endnotes'
        footnotes['aria-label'] = 'Notes'
        title = soup.new_tag('h3')
        title.string = 'Notes'
        footnotes.insert(0, title)
        for item in footnotes.select('ol > li[id^="fn-"]'):
            number = int(item['id'][3:])
            key = note_keys[number]
            item['id'] = f'{prefix}-note-{key}'
            for old in item.select('a.footnote'):
                old.decompose()
            for occurrence in range(1, counts[number] + 1):
                link = soup.new_tag('a', href=f'#{prefix}-ref-{key}-{occurrence}')
                link['class'] = ['footnote-back']
                link['role'] = 'doc-backlink'
                link['aria-label'] = f'Return to note {number}, reference {occurrence}'
                link.string = '↩' if counts[number] == 1 else f'↩{occurrence}'
                item.append(' ')
                item.append(link)

    seen: Counter[str] = Counter()
    title_seen = False
    for heading in soup.find_all(re.compile(r'^h[1-6]$')):
        if heading.find_parent('section', class_='footnotes'):
            continue
        level = int(heading.name[1])
        key = slug(heading.get_text())
        suffix = f'-{seen[key]}' if seen[key] else ''
        seen[key] += 1
        if level == 1 and not title_seen:
            heading.name = 'h1' if path.name == 'README.md' else 'h2'
            heading['class'] = ['doc-title']
            title_seen = True
        else:
            heading.name = f'h{min(level + 1, 6)}'
            heading['id'] = f'{prefix}--{key}{suffix}'
            heading['class'] = ['doc-section' if level == 2 else 'doc-subsection']
    if not title_seen:
        raise ValueError(f'{path.name}: missing document title')

    for link in soup.find_all('a', href=True):
        href = link['href']
        parts = urlsplit(href)
        if href == SITE_URL:
            link['href'] = '#doc-readme'
        elif not parts.scheme and not parts.netloc:
            name = unquote(parts.path).removeprefix('./')
            fragment = unquote(parts.fragment)
            if name in DOCUMENTS:
                link['href'] = '#' + document_id(name) + ('--' + fragment if fragment else '')
            elif name == 'LICENSE':
                link['href'] = '#licence'
            elif name == 'PROVENANCE.json':
                link['href'] = '#provenance'
            elif name == 'index.html':
                link['href'] = '#' + (fragment or 'doc-readme')
            elif not name and fragment and not fragment.startswith(('doc-', 'fn', 'licence', 'provenance')):
                link['href'] = f'#{prefix}--{fragment}'

    for table in soup.select('table'):
        labels = [th.get_text(' ', strip=True) for th in table.select('thead th')]
        for row in table.select('tbody tr'):
            for i, cell in enumerate(row.find_all(['td', 'th'], recursive=False)):
                if i < len(labels):
                    cell['data-label'] = labels[i]
        wrapper = soup.new_tag('div')
        wrapper['class'] = ['table-scroll']
        wrapper['tabindex'] = '0'
        wrapper['role'] = 'region'
        wrapper['aria-label'] = 'Scrollable table'
        table.wrap(wrapper)
    for pre in soup.select('pre'):
        pre['tabindex'] = '0'
    if soup.select('script, iframe, object, embed, style, link'):
        raise ValueError(f'{path.name}: executable or external markup is not allowed in the prose')
    article = soup.new_tag('article', id=prefix)
    article['data-source'] = path.name
    article['data-source-sha256'] = sha256(path.read_bytes()).hexdigest()
    for child in list(soup.contents):
        article.append(child.extract())
    return article


def navigation(articles: dict[str, Tag]) -> str:
    groups = []
    for label, entries in GROUPS:
        items = []
        for name, title in entries:
            nested = ''
            if name == 'THESIS.md':
                nested = '<ul>' + ''.join(
                    f'<li><a href="#{escape(h["id"], quote=True)}">{escape(h.get_text())}</a></li>'
                    for h in articles[name].select('.doc-section')
                ) + '</ul>'
            items.append(f'<li><a class="doc-link" href="#{document_id(name)}">{escape(title)}</a>{nested}</li>')
        groups.append(f'<p class="nav-label">{escape(label)}</p><ul>{"".join(items)}</ul>')
    return ''.join(groups)


def validate(html: str) -> None:
    soup = BeautifulSoup(html, 'html.parser')
    ids = [t['id'] for t in soup.find_all(id=True)]
    duplicate = [key for key, count in Counter(ids).items() if count > 1]
    if duplicate:
        raise ValueError('Duplicate HTML IDs: ' + ', '.join(duplicate))
    known = set(ids)
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('#') and unquote(href[1:]) not in known:
            raise ValueError(f'Broken reader target: {href}')
        parts = urlsplit(href)
        if parts.scheme and parts.scheme not in ('https', 'http', 'mailto'):
            raise ValueError(f'Unsupported link scheme: {parts.scheme}')
        if not parts.scheme and not parts.netloc and parts.path:
            raise ValueError(f'Unmapped local reader link: {href}')
    if len(soup.select('h1')) != 1:
        raise ValueError('The reader must have exactly one h1')
    if soup.select('script[src],link[rel="stylesheet"],iframe,img'):
        raise ValueError('The offline reader must not require external assets')


def build(root: Path = ROOT) -> str:
    metadata = json.loads((root/'PROVENANCE.json').read_text(encoding='utf-8'))
    published = date.fromisoformat(metadata['date'])
    months = ('January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December')
    display_date = f'{published.day} {months[published.month-1]} {published.year}'
    articles = {name: render_document(root/name) for name in DOCUMENTS}
    sections = ['<noscript><p class="no-js-note">All chapters are available below. JavaScript adds convenient navigation and print controls.</p></noscript>']
    for name, article in articles.items():
        content = str(article)
        if name == 'APPENDIX.md':
            content = (f'<details class="reading-branch" id="branch-{document_id(name)}" open="">'
                       '<summary>Notes on grounds and evidence</summary>' + content + '</details>')
        sections.append(content)
    for filename, identifier, title in (
        ('LICENSE', 'licence', 'Licence'), ('PROVENANCE.json', 'provenance', 'Source identities')):
        text = (root/filename).read_text(encoding='utf-8')
        sections.append(f'<details class="reading-branch aux" id="{identifier}" open=""><summary>{title}</summary><pre tabindex="0">{escape(text, quote=False)}</pre></details>')
    template = (root/'site/reader.html').read_text(encoding='utf-8')
    replacements = {'VERSION': escape(str(metadata['version']), quote=True),
                    'DATE': escape(display_date), 'NAVIGATION': navigation(articles),
                    'CONTENT': ''.join(sections)}
    for key in replacements:
        if '{{'+key+'}}' not in template:
            raise ValueError(f'Missing template slot: {key}')
    # One pass: prose containing braces is not evaluated or reinterpreted.
    html = re.sub(r'\{\{(VERSION|DATE|NAVIGATION|CONTENT)\}\}',
                  lambda match: replacements[match.group(1)], template)
    validate(html)
    return html


def write_site(root: Path, output: Path) -> None:
    if output.resolve() == root.resolve():
        raise ValueError('Use a dedicated output directory, not the repository root')
    html = build(root)  # Fail before writing a partial reader.
    output.mkdir(parents=True, exist_ok=True)
    (output/'index.html').write_text(html, encoding='utf-8', newline='\n')
    (output/'.nojekyll').write_text('', encoding='utf-8')
    names = (*DOCUMENTS, 'LICENSE', 'PROVENANCE.json')
    for name in names:
        shutil.copyfile(root/name, output/name)
    files = [output/name for name in ('index.html', '.nojekyll', *names)]
    (output/'SHA256SUMS').write_text(''.join(
        f'{sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
        for path in sorted(files)), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'_site')
    args = parser.parse_args()
    try:
        write_site(ROOT, args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'Reader build failed: {exc}\n')
    print(f'Built {args.output / "index.html"} from {len(DOCUMENTS)} Markdown documents')


if __name__ == '__main__':
    main()

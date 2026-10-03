"""Reader regressions. These check publishing mechanics, not the essay's claims."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


class ReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'tools/build_reader.py'
        if not path.exists():
            return
        spec = importlib.util.spec_from_file_location('build_reader', path)
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def setUp(self):
        self.assertTrue((ROOT / 'tools/build_reader.py').exists(), 'The Markdown reader builder is missing')

    def document(self, text):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'THESIS.md'
            path.write_text(text, encoding='utf-8')
            return self.builder.render_document(path)

    def test_document_headings_keep_reader_classes(self):
        doc = self.document('# Title\n\n## Two\n\n### Three\n')
        self.assertEqual(doc.h2['class'], ['doc-title'])
        self.assertEqual(doc.h3['id'], 'doc-thesis--two')
        self.assertEqual(doc.h3['class'], ['doc-section'])
        self.assertEqual(doc.h4['class'], ['doc-subsection'])

    def test_duplicate_headings_have_unique_ids(self):
        doc = self.document('# T\n\n## Repeat\n\n## Repeat\n')
        self.assertEqual([h['id'] for h in doc.select('h3')], ['doc-thesis--repeat', 'doc-thesis--repeat-1'])

    def test_repeated_notes_have_individual_return_links(self):
        doc = self.document('# T\n\nFirst.[^one] Second.[^one]\n\n[^one]: Note.\n')
        refs = doc.select('.footnote-ref')
        self.assertEqual([r['id'] for r in refs], ['doc-thesis-ref-one-1', 'doc-thesis-ref-one-2'])
        self.assertEqual([a['href'] for a in doc.select('.footnote-back')], ['#'+r['id'] for r in refs])
        self.assertEqual(len(doc.select('section.footnotes li')), 1)

    def test_multiline_notes_are_preserved(self):
        doc = self.document('# T\n\nText.[^a]\n\n[^a]: First paragraph.\n\n    Second paragraph.\n')
        note = doc.select_one('.footnotes')
        self.assertIn('First paragraph.', note.get_text())
        self.assertIn('Second paragraph.', note.get_text())

    def test_tables_keep_mobile_labels(self):
        doc = self.document('# T\n\n| One | Two |\n| --- | --- |\n| A | B |\n')
        self.assertEqual([td['data-label'] for td in doc.select('td')], ['One', 'Two'])
        self.assertIsNotNone(doc.select_one('.table-scroll[tabindex="0"]'))

    def test_cross_document_links_are_rewritten(self):
        doc = self.document('# T\n\n[Elsewhere](OBJECTIONS.md#some-heading) [Rights](LICENSE)\n')
        self.assertEqual([a['href'] for a in doc.select('a')], ['#doc-objections--some-heading', '#licence'])

    def test_output_contains_all_eight_sources(self):
        soup = BeautifulSoup(self.builder.build(ROOT), 'html.parser')
        self.assertEqual([a['data-source'] for a in soup.select('article')], list(self.builder.DOCUMENTS))
        self.assertEqual(len(soup.select('h1')), 1)
        self.assertTrue(all(a.has_attr('data-source-sha256') for a in soup.select('article')))

    def test_the_delivered_css_and_javascript_are_unchanged(self):
        import hashlib
        soup = BeautifulSoup(self.builder.build(ROOT), 'html.parser')
        self.assertEqual(hashlib.sha256(soup.style.string.encode()).hexdigest(), 'f64fce5261c8917b4b069bba2252ccc90222f5d002b24320efe010b2d7313de2')
        self.assertEqual(hashlib.sha256(soup.script.string.encode()).hexdigest(), 'bb932f61dfb5fbb2df545aa9bcc91aa178a6396b34b049d3cfc162c993f73f6f')

    def test_build_is_deterministic_and_leaves_sources_untouched(self):
        before = {name: (ROOT/name).read_bytes() for name in self.builder.DOCUMENTS}
        self.assertEqual(self.builder.build(ROOT), self.builder.build(ROOT))
        self.assertEqual(before, {name: (ROOT/name).read_bytes() for name in before})

    def test_markdown_edits_change_reader_and_navigation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (*self.builder.DOCUMENTS, 'PROVENANCE.json', 'LICENSE'):
                shutil.copyfile(ROOT/name, root/name)
            shutil.copytree(ROOT/'site', root/'site')
            with (root/'THESIS.md').open('a', encoding='utf-8') as f:
                f.write('\n## New heading for the build test\n\nA newly edited paragraph.\n')
            soup = BeautifulSoup(self.builder.build(root), 'html.parser')
            self.assertIsNotNone(soup.select_one('#doc-thesis--new-heading-for-the-build-test'))
            self.assertIsNotNone(soup.select_one('nav a[href="#doc-thesis--new-heading-for-the-build-test"]'))
            self.assertIn('A newly edited paragraph.', soup.get_text())

    def test_broken_anchor_is_rejected(self):
        html = self.builder.build(ROOT)
        bad = html.replace('href="#doc-thesis"', 'href="#missing-target"', 1)
        with self.assertRaisesRegex(ValueError, 'missing-target'):
            self.builder.validate(bad)

    def test_duplicate_id_is_rejected(self):
        html = self.builder.build(ROOT).replace('</main>', '<span id="main"></span></main>')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.builder.validate(html)

    def test_display_requires_no_external_resources(self):
        soup = BeautifulSoup(self.builder.build(ROOT), 'html.parser')
        self.assertEqual(soup.select('script[src],link[rel="stylesheet"],iframe,img'), [])
        self.assertTrue(all(d.has_attr('open') for d in soup.select('details.reading-branch')))
        self.assertTrue(soup.select_one('#print-reader').has_attr('hidden'))

    def test_artifact_includes_current_checksums_and_source_files(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'public'
            self.builder.write_site(ROOT, out)
            for line in (out/'SHA256SUMS').read_text().splitlines():
                digest, name = line.split('  ', 1)
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(), digest)
            self.assertTrue((out/'index.html').is_file())
            self.assertTrue((out/'.nojekyll').is_file())


if __name__ == '__main__':
    unittest.main()

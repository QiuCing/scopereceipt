from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scopereceipt.cli import main
from scopereceipt.core import ScopeError, read, record_event, report, scan


class ScopeReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.docs = self.root / 'docs'
        self.docs.mkdir()
        self.state = self.root / '.scopereceipt'
        (self.docs / 'a.md').write_text('one\ntwo\nthree\n', encoding='utf-8')
        (self.docs / 'b.txt').write_text('hello\nworld\n', encoding='utf-8')

    def _deliver(self, file, start=1, end=None):
        content, event = read(self.state, file, start, end)
        record_event(self.state, event)
        return content

    def test_partial_then_complete(self):
        manifest = scan(self.docs, self.state)
        self.assertEqual(len(manifest['files']), 2)
        self.assertEqual(report(self.state)['status'], 'INCOMPLETE')
        self.assertIn('one', self._deliver('a.md', 1, 2))
        self.assertEqual(report(self.state)['covered_units'], 2)
        self.assertEqual(report(self.state)['covered_files'], 0)
        self._deliver('a.md', 3, 3)
        self._deliver('b.txt', 1, 2)
        result = report(self.state)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual((result['covered_units'], result['total_units']), (5, 5))

    def test_repeated_reads_do_not_double_count(self):
        scan(self.docs, self.state)
        self._deliver('a.md', 1, 2)
        self._deliver('a.md', 1, 2)
        self.assertEqual(report(self.state)['covered_units'], 2)

    def test_source_mutation_invalidates_receipts(self):
        scan(self.docs, self.state)
        self._deliver('a.md', 1, 3)
        self.assertEqual(report(self.state)['covered_files'], 1)
        (self.docs / 'a.md').write_text('replaced\n', encoding='utf-8')
        self.assertTrue(next(f for f in report(self.state)['files'] if f['path'] == 'a.md')['changed'])
        self.assertEqual(report(self.state)['covered_files'], 0)
        with self.assertRaises(ScopeError):
            self._deliver('a.md', 1, 1)

    def test_unsupported_prevents_complete(self):
        (self.docs / 'picture.png').write_bytes(b'PNG')
        scan(self.docs, self.state)
        self._deliver('a.md', 1, 3)
        self._deliver('b.txt', 1, 2)
        self.assertEqual(report(self.state)['status'], 'INCOMPLETE')

    def test_zip_member_read_without_extraction(self):
        archive = self.root / 'bundle.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('nested/notes.md', 'alpha\nbeta\n')
        scan(archive, self.state)
        self.assertIn('alpha', self._deliver('nested/notes.md', 1, 2))
        self.assertEqual(report(self.state)['status'], 'COMPLETE')
        self.assertFalse((self.root / 'nested').exists())

    def test_zip_traversal_rejected(self):
        archive = self.root / 'unsafe.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../not-ok.md', 'no')
        with self.assertRaises(ScopeError):
            scan(archive, self.state)

    def test_empty_pdf_page_remains_unverified(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('optional PyMuPDF not installed')
        doc = fitz.open()
        doc.new_page()
        pdf = self.docs / 'blank.pdf'
        pdf.write_bytes(doc.tobytes())
        doc.close()
        scan(self.docs, self.state)
        content = self._deliver('blank.pdf', 1, 1)
        self.assertIn('visual/OCR', content)
        file = next(f for f in report(self.state)['files'] if f['path'] == 'blank.pdf')
        self.assertEqual(file['visited_units'], 0)
        self.assertFalse(file['complete'])

    def test_pdf_text_page_counts_as_accessed_not_understood(self):
        try:
            import fitz
        except ImportError:
            self.skipTest('optional PyMuPDF not installed')
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), 'Synthetic legal text')
        pdf = self.docs / 'sample.pdf'
        pdf.write_bytes(doc.tobytes())
        doc.close()
        scan(self.docs, self.state)
        content = self._deliver('sample.pdf', 1, 1)
        self.assertIn('Synthetic legal text', content)
        file = next(f for f in report(self.state)['files'] if f['path'] == 'sample.pdf')
        self.assertEqual(file['visited_units'], 1)

    def test_cli_strict_exit_codes(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--state', str(self.state), 'scan', str(self.docs)]), 0)
            self.assertEqual(main(['--state', str(self.state), 'report', '--strict']), 1)
            self.assertEqual(main(['--state', str(self.state), 'read', 'a.md', '--start', '1', '--end', '3']), 0)
            self.assertEqual(main(['--state', str(self.state), 'read', 'b.txt', '--start', '1', '--end', '2']), 0)
            self.assertEqual(main(['--state', str(self.state), 'report', '--strict']), 0)

    def test_refuses_uninventoried_file(self):
        scan(self.docs, self.state)
        with self.assertRaises(ScopeError):
            self._deliver('secret.txt', 1, 1)


if __name__ == '__main__':
    unittest.main()

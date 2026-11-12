import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scopereceipt.cli import main
from scopereceipt.core import ScopeError, read, record_event, report, scan


class CoverageRegressions(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.docs = self.root / 'docs'
        self.docs.mkdir()
        self.file = self.docs / 'a.md'
        self.file.write_text('one\ntwo\nthree\nfour\n', encoding='utf-8')
        self.state = self.root / 'receipts'
        scan(self.docs, self.state)

    def deliver(self, start=1, end=4):
        _, event = read(self.state, 'a.md', start, end)
        record_event(self.state, event)

    def test_new_file_blocks_complete(self):
        self.deliver()
        (self.docs / 'new.txt').write_text('new', encoding='utf-8')
        result = report(self.state)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['added_files'], ['new.txt'])

    def test_deleted_file_blocks_complete(self):
        self.deliver()
        self.file.unlink()
        result = report(self.state)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['removed_files'], ['a.md'])
        self.assertEqual(result['covered_units'], 0)

    def test_missing_ranges_and_overlaps(self):
        self.deliver(2, 2)
        self.deliver(2, 3)
        result = report(self.state)
        self.assertEqual(result['covered_units'], 2)
        self.assertEqual(result['files'][0]['missing_ranges'], [[1, 1], [4, 4]])

    def test_rescan_rejects_inflight_receipt(self):
        _, event = read(self.state, 'a.md')
        scan(self.docs, self.state)
        with self.assertRaises(ScopeError):
            record_event(self.state, event)
        self.assertEqual(report(self.state)['covered_units'], 0)

    def test_old_event_cannot_cross_run(self):
        self.deliver()
        old = (self.state / 'events.jsonl').read_text(encoding='utf-8')
        scan(self.docs, self.state)
        (self.state / 'events.jsonl').write_text(old, encoding='utf-8')
        self.assertEqual(report(self.state)['covered_units'], 0)

    def test_oversized_read_records_nothing(self):
        self.file.write_text('x' * 102401, encoding='utf-8')
        scan(self.docs, self.state)
        with self.assertRaises(ScopeError):
            read(self.state, 'a.md')
        self.assertEqual(report(self.state)['covered_units'], 0)

    def test_cli_failed_flush_records_nothing(self):
        class BrokenOutput(io.StringIO):
            def flush(self):
                raise BrokenPipeError('consumer closed output')
        with patch('sys.stdout', BrokenOutput()), patch('sys.stderr', io.StringIO()):
            self.assertEqual(main(['--state', str(self.state), 'read', 'a.md']), 2)
        self.assertEqual(report(self.state)['covered_units'], 0)

    def test_archive_addition_blocks_complete(self):
        archive = self.root / 'docs.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('a.md', 'one\n')
        scan(archive, self.state)
        self.deliver(1, 1)
        with zipfile.ZipFile(archive, 'a') as z:
            z.writestr('b.md', 'two\n')
        self.assertEqual(report(self.state)['status'], 'INCOMPLETE')

    def test_archive_alias_is_rejected(self):
        archive = self.root / 'alias.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('folder//a.md', 'one\n')
        with self.assertRaises(ScopeError):
            scan(archive, self.state)


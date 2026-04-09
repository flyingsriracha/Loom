from __future__ import annotations

import unittest

from migration.curated_scanner import CuratedSourceScanner
from migration.sources import curated_sources


class CuratedScannerTests(unittest.TestCase):
    def test_curated_sources_exist(self) -> None:
        asam, autosar = curated_sources()
        self.assertTrue(asam.sqlite_path.exists())
        self.assertTrue(autosar.sqlite_path.exists())

    def test_scanner_reads_table_profiles(self) -> None:
        scanner = CuratedSourceScanner()
        asam, _ = curated_sources()

        scan = scanner.scan(asam)

        self.assertEqual(scan.source_system, 'ASAMKnowledgeDB')
        self.assertGreater(len(scan.table_profiles), 0)
        self.assertGreater(scan.total_rows, 0)


if __name__ == '__main__':
    unittest.main()

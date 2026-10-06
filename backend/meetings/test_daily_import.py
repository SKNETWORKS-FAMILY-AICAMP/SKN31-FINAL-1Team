from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from meetings.daily_import import fingerprint, read_folder
from meetings.management.commands.watch_daily_meetings import dated_folders, signature


class DailyImportTests(SimpleTestCase):
    def test_date_folders_and_content_fingerprint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            day = root / '20261006'
            day.mkdir()
            (day / '개발_회의록.txt').write_text('첫 결정', encoding='utf-8')
            self.assertEqual(dated_folders(root), [day])
            _, first = read_folder(day)
            snapshot = signature(day)
            (day / '개발_회의록.txt').write_text('변경된 결정', encoding='utf-8')
            _, second = read_folder(day)
            self.assertNotEqual(fingerprint(first), fingerprint(second))
            self.assertNotEqual(snapshot, signature(day))

    def test_empty_and_unsupported_files_stop_import(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / '20261006'
            folder.mkdir()
            (folder / '개발_회의록.txt').write_text('', encoding='utf-8')
            with self.assertRaises(ValueError):
                read_folder(folder)
            (folder / '개발_회의록.txt').write_text('회의', encoding='utf-8')
            (folder / 'image.png').write_bytes(b'x')
            with self.assertRaises(ValueError):
                read_folder(folder)

    def test_invalid_root_is_rejected(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError):
                dated_folders(Path(tmp) / 'missing')

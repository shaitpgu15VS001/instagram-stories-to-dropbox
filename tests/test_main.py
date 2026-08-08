import os
import tempfile
import unittest

from openpyxl import Workbook

from src.main import _normalize_username, _normalize_row_name, _parse_xlsx


class TestMainParsing(unittest.TestCase):

    def test_normalize_username_from_url(self):
        self.assertEqual(_normalize_username("https://instagram.com/ExampleUser/"), "exampleuser")
        self.assertEqual(_normalize_username("www.instagram.com/ExampleUser"), "exampleuser")
        self.assertEqual(_normalize_username("instagram.com/ExampleUser"), "exampleuser")

    def test_normalize_row_name_preserves_display_name(self):
        row = ["https://instagram.com/ExampleUser/", "Custom Folder"]
        username, display_name = _normalize_row_name(row)
        self.assertEqual(username, "exampleuser")
        self.assertEqual(display_name, "Custom Folder")

    def test_parse_xlsx_preserves_custom_folder_name(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["username", "folder_name"])
        ws.append(["https://instagram.com/ExampleUser/", "My Custom Folder"])

        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb.save(path)
            entries, stats = _parse_xlsx(path)
            self.assertEqual(entries, [("My Custom Folder", "exampleuser")])
            self.assertEqual(stats["valid_records"], 1)
            self.assertEqual(stats["duplicate_count"], 0)
            self.assertEqual(stats["invalid_records"], 0)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()

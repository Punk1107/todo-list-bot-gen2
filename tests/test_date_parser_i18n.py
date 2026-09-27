import unittest
from datetime import datetime
from utils.helpers import parse_deadline


class TestDateParserI18n(unittest.TestCase):
    """Test natural date keywords across all 9 supported languages."""

    def setUp(self):
        self.tz = "Asia/Bangkok"

    def test_relative_days_all_languages(self):
        cases = [
            # English
            ("today 18:00", 18, 0),
            ("tomorrow 12:30", 12, 30),
            ("day after tomorrow 09:15", 9, 15),
            # Thai
            ("วันนี้ 18:00", 18, 0),
            ("พรุ่งนี้ 12:30", 12, 30),
            ("มะรืนนี้ 09:15", 9, 15),
            # German
            ("heute 18:00", 18, 0),
            ("morgen 12:30", 12, 30),
            ("übermorgen 09:15", 9, 15),
            ("ubermorgen 09:15", 9, 15),
            # Spanish
            ("hoy 18:00", 18, 0),
            ("mañana 12:30", 12, 30),
            ("manana 12:30", 12, 30),
            ("pasado mañana 09:15", 9, 15),
            ("pasado manana 09:15", 9, 15),
            # French
            ("aujourd'hui 18:00", 18, 0),
            ("demain 12:30", 12, 30),
            ("après-demain 09:15", 9, 15),
            ("apres-demain 09:15", 9, 15),
            # Japanese
            ("今日 18:00", 18, 0),
            ("明日 12:30", 12, 30),
            ("明後日 09:15", 9, 15),
            # Korean
            ("오늘 18:00", 18, 0),
            ("내일 12:30", 12, 30),
            ("모레 09:15", 9, 15),
            # Chinese
            ("今天 18:00", 18, 0),
            ("明天 12:30", 12, 30),
            ("后天 09:15", 9, 15),
            # Russian
            ("сегодня 18:00", 18, 0),
            ("завтра 12:30", 12, 30),
            ("послезавтра 09:15", 9, 15),
        ]

        for text, expected_h, expected_m in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for '{text}'")
                self.assertIsInstance(res, datetime)

    def test_weekdays_all_languages(self):
        weekday_cases = [
            "monday 15:00", "tuesday 15:00", "wednesday 15:00",
            "วันจันทร์ 15:00", "วันอังคาร 15:00", "วันพุธ 15:00",
            "montag 15:00", "dienstag 15:00", "mittwoch 15:00",
            "lunes 15:00", "martes 15:00", "miércoles 15:00",
            "lundi 15:00", "mardi 15:00", "mercredi 15:00",
            "月曜日 15:00", "火曜日 15:00", "水曜日 15:00",
            "월요일 15:00", "화요일 15:00", "수요일 15:00",
            "星期一 15:00", "周二 15:00", "星期三 15:00",
            "понедельник 15:00", "вторник 15:00", "среда 15:00",
        ]
        for text in weekday_cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for weekday '{text}'")

    def test_unspaced_relative_days_asian(self):
        """Test Asian keywords immediately adjacent to time digits without space."""
        import pytz
        tz = pytz.timezone(self.tz)
        cases = [
            ("พรุ่งนี้18:00", 18, 0),
            ("วันนี้08:30", 8, 30),
            ("มะรืนนี้09:15", 9, 15),
            ("明日12:30", 12, 30),
            ("今日18:00", 18, 0),
            ("明後日09:15", 9, 15),
            ("明天12:30", 12, 30),
            ("今天18:00", 18, 0),
            ("后天09:15", 9, 15),
            ("내일12:30", 12, 30),
            ("오늘18:00", 18, 0),
            ("모레09:15", 9, 15),
        ]
        for text, exp_h, exp_m in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for '{text}'")
                local_dt = res.astimezone(tz)
                self.assertEqual(local_dt.hour, exp_h)
                self.assertEqual(local_dt.minute, exp_m)

    def test_unspaced_weekdays_asian(self):
        """Test Asian weekday keywords immediately adjacent to time digits."""
        cases = [
            "วันจันทร์15:00", "วันอังคาร15:00",
            "月曜日15:00", "火曜日15:00",
            "星期一15:00", "周二15:00",
            "월요일15:00", "화요일15:00",
        ]
        for text in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for unspaced weekday '{text}'")

    def test_thai_dot_time_and_suffix(self):
        """Test Thai dot separator (18.00) and optional น. / น suffix."""
        import pytz
        tz = pytz.timezone(self.tz)
        cases = [
            ("วันนี้ 18.00", 18, 0),
            ("วันนี้ 18.00น.", 18, 0),
            ("วันนี้ 18.00น", 18, 0),
            ("วันนี้ 18:00น.", 18, 0),
            ("พรุ่งนี้ 08.30น.", 8, 30),
            ("พรุ่งนี้18.00น.", 18, 0),
            ("พรุ่งนี้18.00", 18, 0),
        ]
        for text, exp_h, exp_m in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for Thai time '{text}'")
                local_dt = res.astimezone(tz)
                self.assertEqual(local_dt.hour, exp_h)
                self.assertEqual(local_dt.minute, exp_m)

    def test_thai_buddhist_era_conversion(self):
        """Test Thai Buddhist Era (BE >= 2400) automatically converted to CE."""
        import pytz
        tz = pytz.timezone(self.tz)
        cases = [
            ("25/12/2569 18:00", 2026, 12, 25, 18, 0),
            ("25-12-2569 18:00", 2026, 12, 25, 18, 0),
            ("25/12/2569", 2026, 12, 25, 23, 59),
        ]
        for text, exp_y, exp_m, exp_d, exp_h, exp_min in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for BE date '{text}'")
                local_dt = res.astimezone(tz)
                self.assertEqual(local_dt.year, exp_y)
                self.assertEqual(local_dt.month, exp_m)
                self.assertEqual(local_dt.day, exp_d)
                self.assertEqual(local_dt.hour, exp_h)
                self.assertEqual(local_dt.minute, exp_min)

    def test_european_dot_date_formats(self):
        """Test European dot date formats (German, Russian)."""
        import pytz
        tz = pytz.timezone(self.tz)
        cases = [
            ("25.12.2026 18:00", 2026, 12, 25, 18, 0),
            ("25.12.2026", 2026, 12, 25, 23, 59),
            ("25.12 18:00", None, 12, 25, 18, 0),
            ("25.12", None, 12, 25, 23, 59),
        ]
        for text, exp_y, exp_m, exp_d, exp_h, exp_min in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for European date '{text}'")
                local_dt = res.astimezone(tz)
                if exp_y is not None:
                    self.assertEqual(local_dt.year, exp_y)
                self.assertEqual(local_dt.month, exp_m)
                self.assertEqual(local_dt.day, exp_d)
                self.assertEqual(local_dt.hour, exp_h)
                self.assertEqual(local_dt.minute, exp_min)

    def test_east_asian_formats(self):
        """Test East Asian year-first slash, dot, and Kanji/Hanzi formats."""
        import pytz
        tz = pytz.timezone(self.tz)
        cases = [
            ("2026/09/27 15:30", 2026, 9, 27, 15, 30),
            ("2026/09/27", 2026, 9, 27, 23, 59),
            ("2026.09.27 15:30", 2026, 9, 27, 15, 30),
            ("2026.09.27", 2026, 9, 27, 23, 59),
            ("2026年9月27日 15:30", 2026, 9, 27, 15, 30),
            ("2026年09月27日", 2026, 9, 27, 23, 59),
            ("2569年9月27日 15:30", 2026, 9, 27, 15, 30),  # BE in Kanji
        ]
        for text, exp_y, exp_m, exp_d, exp_h, exp_min in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for East Asian date '{text}'")
                local_dt = res.astimezone(tz)
                self.assertEqual(local_dt.year, exp_y)
                self.assertEqual(local_dt.month, exp_m)
                self.assertEqual(local_dt.day, exp_d)
                self.assertEqual(local_dt.hour, exp_h)
                self.assertEqual(local_dt.minute, exp_min)

    def test_korean_hangul_date_formats(self):
        """Test Korean Hangul date formats: 년/월/일 with and without year,
        with optional spaces, and time component."""
        import pytz
        tz = pytz.timezone(self.tz)
        cases = [
            # Full date with time
            ("2026년 9월 27일 15:30", 2026, 9, 27, 15, 30),
            ("2026년9월27일 15:30", 2026, 9, 27, 15, 30),   # no spaces
            # Full date without time (default 23:59)
            ("2026년9월27일", 2026, 9, 27, 23, 59),
            ("2026년 09월 27일", 2026, 9, 27, 23, 59),
            # Year-less shorthand (month+day only) -- year inferred
            ("12월 25일 18:00", None, 12, 25, 18, 0),
            ("12월25일 18:00",  None, 12, 25, 18, 0),
            ("12월25일",         None, 12, 25, 23, 59),
        ]
        for text, exp_y, exp_m, exp_d, exp_h, exp_min in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for Korean date '{text}'")
                local_dt = res.astimezone(tz)
                if exp_y is not None:
                    self.assertEqual(local_dt.year, exp_y)
                self.assertEqual(local_dt.month, exp_m)
                self.assertEqual(local_dt.day, exp_d)
                self.assertEqual(local_dt.hour, exp_h)
                self.assertEqual(local_dt.minute, exp_min)

    def test_asian_yearless_shorthand(self):
        """Test year-less Asian shorthand (MM月/월DD日/일) for both Kanji and Hangul."""
        import pytz
        tz = pytz.timezone(self.tz)
        cases = [
            # Japanese/Chinese yearless
            ("12月25日 18:00", None, 12, 25, 18, 0),
            ("12月25日",       None, 12, 25, 23, 59),
            # Spaced variants
            ("12月 25日 18:00", None, 12, 25, 18, 0),
            # Korean yearless
            ("12월 25일 18:00", None, 12, 25, 18, 0),
            ("12월 25일",       None, 12, 25, 23, 59),
        ]
        for text, exp_y, exp_m, exp_d, exp_h, exp_min in cases:
            with self.subTest(text=text):
                res = parse_deadline(text, self.tz)
                self.assertIsNotNone(res, f"parse_deadline failed for yearless Asian date '{text}'")
                local_dt = res.astimezone(tz)
                if exp_y is not None:
                    self.assertEqual(local_dt.year, exp_y)
                self.assertEqual(local_dt.month, exp_m)
                self.assertEqual(local_dt.day, exp_d)
                self.assertEqual(local_dt.hour, exp_h)
                self.assertEqual(local_dt.minute, exp_min)


if __name__ == "__main__":
    unittest.main()

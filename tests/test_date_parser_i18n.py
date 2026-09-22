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


if __name__ == "__main__":
    unittest.main()

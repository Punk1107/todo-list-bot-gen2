import unittest
from datetime import datetime

import pytz

from recurrence.rules import decode_rule, next_deadline, validate_rule


class TestRecurrenceRules(unittest.TestCase):
    def setUp(self):
        self.utc = pytz.utc

    def _local(self, value):
        return datetime.fromisoformat(value).astimezone(self.utc)

    def test_weekdays_skips_weekend(self):
        friday = self.utc.localize(datetime(2026, 5, 8, 9, 30))
        next_value = next_deadline(friday, rule={"type": "weekdays"})
        self.assertEqual(self._local(next_value), self.utc.localize(datetime(2026, 5, 11, 9, 30)))

    def test_interval_days_and_weeks(self):
        start = self.utc.localize(datetime(2026, 5, 4, 9, 30))
        self.assertEqual(
            self._local(next_deadline(start, rule={"type": "every_n_days", "interval": 2})),
            self.utc.localize(datetime(2026, 5, 6, 9, 30)),
        )
        self.assertEqual(
            self._local(next_deadline(start, rule={"type": "every_n_weeks", "interval": 2})),
            self.utc.localize(datetime(2026, 5, 18, 9, 30)),
        )

    def test_monthly_dates_and_short_month_clamping(self):
        june = self.utc.localize(datetime(2026, 6, 17, 9, 30))
        self.assertEqual(
            self._local(next_deadline(june, rule={"type": "monthly_dates", "days": [1, 16]})),
            self.utc.localize(datetime(2026, 7, 1, 9, 30)),
        )
        january = self.utc.localize(datetime(2027, 1, 31, 9, 30))
        self.assertEqual(
            self._local(next_deadline(january, rule={"type": "monthly_dates", "days": [31]})),
            self.utc.localize(datetime(2027, 2, 28, 9, 30)),
        )

    def test_legacy_rule_and_jsonb_decode(self):
        start = self.utc.localize(datetime(2026, 5, 4, 9, 30))
        self.assertEqual(
            self._local(next_deadline(start, "weekly")),
            self.utc.localize(datetime(2026, 5, 11, 9, 30)),
        )
        self.assertEqual(
            decode_rule('{"type":"monthly_dates","days":[16,1,16]}'),
            {"type": "monthly_dates", "days": [1, 16]},
        )

    def test_invalid_rules_are_rejected(self):
        invalid = [
            {"type": "every_n_days", "interval": 0},
            {"type": "every_n_weeks", "interval": 53},
            {"type": "monthly_dates", "days": []},
            {"type": "monthly_dates", "days": [0, 16]},
            {"type": "unknown"},
        ]
        for rule in invalid:
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                validate_rule(rule)


if __name__ == "__main__":
    unittest.main()

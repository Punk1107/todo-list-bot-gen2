import unittest
from datetime import datetime, timedelta, timezone

from focus.cog import BREAK_MINUTES, WORK_MINUTES, _completed_work_seconds


class TestFocusTimerMath(unittest.TestCase):
    def test_timer_intervals_are_pomodoro_defaults(self):
        self.assertEqual(WORK_MINUTES, 25)
        self.assertEqual(BREAK_MINUTES, 5)

    def test_elapsed_work_is_capped_at_work_interval(self):
        started = datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc)
        ends = started + timedelta(minutes=WORK_MINUTES)
        self.assertEqual(_completed_work_seconds(started, ends, started + timedelta(minutes=7)), 420)
        self.assertEqual(_completed_work_seconds(started, ends, ends + timedelta(hours=1)), 1500)
        self.assertEqual(_completed_work_seconds(started, ends, started - timedelta(seconds=1)), 0)


if __name__ == "__main__":
    unittest.main()

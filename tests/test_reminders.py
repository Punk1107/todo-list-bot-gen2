import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import pytz

from handlers.reminders_cog import RemindersCog


class TestRemindersCogTypes(unittest.IsolatedAsyncioTestCase):
    async def test_reminder_loop_query_param_types(self):
        """Ensure reminder_loop query parameters are correctly typed for PostgreSQL/asyncpg."""
        bot = MagicMock()
        cog = RemindersCog(bot)

        # Mock db.afetchall
        mock_afetchall = AsyncMock(return_value=[])
        with patch("handlers.reminders_cog.db.afetchall", mock_afetchall):
            # Run one iteration of reminder_loop
            await cog.reminder_loop()

        self.assertTrue(mock_afetchall.called, "db.afetchall was not called")
        call_args = mock_afetchall.call_args
        sql, params = call_args[0]

        self.assertEqual(len(params), 3, "Expected 3 query parameters")
        soon_threshold, lookback, remind_cutoff = params

        # $1 and $2 are compared against deadline (TEXT column) -> str
        self.assertIsInstance(soon_threshold, str, "$1 soon_threshold must be str for TEXT deadline")
        self.assertIsInstance(lookback, str, "$2 lookback must be str for TEXT deadline")

        # $3 is compared against last_reminder (TIMESTAMP column) -> datetime instance without tzinfo
        self.assertIsInstance(remind_cutoff, datetime, "$3 remind_cutoff must be a datetime instance")
        self.assertIsNone(remind_cutoff.tzinfo, "$3 remind_cutoff must be naive (tzinfo=None) for asyncpg TIMESTAMP codec")


if __name__ == "__main__":
    unittest.main()

"""Tests for the auto-create-or-ask decision logic. Run: python -m unittest discover tests"""
import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rules  # noqa: E402

TZ = "Africa/Tunis"
NOW = datetime(2026, 10, 19, 10, 0, tzinfo=ZoneInfo(TZ))


def event(**over):
    ev = {"title": "Interview with Acme", "category": "interview", "start_date": "2026-10-22",
          "start_time": "14:00", "timezone": None, "all_day": False, "confidence": "high", "date_issues": []}
    ev.update(over)
    return ev


def fields(qs):
    return [q["field"] for q in qs]


class DecideTests(unittest.TestCase):
    def test_clear_event_is_auto_created(self):
        self.assertEqual(rules.decide(event(), NOW, TZ), [])

    def test_ambiguous_date_asks_with_both_options(self):
        qs = rules.decide(event(start_date="2026-05-04", date_alternatives=["2026-04-05"],
                                date_issues=["ambiguous_date_format"]), NOW, TZ)
        self.assertEqual(fields(qs), ["start_date"])
        self.assertEqual(qs[0]["options"], ["2026-05-04", "2026-04-05"])

    def test_relative_date_without_anchor_asks(self):
        qs = rules.decide(event(date_issues=["relative_date_no_anchor"]), NOW, TZ)
        self.assertEqual(fields(qs), ["start_date"])

    def test_missing_time_asks(self):
        qs = rules.decide(event(start_time=None, date_issues=["no_time"]), NOW, TZ)
        self.assertEqual(fields(qs), ["start_time"])

    def test_past_date_asks(self):
        self.assertEqual(fields(rules.decide(event(start_date="2026-10-01"), NOW, TZ)), ["start_date"])

    def test_unclear_timezone_asks(self):
        qs = rules.decide(event(date_issues=["timezone_unclear"]), NOW, TZ)
        self.assertEqual(fields(qs), ["timezone"])

    def test_stated_foreign_timezone_is_fine(self):
        self.assertEqual(rules.decide(event(timezone="America/New_York"), NOW, TZ), [])

    def test_missing_title_asks(self):
        self.assertEqual(fields(rules.decide(event(title=None), NOW, TZ)), ["title"])

    def test_low_confidence_asks_for_confirmation(self):
        self.assertEqual(fields(rules.decide(event(confidence="medium"), NOW, TZ)), ["confirm"])


class ApplyAnswersTests(unittest.TestCase):
    def test_time_and_date_answers(self):
        ev = event(start_time=None)
        rules.apply_answers(ev, {"start_time": "2pm", "start_date": "2026-10-23"})
        self.assertEqual((ev["start_time"], ev["start_date"]), ("14:00", "2026-10-23"))

    def test_all_day_answer(self):
        ev = event(start_time=None)
        rules.apply_answers(ev, {"start_time": "All day"})
        self.assertTrue(ev["all_day"])

    def test_bad_answers_raise(self):
        with self.assertRaises(ValueError):
            rules.apply_answers(event(), {"start_date": "banana"})
        with self.assertRaises(ValueError):
            rules.apply_answers(event(), {"timezone": "Mars/Base"})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from octobrowse.frecency import (
    DEFAULT_WEIGHT,
    RECENCY_BUCKETS,
    frecency,
    rank_entries,
    recency_weight,
)


DAY = 86400.0
NOW = 1_700_000_000.0


def entry(url: str = "https://a.test", visits: int = 1, age_days: float = 0.0) -> dict:
    return {"url": url, "visits": visits, "last_visit": NOW - age_days * DAY}


class RecencyBucketTests(unittest.TestCase):
    def test_bucket_boundaries_are_inclusive(self) -> None:
        # Each bound belongs to its own bucket, not the next one down.
        self.assertEqual(recency_weight(0.0), 100)
        self.assertEqual(recency_weight(4.0), 100)
        self.assertEqual(recency_weight(4.0001), 70)
        self.assertEqual(recency_weight(14.0), 70)
        self.assertEqual(recency_weight(14.0001), 50)
        self.assertEqual(recency_weight(31.0), 50)
        self.assertEqual(recency_weight(31.0001), 30)
        self.assertEqual(recency_weight(90.0), 30)
        self.assertEqual(recency_weight(90.0001), DEFAULT_WEIGHT)

    def test_buckets_are_ordered_and_decreasing(self) -> None:
        bounds = [bound for bound, _ in RECENCY_BUCKETS]
        weights = [weight for _, weight in RECENCY_BUCKETS]
        self.assertEqual(bounds, sorted(bounds))
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertGreater(weights[-1], DEFAULT_WEIGHT)


class FrecencyTests(unittest.TestCase):
    def test_visits_multiply_the_recency_weight(self) -> None:
        self.assertEqual(frecency(entry(visits=1, age_days=1), NOW), 100.0)
        self.assertEqual(frecency(entry(visits=5, age_days=1), NOW), 500.0)
        self.assertEqual(frecency(entry(visits=5, age_days=100), NOW), 50.0)

    def test_a_recent_page_outranks_an_older_more_visited_one(self) -> None:
        recent = frecency(entry(visits=2, age_days=1), NOW)
        stale = frecency(entry(visits=8, age_days=200), NOW)
        self.assertGreater(recent, stale)

    def test_missing_and_malformed_fields_do_not_raise(self) -> None:
        for record in (
            {},
            {"visits": None, "last_visit": None},
            {"visits": "many", "last_visit": "yesterday"},
            {"visits": 0, "last_visit": 0},
            {"visits": -5, "last_visit": -1},
            {"visits": float("nan"), "last_visit": float("nan")},
        ):
            with self.subTest(record=record):
                score = frecency(record, NOW)
                self.assertIsInstance(score, float)
                self.assertGreaterEqual(score, 0.0)

    def test_a_future_timestamp_is_treated_as_just_visited(self) -> None:
        self.assertEqual(frecency(entry(age_days=-30), NOW), 100.0)

    def test_visit_count_has_a_floor_of_one(self) -> None:
        self.assertEqual(frecency({"visits": 0, "last_visit": NOW}, NOW), 100.0)


class RankEntriesTests(unittest.TestCase):
    def test_orders_best_first(self) -> None:
        entries = [
            entry("https://rare.test", visits=1, age_days=200),
            entry("https://daily.test", visits=20, age_days=1),
            entry("https://weekly.test", visits=5, age_days=10),
        ]
        ranked = [record["url"] for record in rank_entries(entries, NOW)]
        self.assertEqual(
            ranked, ["https://daily.test", "https://weekly.test", "https://rare.test"]
        )

    def test_equal_scores_break_on_url_so_ordering_is_stable(self) -> None:
        entries = [
            entry("https://zeta.test", visits=3, age_days=1),
            entry("https://alpha.test", visits=3, age_days=1),
            entry("https://mid.test", visits=3, age_days=1),
        ]
        first = [record["url"] for record in rank_entries(entries, NOW)]
        second = [record["url"] for record in rank_entries(list(reversed(entries)), NOW)]
        self.assertEqual(first, second)
        self.assertEqual(
            first, ["https://alpha.test", "https://mid.test", "https://zeta.test"]
        )

    def test_limit_truncates(self) -> None:
        entries = [entry(f"https://{index}.test", visits=index + 1) for index in range(10)]
        self.assertEqual(len(rank_entries(entries, NOW, limit=3)), 3)
        self.assertEqual(rank_entries(entries, NOW, limit=0), [])
        self.assertEqual(len(rank_entries(entries, NOW, limit=None)), 10)

    def test_empty_input(self) -> None:
        self.assertEqual(rank_entries([], NOW), [])

    def test_input_is_not_mutated(self) -> None:
        entries = [entry("https://b.test"), entry("https://a.test")]
        original = list(entries)
        rank_entries(entries, NOW)
        self.assertEqual(entries, original)


class MainIntegrationTests(unittest.TestCase):
    def test_main_delegates_to_the_shared_ranking(self) -> None:
        from main import OctoBrowse

        record = entry(visits=3, age_days=2)
        self.assertEqual(OctoBrowse._frecency(record, NOW), frecency(record, NOW))


if __name__ == "__main__":
    unittest.main()

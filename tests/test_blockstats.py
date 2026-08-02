from __future__ import annotations

import threading
import unittest

from octobrowse.blockstats import BlockStats


class BlockStatsTests(unittest.TestCase):
    def test_records_totals_and_site_attribution(self) -> None:
        stats = BlockStats()
        stats.record("news.example", "ads.tracker")
        stats.record("news.example", "ads.tracker")
        stats.record("news.example", "beacon.tracker")
        stats.record("shop.example", "ads.tracker")

        self.assertEqual(stats.total(), 4)
        self.assertEqual(stats.for_site("news.example"), 3)
        self.assertEqual(stats.for_site("shop.example"), 1)
        self.assertEqual(stats.for_site("unvisited.example"), 0)

    def test_lookups_are_case_insensitive(self) -> None:
        stats = BlockStats()
        stats.record("News.Example", "Ads.Tracker")
        self.assertEqual(stats.for_site("news.example"), 1)
        self.assertEqual(stats.top_for_site("NEWS.EXAMPLE"), [("ads.tracker", 1)])

    def test_blocks_without_a_first_party_still_count_towards_the_total(self) -> None:
        stats = BlockStats()
        stats.record("", "ads.tracker")
        self.assertEqual(stats.total(), 1)
        self.assertEqual(stats.for_site(""), 0)

    def test_blank_blocked_host_is_ignored(self) -> None:
        stats = BlockStats()
        stats.record("news.example", "")
        self.assertEqual(stats.total(), 0)

    def test_top_for_site_is_ordered_and_bounded(self) -> None:
        stats = BlockStats()
        for _ in range(5):
            stats.record("news.example", "busy.tracker")
        for _ in range(3):
            stats.record("news.example", "medium.tracker")
        stats.record("news.example", "quiet.tracker")

        self.assertEqual(
            stats.top_for_site("news.example", limit=2),
            [("busy.tracker", 5), ("medium.tracker", 3)],
        )
        self.assertEqual(stats.top_for_site("news.example", limit=0), [])

    def test_equal_counts_break_ties_deterministically(self) -> None:
        stats = BlockStats()
        for host in ("zeta.tracker", "alpha.tracker", "mid.tracker"):
            stats.record("news.example", host)
        self.assertEqual(
            stats.top_for_site("news.example"),
            [("alpha.tracker", 1), ("mid.tracker", 1), ("zeta.tracker", 1)],
        )

    def test_top_for_site_result_is_not_aliased_to_internal_state(self) -> None:
        stats = BlockStats()
        stats.record("news.example", "ads.tracker")
        snapshot = stats.top_for_site("news.example")
        snapshot.append(("injected.tracker", 99))
        self.assertEqual(stats.top_for_site("news.example"), [("ads.tracker", 1)])

    def test_https_upgrades_are_counted_and_reset(self) -> None:
        stats = BlockStats()
        stats.record_https_upgrade()
        stats.record_https_upgrade()
        self.assertEqual(stats.https_upgrades, 2)
        stats.reset()
        self.assertEqual(stats.https_upgrades, 0)

    def test_reset_clears_every_tally(self) -> None:
        stats = BlockStats()
        stats.record("news.example", "ads.tracker")
        stats.reset()
        self.assertEqual(stats.total(), 0)
        self.assertEqual(stats.for_site("news.example"), 0)
        self.assertEqual(stats.top_for_site("news.example"), [])

    def test_concurrent_writes_do_not_disturb_readers(self) -> None:
        """The regression this module exists for: readers must never raise."""

        stats = BlockStats()
        writers = 8
        per_writer = 400
        errors: list[BaseException] = []
        start = threading.Barrier(writers + 1)

        def write(worker: int) -> None:
            try:
                start.wait()
                for index in range(per_writer):
                    stats.record(f"site{index % 32}.example", f"tracker{worker}-{index % 64}")
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        def read() -> None:
            try:
                start.wait()
                for _ in range(3000):
                    stats.total()
                    stats.for_site("site1.example")
                    stats.top_for_site("site1.example")
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(worker,)) for worker in range(writers)]
        threads.append(threading.Thread(target=read))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(stats.total(), writers * per_writer)

    def test_concurrent_reset_and_record_stay_consistent(self) -> None:
        stats = BlockStats()
        errors: list[BaseException] = []
        stop = threading.Event()

        def churn() -> None:
            try:
                while not stop.is_set():
                    stats.record("news.example", "ads.tracker")
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        def clear() -> None:
            try:
                for _ in range(500):
                    stats.reset()
                    stats.total()
                    stats.top_for_site("news.example")
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        writer = threading.Thread(target=churn)
        writer.start()
        reader = threading.Thread(target=clear)
        reader.start()
        reader.join()
        stop.set()
        writer.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()

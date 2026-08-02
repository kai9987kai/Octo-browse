from __future__ import annotations

import unittest

from octobrowse.filtering import (
    FilterRuleSet,
    domain_suffix_match,
    is_third_party_request,
    resource_type_name,
)


class FilteringTests(unittest.TestCase):
    def test_domain_suffix_matching_includes_exact_host(self) -> None:
        domains = {"tracker.example"}
        self.assertEqual(domain_suffix_match("tracker.example", domains), "tracker.example")
        self.assertEqual(domain_suffix_match("cdn.tracker.example", domains), "tracker.example")
        self.assertIsNone(domain_suffix_match("nottracker.example", domains))

    def test_resource_type_option_is_not_applied_unconditionally(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$script")
        url = "https://ads.example/banner.js"
        self.assertTrue(rules.should_block(url, "ads.example", "script", "site.example"))
        self.assertFalse(rules.should_block(url, "ads.example", "image", "site.example"))

    def test_third_party_and_negated_options(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||metrics.example^$third-party,~image")
        url = "https://metrics.example/pixel"
        self.assertTrue(rules.should_block(url, "metrics.example", "script", "publisher.test"))
        self.assertFalse(rules.should_block(url, "metrics.example", "image", "publisher.test"))
        self.assertFalse(rules.should_block(url, "metrics.example", "script", "metrics.example"))

    def test_optioned_exception_only_allows_matching_type(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^\n@@||ads.example/allowed.js$script")
        self.assertFalse(
            rules.should_block(
                "https://ads.example/allowed.js", "ads.example", "script", "news.example"
            )
        )
        self.assertTrue(
            rules.should_block(
                "https://ads.example/allowed.js", "ads.example", "image", "news.example"
            )
        )

    def test_common_public_suffix_same_site_detection(self) -> None:
        self.assertFalse(is_third_party_request("cdn.example.co.uk", "www.example.co.uk"))
        self.assertTrue(is_third_party_request("cdn.other.co.uk", "www.example.co.uk"))
        self.assertTrue(is_third_party_request("cdn.example", ""))

    def test_siblings_on_shared_hosting_are_third_party(self) -> None:
        """Regression: these all used to collapse to one site, disabling
        every $third-party rule on the platforms trackers actually use."""
        for request_host, first_party_host in (
            ("tracker.github.io", "victim.github.io"),
            ("a.pages.dev", "b.pages.dev"),
            ("bucket1.s3.amazonaws.com", "bucket2.s3.amazonaws.com"),
            ("evil.vercel.app", "good.vercel.app"),
            ("spy.herokuapp.com", "shop.herokuapp.com"),
            ("tracker.co.in", "victim.co.in"),
        ):
            with self.subTest(request=request_host, first_party=first_party_host):
                self.assertTrue(
                    is_third_party_request(request_host, first_party_host)
                )

    def test_ancestor_hosts_remain_first_party(self) -> None:
        self.assertFalse(is_third_party_request("cdn.user.github.io", "user.github.io"))
        self.assertFalse(is_third_party_request("www.example.com", "example.com"))
        self.assertFalse(is_third_party_request("example.com", "www.example.com"))
        self.assertFalse(is_third_party_request("foo.localhost", "localhost"))

    def test_a_public_suffix_ancestor_is_not_the_same_site(self) -> None:
        """A document at the apex of a shared host is not first-party with
        every user's subdomain on that platform."""
        for request_host, first_party_host in (
            ("evil.neocities.org", "neocities.org"),
            ("neocities.org", "evil.neocities.org"),
            ("spy.github.io", "github.io"),
            ("tracker.blogspot.com", "blogspot.com"),
        ):
            with self.subTest(request=request_host, first_party=first_party_host):
                self.assertTrue(
                    is_third_party_request(request_host, first_party_host)
                )

    def test_an_unknown_first_party_is_treated_as_third_party(self) -> None:
        """about:blank / file:// / data: all yield an empty host. Returning
        None made every $third-party rule non-matching — the blocker failed
        open on exactly those documents."""
        self.assertTrue(is_third_party_request("tracker.example", ""))
        self.assertIsNone(is_third_party_request("", "victim.test"))
        self.assertIsNone(is_third_party_request("", ""))

        rules = FilterRuleSet()
        rules.parse_text("||tracker.example^$third-party")
        self.assertTrue(
            rules.should_block(
                "https://tracker.example/t.js", "tracker.example", "script", ""
            )
        )

    def test_third_party_rule_fires_across_shared_hosting(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||tracker.github.io^$third-party")

        self.assertTrue(
            rules.should_block(
                "https://tracker.github.io/beacon.js",
                "tracker.github.io",
                "script",
                "victim.github.io",
            )
        )
        # Same publisher: the rule must still not fire on its own subdomain.
        self.assertFalse(
            rules.should_block(
                "https://tracker.github.io/beacon.js",
                "tracker.github.io",
                "script",
                "tracker.github.io",
            )
        )

    def test_resource_type_name_accepts_qt_style_names(self) -> None:
        self.assertEqual(resource_type_name("ResourceTypeXhr"), "xmlhttprequest")
        self.assertEqual(resource_type_name("ResourceTypeMainFrame"), "document")
        self.assertEqual(resource_type_name("something-new"), "other")

    def test_unsupported_options_are_skipped(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$domain=example.com")
        self.assertEqual(rules.rule_count, 0)
        self.assertEqual(rules.skipped_count, 1)


if __name__ == "__main__":
    unittest.main()

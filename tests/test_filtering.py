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
        self.assertIsNone(is_third_party_request("cdn.example", ""))

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

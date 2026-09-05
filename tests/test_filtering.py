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
        rules.parse_text("||ads.example^$rewrite=abp-resource:blank-js")
        self.assertEqual(rules.rule_count, 0)
        self.assertEqual(rules.skipped_count, 1)

    def test_network_domains_scope_the_loading_document(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$script,domain=news.example|magazine.example|~shop.news.example")
        for first_party, expected in (
            ("news.example", True),
            ("WWW.NEWS.EXAMPLE.", True),
            ("magazine.example", True),
            ("shop.news.example", False),
            ("cdn.shop.news.example", False),
            ("notnews.example", False),
            ("ads.example", False),
            ("", False),
        ):
            with self.subTest(first_party=first_party):
                self.assertEqual(
                    rules.should_block("https://ads.example/ad.js", "ads.example", "script", first_party),
                    expected,
                )
        self.assertFalse(rules.should_block("https://ads.example/ad.js", "ads.example", "image", "news.example"))

    def test_exclusion_only_network_scope_and_third_party_are_both_enforced(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$third-party,domain=~news.example")
        for first_party, expected in (
            ("news.example", False),
            ("www.news.example", False),
            ("magazine.example", True),
            ("ads.example", False),
            ("", True),
        ):
            with self.subTest(first_party=first_party):
                self.assertEqual(
                    rules.should_block("https://ads.example/ad.js", "ads.example", "script", first_party),
                    expected,
                )

    def test_domain_scoped_network_exception_does_not_allow_other_publishers(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^\n@@||ads.example^$script,domain=news.example|~shop.news.example")
        for first_party, resource_type, expected in (
            ("news.example", "script", False),
            ("sub.news.example", "script", False),
            ("news.example", "image", True),
            ("shop.news.example", "script", True),
            ("other.example", "script", True),
            ("", "script", True),
        ):
            with self.subTest(first_party=first_party, resource_type=resource_type):
                self.assertEqual(
                    rules.should_block("https://ads.example/ad.js", "ads.example", resource_type, first_party),
                    expected,
                )

    def test_network_domain_scope_uses_requesting_frame_when_provided(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$script,domain=frame.example|~shop.frame.example")
        for top_level, document, expected in (
            ("news.example", "frame.example", True),
            ("news.example", "cdn.frame.example", True),
            ("frame.example", "other.example", False),
            ("frame.example", "shop.frame.example", False),
            ("frame.example", "cdn.shop.frame.example", False),
            ("frame.example", "", False),
            ("frame.example", None, True),
        ):
            with self.subTest(top_level=top_level, document=document):
                self.assertEqual(
                    rules.should_block(
                        "https://ads.example/ad.js", "ads.example", "script", top_level,
                        document_host=document,
                    ),
                    expected,
                )

    def test_frame_domain_scope_preserves_top_level_party_constraints(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$third-party,domain=frame.example")
        self.assertTrue(rules.should_block(
            "https://ads.example/ad.js", "ads.example", "script", "news.example",
            document_host="frame.example",
        ))
        self.assertFalse(rules.should_block(
            "https://ads.example/ad.js", "ads.example", "script", "ads.example",
            document_host="frame.example",
        ))

    def test_frame_scoped_exception_does_not_leak_to_other_frames(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text(
            "||ads.example^\n"
            "@@||ads.example^$script,domain=frame.example|~shop.frame.example|allowed.shop.frame.example"
        )
        for top_level, document, resource_type, allowed in (
            ("news.example", "frame.example", "script", True),
            ("news.example", "sub.frame.example", "script", True),
            ("frame.example", "other.example", "script", False),
            ("frame.example", "shop.frame.example", "script", False),
            ("news.example", "allowed.shop.frame.example", "script", True),
            ("news.example", "frame.example", "image", False),
            ("frame.example", "", "script", False),
            ("frame.example", None, "script", True),
        ):
            with self.subTest(top_level=top_level, document=document, resource_type=resource_type):
                args = ("https://ads.example/ad.js", "ads.example", resource_type, top_level)
                self.assertEqual(rules.allows_request(*args, document_host=document), allowed)
                self.assertEqual(rules.should_block(*args, document_host=document), not allowed)

    def test_malformed_network_domains_never_become_unconditional_rules(self) -> None:
        for scope in (
            "", "~", "example.com|", "example.com||other.test", "https://example.com", "*.example.com",
            "example.com/path", "example.com:443", "example.com|~example.com", "-example.com",
            "example.com,domain=other.example",
        ):
            for prefix in ("", "@@"):
                with self.subTest(scope=scope, prefix=prefix):
                    rules = FilterRuleSet()
                    rules.parse_text(f"{prefix}||ads.example^$domain={scope}")
                    self.assertEqual(rules.rule_count, 0)
                    self.assertEqual(rules.skipped_count, 1)
                    self.assertFalse(rules.allows_request("https://ads.example/ad.js", "ads.example"))
                    self.assertFalse(rules.should_block("https://ads.example/ad.js", "ads.example"))

    def test_more_specific_domain_can_override_parent_exclusion(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$domain=~news.example|allowed.news.example")
        self.assertTrue(
            rules.should_block("https://ads.example/ad.js", "ads.example", "script", "allowed.news.example")
        )
        self.assertFalse(rules.should_block("https://ads.example/ad.js", "ads.example", "script", "news.example"))
        self.assertFalse(rules.should_block("https://ads.example/ad.js", "ads.example", "script", "other.example"))

    def test_idna_network_and_cosmetic_domains_match_unicode_or_ascii_hosts(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("||ads.example^$domain=bücher.example\nbücher.example##.sponsor")
        for host in ("bücher.example", "xn--bcher-kva.example", "WWW.BÜCHER.EXAMPLE."):
            with self.subTest(host=host):
                self.assertTrue(rules.should_block("https://ads.example/ad.js", "ads.example", "script", host))
                self.assertEqual(rules.cosmetic_selectors_for(host), [".sponsor"])

    def test_cosmetic_domain_includes_and_excludes(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("news.example,magazine.example,~shop.news.example##.sponsor")
        for host, expected in (
            ("news.example", [".sponsor"]),
            ("WWW.NEWS.EXAMPLE.", [".sponsor"]),
            ("magazine.example", [".sponsor"]),
            ("shop.news.example", []),
            ("cdn.shop.news.example", []),
            ("notnews.example", []),
            ("", []),
        ):
            with self.subTest(host=host):
                self.assertEqual(rules.cosmetic_selectors_for(host), expected)

    def test_exclusion_only_cosmetic_scope_is_generic_elsewhere(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("~news.example##.sponsor")
        self.assertEqual(rules.cosmetic_selectors_for("news.example"), [])
        self.assertEqual(rules.cosmetic_selectors_for("www.news.example"), [])
        self.assertEqual(rules.cosmetic_selectors_for("other.example"), [".sponsor"])
        self.assertIn(".sponsor", rules.cosmetic_css_for("other.example"))
        self.assertEqual(rules.cosmetic_count, 1)

    def test_cosmetic_exception_undoes_generic_and_specific_hiding(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("##.sponsor\nnews.example##.sponsor\nnews.example##.other")
        rules.parse_text("news.example#@#.sponsor")
        self.assertEqual(rules.cosmetic_selectors_for("news.example"), [".other"])
        self.assertEqual(rules.cosmetic_selectors_for("www.news.example"), [".other"])
        self.assertEqual(rules.cosmetic_selectors_for("notnews.example"), [".sponsor"])

    def test_cosmetic_exception_requires_identical_selector(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("##aside.sponsor\nnews.example#@#aside\nnews.example#@#aside.Sponsor")
        self.assertEqual(rules.cosmetic_selectors_for("news.example"), ["aside.sponsor"])
        rules.parse_text("news.example#@#aside.sponsor")
        self.assertEqual(rules.cosmetic_selectors_for("news.example"), [])

    def test_cosmetic_exception_domains_can_be_excluded(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("##.sponsor\nnews.example,~shop.news.example#@#.sponsor")
        self.assertEqual(rules.cosmetic_selectors_for("news.example"), [])
        self.assertEqual(rules.cosmetic_selectors_for("shop.news.example"), [".sponsor"])
        self.assertEqual(rules.cosmetic_selectors_for("other.example"), [".sponsor"])

    def test_global_cosmetic_exception_is_order_independent(self) -> None:
        for text in ("#@#.sponsor\n##.sponsor", "##.sponsor\n#@#.sponsor"):
            rules = FilterRuleSet()
            rules.parse_text(text)
            self.assertEqual(rules.cosmetic_css_for("news.example"), "")

    def test_cosmetic_css_cache_is_invalidated_by_additional_subscriptions(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("##.sponsor")
        self.assertIn(".sponsor", rules.cosmetic_css_for("news.example"))
        rules.parse_text("news.example#@#.sponsor\n##.other")
        self.assertNotIn(".sponsor", rules.cosmetic_css_for("news.example"))
        self.assertIn(".other", rules.cosmetic_css_for("news.example"))
        self.assertIn(".sponsor", rules.cosmetic_css_for("other.example"))

    def test_duplicate_cosmetic_selectors_are_emitted_once(self) -> None:
        rules = FilterRuleSet()
        rules.parse_text("##.sponsor\nnews.example##.sponsor\nnews.example,~shop.news.example##.sponsor")
        self.assertEqual(rules.cosmetic_css_for("news.example").count(".sponsor"), 1)

    def test_invalid_cosmetic_scopes_and_css_declarations_are_skipped(self) -> None:
        for line in (
            "~##.sponsor", "news.example,##.sponsor", "*.example##.sponsor",
            "https://news.example#@#.sponsor", "news.example,~news.example##.sponsor",
            "news.example##.sponsor { color: red; }", "news.example#@#",
        ):
            with self.subTest(line=line):
                rules = FilterRuleSet()
                rules.parse_text(line)
                self.assertEqual(rules.cosmetic_count, 0)
                self.assertEqual(rules.skipped_count, 1)
                self.assertEqual(rules.cosmetic_selectors_for("news.example"), [])

    def test_exclusion_only_cosmetic_rules_share_generic_cap(self) -> None:
        rules = FilterRuleSet()
        rules.GENERIC_SELECTOR_CAP = 2
        rules.parse_text("##.one\n~news.example##.two\n##.three\n~news.example##.four")
        self.assertEqual(rules.cosmetic_count, 2)
        self.assertEqual(rules.skipped_count, 2)
        self.assertEqual(rules.cosmetic_selectors_for("other.example"), [".one", ".two"])

    def test_cosmetic_cache_is_bounded_without_losing_host_specific_results(self) -> None:
        rules = FilterRuleSet()
        rules.CSS_CACHE_CAP = 2
        rules.parse_text("##.sponsor\nnews.example#@#.sponsor")
        self.assertEqual(rules.cosmetic_css_for("news.example"), "")
        rules.cosmetic_css_for("one.example")
        rules.cosmetic_css_for("two.example")
        self.assertEqual(len(rules._cosmetic_css_cache), 2)
        self.assertEqual(rules.cosmetic_css_for("news.example"), "")


if __name__ == "__main__":
    unittest.main()

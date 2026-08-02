from __future__ import annotations

import unittest

from octobrowse import public_suffix as psl
from octobrowse.public_suffix import (
    is_public_suffix,
    public_suffix,
    registrable_domain,
    same_site,
)


class RulesetInvariantTests(unittest.TestCase):
    """Structural checks on the committed subset itself.

    Both data errors found after the first release — `sch.uk` shipped as a
    plain rule instead of `*.sch.uk`, and seven `!city.<city>.jp` exceptions
    shipped without their `*.<city>.jp` wildcards — are caught here.
    """

    def test_every_exception_has_its_parent_wildcard(self) -> None:
        for rule in sorted(psl._EXCEPTIONS):
            parent = rule.split(".", 1)[1]
            with self.subTest(rule=rule):
                self.assertIn(
                    parent,
                    psl._WILDCARD,
                    f"!{rule} carves a hole in *.{parent}, which is not shipped",
                )

    def test_no_rule_appears_in_two_categories(self) -> None:
        self.assertEqual(psl._NORMAL_RULES & psl._WILDCARD, frozenset())
        self.assertEqual(psl._NORMAL_RULES & psl._EXCEPTIONS, frozenset())

    def test_rules_are_lowercase_and_unanchored(self) -> None:
        for group in (psl._NORMAL_RULES, psl._WILDCARD, psl._EXCEPTIONS):
            for rule in sorted(group):
                with self.subTest(rule=rule):
                    self.assertEqual(rule, rule.lower())
                    self.assertNotIn("*", rule)
                    self.assertNotIn("!", rule)
                    self.assertFalse(rule.startswith("."))
                    self.assertFalse(rule.endswith("."))

    def test_max_rule_labels_covers_every_rule(self) -> None:
        for rule in sorted(psl._NORMAL_RULES | psl._EXCEPTIONS):
            self.assertLessEqual(rule.count(".") + 1, psl._MAX_RULE_LABELS)
        for rule in sorted(psl._WILDCARD):
            # A wildcard consumes one label beyond its own.
            self.assertLessEqual(rule.count(".") + 2, psl._MAX_RULE_LABELS)


class PublicSuffixTests(unittest.TestCase):
    def test_single_label_tlds(self) -> None:
        self.assertEqual(public_suffix("example.com"), "com")
        self.assertEqual(public_suffix("www.example.com"), "com")
        self.assertEqual(public_suffix("example.dev"), "dev")

    def test_icann_second_level_suffixes(self) -> None:
        self.assertEqual(public_suffix("example.co.uk"), "co.uk")
        self.assertEqual(public_suffix("www.example.co.uk"), "co.uk")
        self.assertEqual(public_suffix("example.com.au"), "com.au")
        self.assertEqual(public_suffix("example.co.jp"), "co.jp")

    def test_private_section_suffixes(self) -> None:
        self.assertEqual(public_suffix("user.github.io"), "github.io")
        self.assertEqual(public_suffix("site.pages.dev"), "pages.dev")
        self.assertEqual(public_suffix("app.vercel.app"), "vercel.app")
        self.assertEqual(public_suffix("bucket.s3.amazonaws.com"), "s3.amazonaws.com")
        self.assertEqual(
            public_suffix("bucket.s3.eu-west-1.amazonaws.com"),
            "s3.eu-west-1.amazonaws.com",
        )

    def test_longest_matching_rule_wins(self) -> None:
        # Both "com" and "s3.amazonaws.com" match; the longer rule prevails.
        self.assertEqual(public_suffix("a.b.s3.amazonaws.com"), "s3.amazonaws.com")

    def test_wildcard_rules_consume_one_extra_label(self) -> None:
        self.assertEqual(public_suffix("anything.ck"), "anything.ck")
        self.assertEqual(
            public_suffix("box.compute.amazonaws.com"), "box.compute.amazonaws.com"
        )

    def test_exception_rules_override_wildcards(self) -> None:
        # "!www.ck" makes www.ck registrable despite the "*.ck" wildcard.
        self.assertEqual(public_suffix("www.ck"), "ck")
        self.assertEqual(registrable_domain("www.ck"), "www.ck")

    def test_uk_schools_are_separate_sites(self) -> None:
        """The PSL entry is *.sch.uk, not sch.uk."""
        self.assertEqual(public_suffix("brookfield.leics.sch.uk"), "leics.sch.uk")
        self.assertEqual(
            registrable_domain("stmarys.leics.sch.uk"), "stmarys.leics.sch.uk"
        )
        self.assertFalse(
            same_site("brookfield.leics.sch.uk", "stmarys.leics.sch.uk")
        )

    def test_japanese_city_wildcards_and_their_exceptions(self) -> None:
        # *.kawasaki.jp makes every org under it its own site...
        self.assertEqual(public_suffix("acme.kawasaki.jp"), "acme.kawasaki.jp")
        self.assertEqual(
            registrable_domain("www.acme.kawasaki.jp"), "www.acme.kawasaki.jp"
        )
        self.assertFalse(same_site("a.acme.kawasaki.jp", "b.other.kawasaki.jp"))
        # ...while !city.kawasaki.jp carves the city itself back out.
        self.assertEqual(registrable_domain("city.kawasaki.jp"), "city.kawasaki.jp")
        self.assertTrue(same_site("www.city.kawasaki.jp", "city.kawasaki.jp"))

    def test_ports_and_bracketed_ipv6_are_stripped(self) -> None:
        self.assertEqual(registrable_domain("example.com:8080"), "example.com")
        self.assertEqual(registrable_domain("www.example.com:443"), "example.com")
        self.assertEqual(registrable_domain("localhost:3000"), "localhost")
        self.assertEqual(registrable_domain("[::1]"), "::1")
        self.assertEqual(registrable_domain("[::1]:8080"), "::1")
        self.assertTrue(same_site("example.com:8080", "example.com"))

    def test_is_public_suffix(self) -> None:
        for host in ("github.io", "co.uk", "s3.amazonaws.com", "leics.sch.uk"):
            with self.subTest(host=host):
                self.assertTrue(is_public_suffix(host))
        for host in ("user.github.io", "example.co.uk", "localhost", "192.168.1.1"):
            with self.subTest(host=host):
                self.assertFalse(is_public_suffix(host))
        # A wildcard rule needs a label in front of it: "*.sch.uk" does not
        # match the bare "sch.uk", which falls to the default rule and is
        # therefore registrable. This mirrors the real list.
        self.assertFalse(is_public_suffix("sch.uk"))

    def test_unknown_suffix_falls_back_to_the_default_rule(self) -> None:
        self.assertEqual(public_suffix("example.invalidtld"), "invalidtld")
        self.assertEqual(registrable_domain("www.example.invalidtld"), "example.invalidtld")

    def test_hosts_without_a_suffix(self) -> None:
        self.assertIsNone(public_suffix("localhost"))
        self.assertIsNone(public_suffix(""))
        self.assertIsNone(public_suffix("   "))
        self.assertIsNone(public_suffix(None))  # type: ignore[arg-type]

    def test_ip_literals_are_not_given_a_suffix(self) -> None:
        self.assertIsNone(public_suffix("192.168.1.1"))
        self.assertIsNone(public_suffix("::1"))
        self.assertEqual(registrable_domain("192.168.1.1"), "192.168.1.1")

    def test_trailing_dots_and_case_are_normalized(self) -> None:
        self.assertEqual(public_suffix("WWW.Example.CO.UK."), "co.uk")
        self.assertEqual(registrable_domain("WWW.Example.CO.UK."), "example.co.uk")


class RegistrableDomainTests(unittest.TestCase):
    def test_registrable_domain_adds_exactly_one_label(self) -> None:
        self.assertEqual(registrable_domain("www.example.com"), "example.com")
        self.assertEqual(registrable_domain("a.b.c.example.co.uk"), "example.co.uk")
        self.assertEqual(registrable_domain("user.github.io"), "user.github.io")
        self.assertEqual(registrable_domain("deep.user.github.io"), "user.github.io")

    def test_a_bare_multi_label_public_suffix_has_no_registrable_domain(self) -> None:
        self.assertIsNone(registrable_domain("github.io"))
        self.assertIsNone(registrable_domain("co.uk"))
        self.assertIsNone(registrable_domain("s3.amazonaws.com"))

    def test_single_label_host_is_its_own_site(self) -> None:
        # Intranet names are indistinguishable from bare TLDs without the full
        # ICANN list; treating them as sites is the behaviour that matters.
        self.assertEqual(registrable_domain("localhost"), "localhost")
        self.assertEqual(registrable_domain("intranet"), "intranet")
        self.assertEqual(registrable_domain("com"), "com")


class SameSiteTests(unittest.TestCase):
    def test_subdomains_of_one_site_match(self) -> None:
        self.assertTrue(same_site("www.example.com", "cdn.example.com"))
        self.assertTrue(same_site("example.com", "www.example.com"))
        self.assertTrue(same_site("cdn.example.co.uk", "www.example.co.uk"))

    def test_siblings_under_a_shared_public_suffix_do_not_match(self) -> None:
        self.assertFalse(same_site("tracker.github.io", "victim.github.io"))
        self.assertFalse(same_site("a.pages.dev", "b.pages.dev"))
        self.assertFalse(same_site("one.s3.amazonaws.com", "two.s3.amazonaws.com"))
        self.assertFalse(same_site("evil.vercel.app", "good.vercel.app"))

    def test_unrelated_sites_do_not_match(self) -> None:
        self.assertFalse(same_site("example.com", "example.net"))
        self.assertFalse(same_site("tracker.test", "victim.test"))

    def test_empty_hosts_never_match(self) -> None:
        self.assertFalse(same_site("", "example.com"))
        self.assertFalse(same_site("example.com", ""))
        self.assertFalse(same_site("", ""))


if __name__ == "__main__":
    unittest.main()

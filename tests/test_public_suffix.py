from __future__ import annotations

import unittest

from octobrowse.public_suffix import (
    public_suffix,
    registrable_domain,
    same_site,
)


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

"""Fast, testable Adblock Plus subset used by OctoBrowse.

The parser intentionally supports a bounded part of the ABP grammar, but the
options it accepts are applied faithfully.  In particular, resource-type and
third-party rules must never silently degrade into unconditional blocks.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any

from .public_suffix import is_public_suffix, registrable_domain


RESOURCE_OPTIONS = {
    "script",
    "image",
    "stylesheet",
    "xmlhttprequest",
    "subdocument",
    "object",
    "media",
    "font",
    "websocket",
    "other",
    "ping",
    "document",
}

RESOURCE_TYPE_NAMES = {
    "ResourceTypeMainFrame": "document",
    "ResourceTypeNavigationPreloadMainFrame": "document",
    "ResourceTypeSubFrame": "subdocument",
    "ResourceTypeNavigationPreloadSubFrame": "subdocument",
    "ResourceTypeStylesheet": "stylesheet",
    "ResourceTypeScript": "script",
    "ResourceTypeImage": "image",
    "ResourceTypeFavicon": "image",
    "ResourceTypeFontResource": "font",
    "ResourceTypeObject": "object",
    "ResourceTypePluginResource": "object",
    "ResourceTypeMedia": "media",
    "ResourceTypeXhr": "xmlhttprequest",
    "ResourceTypeJson": "xmlhttprequest",
    "ResourceTypePing": "ping",
    "ResourceTypeWebSocket": "websocket",
}

# Superseded by octobrowse.public_suffix, which covers these plus the private
# hosting platforms.  Retained because it documents the original fallback set
# and because a stale public-suffix subset degrades to exactly this behaviour.
COMMON_MULTI_LABEL_SUFFIXES = {
    "ac.uk", "co.uk", "gov.uk", "ltd.uk", "me.uk", "net.uk", "org.uk", "plc.uk",
    "asn.au", "com.au", "edu.au", "gov.au", "id.au", "net.au", "org.au",
    "ac.nz", "co.nz", "govt.nz", "net.nz", "org.nz",
    "co.jp", "ne.jp", "or.jp",
    "com.br", "com.cn", "com.hk", "com.mx", "com.sg", "com.tr", "co.za",
}


def domain_suffix_match(host: str, domains: set[str]) -> str | None:
    """Return a matching hostname suffix in O(number of host labels)."""
    host = host.lower().strip(".")
    if not host or not domains:
        return None
    parts = host.split(".")
    for index in range(len(parts)):
        candidate = ".".join(parts[index:])
        if candidate in domains:
            return candidate
    return None


def resource_type_name(resource_type: Any) -> str:
    """Map Qt's ResourceType enum (or its name) to an ABP option name."""
    enum_name = getattr(resource_type, "name", str(resource_type or ""))
    if enum_name in RESOURCE_OPTIONS:
        return enum_name
    return RESOURCE_TYPE_NAMES.get(enum_name, "other")


def _site_key(host: str) -> str:
    """Return the site identity of ``host`` — its registrable domain.

    Falls back to the full host when the host *is* a public suffix, so two
    different suffixes never collapse onto one another.
    """
    host = host.lower().strip(".")
    if not host:
        return ""
    return registrable_domain(host) or host


def _is_owned_ancestor(descendant: str, ancestor: str) -> bool:
    """Whether ``ancestor`` is a real parent site of ``descendant``.

    A DNS ancestor is only the *same site* when somebody actually owns it.
    ``neocities.org`` is a DNS ancestor of ``evil.neocities.org`` but it is a
    public suffix, so the two belong to different publishers and must stay
    cross-site — otherwise a document served at the apex of a shared host is
    first-party with every user's subdomain on the platform.
    """
    return descendant.endswith("." + ancestor) and not is_public_suffix(ancestor)


def is_third_party_request(request_host: str, first_party_host: str) -> bool | None:
    """Return whether two hosts are cross-site, or ``None`` without a request.

    An unknown first party (``about:blank``, ``file://``, ``data:`` — all of
    which yield an empty ``QUrl.host()``) is reported as third-party rather
    than unknown. Returning ``None`` made both ``$third-party`` and
    ``$~third-party`` rules non-matching, so the blocker failed open on exactly
    those documents; a blocker should fail toward blocking.
    """
    request_host = request_host.lower().strip(".")
    first_party_host = first_party_host.lower().strip(".")
    if not request_host:
        return None
    if not first_party_host:
        return True
    if request_host == first_party_host:
        return False
    if _is_owned_ancestor(request_host, first_party_host) or _is_owned_ancestor(
        first_party_host, request_host
    ):
        return False
    return _site_key(request_host) != _site_key(first_party_host)


def _normalize_rule_domain(host: str) -> str:
    """Canonicalize DNS names without accepting URL paths or wildcard scopes."""
    try:
        host = host.strip().lower().rstrip(".").encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    if len(host) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in host.split(".")
    ):
        return ""
    return host


@dataclass(frozen=True)
class DomainScope:
    """Document-domain restrictions; the closest matching domain wins."""

    included: frozenset[str] = frozenset()
    excluded: frozenset[str] = frozenset()

    def matches(self, host: str) -> bool:
        if not self.included and not self.excluded:
            return True
        host = _normalize_rule_domain(host)
        while host:
            if host in self.excluded:
                return False
            if host in self.included:
                return True
            host = host.partition(".")[2]
        return not self.included

    @classmethod
    def parse(cls, text: str, separator: str) -> DomainScope | None:
        included: set[str] = set()
        excluded: set[str] = set()
        for entry in text.split(separator):
            entry = entry.strip()
            negated = entry.startswith("~")
            host = _normalize_rule_domain(entry[1:] if negated else entry)
            if not host:
                return None
            (excluded if negated else included).add(host)
        if included & excluded:
            return None
        return cls(frozenset(included), frozenset(excluded))


@dataclass(frozen=True)
class CosmeticRule:
    selector: str
    domains: DomainScope


@dataclass(frozen=True)
class NetworkRule:
    """Compiled network rule plus the ABP request constraints it carries."""

    pattern: re.Pattern[str]
    include_types: frozenset[str] = frozenset()
    exclude_types: frozenset[str] = frozenset()
    third_party: bool | None = None
    domains: DomainScope = DomainScope()

    def matches(
        self,
        url: str,
        resource_type: str,
        third_party: bool | None,
        first_party_host: str = "",
        document_host: str | None = None,
    ) -> bool:
        if self.include_types and resource_type not in self.include_types:
            return False
        if resource_type in self.exclude_types:
            return False
        if self.third_party is not None and third_party is not self.third_party:
            return False
        if not self.domains.matches(first_party_host if document_host is None else document_host):
            return False
        return self.pattern.search(url) is not None


class FilterRuleSet:
    """A practical, indexed subset of the Adblock Plus filter grammar."""

    GENERIC_CAP = 200
    GENERIC_SELECTOR_CAP = 5000
    CSS_CACHE_CAP = 128
    _CSS_CHUNK = 100
    _TOKEN_RE = re.compile(r"[a-z0-9]{4,}")
    _HOSTS_RE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1)\s+([a-z0-9.-]+)$", re.IGNORECASE)
    _DOMAIN_RULE_RE = re.compile(r"^[a-z0-9.-]+\^?$", re.IGNORECASE)
    SUPPORTED_OPTIONS = RESOURCE_OPTIONS | {"third-party", "3p"}

    def __init__(self) -> None:
        self.blocked_domains: set[str] = set()
        self.exception_domains: set[str] = set()
        self.token_buckets: dict[str, list[NetworkRule]] = {}
        self.generic_patterns: list[NetworkRule] = []
        self.exception_token_buckets: dict[str, list[NetworkRule]] = {}
        self.generic_exceptions: list[NetworkRule] = []
        self.generic_selectors: list[str] = []
        self.domain_selectors: dict[str, list[str]] = {}
        self._scoped_selectors: dict[str, list[CosmeticRule]] = {}
        self._cosmetic_exceptions: dict[str, list[CosmeticRule]] = {}
        self._generic_scoped_count = 0
        self.rule_count = 0
        self.cosmetic_count = 0
        self.skipped_count = 0
        self._cosmetic_css_cache: OrderedDict[str, str] = OrderedDict()

    def parse_text(self, text: str) -> None:
        # Filter subscriptions are parsed incrementally into the same rule set.
        self._cosmetic_css_cache.clear()
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("!", "[")):
                continue
            if "#?#" in line or "#$#" in line:
                self.skipped_count += 1
                continue
            if "#@#" in line:
                self._parse_cosmetic(line, exception=True)
                continue
            if "##" in line:
                self._parse_cosmetic(line)
                continue
            hosts_match = self._HOSTS_RE.match(line)
            if hosts_match:
                domain = hosts_match.group(1).lower()
                if domain not in {"localhost", "localhost.localdomain", "broadcasthost"}:
                    self.blocked_domains.add(domain)
                    self.rule_count += 1
                continue

            exception = line.startswith("@@")
            if exception:
                line = line[2:]
            body, _, options_text = line.partition("$")
            constraints = self._parse_options(options_text)
            if constraints is None:
                self.skipped_count += 1
                continue

            # Unqualified hostname rules retain the very fast suffix-set path.
            if not options_text and body.startswith("||"):
                rest = body[2:]
                if self._DOMAIN_RULE_RE.match(rest):
                    domain = rest.rstrip("^").lower().strip(".")
                    if domain:
                        (self.exception_domains if exception else self.blocked_domains).add(domain)
                        self.rule_count += 1
                    continue

            pattern = self._compile_pattern(body)
            if pattern is None:
                self.skipped_count += 1
                continue
            include_types, exclude_types, third_party, domains = constraints
            rule = NetworkRule(pattern, include_types, exclude_types, third_party, domains)
            token = self._pick_token(body)
            if exception:
                buckets, generic = self.exception_token_buckets, self.generic_exceptions
            else:
                buckets, generic = self.token_buckets, self.generic_patterns
            if token:
                buckets.setdefault(token, []).append(rule)
                self.rule_count += 1
            elif len(generic) < self.GENERIC_CAP:
                generic.append(rule)
                self.rule_count += 1
            else:
                self.skipped_count += 1

    @classmethod
    def _parse_options(
        cls, options: str
    ) -> tuple[frozenset[str], frozenset[str], bool | None, DomainScope] | None:
        include_types: set[str] = set()
        exclude_types: set[str] = set()
        third_party: bool | None = None
        domains = DomainScope()
        has_domain_option = False
        if not options:
            return frozenset(), frozenset(), None, domains
        for raw_option in options.split(","):
            option = raw_option.strip().lower()
            if option.startswith("domain="):
                if has_domain_option:
                    return None
                scope = DomainScope.parse(option.partition("=")[2], "|")
                if scope is None:
                    return None
                domains = scope
                has_domain_option = True
                continue
            negated = option.startswith("~")
            if negated:
                option = option[1:]
            if option not in cls.SUPPORTED_OPTIONS:
                return None
            if option in {"third-party", "3p"}:
                desired = not negated
                if third_party is not None and third_party != desired:
                    return None
                third_party = desired
            elif negated:
                exclude_types.add(option)
            else:
                include_types.add(option)
        if include_types & exclude_types:
            return None
        return frozenset(include_types), frozenset(exclude_types), third_party, domains

    def _parse_cosmetic(self, line: str, exception: bool = False) -> None:
        domains_part, _, selector = line.partition("#@#" if exception else "##")
        selector = selector.strip()
        if not selector or "{" in selector or "}" in selector:
            self.skipped_count += 1
            return
        domains_part = domains_part.strip().lower()
        scope = DomainScope.parse(domains_part, ",") if domains_part else DomainScope()
        if scope is None:
            self.skipped_count += 1
            return
        if exception:
            rule = CosmeticRule(selector, scope)
            for domain in sorted(scope.included) or [""]:
                self._cosmetic_exceptions.setdefault(domain, []).append(rule)
            self.cosmetic_count += 1
            return
        if not scope.included and len(self.generic_selectors) + self._generic_scoped_count >= self.GENERIC_SELECTOR_CAP:
            self.skipped_count += 1
            return
        if not domains_part:
            self.generic_selectors.append(selector)
            self.cosmetic_count += 1
            return
        if scope.excluded:
            rule = CosmeticRule(selector, scope)
            for domain in sorted(scope.included) or [""]:
                self._scoped_selectors.setdefault(domain, []).append(rule)
            if not scope.included:
                self._generic_scoped_count += 1
            self.cosmetic_count += 1
            return
        for domain in sorted(scope.included):
            self.domain_selectors.setdefault(domain, []).append(selector)
        self.cosmetic_count += 1

    @classmethod
    def _css_block(cls, selectors: list[str]) -> str:
        blocks = []
        for start in range(0, len(selectors), cls._CSS_CHUNK):
            chunk = selectors[start : start + cls._CSS_CHUNK]
            blocks.append(", ".join(chunk) + " { display: none !important; }")
        return "\n".join(blocks)

    def cosmetic_selectors_for(self, host: str) -> list[str]:
        """Return active selectors after exact-selector exceptions and deduplication."""
        host = _normalize_rule_domain(host)
        parts = host.split(".") if host else []
        suffixes = [".".join(parts[index:]) for index in range(len(parts))] + [""]
        exceptions = {
            rule.selector
            for domain in suffixes
            for rule in self._cosmetic_exceptions.get(domain, ())
            if rule.domains.matches(host)
        }
        selectors = list(self.generic_selectors)
        for domain in suffixes:
            selectors.extend(self.domain_selectors.get(domain, ()))
            selectors.extend(
                rule.selector
                for rule in self._scoped_selectors.get(domain, ())
                if rule.domains.matches(host)
            )
        return list(dict.fromkeys(selector for selector in selectors if selector not in exceptions))

    def cosmetic_css_for(self, host: str) -> str:
        host = _normalize_rule_domain(host)
        cached = self._cosmetic_css_cache.get(host)
        if cached is not None:
            self._cosmetic_css_cache.move_to_end(host)
            return cached
        css = self._css_block(self.cosmetic_selectors_for(host))
        self._cosmetic_css_cache[host] = css
        if len(self._cosmetic_css_cache) > self.CSS_CACHE_CAP:
            self._cosmetic_css_cache.popitem(last=False)
        return css

    @staticmethod
    def _compile_pattern(body: str) -> re.Pattern[str] | None:
        text = body
        host_anchor = anchor_start = anchor_end = False
        if text.startswith("||"):
            host_anchor = True
            text = text[2:]
        elif text.startswith("|"):
            anchor_start = True
            text = text[1:]
        if text.endswith("|"):
            anchor_end = True
            text = text[:-1]
        if not text:
            return None
        parts: list[str] = []
        for char in text:
            if char == "*":
                parts.append(".*")
            elif char == "^":
                parts.append(r"(?:[^a-zA-Z0-9_.%-]|$)")
            else:
                parts.append(re.escape(char))
        regex = "".join(parts)
        if host_anchor:
            regex = r"^[a-z][a-z0-9+.-]*://(?:[^/?#]*\.)?" + regex
        elif anchor_start:
            regex = "^" + regex
        if anchor_end:
            regex += "$"
        try:
            return re.compile(regex, re.IGNORECASE)
        except re.error:
            return None

    def _pick_token(self, body: str) -> str | None:
        tokens: list[str] = []
        for segment in re.split(r"[*^|]", body.lower()):
            tokens.extend(self._TOKEN_RE.findall(segment))
        tokens = [token for token in tokens if token not in {"http", "https", "www"}]
        return max(tokens, key=len) if tokens else None

    def _matching_rules(
        self,
        url_text: str,
        buckets: dict[str, list[NetworkRule]],
        generic: Iterable[NetworkRule],
    ) -> Iterable[NetworkRule]:
        lowered = url_text.lower()
        for token in set(self._TOKEN_RE.findall(lowered)):
            yield from buckets.get(token, ())
        yield from generic

    def allows_request(
        self,
        url_text: str,
        host: str,
        resource_type: str = "other",
        first_party_host: str = "",
        document_host: str | None = None,
    ) -> bool:
        """Match exceptions, optionally scoping ``domain=`` to the requesting frame.

        ABP domain restrictions refer to the loading document, including iframes:
        https://help.adblockplus.org/adblock-plus-help-center/how-to-write-filters
        Omitting ``document_host`` preserves the top-level-host API behavior.
        """
        if domain_suffix_match(host, self.exception_domains) is not None:
            return True
        third_party = is_third_party_request(host, first_party_host)
        return any(
            rule.matches(url_text, resource_type, third_party, first_party_host, document_host)
            for rule in self._matching_rules(
                url_text, self.exception_token_buckets, self.generic_exceptions
            )
        )

    def is_exception_host(self, host: str) -> bool:
        """Compatibility helper for unconditional hostname exceptions."""
        return domain_suffix_match(host, self.exception_domains) is not None

    def should_block(
        self,
        url_text: str,
        host: str,
        resource_type: str = "other",
        first_party_host: str = "",
        document_host: str | None = None,
    ) -> bool:
        """Match rules using the page for party checks and the document for scopes."""
        if self.allows_request(url_text, host, resource_type, first_party_host, document_host):
            return False
        if domain_suffix_match(host, self.blocked_domains) is not None:
            return True
        third_party = is_third_party_request(host, first_party_host)
        return any(
            rule.matches(url_text, resource_type, third_party, first_party_host, document_host)
            for rule in self._matching_rules(url_text, self.token_buckets, self.generic_patterns)
        )

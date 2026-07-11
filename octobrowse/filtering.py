"""Fast, testable Adblock Plus subset used by OctoBrowse.

The parser intentionally supports a bounded part of the ABP grammar, but the
options it accepts are applied faithfully.  In particular, resource-type and
third-party rules must never silently degrade into unconditional blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


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

# Common multi-label public suffixes.  This deliberately small fallback avoids
# a network-updated PSL dependency while handling the domains users encounter
# most often. Exact/subdomain checks below cover intranet and custom suffixes.
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
    host = host.lower().strip(".")
    if not host:
        return ""
    labels = host.split(".")
    if len(labels) <= 2 or all(part.isdigit() for part in labels):
        return host
    suffix = ".".join(labels[-2:])
    if suffix in COMMON_MULTI_LABEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return suffix


def is_third_party_request(request_host: str, first_party_host: str) -> bool | None:
    """Return whether two hosts are cross-site, or ``None`` without an origin."""
    request_host = request_host.lower().strip(".")
    first_party_host = first_party_host.lower().strip(".")
    if not request_host or not first_party_host:
        return None
    if (
        request_host == first_party_host
        or request_host.endswith("." + first_party_host)
        or first_party_host.endswith("." + request_host)
    ):
        return False
    return _site_key(request_host) != _site_key(first_party_host)


@dataclass(frozen=True)
class NetworkRule:
    """Compiled network rule plus the ABP request constraints it carries."""

    pattern: re.Pattern[str]
    include_types: frozenset[str] = frozenset()
    exclude_types: frozenset[str] = frozenset()
    third_party: bool | None = None

    def matches(self, url: str, resource_type: str, third_party: bool | None) -> bool:
        if self.include_types and resource_type not in self.include_types:
            return False
        if resource_type in self.exclude_types:
            return False
        if self.third_party is not None and third_party is not self.third_party:
            return False
        return self.pattern.search(url) is not None


class FilterRuleSet:
    """A practical, indexed subset of the Adblock Plus filter grammar."""

    GENERIC_CAP = 200
    GENERIC_SELECTOR_CAP = 5000
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
        self.rule_count = 0
        self.cosmetic_count = 0
        self.skipped_count = 0
        self._generic_css: str | None = None

    def parse_text(self, text: str) -> None:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("!", "[")):
                continue
            if "#@#" in line or "#?#" in line or "#$#" in line:
                self.skipped_count += 1
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
            include_types, exclude_types, third_party = constraints
            rule = NetworkRule(pattern, include_types, exclude_types, third_party)
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
    ) -> tuple[frozenset[str], frozenset[str], bool | None] | None:
        include_types: set[str] = set()
        exclude_types: set[str] = set()
        third_party: bool | None = None
        if not options:
            return frozenset(), frozenset(), None
        for raw_option in options.split(","):
            option = raw_option.strip().lower()
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
        return frozenset(include_types), frozenset(exclude_types), third_party

    def _parse_cosmetic(self, line: str) -> None:
        domains_part, _, selector = line.partition("##")
        selector = selector.strip()
        if not selector or "{" in selector or "}" in selector:
            self.skipped_count += 1
            return
        domains_part = domains_part.strip().lower()
        if not domains_part:
            if len(self.generic_selectors) < self.GENERIC_SELECTOR_CAP:
                self.generic_selectors.append(selector)
                self.cosmetic_count += 1
            else:
                self.skipped_count += 1
            return
        if "~" in domains_part:
            self.skipped_count += 1
            return
        added = False
        for domain in domains_part.split(","):
            domain = domain.strip()
            if domain:
                self.domain_selectors.setdefault(domain, []).append(selector)
                added = True
        if added:
            self.cosmetic_count += 1
        else:
            self.skipped_count += 1

    @classmethod
    def _css_block(cls, selectors: list[str]) -> str:
        blocks = []
        for start in range(0, len(selectors), cls._CSS_CHUNK):
            chunk = selectors[start : start + cls._CSS_CHUNK]
            blocks.append(", ".join(chunk) + " { display: none !important; }")
        return "\n".join(blocks)

    def cosmetic_css_for(self, host: str) -> str:
        if self._generic_css is None:
            self._generic_css = self._css_block(self.generic_selectors)
        site_selectors: list[str] = []
        if host:
            parts = host.lower().strip(".").split(".")
            for index in range(len(parts)):
                site_selectors.extend(self.domain_selectors.get(".".join(parts[index:]), ()))
        site_css = self._css_block(site_selectors) if site_selectors else ""
        return "\n".join(part for part in (site_css, self._generic_css) if part)

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

    def _matching_rules(self, url_text: str, buckets: dict[str, list[NetworkRule]], generic: Iterable[NetworkRule]) -> Iterable[NetworkRule]:
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
    ) -> bool:
        if domain_suffix_match(host, self.exception_domains) is not None:
            return True
        third_party = is_third_party_request(host, first_party_host)
        return any(
            rule.matches(url_text, resource_type, third_party)
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
    ) -> bool:
        if self.allows_request(url_text, host, resource_type, first_party_host):
            return False
        if domain_suffix_match(host, self.blocked_domains) is not None:
            return True
        third_party = is_third_party_request(host, first_party_host)
        return any(
            rule.matches(url_text, resource_type, third_party)
            for rule in self._matching_rules(url_text, self.token_buckets, self.generic_patterns)
        )


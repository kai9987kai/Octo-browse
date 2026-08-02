"""A committed, offline subset of the Public Suffix List.

OctoBrowse needs to know where one *site* ends and another begins so that
``$third-party`` filter rules fire correctly.  Folding every host to its last
two labels gets this wrong for every multi-label suffix: ``tracker.github.io``
and ``victim.github.io`` are unrelated sites, but naive trimming makes them
look like one, which silently disables every third-party rule on exactly the
hosting platforms trackers use.

The real Public Suffix List is ~15,000 entries and is updated over the network.
OctoBrowse deliberately ships no network-updated data files, so this module
carries a hand-curated subset covering the suffixes that actually matter for
blocking: the ICANN ccTLD second levels users encounter, and the private-section
hosting platforms that let anybody publish under a shared parent domain.

Provenance: entries derive from https://publicsuffix.org/list/public_suffix_list.dat
(Mozilla Public License 2.0).  This subset is a snapshot, not a mirror.  Unknown
suffixes fall back to the list's own default rule (``*``), which is the same
last-two-labels behaviour used before this module existed, so an out-of-date
subset degrades to the old answer rather than to a wrong one.

The matching algorithm is the one specified by publicsuffix.org: collect every
rule matching the host, let an exception rule win over all others, otherwise
take the rule with the most labels, and default to ``*`` when nothing matches.
"""

from __future__ import annotations


__all__ = [
    "is_public_suffix",
    "public_suffix",
    "registrable_domain",
    "same_site",
]


_AWS_REGIONS = (
    "af-south-1",
    "ap-east-1",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ap-south-1",
    "ap-south-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-southeast-3",
    "ap-southeast-4",
    "ca-central-1",
    "eu-central-1",
    "eu-central-2",
    "eu-north-1",
    "eu-south-1",
    "eu-south-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "il-central-1",
    "me-central-1",
    "me-south-1",
    "sa-east-1",
    "us-east-1",
    "us-east-2",
    "us-gov-east-1",
    "us-gov-west-1",
    "us-west-1",
    "us-west-2",
)


# ICANN section: registries that delegate at the second level.
_ICANN_RULES = {
    # United Kingdom
    # NB: sch.uk is NOT here — the real PSL entry is the wildcard *.sch.uk,
    # so it lives in _WILDCARD_RULES. Listing it as a plain rule collapsed
    # every school under a local authority onto one site.
    "ac.uk", "co.uk", "gov.uk", "ltd.uk", "me.uk", "net.uk", "nhs.uk",
    "org.uk", "plc.uk", "police.uk",
    # Australia
    "asn.au", "com.au", "edu.au", "gov.au", "id.au", "net.au", "org.au",
    # New Zealand
    "ac.nz", "co.nz", "geek.nz", "gen.nz", "govt.nz", "health.nz", "iwi.nz",
    "kiwi.nz", "maori.nz", "mil.nz", "net.nz", "org.nz", "parliament.nz",
    "school.nz",
    # Japan
    "ac.jp", "ad.jp", "co.jp", "ed.jp", "go.jp", "gr.jp", "lg.jp", "ne.jp",
    "or.jp",
    # Brazil
    "art.br", "com.br", "edu.br", "gov.br", "net.br", "org.br",
    # China
    "ac.cn", "com.cn", "edu.cn", "gov.cn", "net.cn", "org.cn",
    # Hong Kong / Taiwan
    "com.hk", "edu.hk", "gov.hk", "idv.hk", "net.hk", "org.hk",
    "com.tw", "edu.tw", "gov.tw", "idv.tw", "net.tw", "org.tw",
    # Korea
    "ac.kr", "co.kr", "go.kr", "mil.kr", "ne.kr", "or.kr", "pe.kr", "re.kr",
    # India
    "ac.in", "co.in", "edu.in", "firm.in", "gen.in", "gov.in", "ind.in",
    "net.in", "org.in", "res.in",
    # South Africa
    "ac.za", "co.za", "gov.za", "net.za", "org.za", "web.za",
    # Mexico / Argentina
    "com.mx", "edu.mx", "gob.mx", "net.mx", "org.mx",
    "com.ar", "edu.ar", "gob.ar", "gov.ar", "int.ar", "mil.ar", "net.ar",
    "org.ar",
    # Turkey
    "bel.tr", "com.tr", "edu.tr", "gov.tr", "mil.tr", "net.tr", "org.tr",
    # South-East Asia
    "com.sg", "edu.sg", "gov.sg", "net.sg", "org.sg", "per.sg",
    "com.my", "edu.my", "gov.my", "net.my", "org.my",
    "ac.id", "biz.id", "co.id", "go.id", "my.id", "or.id", "web.id",
    "com.ph", "edu.ph", "gov.ph", "net.ph", "org.ph",
    "ac.th", "co.th", "go.th", "in.th", "mi.th", "net.th", "or.th",
    "com.vn", "edu.vn", "gov.vn", "net.vn", "org.vn",
    "com.pk", "edu.pk", "gov.pk", "net.pk", "org.pk",
    # Israel
    "ac.il", "co.il", "gov.il", "k12.il", "muni.il", "net.il", "org.il",
    # Russia / Ukraine / Poland
    "com.ru", "net.ru", "org.ru", "pp.ru",
    "com.ua", "in.ua", "net.ua", "org.ua",
    "com.pl", "edu.pl", "gov.pl", "info.pl", "net.pl", "org.pl",
    # Western Europe
    "com.es", "edu.es", "gob.es", "nom.es", "org.es",
    "edu.it", "gov.it",
    "co.nl",
    "com.de",
    # Canada provinces
    "ab.ca", "bc.ca", "gc.ca", "mb.ca", "nb.ca", "nf.ca", "nl.ca", "ns.ca",
    "nt.ca", "nu.ca", "on.ca", "pe.ca", "qc.ca", "sk.ca", "yk.ca",
    # Generic gTLD second levels
    "com.co", "net.co", "nom.co",
    "edu.eu.org", "eu.org",
}

# ICANN wildcard rules: every label under these is its own public suffix.
# Every parent of an entry in _EXCEPTION_RULES must appear here — an exception
# exists only to carve a hole in a matching wildcard, and shipping one without
# the other silently merges unrelated organisations onto a single site.
# test_public_suffix.py asserts that invariant.
_WILDCARD_RULES = {
    "bd", "ck", "er", "jm", "kh", "mm", "pg", "ye", "zw",
    "sch.uk",
    # The Japanese city domains carved out by the !city.<city>.jp exceptions.
    "kawasaki.jp", "kitakyushu.jp", "kobe.jp", "nagoya.jp", "sapporo.jp",
    "sendai.jp", "yokohama.jp",
    "compute.amazonaws.com", "compute-1.amazonaws.com",
    "elb.amazonaws.com",
    "s3.dualstack.amazonaws.com",
    "cloud.metacentrum.cz",
    "user.fm",
}

# Exception rules, written without their leading "!".
_EXCEPTION_RULES = {
    "www.ck",
    "city.kawasaki.jp",
    "city.kitakyushu.jp",
    "city.kobe.jp",
    "city.nagoya.jp",
    "city.sapporo.jp",
    "city.sendai.jp",
    "city.yokohama.jp",
}

# Private section: shared parents where unrelated parties publish side by side.
# Getting these right is what stops one user's subdomain being treated as the
# same site as another's.
_PRIVATE_RULES = {
    # Code hosting / pages
    "github.io", "githubusercontent.com", "github.dev", "gitlab.io",
    "bitbucket.io", "codeberg.page", "sourceforge.io", "js.org",
    "readthedocs.io", "neocities.org", "pythonanywhere.com",
    # Cloudflare
    "pages.dev", "workers.dev", "r2.dev", "trycloudflare.com",
    # Google
    "appspot.com", "cloudfunctions.net", "firebaseapp.com", "run.app",
    "web.app", "translate.goog", "withgoogle.com", "blogspot.com",
    # Amazon
    "cloudfront.net", "elasticbeanstalk.com", "amplifyapp.com",
    "awsapprunner.com", "awsglobalaccelerator.com", "s3.amazonaws.com",
    # Microsoft / Azure
    "azurewebsites.net", "azurestaticapps.net", "azureedge.net",
    "cloudapp.net", "cloudapp.azure.com", "blob.core.windows.net",
    "trafficmanager.net", "azurecontainer.io",
    # PaaS and preview hosts
    "herokuapp.com", "herokussl.com", "netlify.app", "vercel.app", "now.sh",
    "onrender.com", "fly.dev", "railway.app", "surge.sh", "glitch.me",
    "repl.co", "replit.dev", "ngrok.io", "ngrok-free.app", "ngrok.app",
    "deno.dev", "val.run", "cyclic.app", "koyeb.app",
    # Site builders and blogs
    "wordpress.com", "wpcomstaging.com", "myshopify.com", "wixsite.com",
    "editorx.io", "webflow.io", "notion.site", "webnode.page",
    "000webhostapp.com", "altervista.org", "strikingly.com",
    "framer.app", "framer.website", "bubbleapps.io", "carrd.co",
    # Dynamic DNS — classic shared-parent abuse vectors
    "duckdns.org", "hopto.org", "no-ip.org", "no-ip.biz", "ddns.net",
    "dynv6.net", "freemyip.com", "myftp.org", "serveftp.com",
    "servehttp.com", "sytes.net", "zapto.org",
    # Object storage and CDNs
    "backblazeb2.com", "digitaloceanspaces.com", "fastly-edge.com",
    "b-cdn.net", "cdn.digitaloceanspaces.com", "storage.yandexcloud.net",
}

_PRIVATE_RULES.update(f"s3.{region}.amazonaws.com" for region in _AWS_REGIONS)
_PRIVATE_RULES.update(f"s3-{region}.amazonaws.com" for region in _AWS_REGIONS)
_PRIVATE_RULES.update(
    f"s3-website.{region}.amazonaws.com" for region in _AWS_REGIONS
)

# One flat set is enough for site identity: OctoBrowse asks "are these the same
# publisher?", for which the private section is exactly as relevant as ICANN's.
_NORMAL_RULES = frozenset(_ICANN_RULES | _PRIVATE_RULES)
_WILDCARD = frozenset(_WILDCARD_RULES)
_EXCEPTIONS = frozenset(_EXCEPTION_RULES)

# Longest rule, in labels, so lookups stop early instead of walking every label.
_MAX_RULE_LABELS = max(
    max((rule.count(".") + 1 for rule in _NORMAL_RULES), default=1),
    max((rule.count(".") + 2 for rule in _WILDCARD), default=1),
    max((rule.count(".") + 1 for rule in _EXCEPTIONS), default=1),
)


def _normalize(host: str) -> str:
    """Reduce an authority to a bare lowercase hostname.

    Callers pass QUrl.host(), which is already bare, but the exported API is
    also reachable with a host:port pair or a bracketed IPv6 literal. Without
    stripping those, ``example.com:8080`` and ``example.com`` resolve to two
    different sites.
    """
    if not isinstance(host, str):
        return ""
    host = host.strip().lower()
    if host.startswith("["):
        closing = host.find("]")
        if closing > 0:
            return host[1:closing]
    # A single colon followed by digits is a port; more than one means IPv6.
    head, separator, tail = host.rpartition(":")
    if separator and head and ":" not in head and tail.isdigit():
        host = head
    return host.strip(".")


def _is_ip_literal(host: str) -> bool:
    if ":" in host:
        return True
    labels = host.split(".")
    return len(labels) == 4 and all(
        label.isdigit() and len(label) <= 3 for label in labels
    )


def public_suffix(host: str) -> str | None:
    """Return the public suffix of ``host``, or ``None`` if it has none.

    A single-label host (``localhost``) and an IP literal have no public
    suffix; neither does an empty string.
    """

    host = _normalize(host)
    if not host or _is_ip_literal(host):
        return None
    labels = host.split(".")
    if len(labels) < 2:
        return None

    limit = min(len(labels), _MAX_RULE_LABELS)

    # Exception rules win outright: the prevailing rule becomes the exception
    # with its leftmost label removed, so the exception host is registrable.
    for count in range(limit, 0, -1):
        candidate = ".".join(labels[len(labels) - count:])
        if candidate in _EXCEPTIONS:
            return ".".join(labels[len(labels) - count + 1:]) or None

    best: str | None = None
    best_labels = 0
    for count in range(limit, 0, -1):
        start = len(labels) - count
        candidate = ".".join(labels[start:])
        if candidate in _NORMAL_RULES and count > best_labels:
            best, best_labels = candidate, count
        # A wildcard rule "*.foo" matches when the labels after the first
        # match "foo", consuming one extra label.
        if count >= 2:
            wildcard_tail = ".".join(labels[start + 1:])
            if wildcard_tail in _WILDCARD and count > best_labels:
                best, best_labels = candidate, count

    if best is not None:
        return best
    # Default rule "*": the TLD alone is the public suffix.
    return labels[-1]


def registrable_domain(host: str) -> str | None:
    """Return the public suffix plus one label — the site identity of ``host``.

    Returns ``None`` when ``host`` is itself a public suffix (``github.io``,
    ``co.uk``) and so cannot identify a single publisher.  IP literals are
    returned unchanged: an address identifies exactly one origin.

    A single-label host is returned as its own site.  Without shipping the
    full ICANN TLD list there is no way to tell ``localhost`` or an intranet
    name apart from a bare TLD like ``com``, and treating real intranet hosts
    as sites matters far more than a bare TLD nobody browses.
    """

    host = _normalize(host)
    if not host:
        return None
    if _is_ip_literal(host):
        return host
    suffix = public_suffix(host)
    if suffix is None:
        return host if "." not in host else None
    if host == suffix:
        return None
    suffix_labels = suffix.count(".") + 1
    labels = host.split(".")
    if len(labels) <= suffix_labels:
        return None
    return ".".join(labels[len(labels) - suffix_labels - 1:])


def is_public_suffix(host: str) -> bool:
    """Whether ``host`` is a shared parent that no single party owns.

    ``github.io`` and ``co.uk`` are; ``user.github.io`` and ``localhost`` are
    not. Callers use this to tell a real shared ancestor from a suffix that
    merely looks like one.
    """

    host = _normalize(host)
    if not host or _is_ip_literal(host):
        return False
    return registrable_domain(host) is None


def same_site(left: str, right: str) -> bool:
    """Whether two hosts belong to the same registrable domain.

    Hosts that are themselves public suffixes never share a site with anything
    but their exact selves, which is what keeps ``a.github.io`` and
    ``b.github.io`` apart.
    """

    left = _normalize(left)
    right = _normalize(right)
    if not left or not right:
        return False
    if left == right:
        return True
    left_site = registrable_domain(left)
    right_site = registrable_domain(right)
    if left_site is None or right_site is None:
        return False
    return left_site == right_site

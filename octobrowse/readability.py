"""Bounded, text-only readable-page extraction for Qt WebEngine."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .ai_context import clean_page_text


MAX_READABLE_CHARS = 120_000
MAX_READABLE_TITLE_CHARS = 512
MAX_READABLE_URL_CHARS = 8_192
MAX_READABLE_BYLINE_CHARS = 512
MAX_READABLE_EXCERPT_CHARS = 1_000
MAX_READABLE_SITE_CHARS = 256
MAX_READABLE_LANGUAGE_CHARS = 32
MAX_READABLE_METHOD_CHARS = 64

_HORIZONTAL_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ReadablePage:
    """Normalized text and metadata returned by the in-page extractor."""

    text: str
    title: str
    url: str
    byline: str = ""
    excerpt: str = ""
    site_name: str = ""
    language: str = ""
    method: str = "fallback:plain-text"

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def reading_minutes(self) -> int:
        return max(1, round(self.word_count / 220)) if self.word_count else 0


def _single_line(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return _HORIZONTAL_SPACE_RE.sub(" ", value).strip()[:limit]


def normalize_readable_page(
    value: Any,
    *,
    fallback_title: Any = "",
    source_url: Any = "",
) -> ReadablePage:
    """Normalize an untrusted QVariant/JavaScript result without stringifying it."""

    record = value if isinstance(value, Mapping) else {}
    raw_text = record.get("text", "")
    if not isinstance(raw_text, str):
        raw_text = ""
    # Bound before Unicode/whitespace normalization as well as after it.
    text = clean_page_text(raw_text[: MAX_READABLE_CHARS * 2])
    text = text[:MAX_READABLE_CHARS].rstrip()
    title = _single_line(record.get("title"), MAX_READABLE_TITLE_CHARS)
    if not title:
        title = _single_line(fallback_title, MAX_READABLE_TITLE_CHARS)
    trusted_url = _single_line(source_url, MAX_READABLE_URL_CHARS)
    return ReadablePage(
        text=text,
        title=title,
        url=trusted_url,
        byline=_single_line(
            record.get("byline"),
            MAX_READABLE_BYLINE_CHARS,
        ),
        excerpt=_single_line(
            record.get("excerpt"),
            MAX_READABLE_EXCERPT_CHARS,
        ),
        site_name=_single_line(
            record.get("site_name"),
            MAX_READABLE_SITE_CHARS,
        ),
        language=_single_line(
            record.get("language"),
            MAX_READABLE_LANGUAGE_CHARS,
        ),
        method=_single_line(
            record.get("method"),
            MAX_READABLE_METHOD_CHARS,
        )
        or "fallback:plain-text",
    )


# This deliberately returns text, never page HTML. It runs in Qt's isolated
# ApplicationWorld so page scripts cannot replace its JavaScript globals.
READABLE_PAGE_SCRIPT = r"""
(() => {
  "use strict";
  const MAX_TEXT = 120000;
  const MAX_CANDIDATES = 40;
  const MAX_BLOCKS = 2500;
  const MAX_SCAN = 20000;
  const MAX_ANCESTORS = 64;
  const CANDIDATE_SELECTOR = [
    "article",
    "main",
    "[role='main']",
    "[itemprop='articleBody']",
    ".article-body",
    ".article-content",
    ".post-content",
    ".entry-content",
    "#article",
    "#content",
    ".content"
  ].join(",");
  const CONTENT_BOUNDARY_SELECTOR = [
    "article",
    "main",
    "[role='main']",
    "[itemprop='articleBody']"
  ].join(",");
  const NOISE_SELECTOR = [
    "script",
    "style",
    "noscript",
    "template",
    "nav",
    "aside",
    "footer",
    "form",
    "dialog",
    "[hidden]",
    "[aria-hidden='true']",
    "[role='navigation']",
    "[role='complementary']",
    "[role='dialog']",
    ".advertisement",
    ".ads",
    ".cookie-banner",
    ".cookie-consent",
    ".newsletter",
    ".paywall",
    ".popup",
    ".share-tools",
    ".social-share"
  ].join(",");
  const NOISE_NAME = /(?:^|[-_\s])(ad|ads|banner|breadcrumb|comment|cookie|footer|menu|modal|nav|newsletter|paywall|promo|related|share|sidebar|social|sponsor)(?:$|[-_\s])/i;
  const BLOCK_SELECTOR = "h1,h2,h3,h4,p,blockquote,pre,li,figcaption,dt,dd,td,th";

  const inlineText = value => String(value || "")
    .slice(0, MAX_TEXT * 2)
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  const identityIsNoise = node => {
    if (!(node instanceof Element)) {
      return false;
    }
    const identity = (
      `${typeof node.id === "string" ? node.id.slice(0, 256) : ""} `
      + `${typeof node.className === "string" ? node.className.slice(0, 256) : ""}`
    );
    return NOISE_NAME.test(identity);
  };

  const treeVisibilityCache = new WeakMap();
  const treeIsVisible = node => {
    if (!(node instanceof Element)) {
      return false;
    }
    if (treeVisibilityCache.has(node)) {
      return treeVisibilityCache.get(node);
    }
    const lineage = [];
    let current = node;
    let visible = true;
    let depth = 0;
    while (current instanceof Element) {
      if (treeVisibilityCache.has(current)) {
        visible = treeVisibilityCache.get(current);
        break;
      }
      if (depth >= MAX_ANCESTORS) {
        visible = false;
        break;
      }
      lineage.push(current);
      const ariaHidden = inlineText(
        current.getAttribute("aria-hidden")
      ).toLowerCase();
      const style = window.getComputedStyle(current);
      if (
        current.hasAttribute("hidden")
        || ariaHidden === "true"
        || style.display === "none"
        || style.visibility === "hidden"
        || Number(style.opacity || "1") === 0
      ) {
        visible = false;
        break;
      }
      current = current.parentElement;
      depth += 1;
    }
    for (const element of lineage) {
      treeVisibilityCache.set(element, visible);
    }
    return visible;
  };

  const isVisible = node => (
    treeIsVisible(node) && node.getClientRects().length > 0
  );

  const noiseTreeCache = new WeakMap();
  const hasNoiseAncestor = node => {
    if (!(node instanceof Element)) {
      return true;
    }
    if (noiseTreeCache.has(node)) {
      return noiseTreeCache.get(node);
    }
    const lineage = [];
    let current = node;
    let noisy = false;
    let depth = 0;
    while (current instanceof Element) {
      if (noiseTreeCache.has(current)) {
        noisy = noiseTreeCache.get(current);
        break;
      }
      if (depth >= MAX_ANCESTORS) {
        noisy = true;
        break;
      }
      lineage.push(current);
      const isContentBoundary = current.matches(
        CONTENT_BOUNDARY_SELECTOR
      );
      const isDocumentRoot = (
        current.tagName === "HTML" || current.tagName === "BODY"
      );
      if (
        current.matches(NOISE_SELECTOR)
        || (
          !isContentBoundary
          && !isDocumentRoot
          && identityIsNoise(current)
        )
      ) {
        noisy = true;
        break;
      }
      if (isContentBoundary) {
        break;
      }
      current = current.parentElement;
      depth += 1;
    }
    for (const element of lineage) {
      noiseTreeCache.set(element, noisy);
    }
    return noisy;
  };

  const collectElements = (
    root,
    predicate,
    matchLimit,
    visitLimit = MAX_SCAN
  ) => {
    const matches = [];
    if (!root) {
      return matches;
    }
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_ELEMENT
    );
    let visited = 0;
    let node = walker.nextNode();
    while (node && visited < visitLimit && matches.length < matchLimit) {
      visited += 1;
      if (predicate(node)) {
        matches.push(node);
      }
      node = walker.nextNode();
    }
    return matches;
  };

  const parentReadableCache = new WeakMap();
  const hasReadableParent = node => {
    const parent = node && node.parentElement;
    if (!parent) {
      return false;
    }
    if (parentReadableCache.has(parent)) {
      return parentReadableCache.get(parent);
    }
    const readable = !hasNoiseAncestor(parent) && isVisible(parent);
    parentReadableCache.set(parent, readable);
    return readable;
  };

  const boundedText = (
    root,
    maxChars = MAX_TEXT,
    visitLimit = MAX_SCAN
  ) => {
    if (!root) {
      return "";
    }
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT
    );
    const pieces = [];
    let length = 0;
    let visited = 0;
    let node = walker.nextNode();
    while (node && visited < visitLimit && length < maxChars) {
      visited += 1;
      if (hasReadableParent(node)) {
        const text = inlineText(node.nodeValue);
        if (text) {
          const remaining = maxChars - length;
          pieces.push(text.slice(0, remaining));
          length += Math.min(text.length, remaining) + 1;
        }
      }
      node = walker.nextNode();
    }
    return pieces.join(" ").slice(0, maxChars);
  };

  const boundedVisibleText = (
    root,
    maxChars = MAX_TEXT,
    visitLimit = MAX_SCAN
  ) => {
    if (!root) {
      return "";
    }
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT
    );
    const pieces = [];
    let length = 0;
    let visited = 0;
    let node = walker.nextNode();
    while (node && visited < visitLimit && length < maxChars) {
      visited += 1;
      const parent = node.parentElement;
      if (parent && isVisible(parent)) {
        const text = inlineText(node.nodeValue);
        if (text) {
          const remaining = maxChars - length;
          pieces.push(text.slice(0, remaining));
          length += Math.min(text.length, remaining) + 1;
        }
      }
      node = walker.nextNode();
    }
    return pieces.join(" ").slice(0, maxChars);
  };

  const candidateScore = node => {
    if (!isVisible(node) || hasNoiseAncestor(node)) {
      return {score: -1, length: 0};
    }
    const text = boundedText(node, 50000, 6000);
    if (text.length < 120) {
      return {score: -1, length: text.length};
    }
    const links = collectElements(
      node,
      element => element.tagName === "A",
      600,
      6000
    );
    const linkLength = links.reduce(
      (total, link) => total + boundedText(link, 2000, 500).length,
      0
    );
    const linkDensity = Math.min(0.95, linkLength / Math.max(1, text.length));
    const paragraphs = collectElements(
      node,
      element => element.tagName === "P",
      1200,
      6000
    );
    const substantialParagraphs = paragraphs.reduce(
      (total, paragraph) => total + (
        boundedText(paragraph, 100, 100).length >= 80 ? 1 : 0
      ),
      0
    );
    const punctuation = (text.match(/[.!?。！？]/g) || []).length;
    const tag = node.tagName.toLowerCase();
    const semanticBoost = tag === "article" ? 1.35 : tag === "main" ? 1.22 : 1;
    const score = (
      text.length + substantialParagraphs * 140 + punctuation * 8
    ) * Math.pow(1 - linkDensity, 2) * semanticBoost;
    return {score, length: text.length};
  };

  const candidates = collectElements(
    document.documentElement,
    element => element.matches(CANDIDATE_SELECTOR),
    MAX_CANDIDATES,
    MAX_SCAN
  );
  if (document.body) {
    candidates.push(document.body);
  }
  let root = document.body || document.documentElement;
  let best = {score: -1, length: 0};
  for (const candidate of candidates) {
    const scored = candidateScore(candidate);
    if (scored.score > best.score) {
      root = candidate;
      best = scored;
    }
  }

  const blocks = collectElements(
    root,
    element => element.matches(BLOCK_SELECTOR),
    MAX_BLOCKS,
    MAX_SCAN
  );
  const seen = new Set();
  const paragraphs = [];
  let outputLength = 0;
  for (const block of blocks) {
    if (
      outputLength >= MAX_TEXT
      || !isVisible(block)
      || hasNoiseAncestor(block)
    ) {
      continue;
    }
    const text = boundedText(
      block,
      Math.min(MAX_TEXT, MAX_TEXT - outputLength),
      5000
    );
    if (text.length < 2 || seen.has(text)) {
      continue;
    }
    const linkText = collectElements(
      block,
      element => element.tagName === "A",
      30,
      300
    ).reduce(
      (total, link) => total + boundedText(link, 500, 100).length,
      0
    );
    if (text.length < 160 && linkText / Math.max(1, text.length) > 0.75) {
      continue;
    }
    seen.add(text);
    const remaining = MAX_TEXT - outputLength;
    paragraphs.push(text.slice(0, remaining));
    outputLength += Math.min(text.length, remaining) + 2;
  }
  let text = paragraphs.join("\n\n").slice(0, MAX_TEXT);
  if (text.length < 120) {
    text = boundedText(root, MAX_TEXT, MAX_SCAN);
  }

  const meta = selector => {
    const node = document.querySelector(selector);
    return inlineText(node && node.getAttribute("content"));
  };
  const heading = collectElements(
    root,
    element => (
      element.tagName === "H1"
      && isVisible(element)
      && !hasNoiseAncestor(element)
    ),
    1,
    5000
  )[0];
  const author = collectElements(
    root,
    element => (
      element.matches(
        "[rel='author'],[itemprop='author'],.byline,.author"
      )
      && isVisible(element)
    ),
    1,
    5000
  )[0];
  const title = inlineText(
    (heading && boundedVisibleText(heading, 512, 200))
    || meta("meta[property='og:title']")
    || document.title
  ).slice(0, 512);
  const byline = boundedVisibleText(author, 512, 200);
  const excerpt = (
    meta("meta[name='description']")
    || meta("meta[property='og:description']")
    || text.slice(0, 280)
  ).slice(0, 1000);
  const siteName = meta("meta[property='og:site_name']").slice(0, 256);
  const language = inlineText(document.documentElement.lang).slice(0, 32);
  const method = root === document.body
    ? "fallback:body"
    : `semantic:${root.tagName.toLowerCase()}`;
  return {
    text,
    title,
    byline,
    excerpt,
    site_name: siteName,
    language,
    method
  };
})()
"""


__all__ = [
    "MAX_READABLE_CHARS",
    "READABLE_PAGE_SCRIPT",
    "ReadablePage",
    "normalize_readable_page",
]

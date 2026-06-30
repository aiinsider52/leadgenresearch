"""Validate discovered contacts and attach evidence-based confidence.

No email addresses are generated or guessed here. Only contacts already found
in public sources are normalized and assessed.
"""
from __future__ import annotations

import re
import socket
from functools import lru_cache
from urllib.parse import urlparse

import requests

from ..identity import domain, normalize_phone

EMAIL_RE = re.compile(r"^[^@\s]+@([a-z0-9.-]+\.[a-z]{2,})$", re.I)
GENERIC_LOCALPARTS = {
    "hello", "info", "contact", "office", "support", "sales", "team",
    "admin", "mail", "reception", "marketing", "jobs", "career", "hr",
}
FREE_EMAIL_DOMAINS = {
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com",
    "proton.me", "protonmail.com", "ukr.net", "mail.ru",
}


def _domain_resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


@lru_cache(maxsize=2048)
def _has_mx(host: str) -> bool:
    """Check mail routing through DNS-over-HTTPS. Does not send SMTP traffic."""
    try:
        response = requests.get(
            "https://dns.google/resolve", params={"name": host, "type": "MX"},
            headers={"Accept": "application/dns-json"}, timeout=5,
        )
        return response.ok and any(x.get("type") == 15 for x in response.json().get("Answer", []))
    except (requests.RequestException, ValueError):
        return False


def assess_contacts(enrichment: dict, website: str | None = None) -> dict:
    """Normalize discovered contacts and add `contact_quality` metadata."""
    en = dict(enrichment or {})
    company_domain = domain(website)
    emails, email_quality, seen = [], [], set()
    for raw in en.get("emails") or []:
        email = str(raw).strip().lower().rstrip(".,;:")
        match = EMAIL_RE.match(email)
        if not match or email in seen:
            continue
        seen.add(email)
        host = match.group(1).lower()
        local = email.split("@", 1)[0]
        same_domain = bool(company_domain and host == company_domain)
        resolves = _domain_resolves(host)
        has_mx = _has_mx(host) if resolves else False
        confidence = "high" if same_domain and has_mx else "medium" if has_mx else "low"
        email_quality.append({
            "email": email,
            "confidence": confidence,
            "same_domain": same_domain,
            "domain_resolves": resolves,
            "mx": has_mx,
            "smtp_checked": False,
            "generic": local in GENERIC_LOCALPARTS,
            "free_provider": host in FREE_EMAIL_DOMAINS,
            "evidence": "public_source",
            "evidence_pages": (en.get("pages_crawled") or [])[:5],
        })
        emails.append(email)

    phones, phone_quality, seen_phones = [], [], set()
    for raw in en.get("phones") or []:
        normalized = normalize_phone(raw)
        if not normalized or normalized in seen_phones:
            continue
        seen_phones.add(normalized)
        phones.append(str(raw).strip())
        phone_quality.append({
            "phone": str(raw).strip(),
            "normalized": normalized,
            "confidence": "medium",
            "evidence": "public_source",
        })

    people_quality = []
    for person in en.get("decision_makers") or []:
        source_url = person.get("source_url") or person.get("linkedin") or ""
        host = urlparse(source_url).netloc.lower()
        confidence = person.get("confidence") or (
            "high" if "linkedin.com/in/" in source_url else "medium" if host else "low"
        )
        person["confidence"] = confidence
        people_quality.append({
            "name": person.get("name"),
            "confidence": confidence,
            "source_url": source_url or None,
        })

    en["emails"] = emails
    en["phones"] = phones
    en["contact_quality"] = {
        "emails": email_quality,
        "phones": phone_quality,
        "decision_makers": people_quality,
        "verified_email_count": sum(x["confidence"] in ("high", "medium") for x in email_quality),
        "high_confidence_dm_count": sum(x["confidence"] == "high" for x in people_quality),
    }
    return en

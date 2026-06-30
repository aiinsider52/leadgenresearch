from __future__ import annotations

import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from leadgen.enrich.people import enrich_decision_makers
from leadgen.enrich.brave_people import _people_from_results
from leadgen.enrich.brave_signals import enrich_news_signals
from leadgen.enrich.brave_intent import enrich_intent_signals
from leadgen.enrich.contact_quality import assess_contacts
from leadgen.analyze.prescore import pre_score
from leadgen.analyze.scoring import score_lead
from leadgen.identity import company_keys, dedupe_companies, domain, normalize_text
from leadgen.sources.brave_places import discover_brave_places
from leadgen.sources.brave_intent import discover_brave_intent
from leadgen.sources.osm import Company
from leadgen.service import ALL_SOURCES, _dedupe_lead_dicts, _expand_search_terms, _merge_enrichment, find_leads, find_leads_multi, SearchResult, Lead
from leadgen import storage


class IdentityTests(unittest.TestCase):
    def test_domain_normalization(self):
        self.assertEqual(domain("https://www.Example.com/path"), "example.com")

    def test_company_name_normalization(self):
        self.assertEqual(normalize_text("Acme GmbH"), "acme")

    def test_cross_source_dedupe_merges_contacts(self):
        osm = Company("Acme GmbH", "agency", "Berlin", "Germany", phone="+49 30 123456",
                      source="osm", raw_tags={"_enrichment": {"emails": ["hello@acme.de"]}})
        maps = Company("ACME", "agency", "Berlin", "Germany", website="https://acme.de",
                       phone="+49 (30) 123456", source="gmaps",
                       raw_tags={"rating": 4.8, "_enrichment": {"phones": ["+4930123456"]}})
        merged = dedupe_companies([osm, maps])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].website, "https://acme.de")
        self.assertEqual(set(merged[0].raw_tags["_sources"]), {"osm", "gmaps"})
        self.assertIn("d:acme.de", company_keys(merged[0]))


class PeopleTests(unittest.TestCase):
    def test_promotes_executive_staff(self):
        enrichment = {
            "staff": [{"name": "Ada Lovelace", "role": "Founder & CEO", "source_url": "https://acme.test/team"}],
            "decision_makers": [], "linkedin_profiles": [],
        }
        out = enrich_decision_makers(enrichment, "Acme")
        self.assertEqual(out["decision_makers"][0]["name"], "Ada Lovelace")
        self.assertIn("linkedin_search", out["decision_makers"][0])

    def test_brave_people_rejects_snippet_false_names(self):
        results = [{
            "title": "Ada Lovelace - Founder & CEO at Acme",
            "description": "Ada Lovelace is founder and CEO of Acme",
            "url": "https://linkedin.com/in/ada-lovelace",
        }]
        people = _people_from_results(results, "Acme")
        self.assertEqual([p["name"] for p in people], ["Ada Lovelace"])

    @patch("leadgen.enrich.brave_signals.news_search")
    def test_brave_news_detects_buying_signal(self, search):
        search.return_value = [{
            "title": "Acme raises $20m funding",
            "description": "Acme closes funding round",
            "url": "https://news.test/acme",
        }]
        out = enrich_news_signals({"signals": {}}, "Acme")
        self.assertTrue(out["signals"]["funding"])
        self.assertTrue(out["signals"]["news_active"])

    @patch("leadgen.enrich.brave_intent.web_search")
    def test_brave_intent_detects_procurement(self, search):
        search.return_value = [{
            "title": "Acme publishes automation RFP",
            "description": "Acme procurement seeks automation partner",
            "url": "https://acme.test/rfp",
        }]
        out = enrich_intent_signals({"signals": {}}, "Acme")
        self.assertTrue(out["signals"]["tender"])
        self.assertTrue(out["signals"]["automation_need"])


class QualityTests(unittest.TestCase):
    @patch("leadgen.enrich.contact_quality._has_mx", return_value=True)
    @patch("leadgen.enrich.contact_quality._domain_resolves", return_value=True)
    def test_contact_quality_uses_only_discovered_email(self, resolves, has_mx):
        out = assess_contacts({"emails": ["INFO@ACME.TEST", "bad"], "phones": []},
                              "https://acme.test")
        self.assertEqual(out["emails"], ["info@acme.test"])
        self.assertEqual(out["contact_quality"]["emails"][0]["confidence"], "high")
        self.assertFalse(out["contact_quality"]["emails"][0]["smtp_checked"])

    def test_prescore_prioritizes_reachable_multisource_company(self):
        strong = pre_score({"website": "https://acme.test", "phone": "123",
                            "sources": ["osm", "gmaps"]})
        weak = pre_score({"name": "Unknown"})
        self.assertGreater(strong["score"], weak["score"])

    def test_score_exposes_dimensions(self):
        score = score_lead({"website": "https://acme.test"},
                           {"emails": ["info@acme.test"], "signals": {"tender": True}})
        self.assertGreater(score["dimensions"]["intent"], 0)
        self.assertGreater(score["dimensions"]["contactability"], 0)

    def test_sqlite_storage_upserts_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "leadgen.db"
            with patch("leadgen.db.DB_FILE", db_path), patch.dict(
                os.environ, {}, clear=False
            ):
                os.environ.pop("DATABASE_URL", None)
                from leadgen.db import init_schema

                init_schema()
                storage.upsert_lead("d:acme.test", {
                    "company": {"name": "Acme", "city": "Kyiv", "source": "brave_intent"},
                    "score": {"score": 75, "tier": "hot"},
                })
                self.assertEqual(storage.status()["leads"], 1)


class LeadStorageTests(unittest.TestCase):
    def test_alias_dedupe_merges_domain_and_phone_records(self):
        a = {"company": {"name": "Acme", "city": "Berlin", "phone": "+49 30 123456"},
             "enrichment": {"emails": ["hello@acme.de"]}}
        b = {"company": {"name": "ACME GmbH", "city": "Berlin", "website": "https://acme.de"},
             "enrichment": {"phones": ["+4930123456"]}}
        merged = _dedupe_lead_dicts([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["company"]["website"], "https://acme.de")

    def test_enrichment_merge_preserves_hiring_contact(self):
        base = {"decision_makers": [{"name": "Ada Lovelace", "role": "Hiring manager"}],
                "signals": {"hiring": True}}
        crawled = {"decision_makers": [{"name": "Grace Hopper", "role": "Founder"}],
                   "signals": {"blog_active": True}}
        merged = _merge_enrichment(base, crawled)
        self.assertEqual(len(merged["decision_makers"]), 2)
        self.assertEqual(merged["signals"], {"hiring": True, "blog_active": True})


class OrchestrationTests(unittest.TestCase):
    @patch("leadgen.service.record_pipeline_metrics")
    @patch("leadgen.service._process", return_value=[])
    @patch("leadgen.service._discover_source", return_value=[])
    def test_all_sources_fans_out(self, discover, process, record):
        find_leads("agency", "Kyiv", limit=2, source="all_sources",
                   enrich=False, discover_websites=False)
        used = {call.args[0] for call in discover.call_args_list}
        self.assertEqual(used, set(ALL_SOURCES))
        process.assert_called_once()
        record.assert_called_once()

    @patch("leadgen.service._discover_source", side_effect=RuntimeError("missing key"))
    def test_explicit_source_surfaces_failure(self, discover):
        with self.assertRaisesRegex(RuntimeError, "brave_places: missing key"):
            find_leads("agency", "Kyiv", source="brave_places",
                       enrich=False, discover_websites=False)

    @patch("leadgen.sources.brave_places.available", return_value=True)
    @patch("leadgen.sources.brave_places.place_search")
    def test_brave_places_maps_payload(self, search, available):
        search.return_value = [{
            "id": "123", "name": "Acme Cafe", "website": "https://acme.test",
            "phone": "+41 44 123 45 67", "address": "Main 1, Zurich",
            "coordinates": {"latitude": 47.3, "longitude": 8.5},
            "rating": 4.7, "review_count": 42, "categories": ["Cafe"],
        }]
        companies = discover_brave_places("cafe", "Zurich", "Switzerland", 5)
        self.assertEqual(companies[0].source, "brave_places")
        self.assertEqual(companies[0].raw_tags["place_id"], "brave:123")
        self.assertEqual(companies[0].lat, 47.3)

    @patch("leadgen.sources.brave_intent.available", return_value=True)
    @patch("leadgen.sources.brave_intent.web_search")
    def test_brave_intent_discovers_company_domain(self, search, available):
        search.return_value = [{
            "title": "Acme Agency - Automation RFP",
            "description": "Acme Agency publishes procurement tender",
            "url": "https://acme.test/news/rfp",
        }]
        companies = discover_brave_intent("agency", "Kyiv", "Ukraine", 5)
        self.assertEqual(companies[0].website, "https://acme.test")
        self.assertTrue(companies[0].raw_tags["_enrichment"]["signals"]["tender"])


class VolumeTests(unittest.TestCase):
    def test_all_sources_includes_linkedin_company(self):
        self.assertIn("linkedin_company", ALL_SOURCES)
        self.assertIn("facebook", ALL_SOURCES)

    def test_expand_osm_dedupes_synonyms(self):
        terms = _expand_search_terms("marketing agency", "en", "osm")
        self.assertTrue(terms)
        slugs = {t for t in terms}
        self.assertGreaterEqual(len(slugs), 1)

    @patch("leadgen.service.find_leads")
    def test_multi_city_pools_then_caps(self, find):
        def fake(cat, city, **kw):
            n = kw.get("limit", 1)
            leads = [
                Lead(company={"name": f"{city}-{i}", "city": city}, enrichment={},
                     score={"score": i + (10 if city == "Kyiv" else 0)})
                for i in range(n)
            ]
            return SearchResult(leads=leads, meta={"requested_limit": n, "returned": n,
                                                    "discovered_raw": n, "deduped_before_enrichment": n,
                                                    "capped": False, "cap_reason": None})

        find.side_effect = fake
        out = find_leads_multi("agency", ["Kyiv", "Lviv"], limit=12, enrich=False)
        self.assertEqual(len(out.leads), 12)
        self.assertEqual(find.call_count, 2)
        for call in find.call_args_list:
            self.assertEqual(call.kwargs.get("limit"), 20)


if __name__ == "__main__":
    unittest.main()

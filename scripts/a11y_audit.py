#!/usr/bin/env python3
"""Basic a11y / static quality checks for LeadGen static frontend."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "leadgen" / "static"
INDEX = STATIC / "index.html"


def main() -> int:
    issues: list[str] = []
    html = INDEX.read_text(encoding="utf-8")

    if "cdn.tailwindcss.com" in html:
        issues.append("Tailwind CDN still referenced in index.html")

    if "<style id=\"design-system\">" in html:
        issues.append("Inline design-system block should be externalized")

    if html.count("<script>") > 1:
        issues.append("Inline scripts should be in js/ modules")

    # Images / icons: interactive controls need accessible names
    buttons = re.findall(r"<button[^>]*>", html, re.I)
    unnamed = [b for b in buttons if "aria-label" not in b and "data-i" not in b and "id=" not in b]
    if len(unnamed) > 40:
        issues.append(f"Many buttons lack aria-label or data-i ({len(unnamed)} found)")

    if 'lang="uk"' not in html and 'lang="uk"' not in html:
        issues.append("html lang attribute missing")

    if 'id="searchProgress"' not in html:
        issues.append("search progress region missing")

    required_ids = [
        "runCity", "category", "cancelSearch", "searchForm", "leadModal",
        "results", "searchProgress", "agentPanel", "searchPanel",
    ]
    for rid in required_ids:
        if f'id="{rid}"' not in html and f"id='{rid}'" not in html:
            issues.append(f"Missing required id: #{rid}")

    css_files = list((STATIC / "css").glob("*.css"))
    js_files = list((STATIC / "js").glob("*.js"))
    if len(css_files) < 5:
        issues.append(f"Expected CSS modules, found {len(css_files)}")
    if len(js_files) < 8:
        issues.append(f"Expected JS modules, found {len(js_files)}")

    print("LeadGen static a11y / quality audit")
    print(f"  index.html: {len(html.splitlines())} lines")
    print(f"  css files: {len(css_files)}")
    print(f"  js files: {len(js_files)}")
    if issues:
        print("\nIssues:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

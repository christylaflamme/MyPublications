#!/usr/bin/env python3
"""Fetch all works for an ORCID from OpenAlex, save papers.json plus a review spreadsheet."""
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

ORCID = "0000-0002-0808-3475"
MAILTO = "asianflamme@gmail.com"
BASE = "https://api.openalex.org/works"

# Preprints with a published version already in the list — citations accrued
# while it was a preprint move over to the published paper, then this entry
# is dropped. Re-applied on every run; add a new pair here whenever a preprint
# graduates to a published paper.
MERGE_PREPRINT_INTO_PUBLISHED = {
    "https://openalex.org/W4413974933": "https://openalex.org/W7143332237",  # RNU2-2 preprint -> published article
    "https://openalex.org/W4366088864": "https://openalex.org/W4399796422",  # neuroblastoma preprint -> published article
    "https://openalex.org/W4387610109": "https://openalex.org/W4401368338",  # methylation preprint -> published article
}

# Duplicate/non-paper entries with no citations of their own — dropped outright,
# re-excluded on every run.
EXCLUDE_IDS = {
    "https://openalex.org/W7136096263",  # RNU2-2 paper, duplicate RWTH Aachen repository entry
    "https://openalex.org/W7155032657",  # RNU2-2 paper, duplicate RWTH Aachen repository entry
    "https://openalex.org/W4393093640",  # AACR conference abstract, restates a listed paper
    "https://openalex.org/W4402267054",  # AACR conference abstract, restates a listed paper
    "https://openalex.org/W3169989224",  # journal cover-art credit, not a research paper
}


def fetch_page(cursor):
    url = f"{BASE}?filter=author.orcid:{ORCID}&per-page=200&cursor={cursor}&mailto={MAILTO}"
    while True:
        try:
            with urllib.request.urlopen(url) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("Rate limited, waiting 5s...", file=sys.stderr)
                time.sleep(5)
                continue
            raise


def main():
    works = []
    cursor = "*"
    while cursor:
        data = fetch_page(cursor)
        works.extend(data["results"])
        cursor = data["meta"].get("next_cursor")
        if not data["results"]:
            break

    papers = []
    for w in works:
        location = w.get("primary_location") or {}
        source = location.get("source") or {}
        authors = [a["author"]["display_name"] for a in w.get("authorships", [])]
        counts_by_year = {c["year"]: c["cited_by_count"] for c in w.get("counts_by_year", [])}
        papers.append({
            "id": w["id"],
            "title": w.get("title"),
            "year": w.get("publication_year"),
            "type": w.get("type"),
            "venue": source.get("display_name"),
            "link": w.get("doi") or location.get("landing_page_url"),
            "cited_by_count": w.get("cited_by_count", 0),
            "counts_by_year": counts_by_year,
            "authors": authors,
        })

    by_id = {p["id"]: p for p in papers}
    for preprint_id, published_id in MERGE_PREPRINT_INTO_PUBLISHED.items():
        preprint, published = by_id.get(preprint_id), by_id.get(published_id)
        if preprint and published:
            published["cited_by_count"] += preprint["cited_by_count"]
            for year, count in preprint["counts_by_year"].items():
                published["counts_by_year"][year] = published["counts_by_year"].get(year, 0) + count

    drop_ids = EXCLUDE_IDS | set(MERGE_PREPRINT_INTO_PUBLISHED.keys())
    papers = [p for p in papers if p["id"] not in drop_ids]
    papers.sort(key=lambda p: (p["year"] or 0), reverse=True)

    with open("papers.json", "w") as f:
        json.dump(papers, f, indent=2)

    with open("papers_review.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["title", "year", "venue", "type", "co-authors", "cited_by_count", "link"])
        for p in papers:
            writer.writerow([
                p["title"], p["year"], p["venue"], p["type"],
                "; ".join(p["authors"]), p["cited_by_count"], p["link"],
            ])

    breakdown = Counter(p["type"] for p in papers)
    print(f"Fetched {len(papers)} works")
    for t, c in breakdown.most_common():
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()

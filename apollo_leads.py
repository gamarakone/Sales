"""
Apollo.io API integration for searching and enriching leads.

Apollo docs: https://apolloio.github.io/apollo-api-docs/
"""
import time
from typing import Any

import urllib.request
import urllib.error
import json

import config
from models import Lead

APOLLO_BASE = "https://api.apollo.io/v1"


def _post(endpoint: str, payload: dict) -> dict:
    payload["api_key"] = config.APOLLO_API_KEY
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{APOLLO_BASE}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"Apollo API error {exc.code}: {body}") from exc


def _lead_from_apollo_person(person: dict, org: dict | None = None) -> Lead:
    """Map an Apollo people-search result to a Lead."""
    org = org or person.get("organization") or {}
    employment = (person.get("employment_history") or [{}])[0]

    raw = {**person, "_org": org}
    lead = Lead(
        full_name=person.get("name", ""),
        first_name=person.get("first_name", ""),
        last_name=person.get("last_name", ""),
        email=person.get("email") or "",
        phone=person.get("phone_numbers", [{}])[0].get("raw_number", "") if person.get("phone_numbers") else "",
        title=person.get("title", ""),
        company=org.get("name") or person.get("organization_name", ""),
        company_domain=org.get("website_url", "").replace("https://", "").replace("http://", "").rstrip("/"),
        linkedin_url=person.get("linkedin_url", ""),
        website=org.get("website_url", ""),
        city=person.get("city", ""),
        state=person.get("state", ""),
        country=person.get("country", ""),
        source_actor="apollo",
        source_dataset="",
        raw=raw,
    )
    return lead


# ---------------------------------------------------------------------------
# People search
# ---------------------------------------------------------------------------

def search_people(
    titles: list[str] | None = None,
    companies: list[str] | None = None,
    locations: list[str] | None = None,
    keywords: str = "",
    seniorities: list[str] | None = None,
    industries: list[str] | None = None,
    page: int = 1,
    per_page: int = 100,
) -> tuple[list[Lead], int]:
    """
    Search Apollo for people matching the criteria.

    Returns (leads, total_count).

    seniorities: e.g. ["senior", "manager", "director", "vp", "c_suite", "founder"]
    """
    payload: dict[str, Any] = {"page": page, "per_page": per_page}
    if titles:
        payload["person_titles"] = titles
    if companies:
        payload["organization_names"] = companies
    if locations:
        payload["person_locations"] = locations
    if keywords:
        payload["q_keywords"] = keywords
    if seniorities:
        payload["person_seniorities"] = seniorities
    if industries:
        payload["organization_industry_tag_names"] = industries

    result = _post("/people/search", payload)
    people = result.get("people") or []
    total = result.get("pagination", {}).get("total_entries", len(people))
    leads = [_lead_from_apollo_person(p) for p in people]
    return leads, total


def search_people_all_pages(
    titles: list[str] | None = None,
    companies: list[str] | None = None,
    locations: list[str] | None = None,
    keywords: str = "",
    seniorities: list[str] | None = None,
    industries: list[str] | None = None,
    max_leads: int = 500,
    per_page: int = 100,
) -> list[Lead]:
    """Paginate through Apollo people search up to *max_leads*."""
    all_leads: list[Lead] = []
    page = 1
    while len(all_leads) < max_leads:
        batch, total = search_people(
            titles=titles,
            companies=companies,
            locations=locations,
            keywords=keywords,
            seniorities=seniorities,
            industries=industries,
            page=page,
            per_page=min(per_page, max_leads - len(all_leads)),
        )
        if not batch:
            break
        all_leads.extend(batch)
        print(f"  Page {page}: {len(batch)} results (total available: {total})")
        if len(all_leads) >= total:
            break
        page += 1
        time.sleep(0.5)  # be polite to the API
    return all_leads


# ---------------------------------------------------------------------------
# Single-person enrichment
# ---------------------------------------------------------------------------

def enrich_person(email: str = "", linkedin_url: str = "", name: str = "", domain: str = "") -> Lead | None:
    """Enrich a single contact by email, LinkedIn URL, or name+domain."""
    payload: dict[str, Any] = {"reveal_personal_emails": True}
    if email:
        payload["email"] = email
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url
    if name:
        payload["name"] = name
    if domain:
        payload["domain"] = domain
    result = _post("/people/match", payload)
    person = result.get("person")
    if not person:
        return None
    return _lead_from_apollo_person(person)


# ---------------------------------------------------------------------------
# Organisation search
# ---------------------------------------------------------------------------

def search_companies(
    names: list[str] | None = None,
    industries: list[str] | None = None,
    locations: list[str] | None = None,
    min_employees: int | None = None,
    max_employees: int | None = None,
    keywords: str = "",
    page: int = 1,
    per_page: int = 100,
) -> tuple[list[dict], int]:
    """Search Apollo for organisations. Returns (orgs, total_count)."""
    payload: dict[str, Any] = {"page": page, "per_page": per_page}
    if names:
        payload["organization_names"] = names
    if industries:
        payload["organization_industry_tag_names"] = industries
    if locations:
        payload["organization_locations"] = locations
    if min_employees is not None:
        payload["organization_num_employees_ranges"] = [
            f"{min_employees},{max_employees or 999999}"
        ]
    if keywords:
        payload["q_keywords"] = keywords
    result = _post("/organizations/search", payload)
    orgs = result.get("organizations") or []
    total = result.get("pagination", {}).get("total_entries", len(orgs))
    return orgs, total

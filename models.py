"""Lead data model — normalises raw Apify output into a consistent shape."""
from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class Lead:
    # Identity
    full_name: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""

    # Professional
    title: str = ""
    company: str = ""
    company_domain: str = ""
    linkedin_url: str = ""
    website: str = ""

    # Location
    city: str = ""
    state: str = ""
    country: str = ""

    # Metadata
    source_actor: str = ""
    source_dataset: str = ""
    raw: dict = field(default_factory=dict)

    # Candidate field names from various Apify actor outputs → Lead field
    _FIELD_MAP: dict = field(default_factory=lambda: {
        "name":            "full_name",
        "fullName":        "full_name",
        "full_name":       "full_name",
        "firstName":       "first_name",
        "first_name":      "first_name",
        "lastName":        "last_name",
        "last_name":       "last_name",
        "email":           "email",
        "emailAddress":    "email",
        "phone":           "phone",
        "phoneNumber":     "phone",
        "mobilePhone":     "phone",
        "title":           "title",
        "jobTitle":        "title",
        "position":        "title",
        "occupation":      "title",
        "company":         "company",
        "companyName":     "company",
        "organization":    "company",
        "employer":        "company",
        "companyDomain":   "company_domain",
        "domain":          "company_domain",
        "linkedinUrl":     "linkedin_url",
        "linkedin":        "linkedin_url",
        "profileUrl":      "linkedin_url",
        "url":             "linkedin_url",
        "website":         "website",
        "companyWebsite":  "website",
        "city":            "city",
        "location":        "city",
        "state":           "state",
        "country":         "country",
    }, repr=False)

    @classmethod
    def from_raw(cls, raw: dict[str, Any], source_actor: str = "", source_dataset: str = "") -> "Lead":
        lead = cls(source_actor=source_actor, source_dataset=source_dataset, raw=raw)
        field_map = lead._FIELD_MAP
        for raw_key, value in raw.items():
            mapped = field_map.get(raw_key)
            if mapped and isinstance(value, str) and value.strip():
                setattr(lead, mapped, value.strip())
        # Derive full_name if missing
        if not lead.full_name and (lead.first_name or lead.last_name):
            lead.full_name = f"{lead.first_name} {lead.last_name}".strip()
        return lead

    def to_dict(self) -> dict[str, Any]:
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name not in ("raw", "_FIELD_MAP")
        }

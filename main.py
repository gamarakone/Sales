"""
CLI for the leads integration (Apify + Apollo.io).

Usage examples:

  # --- Apollo (direct API) ---
  python main.py apollo-search --title "VP Sales" --location "New York" --max 200
  python main.py apollo-search --industry "SaaS" --seniority vp --seniority c_suite
  python main.py apollo-enrich --email jane@acme.com
  python main.py apollo-companies --industry "Fintech" --min-employees 50

  # --- Apify ---
  python main.py run --actor apify/linkedin-profile-scraper \
      --input '{"profileUrls": ["https://linkedin.com/in/..."]}'
  python main.py dataset --id <dataset_id>
  python main.py last-run --actor apify/linkedin-profile-scraper

  # --- Storage ---
  python main.py list --company "Acme"
  python main.py export --output leads.csv
  python main.py stats
"""
import json
import sys

import click

import apify_leads
import apollo_leads
import storage
from models import Lead


def _normalise_and_store(
    raw_items: list[dict],
    source_actor: str,
    source_dataset: str,
) -> None:
    leads = [Lead.from_raw(item, source_actor, source_dataset) for item in raw_items]
    inserted, skipped = storage.upsert_leads(leads)
    click.echo(f"Stored {inserted} new leads ({skipped} duplicates skipped).")


def _store_leads(leads: list[Lead]) -> None:
    inserted, skipped = storage.upsert_leads(leads)
    click.echo(f"Stored {inserted} new leads ({skipped} duplicates skipped).")


@click.group()
def cli():
    """Leads integration — Apollo.io + Apify — pull, store, and export."""
    storage.init_db()


# ---------------------------------------------------------------------------
# Apollo commands
# ---------------------------------------------------------------------------

@cli.command("apollo-search")
@click.option("--title", "titles", multiple=True, help="Job title filter (repeatable)")
@click.option("--company", "companies", multiple=True, help="Company name filter (repeatable)")
@click.option("--location", "locations", multiple=True, help="Location filter (repeatable)")
@click.option("--industry", "industries", multiple=True, help="Industry tag (repeatable)")
@click.option("--seniority", "seniorities", multiple=True,
              help="Seniority level: senior|manager|director|vp|c_suite|founder (repeatable)")
@click.option("--keywords", default="", help="Keyword search string")
@click.option("--max", "max_leads", default=100, show_default=True, help="Max leads to pull")
def apollo_search(titles, companies, locations, industries, seniorities, keywords, max_leads):
    """Search Apollo.io for people and store results."""
    click.echo(f"Searching Apollo for up to {max_leads} leads...")
    leads = apollo_leads.search_people_all_pages(
        titles=list(titles) or None,
        companies=list(companies) or None,
        locations=list(locations) or None,
        industries=list(industries) or None,
        seniorities=list(seniorities) or None,
        keywords=keywords,
        max_leads=max_leads,
    )
    click.echo(f"Found {len(leads)} leads from Apollo.")
    _store_leads(leads)


@cli.command("apollo-enrich")
@click.option("--email", default="", help="Email address to enrich")
@click.option("--linkedin", default="", help="LinkedIn URL to enrich")
@click.option("--name", default="", help="Full name (use with --domain)")
@click.option("--domain", default="", help="Company domain (use with --name)")
def apollo_enrich(email, linkedin, name, domain):
    """Enrich a single contact via Apollo.io and store the result."""
    if not any([email, linkedin, name]):
        click.echo("Provide at least one of --email, --linkedin, or --name.", err=True)
        sys.exit(1)
    lead = apollo_leads.enrich_person(email=email, linkedin_url=linkedin, name=name, domain=domain)
    if not lead:
        click.echo("No match found in Apollo.")
        return
    click.echo(f"Enriched: {lead.full_name} | {lead.title} | {lead.company} | {lead.email}")
    _store_leads([lead])


@cli.command("apollo-companies")
@click.option("--name", "names", multiple=True, help="Company name filter (repeatable)")
@click.option("--industry", "industries", multiple=True, help="Industry tag (repeatable)")
@click.option("--location", "locations", multiple=True, help="Location filter (repeatable)")
@click.option("--min-employees", type=int, default=None, help="Min employee count")
@click.option("--max-employees", type=int, default=None, help="Max employee count")
@click.option("--keywords", default="", help="Keyword search string")
@click.option("--page", default=1, show_default=True)
def apollo_companies(names, industries, locations, min_employees, max_employees, keywords, page):
    """Search Apollo.io for companies (outputs to terminal, not stored)."""
    orgs, total = apollo_leads.search_companies(
        names=list(names) or None,
        industries=list(industries) or None,
        locations=list(locations) or None,
        min_employees=min_employees,
        max_employees=max_employees,
        keywords=keywords,
        page=page,
    )
    click.echo(f"Found {total} companies (showing page {page}):")
    for org in orgs:
        click.echo(
            f"  {org.get('name', '?')}  |  "
            f"{org.get('website_url', '')}  |  "
            f"employees={org.get('estimated_num_employees', '?')}  |  "
            f"industry={org.get('industry', '')}"
        )


@cli.command()
@click.option("--actor", required=True, help="Apify actor ID (e.g. apify/website-content-crawler)")
@click.option("--input", "run_input", default="{}", show_default=True,
              help="JSON string passed as actor input")
@click.option("--timeout", default=300, show_default=True,
              help="Max seconds to wait for the actor run")
@click.option("--limit", default=1000, show_default=True,
              help="Max number of items to fetch from the result dataset")
def run(actor: str, run_input: str, timeout: int, limit: int):
    """Run an Apify actor and store its output as leads."""
    try:
        parsed_input = json.loads(run_input)
    except json.JSONDecodeError as exc:
        click.echo(f"Error: --input is not valid JSON: {exc}", err=True)
        sys.exit(1)
    items = apify_leads.pull_leads_from_actor(actor, parsed_input, timeout, limit)
    dataset_id = items[0].get("datasetId", "") if items else ""
    leads = [Lead.from_raw(item, source_actor=actor, source_dataset=dataset_id) for item in items]
    _store_leads(leads)


@cli.command()
@click.option("--id", "dataset_id", required=True, help="Apify dataset ID")
@click.option("--actor", default="", help="Actor label to attach to stored leads (optional)")
@click.option("--limit", default=1000, show_default=True, help="Max items to fetch")
def dataset(dataset_id: str, actor: str, limit: int):
    """Fetch leads from an existing Apify dataset."""
    items = apify_leads.pull_leads_from_dataset(dataset_id, limit)
    leads = [Lead.from_raw(item, source_actor=actor, source_dataset=dataset_id) for item in items]
    _store_leads(leads)


@cli.command("last-run")
@click.option("--actor", required=True, help="Apify actor ID")
@click.option("--limit", default=1000, show_default=True, help="Max items to fetch")
def last_run(actor: str, limit: int):
    """Fetch leads from the most recent successful run of an actor."""
    items = apify_leads.pull_leads_from_last_run(actor, limit)
    leads = [Lead.from_raw(item, source_actor=actor, source_dataset="") for item in items]
    _store_leads(leads)


@cli.command("list")
@click.option("--company", default="", help="Filter by company name (partial match)")
@click.option("--email", default="", help="Filter by email (partial match)")
@click.option("--name", default="", help="Filter by full name (partial match)")
@click.option("--limit", default=50, show_default=True)
def list_leads(company: str, email: str, name: str, limit: int):
    """List stored leads, optionally filtered."""
    rows = storage.query_leads(company=company, email=email, name=name, limit=limit)
    if not rows:
        click.echo("No leads found.")
        return
    for row in rows:
        parts = [
            row.get("full_name") or "(no name)",
            row.get("title") or "",
            row.get("company") or "",
            row.get("email") or "",
        ]
        click.echo("  |  ".join(p for p in parts if p))


@cli.command()
@click.option("--output", default="leads.csv", show_default=True, help="Output CSV file path")
@click.option("--company", default="", help="Filter by company name")
@click.option("--email", default="", help="Filter by email")
@click.option("--name", default="", help="Filter by name")
def export(output: str, company: str, email: str, name: str):
    """Export leads to a CSV file."""
    count = storage.export_to_csv(output, company=company, email=email, name=name)
    click.echo(f"Exported {count} leads to '{output}'.")


@cli.command()
def stats():
    """Show total number of stored leads."""
    total = storage.count_leads()
    click.echo(f"Total leads in database: {total}")


@cli.command()
def insights():
    """Show analytics and breakdowns of stored leads."""
    data = storage.insights_data()
    total = data["total"]
    if total == 0:
        click.echo("No leads in database yet.")
        return

    def pct(n):
        return f"{n / total * 100:.0f}%" if total else "—"

    def bar(n, width=20):
        filled = round(n / total * width) if total else 0
        return "█" * filled + "░" * (width - filled)

    click.echo("")
    click.echo("━━━  Lead Database Insights  ━━━")
    click.echo(f"  Total leads : {total:,}")
    click.echo(f"  With email  : {data['with_email']:,}  ({pct(data['with_email'])})")
    click.echo(f"  With LinkedIn: {data['with_linkedin']:,}  ({pct(data['with_linkedin'])})")
    click.echo(f"  With phone  : {data['with_phone']:,}  ({pct(data['with_phone'])})")

    if data["by_source"]:
        click.echo("")
        click.echo("── By Source ──")
        for row in data["by_source"]:
            src = row["source_actor"] or "(unknown)"
            cnt = row["cnt"]
            click.echo(f"  {src:<40}  {cnt:>6,}  {bar(cnt)}")

    if data["top_countries"]:
        click.echo("")
        click.echo("── Top Countries ──")
        for row in data["top_countries"]:
            click.echo(f"  {row['country']:<30}  {row['cnt']:>6,}  {bar(row['cnt'])}")

    if data["top_companies"]:
        click.echo("")
        click.echo("── Top Companies ──")
        for row in data["top_companies"]:
            click.echo(f"  {row['company']:<35}  {row['cnt']:>6,}")

    if data["top_titles"]:
        click.echo("")
        click.echo("── Top Titles ──")
        for row in data["top_titles"]:
            click.echo(f"  {row['title']:<40}  {row['cnt']:>6,}")

    if data["by_day"]:
        click.echo("")
        click.echo("── Leads Added (last 14 days) ──")
        for row in reversed(data["by_day"]):
            click.echo(f"  {row['day']}  {row['cnt']:>6,}  {bar(row['cnt'])}")

    click.echo("")


@cli.command("list-datasets")
@click.option("--limit", default=20, show_default=True)
def list_datasets(limit: int):
    """List recent Apify datasets in your account."""
    datasets = apify_leads.list_datasets(limit)
    if not datasets:
        click.echo("No datasets found.")
        return
    for ds in datasets:
        click.echo(f"{ds.get('id')}  items={ds.get('itemCount', '?')}  name={ds.get('name', '')}")


@cli.command("list-runs")
@click.option("--actor", required=True, help="Apify actor ID")
@click.option("--limit", default=10, show_default=True)
def list_runs(actor: str, limit: int):
    """List recent runs of an Apify actor."""
    runs = apify_leads.list_actor_runs(actor, limit)
    if not runs:
        click.echo("No runs found.")
        return
    for r in runs:
        click.echo(
            f"{r.get('id')}  status={r.get('status')}  "
            f"dataset={r.get('defaultDatasetId')}  "
            f"started={r.get('startedAt', '')[:19]}"
        )


if __name__ == "__main__":
    cli()

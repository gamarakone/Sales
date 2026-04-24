"""
CLI for the Apify leads integration.

Usage examples:

  # Run an actor and store results
  python main.py run --actor apify/linkedin-profile-scraper \
      --input '{"profileUrls": ["https://linkedin.com/in/..."]}'

  # Pull from an existing dataset (no new run)
  python main.py dataset --id <dataset_id>

  # Pull from the last successful run of an actor
  python main.py last-run --actor apify/linkedin-profile-scraper

  # List stored leads
  python main.py list --company "Acme"

  # Export to CSV
  python main.py export --output leads.csv

  # Show total count
  python main.py stats
"""
import json
import sys

import click

import apify_leads
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


@click.group()
def cli():
    """Apify leads integration — pull, store, and export leads."""
    storage.init_db()


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
    _normalise_and_store(items, source_actor=actor, source_dataset=dataset_id)


@cli.command()
@click.option("--id", "dataset_id", required=True, help="Apify dataset ID")
@click.option("--actor", default="", help="Actor label to attach to stored leads (optional)")
@click.option("--limit", default=1000, show_default=True, help="Max items to fetch")
def dataset(dataset_id: str, actor: str, limit: int):
    """Fetch leads from an existing Apify dataset."""
    items = apify_leads.pull_leads_from_dataset(dataset_id, limit)
    _normalise_and_store(items, source_actor=actor, source_dataset=dataset_id)


@cli.command("last-run")
@click.option("--actor", required=True, help="Apify actor ID")
@click.option("--limit", default=1000, show_default=True, help="Max items to fetch")
def last_run(actor: str, limit: int):
    """Fetch leads from the most recent successful run of an actor."""
    items = apify_leads.pull_leads_from_last_run(actor, limit)
    _normalise_and_store(items, source_actor=actor, source_dataset="")


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

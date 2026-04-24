"""
Apify integration for pulling leads from actors and datasets.
"""
import time
from typing import Any

from apify_client import ApifyClient

import config


def _client() -> ApifyClient:
    return ApifyClient(config.APIFY_API_KEY)


# ---------------------------------------------------------------------------
# Actor management
# ---------------------------------------------------------------------------

def run_actor(actor_id: str, run_input: dict[str, Any], timeout_secs: int = 300) -> str:
    """Run an Apify actor and wait for it to finish. Returns the default dataset ID."""
    client = _client()
    print(f"Starting actor '{actor_id}'...")
    run = client.actor(actor_id).call(run_input=run_input, timeout_secs=timeout_secs)
    status = run.get("status")
    dataset_id = run.get("defaultDatasetId")
    print(f"Actor run finished with status '{status}'. Dataset: {dataset_id}")
    if status != "SUCCEEDED":
        raise RuntimeError(f"Actor run did not succeed (status={status}). Check Apify console for details.")
    return dataset_id


# ---------------------------------------------------------------------------
# Dataset fetching
# ---------------------------------------------------------------------------

def fetch_dataset_items(dataset_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Return all items from an Apify dataset (up to *limit*)."""
    client = _client()
    items = list(
        client.dataset(dataset_id).iterate_items(limit=limit)
    )
    print(f"Fetched {len(items)} items from dataset '{dataset_id}'.")
    return items


def list_datasets(limit: int = 50) -> list[dict[str, Any]]:
    """List the most recent datasets in the account."""
    client = _client()
    datasets = list(client.datasets().list(limit=limit).items)
    return datasets


def list_actor_runs(actor_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """List recent runs for a given actor."""
    client = _client()
    runs = list(client.actor(actor_id).runs().list(limit=limit).items)
    return runs


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

def pull_leads_from_actor(
    actor_id: str,
    run_input: dict[str, Any],
    timeout_secs: int = 300,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Run an actor and return its output items as a flat list."""
    dataset_id = run_actor(actor_id, run_input, timeout_secs)
    return fetch_dataset_items(dataset_id, limit)


def pull_leads_from_dataset(dataset_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Fetch leads directly from an existing dataset (no new run)."""
    return fetch_dataset_items(dataset_id, limit)


def pull_leads_from_last_run(actor_id: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Fetch leads from the most recent successful run of an actor."""
    client = _client()
    runs = list(client.actor(actor_id).runs().list(limit=10).items)
    succeeded = [r for r in runs if r.get("status") == "SUCCEEDED"]
    if not succeeded:
        raise RuntimeError(f"No successful runs found for actor '{actor_id}'.")
    latest = succeeded[0]
    dataset_id = latest["defaultDatasetId"]
    print(f"Using dataset '{dataset_id}' from run '{latest['id']}'.")
    return fetch_dataset_items(dataset_id, limit)

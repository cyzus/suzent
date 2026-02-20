"""
CLI subcommands for cron job management.

Usage:
    suzent cron list
    suzent cron add --name "daily-report" --cron "0 9 * * *" --prompt "Summarize my inbox"
    suzent cron edit <job_id> --name "new-name" --cron "0 10 * * *"
    suzent cron trigger <job_id>
    suzent cron remove <job_id>
    suzent cron toggle <job_id>
    suzent cron history <job_id>
    suzent cron status
"""

from datetime import datetime
from typing import Optional

import typer

from suzent.cli._http import _http_delete, _http_get, _http_post, _http_put

cron_app = typer.Typer(help="Manage scheduled cron jobs.")


@cron_app.command("list")
def list_jobs(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full details"),
):
    """List all scheduled cron jobs."""
    data = _http_get("/cron/jobs")
    jobs = data.get("jobs", [])

    if not jobs:
        typer.echo("No cron jobs configured.")
        return

    for job in jobs:
        status = "ON" if job["active"] else "OFF"
        typer.echo(
            f"  #{job['id']:>3}  [{status}]  {job['name']:<20}  {job['cron_expr']:<15}"
        )

        if verbose:
            prompt = job["prompt"]
            typer.echo(
                f"        Prompt:   {prompt[:80]}{'...' if len(prompt) > 80 else ''}"
            )
            typer.echo(f"        Delivery: {job['delivery_mode']}")
            if job.get("model_override"):
                typer.echo(f"        Model:    {job['model_override']}")
            typer.echo(f"        Last run: {job['last_run_at'] or '-'}")
            typer.echo(f"        Next run: {job['next_run_at'] or '-'}")
            if job.get("last_result"):
                result = job["last_result"][:100]
                typer.echo(f"        Result:   {result}")
            if job.get("last_error"):
                typer.echo(f"        Error:    {job['last_error']}")
            typer.echo()

    typer.echo(
        f"\n  {len(jobs)} job(s) total, {sum(1 for j in jobs if j['active'])} active"
    )


@cron_app.command("add")
def add_job(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    cron: str = typer.Option(
        ..., "--cron", "-c", help="Cron expression (e.g. '*/5 * * * *')"
    ),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt to execute"),
    delivery: str = typer.Option(
        "announce", "--delivery", "-d", help="Delivery mode: announce or none"
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model override"),
    inactive: bool = typer.Option(False, "--inactive", help="Create in disabled state"),
):
    """Create a new cron job — runs a prompt on schedule in an isolated session."""
    payload = {
        "name": name,
        "cron_expr": cron,
        "prompt": prompt,
        "delivery_mode": delivery,
        "model_override": model,
        "active": not inactive,
    }

    data = _http_post("/cron/jobs", payload)
    job = data.get("job", {})
    typer.echo(f"Created cron job #{job.get('id')}: {name}")
    typer.echo(f"  Schedule: {cron}")
    typer.echo(f"  Next run: {job.get('next_run_at', '-')}")


@cron_app.command("remove")
def remove_job(
    job_id: int = typer.Argument(..., help="Job ID to delete"),
):
    """Delete a cron job."""
    _http_delete(f"/cron/jobs/{job_id}")
    typer.echo(f"Deleted job #{job_id}")


@cron_app.command("trigger")
def trigger_job(
    job_id: int = typer.Argument(..., help="Job ID to trigger immediately"),
):
    """Trigger immediate execution of a cron job."""
    _http_post(f"/cron/jobs/{job_id}/trigger")
    typer.echo(f"Triggered job #{job_id}")


@cron_app.command("toggle")
def toggle_job(
    job_id: int = typer.Argument(..., help="Job ID to toggle"),
):
    """Toggle a cron job active/inactive."""
    # First get current state
    jobs_data = _http_get("/cron/jobs")
    jobs = jobs_data.get("jobs", [])
    job = next((j for j in jobs if j["id"] == job_id), None)

    if not job:
        typer.echo(f"Job #{job_id} not found.")
        raise typer.Exit(code=1)

    new_state = not job["active"]
    _http_put(f"/cron/jobs/{job_id}", {"active": new_state})
    state_str = "activated" if new_state else "deactivated"
    typer.echo(f"Job #{job_id} ({job['name']}) {state_str}")


@cron_app.command("edit")
def edit_job(
    job_id: int = typer.Argument(..., help="Job ID to edit"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New job name"),
    cron: Optional[str] = typer.Option(
        None, "--cron", "-c", help="New cron expression"
    ),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="New prompt"),
    delivery: Optional[str] = typer.Option(
        None, "--delivery", "-d", help="Delivery mode: announce or none"
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Model override (use 'none' to clear)"
    ),
):
    """Edit an existing cron job's fields."""
    updates = {}
    if name is not None:
        updates["name"] = name
    if cron is not None:
        updates["cron_expr"] = cron
    if prompt is not None:
        updates["prompt"] = prompt
    if delivery is not None:
        updates["delivery_mode"] = delivery
    if model is not None:
        updates["model_override"] = None if model.lower() == "none" else model

    if not updates:
        typer.echo(
            "No fields to update. Use --name, --cron, --prompt, --delivery, or --model."
        )
        raise typer.Exit(code=1)

    data = _http_put(f"/cron/jobs/{job_id}", updates)
    job = data.get("job", {})
    typer.echo(f"Updated job #{job_id}: {job.get('name', '?')}")
    if cron is not None:
        typer.echo(f"  Next run: {job.get('next_run_at', '-')}")


@cron_app.command("history")
def job_history(
    job_id: int = typer.Argument(..., help="Job ID"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of recent runs"),
):
    """Show run history for a cron job."""
    data = _http_get(f"/cron/jobs/{job_id}/runs?limit={limit}")
    runs = data.get("runs", [])

    if not runs:
        typer.echo(f"No run history for job #{job_id}.")
        return

    status_icons = {"success": "+", "error": "x", "running": "~"}

    for run in runs:
        icon = status_icons.get(run["status"], "?")
        started = run["started_at"][:19].replace("T", " ")
        duration = ""
        if finished := run.get("finished_at"):
            try:
                s = datetime.fromisoformat(run["started_at"])
                f = datetime.fromisoformat(finished)
                duration = f" ({int((f - s).total_seconds())}s)"
            except ValueError:
                pass

        typer.echo(f"  [{icon}] {started}{duration}")
        if run.get("result"):
            typer.echo(f"      {run['result'][:100]}")
        if run.get("error"):
            typer.echo(f"      ERROR: {run['error'][:100]}")


@cron_app.command("status")
def scheduler_status():
    """Show scheduler status and job counts."""
    data = _http_get("/cron/status")
    running = data.get("scheduler_running", False)
    total = data.get("total_jobs", 0)
    active = data.get("active_jobs", 0)

    status = "RUNNING" if running else "STOPPED"
    typer.echo(f"  Scheduler: {status}")
    typer.echo(f"  Jobs:      {active} active / {total} total")

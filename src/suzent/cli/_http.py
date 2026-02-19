"""
Shared HTTP helpers for CLI commands that talk to the running server.
"""

import os

import typer


def get_server_url() -> str:
    """Get the server URL from environment or default."""
    port = os.getenv("SUZENT_PORT", "8000")
    host = os.getenv("SUZENT_HOST", "localhost")
    return os.getenv("SUZENT_SERVER_URL", f"http://{host}:{port}")


def _http_get(path: str) -> dict:
    """Make a GET request to the running server."""
    import httpx

    url = f"{get_server_url()}{path}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        typer.echo("❌ Cannot connect to Suzent server. Is it running?")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"❌ Server error: {e.response.status_code}")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"❌ Error: {e}")
        raise typer.Exit(code=1)


def _http_post(path: str, data: dict = None) -> dict:
    """Make a POST request to the running server."""
    import httpx

    url = f"{get_server_url()}{path}"
    try:
        resp = httpx.post(url, json=data or {}, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        typer.echo("❌ Cannot connect to Suzent server. Is it running?")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("error", str(e))
        except Exception:
            detail = str(e)
        typer.echo(f"❌ Server error: {detail}")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"❌ Error: {e}")
        raise typer.Exit(code=1)


def _http_put(path: str, data: dict = None) -> dict:
    """Make a PUT request to the running server."""
    import httpx

    url = f"{get_server_url()}{path}"
    try:
        resp = httpx.put(url, json=data or {}, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        typer.echo("Cannot connect to Suzent server. Is it running?")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("error", str(e))
        except Exception:
            detail = str(e)
        typer.echo(f"Server error: {detail}")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)


def _http_delete(path: str) -> dict:
    """Make a DELETE request to the running server."""
    import httpx

    url = f"{get_server_url()}{path}"
    try:
        resp = httpx.delete(url, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        typer.echo("Cannot connect to Suzent server. Is it running?")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as e:
        typer.echo(f"Server error: {e.response.status_code}")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error: {e}")
        raise typer.Exit(code=1)


def _http_post_stream(path: str, data: dict = None):
    """Make a streaming POST request to the running server, yielding lines."""
    import httpx

    url = f"{get_server_url()}{path}"
    try:
        # Use a client to manage the stream context
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", url, json=data or {}) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    yield line
    except httpx.ConnectError:
        typer.echo("❌ Cannot connect to Suzent server. Is it running?")
        raise typer.Exit(code=1)
    except httpx.HTTPStatusError as e:
        try:
            # Try to read error details if available (might not be possible on stream error)
            # Re-read response content if not streamed yet? stream response doesn't have .json()
            # Just print status
            detail = str(e)
        except Exception:
            detail = str(e)
        typer.echo(f"❌ Server error: {detail}")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"❌ Error: {e}")
        raise typer.Exit(code=1)

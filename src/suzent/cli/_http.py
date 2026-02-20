"""
Shared HTTP helpers for CLI commands that talk to the running server.
"""

import os
from pathlib import Path

import typer


def get_server_url() -> str:
    """Get the server URL from environment or default."""

    # 1. Environment variable (explicit override)
    port = os.getenv("SUZENT_PORT")

    if port == "0":
        port = None

    # 2. File (running instance)
    if not port:
        try:
            from suzent.config import DATA_DIR

            # Primary check: Active DATA_DIR (Dev or Prod depending on config.py)
            port_file = DATA_DIR / "server.port"
            if port_file.exists():
                port = port_file.read_text(encoding="utf-8").strip()

            # Secondary check: Production AppData (GUI might be running there while CLI is in Dev mode)
            if not port:
                import platform

                system = platform.system()
                prod_dir = None

                if system == "Windows":
                    # Backend uses Tauri's app_data_dir() which maps to Roaming on Windows
                    roaming = os.getenv("APPDATA")
                    if roaming:
                        prod_dir = Path(roaming) / "com.suzent.app"
                elif system == "Darwin":
                    prod_dir = (
                        Path.home() / "Library/Application Support/com.suzent.app"
                    )
                else:  # Linux
                    xdg = os.getenv("XDG_DATA_HOME")
                    if xdg:
                        prod_dir = Path(xdg) / "com.suzent.app"
                    else:
                        prod_dir = Path.home() / ".local/share/com.suzent.app"

                if prod_dir:
                    prod_port_file = prod_dir / "server.port"
                    # Note: Backend writes to app_data_dir directly, check where sync_app_data writes
                    # backend.rs: env("SUZENT_APP_DATA", &app_data_dir) matches this

                    if prod_port_file.exists():
                        port = prod_port_file.read_text(encoding="utf-8").strip()
                    else:
                        # try nested .suzent if ancient logic exists?
                        nested = prod_dir / ".suzent" / "server.port"
                        if nested.exists():
                            port = nested.read_text(encoding="utf-8").strip()

        except Exception:
            pass

    # 3. Default
    if not port:
        port = "8000"

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

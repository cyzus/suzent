from pathlib import Path

SETUP_PS1 = Path(__file__).resolve().parents[1] / "scripts" / "setup.ps1"


def test_setup_ps1_is_ascii():
    # Windows PowerShell 5.1's `irm | iex` decodes a response without a charset
    # (jsDelivr, many mirrors) as Latin-1, so any non-ASCII byte turns to garbage.
    text = SETUP_PS1.read_bytes()
    bad = [i for i, byte in enumerate(text) if byte > 0x7F]
    assert not bad, f"non-ASCII byte at offset {bad[0]}"

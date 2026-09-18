"""Render the iOS launcher from the shared mobile SVG (requires librsvg)."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    target = ROOT / "apps/ios/Suzent/Assets.xcassets/AppIcon.appiconset"
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "rsvg-convert",
            "--width",
            "1024",
            "--height",
            "1024",
            "--background-color",
            "#0066FF",
            "--output",
            str(target / "AppIcon.png"),
            str(ROOT / "packages/presentation/mobile-icon.svg"),
        ],
        check=True,
    )
    (target / "Contents.json").write_text(
        json.dumps(
            {
                "images": [
                    {
                        "filename": "AppIcon.png",
                        "idiom": "universal",
                        "platform": "ios",
                        "size": "1024x1024",
                    }
                ],
                "info": {"author": "xcode", "version": 1},
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()

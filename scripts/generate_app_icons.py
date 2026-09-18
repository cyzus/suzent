"""Package the approved mobile artwork for both launchers (macOS sips)."""

import json
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    target = ROOT / "apps/ios/Suzent/Assets.xcassets/AppIcon.appiconset"
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "sips",
            "--resampleHeightWidth",
            "1024",
            "1024",
            str(ROOT / "packages/presentation/assets/mobile-icon.png"),
            "--out",
            str(target / "AppIcon.png"),
        ],
        check=True,
    )
    android = ROOT / "apps/android/app/src/main/res/drawable-nodpi"
    android.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target / "AppIcon.png", android / "suzent_launcher_artwork.png")
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

"""Native logo geometry generated from the desktop's canonical favicon."""

import math
import xml.etree.ElementTree as ET
from pathlib import Path


def logo_outputs(root: Path) -> dict[Path, str]:
    rects = (
        ET.parse(root / "frontend/public/favicon.svg")
        .getroot()
        .findall("{http://www.w3.org/2000/svg}rect")
    )
    geometry = [
        [float(rect.get(key, "0")) for key in ("x", "y", "width", "height", "rx")]
        for rect in rects
    ]

    def outline(rect: list[float]) -> list[tuple[float, float]]:
        x, y, width, height, radius = rect
        points = []
        for cx, cy, start in [
            (x + width - radius, y + radius, -90),
            (x + width - radius, y + height - radius, 0),
            (x + radius, y + height - radius, 90),
            (x + radius, y + radius, 180),
        ]:
            for index in range(9):
                angle = math.radians(start + index * 90 / 8)
                points.append(
                    (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
                )
        return points

    def project(point: tuple[float, float]) -> tuple[float, float]:
        # Homography from the canonical 24-unit face to the native cube front.
        u, v = (value / 24 for value in point)
        x0, y0, x1, y1, x2, y2, x3, y3 = 65, 57, 143, 45, 138, 122, 65, 141
        dx1, dx2, dx3 = x1 - x2, x3 - x2, x0 - x1 + x2 - x3
        dy1, dy2, dy3 = y1 - y2, y3 - y2, y0 - y1 + y2 - y3
        denominator = dx1 * dy2 - dx2 * dy1
        g, h = (
            (dx3 * dy2 - dx2 * dy3) / denominator,
            (dx1 * dy3 - dx3 * dy1) / denominator,
        )
        return (
            ((x1 - x0 + g * x1) * u + (x3 - x0 + h * x3) * v + x0)
            / (g * u + h * v + 1),
            ((y1 - y0 + g * y1) * u + (y3 - y0 + h * y3) * v + y0)
            / (g * u + h * v + 1),
        )

    def path(points: list[tuple[float, float]]) -> str:
        return "M" + " L".join(f"{x:.4f},{y:.4f}" for x, y in points) + " Z"

    def vector(size: int, paths: list[tuple[str, str]], outlined: int = 0) -> str:
        stroke = ' android:strokeColor="#808080" android:strokeWidth="1"'
        return (
            f'<!-- Generated from frontend/public/favicon.svg. -->\n<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="{size}dp" android:height="{size}dp" android:viewportWidth="{size}" android:viewportHeight="{size}">\n'
            + "".join(
                f'    <path android:pathData="{data}" android:fillColor="{color}"{stroke if index < outlined else ""} />\n'
                for index, (data, color) in enumerate(paths)
            )
            + "</vector>\n"
        )

    eyes = [[project(point) for point in outline(rect)] for rect in geometry[1:]]
    swift = "// Generated from frontend/public/favicon.svg.\npublic enum SuzentLogoGeometry {\n"
    swift += "    public static let rectangles: [[Double]] = " + repr(geometry) + "\n"
    swift += (
        "    public static let eyes: [[(Double, Double)]] = [\n"
        + "".join(
            "        [" + ", ".join(f"({x:.4f}, {y:.4f})" for x, y in eye) + "],\n"
            for eye in eyes
        )
        + "    ]\n}\n"
    )
    faces = [
        ("M28,36 L95,27 L143,45 L65,57 Z", "#2E2E2E"),
        ("M28,36 L65,57 L65,141 L28,109 Z", "#0A0A0A"),
        ("M65,57 L143,45 L138,122 L65,141 Z", "#000000"),
    ]
    drawable = root / "apps/android/app/src/main/res/drawable"
    return {
        drawable / "suzent_logo.xml": vector(
            24,
            [
                (path(outline(rect)), rects[index].get("fill", "#000000"))
                for index, rect in enumerate(geometry)
            ],
        ),
        drawable / "greeting_cube.xml": vector(
            160, faces + [(path(eye), "#FFFFFF") for eye in eyes], outlined=3
        ),
        root / "packages/SuzentCore/Sources/SuzentCore/SuzentLogoGeometry.swift": swift,
    }

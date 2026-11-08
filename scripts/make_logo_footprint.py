#!/usr/bin/env python3
"""Turn a transparent-background logo PNG into a KiCad silkscreen footprint.

Every opaque pixel (alpha > 127) becomes silkscreen. Horizontal pixel runs are merged with identical
runs on the rows below into filled rectangles, so the footprint stays reasonably small. The footprint
is board-only: no pads, no courtyard, excluded from the BOM and placement files. Place it on F.SilkS,
or flip it in KiCad to put it on the back (KiCad mirrors it so it reads correctly from that side).

Usage:
  python3 scripts/make_logo_footprint.py PCB/libraries/logos/PunderWorks-black.png 14 \
      PCB/libraries/DroidPowerSense.pretty/PunderWorks_Logo_14mm.kicad_mod
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

from PIL import Image


def rectangles(mask: list[list[bool]]) -> list[tuple[int, int, int, int]]:
    """Merge opaque pixel runs into rectangles (x0, y0, x1, y1), end-exclusive, in pixels."""
    open_runs: dict[tuple[int, int], int] = {}  # (x0, x1) -> start row
    rects = []
    for y, row in enumerate(mask + [[False] * len(mask[0])]):
        runs, x = set(), 0
        while x < len(row):
            if row[x]:
                x0 = x
                while x < len(row) and row[x]:
                    x += 1
                runs.add((x0, x))
            else:
                x += 1
        for key in list(open_runs):
            if key not in runs:
                rects.append((key[0], open_runs.pop(key), key[1], y))
        for key in runs:
            open_runs.setdefault(key, y)
    return rects


def main() -> int:
    src, width_mm, out = Path(sys.argv[1]), float(sys.argv[2]), Path(sys.argv[3])
    alpha = Image.open(src).convert("RGBA").split()[3]
    alpha = alpha.crop(alpha.point(lambda v: 255 if v > 127 else 0).getbbox())
    w, h = alpha.size
    mask = [[alpha.getpixel((x, y)) > 127 for x in range(w)] for y in range(h)]
    scale = width_mm / w
    ox, oy = w / 2, h / 2  # footprint origin at the logo's centre
    name = out.stem
    u = lambda: str(uuid.uuid4())
    polys = []
    for x0, y0, x1, y1 in rectangles(mask):
        pts = [((x0 - ox) * scale, (y0 - oy) * scale), ((x1 - ox) * scale, (y0 - oy) * scale),
               ((x1 - ox) * scale, (y1 - oy) * scale), ((x0 - ox) * scale, (y1 - oy) * scale)]
        xy = " ".join(f"(xy {px:.4f} {py:.4f})" for px, py in pts)
        polys.append(f'\t(fp_poly (pts {xy}) (stroke (width 0) (type solid)) (fill yes) (layer "F.SilkS") (uuid "{u()}"))')
    height_mm = h * scale
    out.write_text(f'''(footprint "{name}"
\t(version 20260206)
\t(generator "make_logo_footprint.py")
\t(layer "F.Cu")
\t(descr "Silkscreen logo from {src.name}, {width_mm:g} x {height_mm:.2f} mm. Board-only, no pads; flip to place on the back.")
\t(tags "logo silkscreen")
\t(attr board_only exclude_from_pos_files exclude_from_bom allow_missing_courtyard)
\t(property "Reference" "LOGO**" (at 0 {height_mm / 2 + 1:.2f} 0) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))
\t(property "Value" "{name}" (at 0 {-height_mm / 2 - 1:.2f} 0) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1 1) (thickness 0.15))))
\t(property "Datasheet" "" (at 0 0 0) (unlocked yes) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1.27 1.27))))
\t(property "Description" "Silkscreen logo" (at 0 0 0) (unlocked yes) (layer "F.Fab") (hide yes) (uuid "{u()}") (effects (font (size 1.27 1.27))))
{chr(10).join(polys)}
)
''')
    print(f"{out}: {width_mm:g} x {height_mm:.2f} mm, {len(polys)} rectangles, {scale * 1000:.1f} um/px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

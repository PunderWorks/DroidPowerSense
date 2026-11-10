#!/usr/bin/env python3
"""Convert the hand-placed 70 x 50 mm 6-layer board to 76 x 58 mm on 4 layers (no signal routing).

Unlike scripts/layout_compact.py this does not place parts from a table. It moves the existing,
hand-tuned placement and silkscreen by region, so the layout keeps its arrangement and only gains
the space a 4-layer board needs:

- The board edge moves up 2.5 mm and the power pours grow with it (8.7 -> 11.2 mm tall), so three
  power layers (F.Cu 2 oz, In2.Cu 1 oz, B.Cu 2 oz) carry about the same copper cross-section as the
  four the 6-layer board had (2 + 1 + 1 + 2 oz x 8.7 mm).
- Everything below the gate-drive band moves down 3 mm (the module, buck and bottom-edge parts
  5.5 mm, keeping the antenna and buck at the bottom edge): routing room under the power row.
- The right side spreads out to the right by up to 6 mm: the shunt/INA237, output TVS, flyback
  diode and XT60 out, the CAN column and the UART level shifters.

It deletes every track, via and zone (the old routing does not survive the move), then adds the
outline, power pours, ground planes, an In2.Cu +3V3 pour and stitching vias, places F1/F2 (the
CAN/UART ground PTCs), redraws the J5/J6/J8 pin labels for the 3-pin connectors and swaps the
board stackup to 4 layers. Signal routing is done by hand in KiCad afterwards; once it is, the
board file is the source of truth and this script must not be re-run (it reads positions from the
6-layer board, which no longer exists after the first run).

Run with KiCad 10's bundled Python, with the board closed, after syncing from Stackup:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      scripts/layout_4layer.py
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout_pcb import (  # noqa: E402
    BOARD_PATH, add_rect_zone, add_rounded_rect_outline, add_via, mm, pt,
)

# Old and new outline. The left edge stays at x = 50.
OLD = (50.0, 46.5, 120.0, 96.5)
X0, Y0, X1, Y1 = 50.0, 44.0, 126.0, 102.0

# ── Footprint moves (dx, dy) in mm, by current reference ───────────────────────────────────────
MOVES: dict[str, tuple[float, float]] = {}


def group(refs: str, dx: float, dy: float) -> None:
    for ref in refs.split():
        MOVES[ref] = (dx, dy)


# Power row: J1, D1, Q1, Q2 stay; the shunt + INA237 Kelvin pair move together.
group("J1 D1 Q1 Q2", 0, 0)
group("R13 U2 C4", 2.0, 0)            # R_SHUNT, U_INA, C_INA_VS
group("D6", 3.0, 0)                   # D_TVS_OUT
group("D5", 4.5, 0)                   # D_FLY
group("J2", 6.0, 0)                   # XT60 out
group("LOGO**", 1.5, 0)               # back-side logo, recentred in the wider heatsink area
# Gate drive / LM5060 band: spread right and the lower row down.
group("D4 Q3 R3 R4", 0, 0)            # D_REV, Q_REV, R_REV, R_SENSE
group("D3 R1", 1.0, 0)                # D_GOFF, R_GATE
group("U1", 1.0, 1.5)                 # LM5060
group("C1", 0, 1.5)                   # C_PROT_VIN
group("R2 C2 R5", 2.0, 0)             # R_GATE_C, C_GATE, R_OUT
group("C3", 2.0, 1.5)                 # C_TIMER
# Left column: dividers, power LED, remote switch, Q_LED.
group("R8 R9 R6 R7 R10 R11 D8 R26", 0, 3.0)
group("J3 D2", 0, 3.0)
group("Q5", 0, 4.0)
group("H1", 0, 0)
# 5 V buck keeps its bottom-edge position.
group("R16 C7 D7 C10 L1 C6 U3 C11 C8 R17 R18 C9 R20 R19 C12", 0, 5.5)
group("H3", 0, 5.5)
# Module on sockets and the parts under it: antenna stays at the bottom edge.
group("U4 J10 J11 C13 R27 Q4 R12 C14 R24 R21 R22 R25 R23 R14 R15 C5", 1.5, 5.5)
group("J9 SH1", 2.5, 5.5)             # UART voltage select beside the module
# Circuit ID jumper (below D5).
group("J4 SH3", 4.0, 0)
# CAN column.
group("U5", 6.0, 3.0)
group("C15", 6.0, 3.5)                # U_CAN VCC bypass, clear of the J9 labels
group("J7 SH2 R28", 6.0, -1.0)        # termination jumper and resistor
group("H2", 6.0, 0)
group("H4", 6.0, 5.5)
# UART level shifters and connector.
group("Q6 Q7 R29 R30 R31 R32", 4.0, 3.0)
group("J8", 4.0, 5.5)

# Absolute positions (x, y, rotation) for the parts whose move is not a plain offset.
ABSOLUTE: dict[str, tuple[float, float, float]] = {
    # 3-pin XH rotated 90: pin 1 (GND) at the origin, pins 2 and 3 at -2.5 / -5.0 mm in y.
    "J5": (122.0, 79.0, 90.0),        # CAN in:  GND 79.0, CANL 76.5, CANH 74.0
    "J6": (122.0, 90.5, 90.0),        # CAN out: GND 90.5, CANL 88.0, CANH 85.5
    "F1": (114.8, 92.6, 0.0),         # F_CAN_GND, below the J6 pin labels, near the J6 GND pin
    "F2": (99.0, 97.0, 90.0),         # F_UART_GND, between the module and J8
}

# ── Silkscreen and drawings ─────────────────────────────────────────────────────────────────────
# Text items moved by their text (layer F/B silkscreen); anything not listed stays put.
TEXT_MOVES: dict[str, tuple[float, float]] = {
    "BAT IN": (0, 0), "REMOTE SW": (0, 3.0), "BAT+": (0, 3.0), "SW": (0, 3.0), "LED-": (0, 3.0),
    "LED+": (0, 3.0), "PWR": (0, 3.0),
    "3V3": (2.5, 5.5), "UART V": (2.5, 5.5),
    "CIRCUIT ID": (4.0, 0), "NO JUMPER = 1": (4.0, 0), "JUMPER ON = 2": (4.0, 0),
    "TERM": (6.0, -1.0), "LOAD OUT": (6.0, 0),
    "HEATSINK AREA - INSULATING THERMAL PAD ONLY": (1.5, 0),
    "DroidPowerSense V1.0": (1.5, 0),
}
# Rebuilt below for the 3-pin connectors (two of them share text with the J9 labels).
CONNECTOR_LABELS = {"CANH", "CANL", "CAN IN", "CAN OUT", "RX", "TX"}

# Back-side heatsink area under D_TVS_IN ... D_FLY (no through-hole tails inside it).
HEATSINK = (65.0, 45.0, 108.0, 61.0)

# High-current pours on F.Cu, In2.Cu and B.Cu (priority 3, pads connected solidly), 11.2 mm tall.
POWER_POURS = {
    "VBAT_IN": (57.5, 44.4, 76.7, 55.6),    # J1 +, D1, Q1 drain
    "VSW_OUT": (81.2, 44.4, 90.0, 53.0),    # Q2 drain, R_SHUNT pad 1 (Kelvin taps below)
    "VOUT": (94.8, 44.4, 118.0, 55.6),      # R_SHUNT pad 2, D6, D5, J2 +
}
VSW_MID_POUR = (77.0, 48.6, 81.0, 54.0)     # F.Cu only, Q1 sources to Q2 sources
IN2_3V3 = (76.2, 61.5, 125.5, 101.5)        # +3V3 pour under the module, CAN and UART
STITCH_PITCH = 1.27
STITCH_KEEPOFF = 0.4

STACKUP_4L = """			(layer "F.Cu"
				(type "copper")
				(thickness 0.07)
			)
			(layer "dielectric 1"
				(type "prepreg")
				(thickness 0.2104)
				(material "FR4")
				(epsilon_r 4.5)
				(loss_tangent 0.02)
			)
			(layer "In1.Cu"
				(type "copper")
				(thickness 0.035)
			)
			(layer "dielectric 2"
				(type "core")
				(thickness 0.95)
				(material "FR4")
				(epsilon_r 4.5)
				(loss_tangent 0.02)
			)
			(layer "In2.Cu"
				(type "copper")
				(thickness 0.035)
			)
			(layer "dielectric 3"
				(type "prepreg")
				(thickness 0.2104)
				(material "FR4")
				(epsilon_r 4.5)
				(loss_tangent 0.02)
			)
			(layer "B.Cu"
				(type "copper")
				(thickness 0.07)
			)
"""


def text_of(item) -> str | None:
    return item.GetText() if item.GetClass() in ("PCB_TEXT", "PCB_TEXTBOX") else None


def move_footprints(fps: dict[str, pcbnew.FOOTPRINT]) -> None:
    missing = sorted(set(fps) - set(MOVES) - set(ABSOLUTE))
    if missing:
        raise SystemExit(f"no move for: {', '.join(missing)}")
    for ref, (dx, dy) in MOVES.items():
        fps[ref].Move(pcbnew.VECTOR2I(mm(dx), mm(dy)))
    for ref, (x, y, rot) in ABSOLUTE.items():
        fp = fps[ref]
        fp.SetOrientationDegrees(0.0)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        fp.Reference().SetTextAngleDegrees(0.0)
    for ref in ("J5", "J6", "J8", "F1", "F2"):
        fps[ref].Reference().SetVisible(False)   # functional labels name them instead


def move_drawings(board: pcbnew.BOARD, drawings: list) -> list:
    """Move silkscreen by text. Returns the old outline, heatsink marks and 2-pin connector labels,
    to remove once everything new is in place."""
    remove = []
    for item in drawings:
        layer = board.GetLayerName(item.GetLayer())
        text = text_of(item)
        if item.GetClass() == "PCB_SHAPE" and layer in ("Edge.Cuts", "B.Silkscreen", "User.Drawings"):
            remove.append(item)                           # outline and heatsink marks, redrawn
        elif text is None and layer == "B.Silkscreen":    # the QR code moves with the left column
            item.Move(pcbnew.VECTOR2I(0, mm(3.0)))
        elif text in CONNECTOR_LABELS or (text == "UART" and item.GetPosition().y > mm(90)):
            remove.append(item)
        elif text == "UART":                              # the J9 middle-pin label
            item.Move(pcbnew.VECTOR2I(mm(2.5), mm(5.5)))
        elif text == "5V":
            item.Move(pcbnew.VECTOR2I(mm(2.5), mm(5.5)))
        elif text is not None and text.startswith("github.com"):
            item.Move(pcbnew.VECTOR2I(mm(1.5), 0))
        elif text in TEXT_MOVES:
            dx, dy = TEXT_MOVES[text]
            item.Move(pcbnew.VECTOR2I(mm(dx), mm(dy)))
        elif text is not None:
            raise SystemExit(f"no move for silkscreen text {text!r}")
    return remove


def label(board: pcbnew.BOARD, text: str, x: float, y: float, align: str = "L", angle: float = 0.0) -> None:
    t = pcbnew.PCB_TEXT(board)
    t.SetLayer(board.GetLayerID("F.SilkS"))
    t.SetText(text)
    t.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
    t.SetTextThickness(mm(0.15))
    t.SetHorizJustify({"L": pcbnew.GR_TEXT_H_ALIGN_LEFT, "C": pcbnew.GR_TEXT_H_ALIGN_CENTER,
                       "R": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[align])
    t.SetPosition(pt(x, y))
    t.SetTextAngleDegrees(angle)
    board.Add(t)


def add_connector_labels(board: pcbnew.BOARD) -> None:
    """Pin functions in line with each pin of the 3-pin J5 / J6 (left of the body) and J8 (above)."""
    for (_, y, _), name in ((ABSOLUTE["J5"], "CAN IN"), (ABSOLUTE["J6"], "CAN OUT")):
        for text, py in (("GND", y), ("CANL", y - 2.5), ("CANH", y - 5.0)):
            label(board, text, 118.9, py, "R")
    # No room above / below the connectors (mounting holes), so the headings run vertically
    # beside each connector's pin labels.
    label(board, "CAN IN", 114.2, ABSOLUTE["J5"][1] - 3.0, "C", 90.0)
    label(board, "CAN OUT", 114.2, ABSOLUTE["J6"][1] - 3.0, "C", 90.0)
    j8x = 101.5 + 4.0
    for i, text in enumerate(("GND", "RX", "TX")):
        label(board, text, j8x + 2.5 * i, 93.75, "C")
    label(board, "UART", 113.5, 98.5)


def mark_heatsink_area(board: pcbnew.BOARD) -> None:
    x0, y0, x1, y1 = HEATSINK
    for layer, brackets in (("B.SilkS", True), ("Dwgs.User", False)):
        lid = board.GetLayerID(layer)
        if brackets:
            segs = []
            for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
                segs += [((cx, cy), (cx + dx * 3.0, cy)), ((cx, cy), (cx, cy + dy * 3.0))]
        else:
            segs = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
        for (sx, sy), (ex, ey) in segs:
            s = pcbnew.PCB_SHAPE(board)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetLayer(lid)
            s.SetStart(pt(sx, sy))
            s.SetEnd(pt(ex, ey))
            s.SetWidth(mm(0.15))
            board.Add(s)


def add_pours(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT]) -> int:
    for net, rect in POWER_POURS.items():
        for layer in ("F.Cu", "In2.Cu", "B.Cu"):
            add_rect_zone(board, net, layer, *rect, priority=3, solid_pads=True)
    add_rect_zone(board, "VSW_MID", "F.Cu", *VSW_MID_POUR, priority=3, solid_pads=True)
    add_rect_zone(board, "+3V3", "In2.Cu", *IN2_3V3, priority=1)
    for layer in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        add_rect_zone(board, "GND", layer, X0 + 0.3, Y0 + 0.3, X1 - 0.3, Y1 - 0.3, priority=0)

    pads = []
    for fp in fps.values():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            pads.append(tuple(pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())))
    r = 0.4 + STITCH_KEEPOFF
    count = 0
    for net, (x0, y0, x1, y1) in POWER_POURS.items():
        y = y0 + 0.9
        while y <= y1 - 0.9:
            x = x0 + 0.9
            while x <= x1 - 0.9:
                if not any(px0 - r < x < px1 + r and py0 - r < y < py1 + r for px0, py0, px1, py1 in pads):
                    add_via(board, net, round(x, 3), round(y, 3), size_mm=0.8, drill_mm=0.4)
                    count += 1
                x += STITCH_PITCH
            y += STITCH_PITCH
    return count


def set_stackup_text(path: Path) -> None:
    """Replace the copper and dielectric layers of the saved stackup with the 4-layer ones (mask,
    silkscreen colours and finish are kept)."""
    src = path.read_text()
    start = src.index('\t\t\t(layer "F.Cu"', src.index("\t\t(stackup\n"))
    end = src.index('\t\t\t(layer "B.Mask"', start)
    path.write_text(src[:start] + STACKUP_4L + src[end:])


def main() -> None:
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    if board.GetCopperLayerCount() != 6:
        raise SystemExit("expected the 6-layer board; this conversion has already been run")
    # KiCad's SWIG wrappers stop working once items are removed, so list everything up front and
    # remove the old copper and drawings only after the new placement and drawings are done.
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    drawings = list(board.GetDrawings())
    old = list(board.GetTracks()) + list(board.Zones())
    move_footprints(fps)
    old += move_drawings(board, drawings)
    board.SetCopperLayerCount(4)
    add_rounded_rect_outline(board, X0, Y0, X1, Y1, r=2.0)
    add_connector_labels(board)
    mark_heatsink_area(board)
    vias = add_pours(board, fps)
    for item in old:
        board.Remove(item)
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    set_stackup_text(Path(BOARD_PATH))
    print(f"76 x 58 mm, 4 layers; {vias} stitching vias")
    print("Fill zones next: kicad-cli pcb drc --refill-zones --save-board PCB/DroidPowerSense.kicad_pcb")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Placement and pours for the 70 x 50 mm DroidPowerSense board (no signal routing).

Clears copper and drawings from PCB/DroidPowerSense.kicad_pcb, draws the 70 x 50 mm outline, moves the
mounting holes, places every synced footprint, and marks the back-side heatsink area. Routing and
the power, ground and In2 supply pours (with stitching vias) are added here; signal routing is done
by hand in KiCad. Like scripts/layout_pcb.py this is a starting point: once the board
has been hand-edited, the board file is the source of truth and this script should not be re-run.

Run with KiCad 10's bundled Python (sync from Stackup first):
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      scripts/layout_compact.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from layout_pcb import (  # noqa: E402
    BOARD_PATH, add_rect_zone, add_rounded_rect_outline, add_silk_text, add_via, mm, pt,
)

# Board outline: 70 x 50 mm, origin kept where the 90 x 66 board's was.
X0, Y0, X1, Y1 = 50.0, 46.5, 120.0, 96.5

HOLES = {"H1": (53.5, 66.8), "H2": (116.5, 66.8), "H3": (53.5, 93.0), "H4": (116.5, 93.0)}

# Back-side heatsink area under D1..D5 / Q1 / Q2 / R12: no through-hole tails inside it.
HEATSINK = (65.0, 47.5, 105.0, 61.0)

# ref: (x, y, rotation). Reference positions are left to the footprint defaults.
PLACEMENTS: dict[str, tuple[float, float, float]] = {
    # ── Power row (top). XT60 bodies overhang the side edges ~5 mm; pins and pegs stay on board.
    "J1": (61.5, 58.5, 90.0),     # XT60PW-M: VBAT_IN (61.5, 51.3), GND (61.5, 58.5)
    "D1": (67.7, 57.0, -90.0),    # input TVS: VBAT_IN top (53.6), GND bottom (60.4)
    "Q1": (75.0, 51.3, 180.0),    # drain (VBAT_IN) left, sources right, gate top-right
    "Q2": (82.6, 51.3, 0.0),      # sources left, gate bottom-left, drain (VSW_OUT) right
    "R12": (90.4, 51.3, 0.0),     # 1 mOhm shunt: VSW_OUT left, VOUT right
    "D6": (96.7, 56.2, -90.0),    # output TVS: VOUT top, GND bottom
    "D5": (102.5, 57.0, -90.0),   # flyback: VOUT top, GND bottom
    "J2": (108.5, 58.5, -90.0),   # XT60PW-F: VOUT (108.5, 51.3), GND (108.5, 58.5)

    # ── Gate drive, reverse clamp, LM5060 and INA226 (below the power row)
    "D4": (73.0, 57.6, 90.0),     # D_REV
    "Q3": (76.4, 57.4, 90.0),     # Q_REV
    "R2": (73.0, 61.6, 90.0),     # R_REV
    "R3": (76.6, 61.4, 90.0),     # R_SENSE (VBAT_IN -> PROT_SENSE)
    "C1": (76.6, 65.0, 90.0),     # LM5060 VIN bypass
    "D3": (82.0, 56.6, 0.0),      # D_GOFF
    "R1": (82.0, 59.6, 0.0),      # R_GATE
    "U1": (82.0, 63.0, 0.0),      # LM5060
    "R4": (87.0, 61.2, 90.0),     # R_OUT (VSW_OUT -> PROT_OUT)
    "C2": (87.0, 64.8, 90.0),     # C_TIMER
    "U2": (90.4, 58.6, 90.0),     # INA226, Kelvin to R12 pads
    "C3": (93.3, 60.0, 90.0),     # INA226 bypass

    # ── LM5060 dividers (VSW_CTRL -> OVP / UVLO / EN)
    "R7": (68.0, 65.0, 0.0), "R8": (72.0, 65.0, 0.0),     # OVP 180k / 10k
    "R5": (68.0, 67.0, 0.0), "R6": (72.0, 67.0, 0.0),     # UVLO 33k / 10k
    "R9": (68.0, 69.0, 0.0), "R10": (72.0, 69.0, 0.0),    # EN 100k / 47k

    # ── Power LED (visible, top-left)
    "D8": (60.0, 65.5, 0.0), "R24": (60.0, 67.5, 0.0),

    # ── Remote switch J3 (left edge) and D_SW; pin labels go between J3 and D2
    "J3": (55.5, 74.0, -90.0),    # 1 BAT+ (74.0), 2 SW (76.5), 3 LED- (79.0), 4 LED+ (81.5)
    "D2": (66.0, 76.5, 180.0),    # VSW_RAW left, VSW_CTRL right
    "Q5": (54.5, 86.9, 0.0),      # Q_LED (below J3)

    # ── 5 V buck (bottom-left)
    "C6": (65.0, 81.6, 0.0),      # VIN 10 uF
    "C9": (64.0, 84.9, 0.0),      # BOOT
    "U3": (64.0, 89.0, 0.0),      # LMR14030
    "C5": (58.9, 88.6, 90.0),     # VIN 10 uF
    "D7": (72.0, 82.0, 0.0),      # catch diode
    "L1": (72.0, 88.0, 0.0),      # 10 uH
    "C10": (72.0, 92.75, 0.0),    # +5V 10 uF
    "C11": (72.0, 95.2, 0.0),     # +5V 10 uF
    "C7": (59.2, 93.6, 90.0),     # VIN 100 nF
    "R15": (61.0, 93.6, 90.0),    # EN pull-up
    "R16": (62.8, 93.6, 90.0),    # RT
    "C8": (64.6, 93.6, 90.0),     # SS
    "R18": (66.4, 93.6, 90.0),    # FB bottom
    "R17": (68.2, 93.6, 90.0),    # FB top

    # ── ESP32-C5-Zero-M on sockets; antenna at the bottom edge, USB-C toward the power row
    "U4": (85.0, 82.3, 0.0),
    "J10": (77.38, 82.3, 0.0),    # socket under pins 1-9
    "J11": (92.62, 82.3, 0.0),    # socket under pins 10-18

    # ── Under the module (low parts only; the module sits ~11 mm up)
    "C12": (80.6, 70.0, 0.0),     # +5V at module pin 1
    "Q4": (81.0, 73.0, 0.0),      # Q_CUTOFF
    "R11": (84.6, 73.0, 90.0),    # cutoff gate pull-down
    "C13": (80.6, 76.0, 0.0),     # +3V3 bypass at module pin 3
    "R22": (80.6, 78.0, 0.0),     # PGOOD pull-up
    "R19": (80.6, 82.4, 0.0),     # SDA pull-up
    "R20": (80.6, 84.4, 0.0),     # SCL pull-up
    "R21": (80.6, 86.4, 0.0),     # ALERT pull-up
    "R25": (89.4, 72.4, 0.0),     # SW_LED_EN pull-up (module pin 17)
    "R23": (89.4, 85.0, 0.0),     # CIRCUIT_ID pull-up (module pin 11)
    "R13": (86.0, 87.4, 0.0),     # VBAT ADC top
    "R14": (89.4, 87.4, 0.0),     # VBAT ADC bottom
    "C4": (89.4, 89.4, 0.0),      # VBAT ADC filter

    # ── Circuit ID jumper (below D5)
    "J4": (101.0, 64.5, 0.0),

    # ── CAN (right edge)
    "R26": (110.5, 73.0, 0.0),    # 120R terminator
    "J7": (104.5, 73.0, 90.0),    # termination jumper (horizontal, above U5)
    "U5": (103.0, 79.0, 0.0),     # TCAN334G
    "C14": (97.6, 79.6, 90.0),
    "J5": (116.0, 77.0, 90.0),    # CAN IN
    "J6": (116.0, 85.5, 90.0),    # CAN OUT

    # ── UART: level shifters, VIO jumper, J8 on the bottom edge
    "Q6": (100.5, 84.5, 0.0),     # Q_TX
    "Q7": (104.6, 84.5, 0.0),     # Q_RX
    "R27": (98.6, 87.9, 90.0), "R28": (100.4, 87.9, 90.0),
    "R29": (102.2, 87.9, 90.0), "R30": (104.0, 87.9, 90.0),
    "J9": (97.0, 70.5, 0.0),      # VIO select (beside the module, right of the socket)
    "J8": (101.5, 92.45, 0.0),    # UART
}


# High-current pours on F.Cu, In2.Cu and B.Cu (priority 3, pads connected solidly). The power row
# runs along y 46.9-55.6; the XT60 GND pins and the TVS/flyback GND pads sit just below it.
POWER_POURS = {
    "VBAT_IN": (57.5, 46.9, 76.7, 55.6),    # J1 +, D1, Q1 drain
    "VSW_OUT": (81.2, 46.9, 88.6, 55.0),    # Q2 drain, R12 pad 1
    "VOUT": (92.4, 46.9, 112.0, 55.6),      # R12 pad 2, D6, D5, J2 +
}
# Q1 sources to Q2 sources: F.Cu only (1.8 mm, ~0.1 mOhm). The gap between the FETs is too narrow
# for a via, and keeping it off B.Cu leaves room for the GATE_FET link to cross there.
VSW_MID_POUR = (77.0, 48.6, 81.0, 54.0)
# In2.Cu supply planes below the power row (priority 2).
IN2_PLANES = {
    "VSW_CTRL": (50.5, 56.2, 75.6, 96.0),   # remote-switch rail: LM5060, dividers, buck input
    "+3V3": (76.2, 56.2, 119.5, 96.0),      # module, INA226, CAN, UART, pull-ups
}
STITCH_PITCH = 1.27       # mm, grid for stitching / thermal vias in the power pours
STITCH_KEEPOFF = 0.4      # mm from any pad to a via's copper


# Silkscreen references: hidden where a functional label already names the part or there is no room
# (they stay on F.Fab), centred on the body for the ICs and the inductor.
HIDDEN_REFS = {"J3", "J4", "J5", "J6", "J7", "J8", "D3", "D4", "D8", "Q3", "Q4", "Q6", "Q7", "U3"}
CENTERED_REFS = {"U1", "U2", "U5", "L1"}


def old_items(board: pcbnew.BOARD) -> list:
    """Every track, via, zone and drawing on the loaded board, to remove before saving."""
    return list(board.GetDrawings()) + list(board.GetTracks()) + list(board.Zones())


def place(fps: dict[str, pcbnew.FOOTPRINT]) -> None:
    missing = sorted(set(fps) - set(PLACEMENTS) - set(HOLES))
    if missing:
        raise SystemExit(f"no placement for: {', '.join(missing)}")
    for ref, (x, y) in HOLES.items():
        fps[ref].SetPosition(pt(x, y))
    for ref, (x, y, rot) in PLACEMENTS.items():
        fp = fps[ref]
        fp.SetOrientationDegrees(0.0)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        fp.Reference().SetTextAngleDegrees(0.0)
        # Passive references stay on the Fab layer only (as on the 90 x 66 board); the labelled
        # connectors J5 / J6 / J8 carry functional silkscreen instead of a reference.
        if ref[0] in "RC" or ref in HIDDEN_REFS:
            fp.Reference().SetVisible(False)
        elif ref in CENTERED_REFS:
            fp.Reference().SetPosition(pt(x, y))
            fp.Reference().SetTextAngleDegrees(rot if abs(rot) == 90 else 0.0)
            fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            fp.Reference().SetTextThickness(mm(0.15))


def mark_heatsink_area(board: pcbnew.BOARD) -> None:
    """Corner brackets on B.SilkS and an outline on Dwgs.User for the optional heatsink."""
    x0, y0, x1, y1 = HEATSINK
    for layer, brackets in (("B.SilkS", True), ("Dwgs.User", False)):
        lid = board.GetLayerID(layer)
        segs = []
        if brackets:
            L = 3.0
            for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
                segs += [((cx, cy), (cx + dx * L, cy)), ((cx, cy), (cx, cy + dy * L))]
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
    add_silk_text(board, "HEATSINK AREA - INSULATING THERMAL PAD ONLY", (x0 + x1) / 2, y1 + 1.6,
                  size_mm=0.8, thick_mm=0.15, layer_name="B.SilkS", mirrored=True)


def add_labels(board: pcbnew.BOARD) -> None:
    """Functional silkscreen: connector pin functions in line with each pin, CAN IN / OUT, and the
    circuit ID jumper spelled out. Pin labels may cross the tracks running into the pins."""
    L, R = pcbnew.GR_TEXT_H_ALIGN_LEFT, pcbnew.GR_TEXT_H_ALIGN_RIGHT

    def label(text: str, x: float, y: float, align=L, size: float = 0.8) -> None:
        t = pcbnew.PCB_TEXT(board)
        t.SetLayer(board.GetLayerID("F.SilkS"))
        t.SetText(text)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(0.15))
        t.SetHorizJustify(align)
        t.SetPosition(pt(x, y))
        board.Add(t)

    # Power connectors and power LED
    label("BAT IN", 50.8, 63.7)
    label("LOAD OUT", 119.2, 63.7, R)
    label("PWR", 62.0, 66.5)
    # J3 remote switch: pins at x 55.5, y 74 / 76.5 / 79 / 81.5
    label("REMOTE SW", 51.0, 70.65)
    for text, y in (("BAT+", 74.0), ("SW", 76.5), ("LED-", 79.0), ("LED+", 81.5)):
        label(text, 59.0, y)
    # Circuit ID jumper J4 (pins at y 64.5 / 67.04)
    label("CIRCUIT ID", 103.0, 64.6)
    label("NO JUMPER = 1", 103.0, 66.0)
    label("JUMPER ON = 2", 103.0, 67.4)
    # CAN: J5 in, J6 out (pin 2 CANH above pin 1 CANL)
    label("CAN IN", 119.5, 70.9, R)
    label("CAN OUT", 119.5, 89.2, R)
    for y_h, y_l in ((74.5, 77.0), (83.0, 85.5)):
        label("CANH", 112.9, y_h, R)
        label("CANL", 112.9, y_l, R)
    label("120R", 104.5, 70.6)
    # UART: J8 on the bottom edge (pin 1 RX at x 101.5, pin 2 TX at x 104.0), J9 VIO select
    label("RX", 98.3, 92.45, R)
    label("TX", 107.3, 92.45)
    label("UART", 107.3, 94.4)
    for text, y in (("3V3", 70.5), ("VIO", 73.04), ("5V", 75.58)):
        label(text, 99.2, y)


def add_pours(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT]) -> int:
    """Power-row pours, ground planes, In2 supply planes, and stitching vias. Returns the via count."""
    for net, (x0, y0, x1, y1) in POWER_POURS.items():
        for layer in ("F.Cu", "In2.Cu", "B.Cu"):
            add_rect_zone(board, net, layer, x0, y0, x1, y1, priority=3, solid_pads=True)
    add_rect_zone(board, "VSW_MID", "F.Cu", *VSW_MID_POUR, priority=3, solid_pads=True)
    for net, rect in IN2_PLANES.items():
        add_rect_zone(board, net, "In2.Cu", *rect, priority=2)
    for layer in ("F.Cu", "In1.Cu", "B.Cu"):
        add_rect_zone(board, "GND", layer, X0 + 0.3, Y0 + 0.3, X1 - 0.3, Y1 - 0.3, priority=0)

    # The 30 A return and TVS / flyback surges: solid (not spoked) GND connections.
    for ref in ("J1", "J2", "D1", "D5", "D6"):
        for pad in fps[ref].Pads():
            if pad.GetNetname() == "GND":
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    # Stitching vias tie the three layers of each power pour together and carry FET heat to the
    # back-side heatsink area. Grid points that would land on or near any pad are skipped.
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


def main() -> int:
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    # KiCad's SWIG wrappers stop working once items are removed, so list everything up front and
    # remove the old copper and drawings only after the new placement and drawings are done.
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    old = old_items(board)
    place(fps)
    add_rounded_rect_outline(board, X0, Y0, X1, Y1, r=2.0)
    mark_heatsink_area(board)
    add_labels(board)
    vias = add_pours(board, fps)
    for item in old:
        board.Remove(item)
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    print(f"Placed {len(PLACEMENTS)} footprints, added pours and {vias} stitching vias on {BOARD_PATH}")
    print("Fill zones next: kicad-cli pcb drc --refill-zones --save-board PCB/DroidPowerSense.kicad_pcb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

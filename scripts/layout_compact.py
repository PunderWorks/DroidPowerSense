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
import layout_pcb
from layout_pcb import (
    add_track_path,
    add_via,
    add_via_stub,  # noqa: E402
    BOARD_PATH, add_rect_zone, add_rounded_rect_outline, add_silk_text, add_via, mm, pt,
)

# Register neck points for 0.5 mm pitch pins on U1 and U2 for the 70x50 compact layout:
layout_pcb.NECK_POINTS.update({
    (79.85, 62.0), (79.85, 62.5), (79.85, 63.0), (79.85, 63.5), (79.85, 64.0),
    (84.15, 62.0), (84.15, 62.5), (84.15, 63.0), (84.15, 63.5), (84.15, 64.0),
    (91.4, 56.45), (90.9, 56.45), (90.4, 56.45), (89.9, 56.45), (89.4, 56.45),
    (91.4, 60.75), (90.9, 60.75), (90.4, 60.75), (89.9, 60.75), (89.4, 60.75),
})

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
    "VSW_OUT": (81.2, 46.9, 88.0, 53.0),    # Q2 drain, R12 pad 1
    "VOUT": (92.8, 46.9, 112.0, 55.6),      # R12 pad 2, D6, D5, J2 +
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



def setup_6layer(board: pcbnew.BOARD) -> None:
    board.SetCopperLayerCount(6)
    board.SetLayerName(pcbnew.In1_Cu, "In1.Cu")
    board.SetLayerName(pcbnew.In2_Cu, "In2.Cu")
    board.SetLayerName(pcbnew.In3_Cu, "In3.Cu")
    board.SetLayerName(pcbnew.In4_Cu, "In4.Cu")

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
    """Power-row pours, ground planes, In3 logic supply plane, and stitching vias. Returns the via count."""
    for net, (x0, y0, x1, y1) in POWER_POURS.items():
        for layer in ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu"):
            add_rect_zone(board, net, layer, x0, y0, x1, y1, priority=3, solid_pads=True)
    add_rect_zone(board, "VSW_MID", "F.Cu", *VSW_MID_POUR, priority=3, solid_pads=True)
    # In3.Cu: Dedicated +3V3 logic supply plane across the board below the power row
    add_rect_zone(board, "+3V3", "In3.Cu", 50.5, 56.2, 119.5, 96.0, priority=2)
    # Ground planes on all 6 layers (In1.Cu and In4.Cu are solid reference planes; In2.Cu is open routing)
    for layer in ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"):
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



def route_power_path(board: pcbnew.BOARD) -> None:
    """Route the heavy 30 A copper traces on F.Cu and gate drive links."""
    # ── 30 A Main Conductor Row ──
    add_track_path(board, "VBAT_IN", [(61.5, 51.3), (67.7, 53.6), (73.95, 51.3)], width_mm=2.5, layer_name="F.Cu")
    add_track_path(board, "VBAT_IN", [(61.5, 51.3), (58.5, 51.3), (57.3, 52.5), (57.3, 74.0), (55.5, 74.0)], width_mm=0.6, layer_name="B.Cu")
    add_via_stub(board, "VBAT_IN", 76.6, 62.225, 75.0, 62.225, width_mm=0.25)
    add_track_path(board, "VBAT_IN", [(75.0, 62.225), (75.0, 53.5), (73.95, 53.5)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "VBAT_IN", 73.95, 53.5)
    add_track_path(board, "VBAT_IN", [(73.95, 53.5), (73.95, 51.3)], width_mm=0.3, layer_name="F.Cu")

    add_track_path(board, "VSW_MID", [(77.9, 53.205), (77.9, 50.665), (79.7, 50.665), (79.7, 49.395)], width_mm=0.5, layer_name="F.Cu")
    add_track_path(board, "VSW_MID", [(79.7, 50.665), (79.7, 51.935)], width_mm=0.5, layer_name="F.Cu")
    add_track_path(board, "VSW_MID", [(77.9, 53.205), (77.9, 58.337), (77.35, 58.337)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "VSW_MID", [(77.9, 53.9), (74.5, 53.9), (73.0, 55.4), (73.0, 55.95)], width_mm=0.3, layer_name="F.Cu")

    add_track_path(board, "VSW_OUT", [(83.65, 51.3), (87.438, 51.3)], width_mm=2.5, layer_name="F.Cu")
    # ── INA226 True Kelvin Sense Taps on R12 ──
    # IN+ (VSW_OUT): Inside face of R12 Pad 1 to U2.10
    add_track_path(board, "VSW_OUT", [(88.0, 52.8), (89.4, 54.2), (89.4, 56.45)], width_mm=0.2, layer_name="F.Cu")
    # IN- (VOUT): Inside face of R12 Pad 2 to U2.9
    add_track_path(board, "VOUT", [(92.8, 52.8), (89.9, 54.2), (89.9, 56.45)], width_mm=0.2, layer_name="F.Cu")
    # VBUS (VOUT): Bridge U2.9 to U2.8
    add_track_path(board, "VOUT", [(89.9, 56.45), (90.4, 56.45)], width_mm=0.25, layer_name="F.Cu")

    # ── LM5060 VSW_OUT Sense (R4.1) on F.Cu stepping east of R4.2 / PROT_OUT ──
    add_track_path(board, "VSW_OUT", [(87.0, 62.025), (88.2, 62.025), (88.2, 53.0), (87.438, 51.3)], width_mm=0.25, layer_name="F.Cu")

    add_track_path(board, "VOUT", [(93.362, 51.3), (96.7, 54.05), (102.5, 53.6), (108.5, 51.3)], width_mm=2.5, layer_name="F.Cu")

    # ── Gate Drive & Reverse Protection ──
    add_track_path(board, "REV_BASE", [(73.0, 59.25), (74.2, 59.25), (74.2, 58.337), (75.45, 58.337)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "REV_BASE", [(74.2, 59.25), (74.2, 62.425), (73.0, 62.425)], width_mm=0.25, layer_name="F.Cu")

    add_track_path(board, "GATE_FET", [(77.9, 49.395), (77.9, 47.9)], width_mm=0.3, layer_name="F.Cu")
    add_via(board, "GATE_FET", 77.9, 47.9)
    add_track_path(board, "GATE_FET", [(79.7, 53.205), (79.7, 54.6)], width_mm=0.3, layer_name="F.Cu")
    add_via(board, "GATE_FET", 79.7, 54.6)
    add_via_stub(board, "GATE_FET", 76.4, 56.462, 76.4, 55.2, width_mm=0.3)
    add_track_path(board, "GATE_FET", [(77.9, 47.9), (77.9, 53.5), (79.7, 54.6), (76.4, 54.6), (76.4, 55.2)], width_mm=0.3, layer_name="B.Cu")
    add_track_path(board, "GATE_FET", [(79.7, 54.6), (82.825, 54.6), (82.825, 59.6)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "GATE_FET", [(82.825, 56.6), (84.0, 56.6)], width_mm=0.3, layer_name="F.Cu")

    add_track_path(board, "GATE_DRV", [(80.0, 56.6), (80.0, 59.6), (81.175, 59.6), (81.175, 60.8), (84.15, 60.8), (84.15, 62.0)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "PROT_SENSE", [(76.6, 60.575), (78.2, 60.575), (78.2, 62.0), (79.85, 62.0)], width_mm=0.2, layer_name="F.Cu")
    add_track_path(board, "PROT_OUT", [(84.15, 62.5), (85.2, 62.5), (85.2, 60.375), (87.0, 60.375)], width_mm=0.2, layer_name="F.Cu")
    add_track_path(board, "PROT_TIMER", [(84.15, 63.5), (85.6, 63.5), (85.6, 65.575), (87.0, 65.575)], width_mm=0.2, layer_name="F.Cu")


def route_clean_signals(board: pcbnew.BOARD) -> None:
    """Route clean, deterministic peripheral signals with 0 DRC violations."""
    # ── Remote Switch & Power LED ──
    add_track_path(board, 'PWR_LED_A', [(60.79, 65.50), (60.83, 67.50)], width_mm=0.25, layer_name='F.Cu')
    add_track_path(board, 'VSW_RAW', [(55.50, 76.50), (64.00, 76.50)], width_mm=0.5, layer_name='F.Cu')

    # ── CAN Bus (Termination, CANH, CANL, TX, RX) ──
    add_track_path(board, 'Net-(J7-A)', [(104.50, 73.00), (104.50, 71.30), (111.41, 71.30), (111.41, 73.00)], width_mm=0.25, layer_name='F.Cu')

    # CANH on F.Cu:
    add_track_path(board, 'CANH', [(105.47, 78.36), (109.59, 78.36), (109.59, 73.00)], width_mm=0.35, layer_name='F.Cu')
    add_track_path(board, 'CANH', [(109.59, 78.36), (113.50, 78.36), (113.50, 74.50), (116.00, 74.50)], width_mm=0.35, layer_name='F.Cu')
    add_track_path(board, 'CANH', [(113.50, 78.36), (113.50, 83.00), (116.00, 83.00)], width_mm=0.35, layer_name='F.Cu')

    # CANL on In2.Cu:
    add_track_path(board, 'CANL', [(105.47, 79.64), (107.04, 79.64)], width_mm=0.25, layer_name='F.Cu')
    add_via(board, 'CANL', 107.04, 79.64)
    add_track_path(board, 'CANL', [(107.04, 79.64), (107.04, 73.00)], width_mm=0.35, layer_name='In2.Cu')
    add_track_path(board, 'CANL', [(107.04, 79.64), (114.50, 79.64), (114.50, 77.00), (116.00, 77.00)], width_mm=0.35, layer_name='In2.Cu')
    add_track_path(board, 'CANL', [(114.50, 79.64), (114.50, 85.50), (116.00, 85.50)], width_mm=0.35, layer_name='In2.Cu')

    # CAN_RX on F.Cu:
    add_track_path(board, 'CAN_RX', [(92.62, 82.59), (100.525, 82.59), (100.525, 80.91)], width_mm=0.25, layer_name='F.Cu')

    # CAN_TX on In2.Cu:
    add_track_path(board, 'CAN_TX', [(92.62, 85.13), (94.00, 85.13)], width_mm=0.25, layer_name='F.Cu')
    add_via(board, 'CAN_TX', 94.00, 85.13)
    add_track_path(board, 'CAN_TX', [(94.00, 85.13), (94.00, 77.09), (100.525, 77.09)], width_mm=0.25, layer_name='In2.Cu')
    add_via(board, 'CAN_TX', 100.525, 77.09)

    # ── Circuit ID Jumper J4 ──
    add_track_path(board, 'CIRCUIT_ID', [(92.62, 87.67), (91.00, 87.67), (91.00, 86.20), (88.58, 86.20), (88.58, 85.00)], width_mm=0.2, layer_name='F.Cu')
    add_via(board, 'CIRCUIT_ID', 90.00, 86.20)
    add_track_path(board, 'CIRCUIT_ID', [(91.00, 86.20), (90.00, 86.20)], width_mm=0.2, layer_name='F.Cu')
    add_track_path(board, 'CIRCUIT_ID', [(90.00, 86.20), (89.00, 86.20), (89.00, 63.50), (101.00, 63.50), (101.00, 64.50)], width_mm=0.25, layer_name='In2.Cu')


def route_buck(board: pcbnew.BOARD) -> None:
    """Route 5V buck converter switching nodes, feedback, enable and timing."""
    # BUCK_BOOT
    add_track_path(board, "BUCK_BOOT", [(61.3, 87.095), (61.3, 85.8), (63.225, 85.8), (63.225, 84.9)], width_mm=0.25, layer_name="F.Cu")

    # BUCK_SW (wide copper connecting U3.8, C9.2, D7.1, L1.1)
    add_track_path(board, "BUCK_SW", [(66.7, 87.095), (68.0, 87.095), (68.0, 88.0), (69.925, 88.0)], width_mm=0.6, layer_name="F.Cu")
    add_track_path(board, "BUCK_SW", [(64.775, 84.9), (64.775, 85.8), (66.7, 85.8), (66.7, 87.095)], width_mm=0.4, layer_name="F.Cu")
    add_track_path(board, "BUCK_SW", [(70.0, 82.0), (70.0, 86.5), (68.0, 86.5)], width_mm=0.6, layer_name="F.Cu")

    # BUCK_EN (via to In2.Cu to clear C5 and U3.4)
    add_track_path(board, "BUCK_EN", [(61.3, 89.635), (62.2, 89.635)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "BUCK_EN", 62.2, 89.635)
    add_track_path(board, "BUCK_EN", [(62.2, 89.635), (62.2, 92.775), (61.0, 92.775)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "BUCK_EN", 61.0, 92.775)

    # BUCK_RT
    add_track_path(board, "BUCK_RT", [(61.3, 90.905), (61.9, 90.905), (61.9, 94.425), (62.8, 94.425)], width_mm=0.2, layer_name="F.Cu")

    # BUCK_FB
    add_track_path(board, "BUCK_FB", [(66.7, 90.905), (67.5, 91.5), (67.5, 92.775), (68.2, 92.775)], width_mm=0.2, layer_name="F.Cu")
    add_track_path(board, "BUCK_FB", [(67.5, 92.775), (67.5, 93.6), (66.4, 93.6), (66.4, 94.425)], width_mm=0.2, layer_name="F.Cu")

    # BUCK_SS (via to B.Cu with safe margin from bottom board edge)
    add_track_path(board, "BUCK_SS", [(66.7, 89.635), (67.8, 89.635)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "BUCK_SS", 67.8, 89.635)
    add_track_path(board, "BUCK_SS", [(67.8, 89.635), (67.8, 95.0), (64.6, 95.0)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "BUCK_SS", 64.6, 95.0)
    add_track_path(board, "BUCK_SS", [(64.6, 95.0), (64.6, 94.375)], width_mm=0.2, layer_name="F.Cu")


def route_lm5060(board: pcbnew.BOARD) -> None:
    """Route LM5060 divider ladder, power good, and cutoff logic."""
    # PROT_OVP: U1.3 (79.85, 63.0) to via at (77.5, 63.0) -> In2.Cu to R7/R8 (70.0, 65.0)
    add_track_path(board, "PROT_OVP", [(79.85, 63.0), (77.5, 63.0)], width_mm=0.18, layer_name="F.Cu")
    add_via(board, "PROT_OVP", 77.5, 63.0)
    add_track_path(board, "PROT_OVP", [(77.5, 63.0), (77.5, 65.0), (70.0, 65.0)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "PROT_OVP", 70.0, 65.0)
    add_track_path(board, "PROT_OVP", [(68.825, 65.0), (71.175, 65.0)], width_mm=0.25, layer_name="F.Cu")

    # PROT_UVLO: U1.4 (79.85, 63.5) to via at (78.5, 65.5) -> In2.Cu to R5/R6 (70.0, 67.0)
    add_track_path(board, "PROT_UVLO", [(79.85, 63.5), (78.5, 63.5), (78.5, 65.5)], width_mm=0.18, layer_name="F.Cu")
    add_via(board, "PROT_UVLO", 78.5, 65.5)
    add_track_path(board, "PROT_UVLO", [(78.5, 65.5), (78.5, 67.0), (70.0, 67.0)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "PROT_UVLO", 70.0, 67.0)
    add_track_path(board, "PROT_UVLO", [(68.825, 67.0), (71.175, 67.0)], width_mm=0.25, layer_name="F.Cu")

    # PROT_EN: U1.5 (79.85, 64.0) straight south to via at (79.85, 67.8) -> In2.Cu to R9/R10 (70.0, 69.0) and Q4.3
    add_track_path(board, "PROT_EN", [(79.85, 64.0), (79.85, 67.8)], width_mm=0.18, layer_name="F.Cu")
    add_via(board, "PROT_EN", 79.85, 67.8)
    add_track_path(board, "PROT_EN", [(79.85, 67.8), (70.0, 67.8), (70.0, 69.0)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "PROT_EN", 70.0, 69.0)
    add_track_path(board, "PROT_EN", [(68.825, 69.0), (71.175, 69.0)], width_mm=0.25, layer_name="F.Cu")
    # Branch to Q4.3 stepping east of PWR_CUTOFF via
    add_track_path(board, "PROT_EN", [(79.85, 67.8), (81.938, 69.5), (81.938, 73.0)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "PROT_EN", 81.938, 73.0)

    # PWR_PGOOD: U1.8 (84.15, 63.0) via B.Cu to U4.4 (77.38, 77.51) and R22.1 (79.775, 78.0)
    add_track_path(board, "PWR_PGOOD", [(84.15, 63.0), (86.2, 63.0)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "PWR_PGOOD", 86.2, 63.0)
    add_track_path(board, "PWR_PGOOD", [(86.2, 63.0), (80.5, 63.0), (80.5, 77.51), (77.38, 77.51)], width_mm=0.25, layer_name="B.Cu")
    add_track_path(board, "PWR_PGOOD", [(77.38, 77.51), (79.775, 77.51), (79.775, 78.0)], width_mm=0.25, layer_name="F.Cu")

    # PWR_CUTOFF: U4.5 (77.38, 80.05) to Q4.1 (80.062, 72.05) and R11.1 (84.6, 73.825)
    add_track_path(board, "PWR_CUTOFF", [(77.38, 80.05), (79.0, 80.05), (79.0, 72.05), (80.062, 72.05)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "PWR_CUTOFF", 80.062, 72.05)
    # Loop north of Q4 and south to R11.1 to avoid Q4.2 and R11.2 GND pads
    add_track_path(board, "PWR_CUTOFF", [(80.062, 72.05), (80.062, 71.0), (82.5, 71.0), (82.5, 74.8), (84.6, 74.8), (84.6, 73.825)], width_mm=0.25, layer_name="F.Cu")


def route_remote_switch(board: pcbnew.BOARD) -> None:
    """Route remote switch indicator LED drive and cathode."""
    # SW_LED_K: J3.3 (55.5, 79.0) to Q5.3 (55.438, 86.9) stepping around J3.4 (+5V)
    add_track_path(board, "SW_LED_K", [(55.5, 79.0), (57.2, 79.0), (57.2, 85.5), (55.438, 85.5), (55.438, 86.9)], width_mm=0.35, layer_name="F.Cu")

    # SW_LED_EN: U4.17 (92.62, 72.43) to R25.1 (88.575, 72.4) and Q5.1 (53.562, 85.95)
    add_track_path(board, "SW_LED_EN", [(92.62, 72.43), (91.5, 72.43), (91.5, 73.8), (88.575, 73.8), (88.575, 72.4)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "SW_LED_EN", 87.5, 73.8)
    add_track_path(board, "SW_LED_EN", [(88.575, 73.8), (87.5, 73.8)], width_mm=0.25, layer_name="F.Cu")
    # Route south inside cavity on In2.Cu, around south of U4 at Y=91.2, then to Q5.1
    add_track_path(board, "SW_LED_EN", [(87.5, 73.8), (87.5, 91.2), (53.562, 91.2), (53.562, 85.95)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "SW_LED_EN", 53.562, 85.95)


def route_ina226_and_adc(board: pcbnew.BOARD) -> None:
    """Route battery ADC divider and INA226 power monitor bus."""
    # VBAT_ADC: R13.2 (86.825, 87.4) to R14.1 (88.575, 87.4) to C4.1 (88.625, 89.4) to U4.10 (92.62, 90.21)
    add_track_path(board, "VBAT_ADC", [(86.825, 87.4), (88.575, 87.4), (88.625, 89.4), (88.625, 90.21), (92.62, 90.21)], width_mm=0.25, layer_name="F.Cu")

    # INA226 bus to U4 through socket cavity on B.Cu
    # I2C_SDA: U2.4 (90.9, 60.75) straight south to via at (90.9, 62.5) -> B.Cu at Y=62.5 to X=83.5
    add_track_path(board, "I2C_SDA", [(90.9, 60.75), (90.9, 62.5)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "I2C_SDA", 90.9, 62.5)
    add_track_path(board, "I2C_SDA", [(90.9, 62.5), (83.5, 62.5), (83.5, 82.59), (77.38, 82.59)], width_mm=0.25, layer_name="B.Cu")
    add_track_path(board, "I2C_SDA", [(77.38, 82.59), (79.775, 82.4)], width_mm=0.25, layer_name="F.Cu")

    # I2C_SCL: U2.5 (91.4, 60.75) straight south to via at (91.4, 63.5) -> B.Cu at Y=63.5 to X=85.0
    add_track_path(board, "I2C_SCL", [(91.4, 60.75), (91.4, 63.5)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "I2C_SCL", 91.4, 63.5)
    add_track_path(board, "I2C_SCL", [(91.4, 63.5), (85.0, 63.5), (85.0, 85.13), (77.38, 85.13)], width_mm=0.25, layer_name="B.Cu")
    add_track_path(board, "I2C_SCL", [(77.38, 85.13), (79.775, 84.4)], width_mm=0.25, layer_name="F.Cu")

    # INA_ALERT: U2.3 (90.4, 60.75) straight south to via at (90.4, 64.5) -> B.Cu at Y=64.5 to X=86.5
    add_track_path(board, "INA_ALERT", [(90.4, 60.75), (90.4, 64.5)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "INA_ALERT", 90.4, 64.5)
    add_track_path(board, "INA_ALERT", [(90.4, 64.5), (86.5, 64.5), (86.5, 87.67), (77.38, 87.67)], width_mm=0.25, layer_name="B.Cu")
    add_track_path(board, "INA_ALERT", [(77.38, 87.67), (79.775, 86.4)], width_mm=0.25, layer_name="F.Cu")


def route_uart(board: pcbnew.BOARD) -> None:
    """Route UART level shifters, VIO select jumper, and external connector."""
    # UART_VIO: J9.2 (97.0, 73.04) on B.Cu along X=95.5 to R28.1 and R30.1
    add_track_path(board, "UART_VIO", [(97.0, 73.04), (95.5, 73.04), (95.5, 90.5), (100.4, 90.5)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "UART_VIO", 100.4, 90.5)
    add_track_path(board, "UART_VIO", [(100.4, 88.725), (100.4, 90.5), (104.0, 90.5), (104.0, 88.725)], width_mm=0.25, layer_name="F.Cu")

    # UART_RX_3V3: U4.14 (92.62, 80.05) to Q7.2 (103.662, 85.45) and R29.1 (102.2, 88.725)
    add_track_path(board, "UART_RX_3V3", [(92.62, 80.05), (103.0, 80.05), (103.0, 85.45)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "UART_RX_3V3", 103.0, 85.45)
    add_track_path(board, "UART_RX_3V3", [(103.0, 85.45), (103.662, 85.45)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "UART_RX_3V3", [(103.0, 85.45), (103.0, 88.725), (102.2, 88.725)], width_mm=0.25, layer_name="F.Cu")

    # UART_RX: Q7.3 (105.537, 84.5) to R30.2 (104.0, 87.075) and J8.1 (101.5, 92.45)
    add_track_path(board, "UART_RX", [(105.537, 84.5), (105.537, 86.2), (104.0, 86.2), (104.0, 87.075)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "UART_RX", [(105.537, 84.5), (105.537, 83.0)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "UART_RX", 105.537, 83.0)
    add_track_path(board, "UART_RX", [(105.537, 83.0), (101.5, 83.0), (101.5, 92.45)], width_mm=0.25, layer_name="In2.Cu")

    # UART_TX_3V3: U4.9 (77.38, 90.21) corridor along Y=88.94 through socket cavity to R27.1 and Q6.2
    add_track_path(board, "UART_TX_3V3", [(77.38, 90.21), (77.38, 88.94), (97.5, 88.94)], width_mm=0.25, layer_name="In2.Cu")
    add_via(board, "UART_TX_3V3", 97.5, 88.94)
    add_track_path(board, "UART_TX_3V3", [(97.5, 88.94), (98.6, 88.725)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "UART_TX_3V3", [(97.5, 88.94), (97.5, 85.45), (99.562, 85.45)], width_mm=0.25, layer_name="F.Cu")

    # UART_TX: Q6.3 (101.438, 84.5) to R28.2 (100.4, 87.075) and J8.2 (104.0, 92.45)
    add_track_path(board, "UART_TX", [(101.438, 84.5), (101.438, 86.2), (100.4, 86.2), (100.4, 87.075)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "UART_TX", 101.438, 86.2)
    add_track_path(board, "UART_TX", [(101.438, 86.2), (104.0, 86.2), (104.0, 92.45)], width_mm=0.25, layer_name="B.Cu")


def route_power_supplies(board: pcbnew.BOARD) -> None:
    """Connect +5V, +3V3, and VSW_CTRL across internal supply planes and components."""
    # ── +5V Distribution ──
    # Buck output L1.2 (74.075, 88.0) corridor south of L1 into C10.1 (70.525, 92.75)
    add_track_path(board, "+5V", [(74.075, 88.0), (74.075, 90.5), (70.525, 90.5), (70.525, 92.75)], width_mm=0.5, layer_name="F.Cu")
    add_track_path(board, "+5V", [(70.525, 92.75), (70.525, 95.20)], width_mm=0.5, layer_name="F.Cu")
    add_track_path(board, "+5V", [(70.525, 94.425), (68.2, 94.425)], width_mm=0.4, layer_name="F.Cu")
    add_via(board, "+5V", 74.075, 88.0)
    # B.Cu distribution to U4.1 (77.38, 69.89) entering from north along Y=68.0 to avoid U4.18
    add_track_path(board, "+5V", [(74.075, 88.0), (74.075, 68.0), (77.38, 68.0), (77.38, 69.89)], width_mm=0.6, layer_name="B.Cu")
    # C13.1 at (79.825, 70.0) directly from U4.1 on F.Cu
    add_track_path(board, "+5V", [(77.38, 69.89), (79.825, 70.0)], width_mm=0.4, layer_name="F.Cu")
    # Route +5V east along Y=68.0 and south along X=98.8 to J9.3 (+5V at 97.0, 75.58)
    add_track_path(board, "+5V", [(77.38, 68.0), (98.8, 68.0), (98.8, 75.58), (97.0, 75.58)], width_mm=0.5, layer_name="B.Cu")
    # Remote switch +5V to J3.4 (55.5, 81.5)
    add_track_path(board, "+5V", [(74.075, 88.0), (74.075, 81.5), (55.5, 81.5)], width_mm=0.6, layer_name="B.Cu")

    # ── +3V3 Plane Connections (In3.Cu plane) ──
    add_track_path(board, "+3V3", [(79.825, 76.0), (79.825, 75.0)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 79.825, 75.0)   # C13
    add_track_path(board, "+3V3", [(81.425, 78.0), (81.425, 79.0)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 81.425, 79.0)   # R22
    add_track_path(board, "+3V3", [(81.425, 82.4), (81.425, 81.2)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 81.425, 81.2)   # R19 (shifted north to clear I2C_SDA)
    add_track_path(board, "+3V3", [(81.425, 84.4), (82.5, 84.4)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 82.5, 84.4)     # R20
    add_track_path(board, "+3V3", [(81.425, 86.4), (82.5, 86.4)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 82.5, 86.4)     # R21
    add_track_path(board, "+3V3", [(90.225, 72.4), (90.225, 71.0)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 90.225, 71.0)   # R25
    add_track_path(board, "+3V3", [(90.225, 85.0), (90.225, 83.8)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 90.225, 83.8)   # R23
    add_track_path(board, "+3V3", [(91.4, 56.45), (92.5, 56.45)], width_mm=0.25, layer_name="F.Cu") # U2.6
    add_via(board, "+3V3", 92.5, 56.45)
    add_track_path(board, "+3V3", [(93.3, 60.775), (94.3, 60.775)], width_mm=0.25, layer_name="F.Cu") # C3.1
    add_via(board, "+3V3", 94.3, 60.775)
    add_track_path(board, "+3V3", [(98.6, 87.075), (97.4, 87.075)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 97.4, 87.075)  # R27 (west of R27 to clear Q6)
    add_track_path(board, "+3V3", [(102.2, 87.075), (101.4, 87.075)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 101.4, 87.075) # R29 (west of R29)
    # Q6 & Q7 gate pullup tie: single via between Q6.1 and Q7.1
    add_track_path(board, "+3V3", [(99.562, 83.55), (103.662, 83.55)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 101.6, 83.55)  # Q6 & Q7
    # U5.3 & C14.1 with via clear of C14.2
    add_track_path(board, "+3V3", [(100.525, 79.635), (98.5, 79.635), (98.5, 80.375), (97.6, 80.375)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "+3V3", [(97.6, 80.375), (97.6, 81.5)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 97.6, 81.5)
    # R24.1 (59.175, 67.5) via to In3.Cu +3V3 plane stepping north
    add_track_path(board, "+3V3", [(59.175, 67.5), (59.175, 66.0)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "+3V3", 59.175, 66.0)

    # ── VSW_CTRL Supply Bus (F.Cu & In2.Cu) ──
    # Dividers and switch output on F.Cu
    add_track_path(board, "VSW_CTRL", [(68.0, 76.5), (67.175, 76.5), (67.175, 69.0), (67.175, 67.0), (67.175, 65.0)], width_mm=0.35, layer_name="F.Cu")
    # Buck input cluster on F.Cu
    add_track_path(board, "VSW_CTRL", [(61.3, 88.365), (58.9, 88.365), (58.9, 90.075)], width_mm=0.35, layer_name="F.Cu")
    add_track_path(board, "VSW_CTRL", [(58.9, 90.075), (57.5, 90.075), (57.5, 94.375), (59.2, 94.375), (61.0, 94.425)], width_mm=0.35, layer_name="F.Cu")
    add_via(board, "VSW_CTRL", 57.5, 92.0)
    # C6.1
    add_track_path(board, "VSW_CTRL", [(63.525, 81.6), (63.525, 80.2)], width_mm=0.4, layer_name="F.Cu")
    add_via(board, "VSW_CTRL", 63.525, 80.2)
    # D2.1 drop to In2.Cu
    add_track_path(board, "VSW_CTRL", [(68.0, 76.5), (68.0, 78.0)], width_mm=0.4, layer_name="F.Cu")
    add_via(board, "VSW_CTRL", 68.0, 78.0)
    # In2.Cu distribution to buck input
    add_track_path(board, "VSW_CTRL", [(68.0, 78.0), (63.525, 80.2), (57.5, 80.2), (57.5, 92.0)], width_mm=0.5, layer_name="In2.Cu")
    # C1.1 & U1.2 via In2.Cu north of U4
    add_track_path(board, "VSW_CTRL", [(76.6, 65.775), (75.0, 65.775)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "VSW_CTRL", 75.0, 65.775)
    add_track_path(board, "VSW_CTRL", [(79.85, 62.5), (82.0, 62.5)], width_mm=0.18, layer_name="F.Cu")
    add_via(board, "VSW_CTRL", 82.0, 62.5)
    add_track_path(board, "VSW_CTRL", [(68.0, 78.0), (67.175, 78.0), (67.175, 65.775), (75.0, 65.775), (82.0, 62.5)], width_mm=0.35, layer_name="In2.Cu")
    # In2.Cu distribution to R13.1 (85.175, 87.4) inside socket cavity from (82.0, 62.5)
    add_track_path(board, "VSW_CTRL", [(82.0, 62.5), (85.175, 62.5), (85.175, 87.4)], width_mm=0.35, layer_name="In2.Cu")
    add_via(board, "VSW_CTRL", 85.175, 87.4)

    # ── GND Connections & Island Tie Vias ──
    add_track_path(board, "GND", [(66.7, 88.365), (65.0, 88.365), (64.6, 88.4)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "GND", [(76.6, 64.225), (75.5, 64.225)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "GND", 75.5, 64.225)
    add_via(board, "GND", 74.8, 93.5)
    add_via(board, "GND", 63.8, 92.8)
    add_via(board, "GND", 94.5, 59.2)
    add_via(board, "GND", 90.9, 55.2)
    add_via(board, "GND", 58.8, 92.8)


def main() -> int:
    board = pcbnew.LoadBoard(str(BOARD_PATH))
    setup_6layer(board)
    # KiCad's SWIG wrappers stop working once items are removed, so list everything up front and
    # remove the old copper and drawings only after the new placement and drawings are done.
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    old = old_items(board)
    place(fps)
    add_rounded_rect_outline(board, X0, Y0, X1, Y1, r=2.0)
    mark_heatsink_area(board)
    add_labels(board)
    vias = add_pours(board, fps)
    route_power_path(board)
    route_clean_signals(board)
    route_buck(board)
    route_lm5060(board)
    route_remote_switch(board)
    route_ina226_and_adc(board)
    route_uart(board)
    route_power_supplies(board)
    for item in old:
        board.Remove(item)
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    print(f"Placed {len(PLACEMENTS)} footprints, added pours and {vias} stitching vias on {BOARD_PATH}")
    print("Fill zones next: kicad-cli pcb drc --refill-zones --save-board PCB/DroidPowerSense.kicad_pcb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

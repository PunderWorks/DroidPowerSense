#!/usr/bin/env python3
"""Deterministic placement, copper pours, routing, and silkscreen for PCB/DroidPowerSense.kicad_pcb.

Run with KiCad 10's bundled Python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 scripts/layout_pcb.py
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import pcbnew


BOARD_PATH = Path(__file__).resolve().parents[1] / "PCB" / "DroidPowerSense.kicad_pcb"
KI10_MOD_DIR = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
SYNC_HEADLESS = Path("/Users/jessica/repos/stackup/kicad-plugin")

PROJECT_PATH = BOARD_PATH.with_suffix(".kicad_pro")

# Net classes (2 oz outer / 1 oz inner copper): the routing defaults KiCad uses for each net.
# The high-current path itself is carried by pours. Some tracks below are deliberately narrower
# than their class: the Kelvin sense lines to the INA226 (0.5 mm pitch), the VBAT_IN sense line to
# R3, and the VSW_MID spur to the reverse-polarity clamp carry microamps to milliamps.
# (name, track mm, clearance mm, via dia mm, via drill mm, description, net patterns)
NET_CLASSES = [
    ("HighCurrent", 3.0, 0.2, 0.8, 0.4, "30 A continuous / 60 A peak battery passthrough",
     ["VBAT_IN", "VSW_MID", "VSW_OUT", "VOUT"]),
    ("Power", 0.5, 0.2, 0.6, 0.3, "Board supplies and returns (< 1 A)",
     ["GND", "VSW_CTRL", "VSW_RAW", "+5V", "+3V3", "BUCK_SW", "UART_VIO"]),
    ("GateDrive", 0.3, 0.2, 0.6, 0.3, "LM5060 gate drive, 80 mA fault pull-down",
     ["GATE_FET", "GATE_DRV", "REV_BASE"]),
    ("CAN", 0.35, 0.2, 0.6, 0.3, "CAN FD bus pair",
     ["CANH", "CANL", "Net-(J7-A)"]),
]

CLASS_MIN_WIDTH = {
    net: track for name, track, _, _, _, _, nets in NET_CLASSES if name != "HighCurrent" for net in nets
}

# Pins on U1 (LM5060, VSSOP-10) and U2 (INA226, VSSOP-10) where a class-width track won't fit.
NECK_POINTS = {
    (75.85, 75.0), (80.15, 76.5),                    # U1.2 VIN, U1.6 GND
    (74.2, 75.0),                                    # VSW_CTRL bend beside PROT_OVP
    (105.5, 67.35), (105.0, 67.35),                  # U2.6 VS, U2.7 GND
    (104.0, 71.65), (103.5, 71.65),                  # U2.2 A0, U2.1 A1 (GND)
}


def write_net_classes() -> None:
    """Write NET_CLASSES and their net patterns into the KiCad project. Stackup's sync keeps
    classes and patterns that aren't prefixed `stackup:`, and the board picks them up on load."""
    import json

    pro = json.loads(PROJECT_PATH.read_text())
    ns = pro.setdefault("net_settings", {})
    classes = [c for c in ns.get("classes", []) if c.get("name") == "Default"]
    template = dict(classes[0]) if classes else {}
    for name, track, clearance, via_dia, via_drill, desc, _ in NET_CLASSES:
        c = dict(template)
        c.update({
            "name": name, "description": desc, "track_width": track, "clearance": clearance,
            "via_diameter": via_dia, "via_drill": via_drill, "priority": len(classes) - 1,
        })
        classes.append(c)
    ns["classes"] = classes
    ns["netclass_patterns"] = [
        {"netclass": name, "pattern": net}
        for name, _, _, _, _, _, nets in NET_CLASSES for net in nets
    ]
    PROJECT_PATH.write_text(json.dumps(pro, indent=2) + "\n")


EMPTY_4LAYER_PCB = """(kicad_pcb
\t(version 20260206)
\t(generator "pcbnew")
\t(generator_version "10.0")
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(4 "In1.Cu" signal)
\t\t(6 "In2.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t\t(39 "User.1" user "stackup")
\t\t(41 "User.2" user)
\t\t(43 "User.3" user)
\t\t(45 "User.4" user)
\t)
\t(setup
\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.07))
\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 2" (type "core") (thickness 0.95) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.2104) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.07))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
\t\t\t(copper_finish "ENIG")
\t\t\t(dielectric_constraints no)
\t\t)
\t\t(pad_to_mask_clearance 0)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(tenting (front yes) (back yes))
\t\t(covering (front no) (back no))
\t\t(plugging (front no) (back no))
\t\t(capping no)
\t\t(filling no)
\t)
\t(net 0 "")
)
"""


def mm(val: float) -> int:
    return pcbnew.FromMM(val)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def fresh_synced_board() -> pcbnew.BOARD:
    """Write a clean 4-layer PCB header, sync from stackup/board.kdl, and return the loaded board."""
    BOARD_PATH.write_text(EMPTY_4LAYER_PCB)
    write_net_classes()
    sys.path.insert(0, str(SYNC_HEADLESS))
    import sync_headless
    sync_headless.sync(BOARD_PATH, force=True)
    return pcbnew.LoadBoard(str(BOARD_PATH))


def add_rounded_rect_outline(
    board: pcbnew.BOARD, x0: float, y0: float, x1: float, y1: float, r: float = 2.0
) -> None:
    """Add a closed rounded-rectangle Edge.Cuts outline."""
    layer = board.GetLayerID("Edge.Cuts")
    width = mm(0.1)

    segments = [
        ((x0 + r, y0), (x1 - r, y0)),
        ((x1, y0 + r), (x1, y1 - r)),
        ((x1 - r, y1), (x0 + r, y1)),
        ((x0, y1 - r), (x0, y0 + r)),
    ]
    for (sx, sy), (ex, ey) in segments:
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(layer)
        seg.SetStart(pt(sx, sy))
        seg.SetEnd(pt(ex, ey))
        seg.SetWidth(width)
        board.Add(seg)

    s45 = r * math.sin(math.pi / 4.0)
    corners = [
        ((x0, y0 + r), (x0 + r - s45, y0 + r - s45), (x0 + r, y0)),
        ((x1 - r, y0), (x1 - r + s45, y0 + r - s45), (x1, y0 + r)),
        ((x1, y1 - r), (x1 - r + s45, y1 - r + s45), (x1 - r, y1)),
        ((x0 + r, y1), (x0 + r - s45, y1 - r + s45), (x0, y1 - r)),
    ]
    for (sx, sy), (mx, my), (ex, ey) in corners:
        arc = pcbnew.PCB_SHAPE(board)
        arc.SetShape(pcbnew.SHAPE_T_ARC)
        arc.SetLayer(layer)
        arc.SetArcGeometry(pt(sx, sy), pt(mx, my), pt(ex, ey))
        arc.SetWidth(width)
        board.Add(arc)


def add_mounting_holes(board: pcbnew.BOARD) -> None:
    """Place 4 M3 mounting holes (board_only) at the 4 corners."""
    lib_path = str(KI10_MOD_DIR / "MountingHole.pretty")
    coords = [
        ("H1", 54.0, 50.0),
        ("H2", 136.0, 50.0),
        ("H3", 54.0, 108.0),
        ("H4", 136.0, 108.0),
    ]
    for ref, x, y in coords:
        fp = pcbnew.FootprintLoad(lib_path, "MountingHole_3.2mm_M3")
        fp.SetReference(ref)
        fp.SetValue("M3")
        fp.SetPosition(pt(x, y))
        fp.SetAttributes(
            pcbnew.FP_THROUGH_HOLE
            | pcbnew.FP_BOARD_ONLY
            | pcbnew.FP_EXCLUDE_FROM_POS_FILES
            | pcbnew.FP_EXCLUDE_FROM_BOM
        )
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        board.Add(fp)


def place_footprints(board: pcbnew.BOARD) -> dict[str, pcbnew.FOOTPRINT]:
    """Place all 72 synced footprints and configure reference label positions."""
    placements: dict[str, tuple[float, float, float, float, float, bool]] = {
        # ── High-current power path (top strip, Y = 58..66) ──
        "J1": (67.0, 66.0, 90.0, -7.5, -9.5, True),     # XT60PW-M (VBAT_IN at 67,58.8; GND at 67,66)
        "D1": (75.0, 62.4, -90.0, 0.0, -5.8, True),    # SMCJ33CA input TVS (1=VBAT_IN at 59.0, 2=GND at 65.8)
        "Q1": (83.5, 58.8, 180.0, 0.0, -4.0, True),    # CSD18532Q5B (5=VBAT_IN at 82.45,58.8; 1-3=VSW_MID at 86.4; 4=GATE at 86.4,56.895)
        "Q2": (94.5, 58.8, 0.0, 0.0, -4.0, True),      # CSD18532Q5B (1-3=VSW_MID at 91.6; 4=GATE at 91.6,60.705; 5=VSW_OUT at 95.55,58.8)
        "R12": (104.5, 58.8, 0.0, 0.0, -3.0, True),    # 1mOhm 2512 shunt (1=VSW_OUT at 101.537, 2=VOUT at 107.463)
        "D6": (111.5, 62.4, -90.0, 0.0, -4.5, True),   # SMBJ33CA output TVS (1=VOUT at 60.25, 2=GND at 64.55)
        "D5": (117.5, 62.4, -90.0, 0.0, -5.8, True),   # B560C output flyback (1=VOUT at 59.0, 2=GND at 65.8)
        "J2": (124.0, 66.0, -90.0, 7.5, -9.5, True),    # XT60PW-F (VOUT at 124,58.8; GND at 124,66)

        # ── Gate clamp & sense passives near Q1/Q2/U1 ──
        "Q3": (89.0, 52.0, -90.0, -3.2, 0.0, True),    # Q_REV MMBT3904 (1=REV_BASE at 89.95,51.062; 2=VSW_MID at 88.05,51.062; 3=GATE_FET at 89.0,52.938)
        "D4": (89.0, 48.2, 180.0, 0.0, -1.8, False),   # D_REV 1N4148W (2=VSW_MID at 87.35,48.2; 1=REV_BASE at 90.65,48.2)
        "R2": (94.0, 51.062, 0.0, 0.0, -1.5, False),   # R_REV 47k (1=REV_BASE at 93.175; 2=GND at 94.825)
        "R3": (76.0, 69.5, -90.0, -2.0, 0.0, False),   # R_SENSE 22k (1=VBAT_IN at 68.675; 2=PROT_SENSE at 70.325)
        "R4": (96.0, 65.5, -90.0, 2.0, 0.0, False),    # R_OUT 10k (1=VSW_OUT at 64.675; 2=PROT_OUT at 66.325)
        "D3": (83.5, 66.5, 90.0, -2.8, 0.0, True),     # D_GOFF B160 (2=GATE_FET at 64.5; 1=GATE_DRV at 68.5)
        "R1": (87.5, 66.5, 90.0, 2.0, 0.0, False),     # R_GATE 2.2k (2=GATE_FET at 65.675; 1=GATE_DRV at 67.325)

        # ── Remote switch J3 & LM5060 high-side protection controller U1 ──
        "J3": (55.5, 78.0, -90.0, 0.0, -4.8, True),    # J_SW JST-XH (1=VBAT_IN at 55.5,78.0; 2=VSW_RAW at 55.5,80.5)
        "D2": (63.0, 80.5, 180.0, 0.0, 2.6, True),     # D_SW B160 (2=VSW_RAW at 61.0,80.5; 1=VSW_CTRL at 65.0,80.5)
        "U1": (78.0, 75.5, 0.0, 0.0, -2.6, True),      # LM5060 (pins 1-5 at X=75.85, Y=74.5..76.5; pins 6-10 at X=80.15, Y=76.5..74.5)
        "C1": (71.5, 73.0, 0.0, 0.0, -1.5, False),     # C_PROT_VIN 100nF (1=VSW_CTRL at 70.725, 2=GND at 72.275)
        "R7": (71.5, 75.0, 0.0, 0.0, -1.5, False),     # R_OVP1 180k (1=VSW_CTRL at 70.675, 2=PROT_OVP at 72.325)
        "R8": (71.5, 77.0, 180.0, 0.0, -1.5, False),   # R_OVP2 10k (2=GND at 70.675, 1=PROT_OVP at 72.325)
        "R5": (71.5, 79.0, 0.0, 0.0, -1.5, False),     # R_UVLO1 33k (1=VSW_CTRL at 70.675, 2=PROT_UVLO at 72.325)
        "R6": (71.5, 81.0, 180.0, 0.0, -1.5, False),   # R_UVLO2 10k (2=GND at 70.675, 1=PROT_UVLO at 72.325)
        "R9": (71.5, 83.0, 0.0, 0.0, -1.5, False),     # R_EN1 100k (1=VSW_CTRL at 70.675, 2=PROT_EN at 72.325)
        "R10": (71.5, 85.0, 180.0, 0.0, -1.5, False),  # R_EN2 47k (2=GND at 70.675, 1=PROT_EN at 72.325)
        "Q4": (78.0, 83.5, 180.0, -3.2, 0.0, True),     # Q_CUTOFF BSS138 (1=PWR_CUTOFF at 78.938,84.45; 2=GND at 78.938,82.55; 3=PROT_EN at 77.062,83.5)
        "R11": (78.0, 86.5, 180.0, 0.0, 1.5, False),   # R_CUTOFF_PD 100k (2=GND at 77.175, 1=PWR_CUTOFF at 78.825)
        "R22": (84.0, 75.5, 0.0, 0.0, -1.5, False),    # R_PROT_PGD 10k (1=PWR_PGOOD at 83.175, 2=+3V3 at 84.825)
        "C2": (84.0, 77.5, 0.0, 0.0, 1.5, False),      # C_TIMER 100nF (1=PROT_TIMER at 83.225, 2=GND at 84.775)

        # ── Pre-MOSFET battery ADC divider (feeds U4.Pad10 VBAT_ADC) ──
        "R13": (65.0, 85.0, 0.0, 0.0, -1.5, False),    # R_VBAT_TOP 100k (1=VSW_CTRL at 64.175, 2=VBAT_ADC at 65.825)
        "R14": (65.0, 87.0, 180.0, 0.0, -1.5, False),  # R_VBAT_BOT 10k (2=GND at 64.175, 1=VBAT_ADC at 65.825)
        "C4": (65.0, 89.0, 180.0, 0.0, -1.5, False),   # C_VBAT_ADC 100nF (2=GND at 64.225, 1=VBAT_ADC at 65.775)

        # ── Current & Voltage Monitor U2 (INA226) right below R12 ──
        "U2": (104.5, 69.5, 90.0, 3.6, 0.0, True),     # INA226 (rot 90: 8,9=VOUT & 10=VSW_OUT at Y=67.35; 3=ALERT,4=SDA,5=SCL at Y=71.65)
        "C3": (100.0, 69.5, 180.0, 0.0, -1.5, False),  # U_INA Cvs 100nF (1=+3V3 at 100.775, 2=GND at 99.225)
        "R21": (96.0, 73.5, 180.0, 0.0, -1.5, False),  # R_INA_ALERT 10k (2=+3V3 at 95.175, 1=INA_ALERT at 96.825)
        "R19": (96.0, 75.5, 180.0, 0.0, -1.5, False),  # R_I2C_SDA 4.7k (2=+3V3 at 95.175, 1=I2C_SDA at 96.825)
        "R20": (96.0, 77.5, 180.0, 0.0, -1.5, False),  # R_I2C_SCL 4.7k (2=+3V3 at 95.175, 1=I2C_SCL at 96.825)

        # ── 5V Step-Down Buck Converter (LMR14030SDDAR, bottom-left quadrant) ──
        "C5": (60.5, 94.0, 0.0, 0.0, -2.0, False),     # C_BUCK_IN1 10uF 1206 (1=VSW_CTRL, 2=GND)
        "C6": (60.5, 97.2, 0.0, 0.0, -2.0, False),     # C_BUCK_IN2 10uF 1206 (1=VSW_CTRL, 2=GND)
        "C7": (61.2, 99.8, 0.0, 0.0, -1.5, False),     # C_BUCK_IN3 100nF (1=VSW_CTRL, 2=GND)
        "R15": (61.2, 101.8, 0.0, 0.0, -1.5, False),   # R_BUCK_EN 100k (1=VSW_CTRL, 2=BUCK_EN)
        "R16": (61.2, 103.8, 0.0, 0.0, -1.5, False),   # R_BUCK_RT 100k (1=BUCK_RT, 2=GND)
        "U3": (67.5, 100.0, 0.0, 0.0, -6.5, True),     # LMR14030 (1=BOOT,2=VIN,3=EN,4=RT at X=64.8; 5=FB,6=SS,7=GND,8=SW at X=70.2)
        "C9": (67.5, 95.5, 0.0, 0.0, -1.5, False),     # C_BUCK_BOOT 100nF (1=BUCK_BOOT, 2=BUCK_SW)
        "D7": (73.0, 95.5, 0.0, 0.0, -2.5, True),      # D_BUCK B360A (1=BUCK_SW at 71.0, 2=GND at 75.0)
        "L1": (75.5, 101.5, 0.0, 0.0, 4.0, True),      # L_BUCK 10uH (1=BUCK_SW at 73.425, 2=+5V at 77.575)
        "C8": (73.5, 106.5, 0.0, 0.0, 1.5, False),     # C_BUCK_SS 10nF (1=BUCK_SS, 2=GND)
        "R17": (67.5, 105.0, 0.0, 0.0, 1.5, False),    # R_FB_TOP 56.2k (1=+5V at 66.675, 2=BUCK_FB at 68.325)
        "R18": (67.5, 107.0, 180.0, 0.0, 1.5, False),  # R_FB_BOT 10k (2=GND at 66.675, 1=BUCK_FB at 68.325)
        "C10": (80.5, 89.2, 180.0, 0.0, -2.0, False),  # C_BUCK_OUT1 10uF 1206 (1=+5V at 81.975, 2=GND at 79.025)
        "C11": (80.5, 92.4, 180.0, 0.0, -2.0, False),  # C_BUCK_OUT2 10uF 1206 (1=+5V at 81.975, 2=GND at 79.025)
        "C12": (81.2, 86.5, 180.0, 0.0, -1.5, False),  # C_BUCK_OUT3 100nF (1=+5V at 81.975, 2=GND at 80.425)

        # ── MCU (Waveshare ESP32-C5-Zero) & +3V3 local bypass / LED ──
        "U4": (95.0, 97.5, 0.0, 0.0, -16.5, True),     # ESP32-C5-Zero (pads 1-9 at X=86.8, Y=85.09..105.41; pads 10-18 at X=103.2)
        "C13": (82.0, 98.0, 180.0, 0.0, -1.5, False),  # C_3V3_1 100nF (1=+3V3 at 82.775, 2=GND at 81.225)
        "R24": (82.0, 101.0, 180.0, 0.0, -1.5, False), # R_PWR_LED 1k (1=+3V3 at 82.825, 2=PWR_LED_A at 81.175)
        "D8": (82.0, 103.5, 0.0, 0.0, 2.2, True),       # D_PWR_LED green (1=GND at 81.213, 2=PWR_LED_A at 82.787)

        # ── Circuit ID jumper (J4) & pull-up (R23) ──
        "R23": (108.5, 102.87, 0.0, 0.0, -1.5, False), # R_CIRCUIT_PU 10k (1=CIRCUIT_ID, 2=+3V3)
        "J4": (113.5, 102.87, 0.0, 0.0, -2.5, True),   # J_CIRCUIT 1x02 (1=CIRCUIT_ID at 102.87, 2=GND at 105.41)

        # ── CAN FD Transceiver (U5 TCAN334G), Termination (R25, J7), Dual JST-XH (J5, J6) ──
        "U5": (115.5, 96.0, 0.0, 0.0, -3.5, True),     # TCAN334G (1=TX,2=GND,3=+3V3,4=RX at X=113.025; 6=CANL,7=CANH at X=117.975)
        "C14": (109.5, 96.635, 0.0, 0.0, -1.5, False), # Cvcc 100nF (1=+3V3, 2=GND)
        "R25": (122.5, 95.365, 0.0, 0.0, 2.4, True),   # R_TERM 120R 0805 (1=CANH at 121.588, 2=Net-(J7-A) at 123.412)
        "J7": (126.5, 95.365, 0.0, 0.0, 5.8, True),    # J_TERM 1x02 (1=Net-(J7-A) at 95.365, 2=CANL at 97.905)
        "J5": (134.5, 91.5, 90.0, 0.0, -5.8, True),    # J_CAN1 JST-XH (1=CANL at 134.5,91.5; 2=CANH at 134.5,89.0)
        "J6": (134.5, 100.0, 90.0, 0.0, 3.3, True),    # J_CAN2 JST-XH (1=CANL at 134.5,100.0; 2=CANH at 134.5,97.5)

        # ── Level-Shifted UART (Q5, Q6, R26..R29, J9 VIO jumper, J8 JST-XH) ──
        "Q6": (110.5, 86.0, 0.0, 0.0, -2.4, True),     # Q_RX BSS138 (1=+3V3 at 109.562,85.05; 2=UART_RX_3V3 at 109.562,86.95; 3=UART_RX at 111.438,86.0)
        "R28": (109.5, 89.2, 0.0, 0.0, -1.5, False),   # R_RX_3V3 4.7k (1=UART_RX_3V3, 2=+3V3)
        "R29": (115.5, 86.0, 180.0, 0.0, -1.5, False), # R_RX_VIO 4.7k (1=UART_VIO at 116.325, 2=UART_RX at 114.675)
        "Q5": (110.5, 79.0, 0.0, 0.0, -2.4, True),     # Q_TX BSS138 (1=+3V3 at 109.562,78.05; 2=UART_TX_3V3 at 109.562,79.95; 3=UART_TX at 111.438,79.0)
        "R26": (109.5, 82.2, 0.0, 0.0, -1.5, False),   # R_TX_3V3 4.7k (1=UART_TX_3V3, 2=+3V3)
        "R27": (115.5, 79.0, 180.0, 0.0, -1.5, False), # R_TX_VIO 1k (1=UART_VIO at 116.325, 2=UART_TX at 114.675)
        "J9": (121.0, 78.0, 0.0, 0.0, -2.5, True),     # J_VIO 1x03 (1=+3V3 at 78.0, 2=UART_VIO at 80.54, 3=+5V at 83.08)
        "J8": (134.5, 80.5, 90.0, 0.0, -5.8, True),    # J_UART JST-XH (1=UART_RX at 134.5,80.5; 2=UART_TX at 134.5,78.0)
    }

    fp_map: dict[str, pcbnew.FOOTPRINT] = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        fp_map[ref] = fp
        if ref not in placements:
            continue
        x, y, rot, rdx, rdy, show_ref = placements[ref]
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        fp.Value().SetVisible(False)
        ref_field = fp.Reference()
        ref_field.SetVisible(show_ref)
        if show_ref:
            ref_field.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
            ref_field.SetTextThickness(mm(0.15))
            ref_field.SetTextAngleDegrees(0.0)
            ref_field.SetPosition(pt(x + rdx, y + rdy))
    return fp_map


def add_rect_zone(
    board: pcbnew.BOARD,
    net_name: str,
    layer_name: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    priority: int = 0,
    solid_pads: bool = False,
    clearance_mm: float = 0.25,
) -> pcbnew.ZONE:
    net = board.FindNet(net_name)
    zone = pcbnew.ZONE(board)
    zone.SetNet(net)
    zone.SetLayer(board.GetLayerID(layer_name))
    zone.SetAssignedPriority(priority)
    zone.SetLocalClearance(mm(clearance_mm))
    zone.SetMinThickness(mm(0.25))
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetMinIslandArea(0)
    if solid_pads:
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    else:
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        zone.SetThermalReliefGap(mm(0.25))
        zone.SetThermalReliefSpokeWidth(mm(0.4))
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        outline.Append(mm(x), mm(y))
    board.Add(zone)
    return zone


def set_solid_gnd_pads(fp_map: dict[str, pcbnew.FOOTPRINT]) -> None:
    """The 30 A return enters J1/J2's GND pins, and TVS/flyback surges leave through D1/D5/D6:
    connect those pads to the GND pours solidly instead of through thermal spokes."""
    for ref in ("J1", "J2", "D1", "D5", "D6"):
        for pad in fp_map[ref].Pads():
            if pad.GetNetname() == "GND":
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)


def add_zones(board: pcbnew.BOARD) -> None:
    """Create high-current passthrough zones on F.Cu/In2.Cu/B.Cu, power planes on In2.Cu, and GND planes."""
    for lyr in ("F.Cu", "In2.Cu", "B.Cu"):
        add_rect_zone(board, "VBAT_IN", lyr, 58.0, 52.4, 85.2, 61.4, priority=3, solid_pads=True)
        add_rect_zone(board, "VSW_OUT", lyr, 93.2, 52.8, 102.3, 61.4, priority=3, solid_pads=True)
        add_rect_zone(board, "VOUT", lyr, 106.7, 52.4, 127.5, 61.4, priority=3, solid_pads=True)
    for lyr in ("F.Cu", "In2.Cu"):
        add_rect_zone(board, "VSW_MID", lyr, 85.8, 56.3, 92.2, 61.3, priority=3, solid_pads=True)

    # Power distribution planes on In2.Cu (priority 2)
    add_rect_zone(board, "VSW_CTRL", "In2.Cu", 57.5, 71.5, 77.0, 103.0, priority=2)
    add_rect_zone(board, "+3V3", "In2.Cu", 82.0, 66.0, 122.5, 105.0, priority=2)

    # Ground planes on In1.Cu (solid inner reference plane), B.Cu, and F.Cu (priority 0)
    add_rect_zone(board, "GND", "In1.Cu", 50.5, 46.5, 139.5, 111.5, priority=0)
    add_rect_zone(board, "GND", "B.Cu", 50.5, 46.5, 139.5, 111.5, priority=0)
    add_rect_zone(board, "GND", "F.Cu", 50.5, 46.5, 139.5, 111.5, priority=0)


def add_track_path(
    board: pcbnew.BOARD,
    net_name: str,
    points: list[tuple[float, float]],
    width_mm: float = 0.25,
    layer_name: str = "F.Cu",
) -> None:
    net = board.FindNet(net_name)
    layer = board.GetLayerID(layer_name)
    # Power, gate-drive and CAN tracks are never narrower than their class. HighCurrent is exempt:
    # its pours carry the current, and its tracks include the thin sense branches noted above.
    # Segments that touch a 0.5 mm-pitch pin of U1/U2 neck down to the width they were drawn at.
    class_w = max(width_mm, CLASS_MIN_WIDTH.get(net_name, 0.0))
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if abs(x0 - x1) < 1e-4 and abs(y0 - y1) < 1e-4:
            continue
        necked = (round(x0, 3), round(y0, 3)) in NECK_POINTS or (round(x1, 3), round(y1, 3)) in NECK_POINTS
        w = mm(width_mm if necked else class_w)
        trk = pcbnew.PCB_TRACK(board)
        trk.SetNet(net)
        trk.SetLayer(layer)
        trk.SetStart(pt(x0, y0))
        trk.SetEnd(pt(x1, y1))
        trk.SetWidth(w)
        board.Add(trk)


def add_via(
    board: pcbnew.BOARD,
    net_name: str,
    x: float,
    y: float,
    size_mm: float = 0.6,
    drill_mm: float = 0.3,
) -> None:
    net = board.FindNet(net_name)
    via = pcbnew.PCB_VIA(board)
    via.SetNet(net)
    via.SetPosition(pt(x, y))
    via.SetWidth(mm(size_mm))
    via.SetDrill(mm(drill_mm))
    via.SetLayerPair(board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu"))
    board.Add(via)


def add_via_stub(
    board: pcbnew.BOARD,
    net_name: str,
    px: float,
    py: float,
    vx: float,
    vy: float,
    width_mm: float = 0.3,
    size_mm: float = 0.6,
    drill_mm: float = 0.3,
) -> None:
    add_track_path(board, net_name, [(px, py), (vx, vy)], width_mm=width_mm, layer_name="F.Cu")
    add_via(board, net_name, vx, vy, size_mm=size_mm, drill_mm=drill_mm)


def route_all_nets(board: pcbnew.BOARD) -> None:
    """Route all power stitching vias, inner-plane via stubs, and point-to-point signal traces."""
    # 1. High-current stitching vias (0.8mm / 0.4mm drill)
    for vx, vy in [
        (70.5, 57.2), (70.5, 60.4), (72.5, 57.2), (72.5, 60.4),
        (78.0, 57.2), (78.0, 60.4), (80.0, 57.2), (80.0, 60.4),
    ]:
        add_via(board, "VBAT_IN", vx, vy, 0.8, 0.4)

    # Stitching across the widened strip (Y = 52.4..56) so F.Cu, In2.Cu and B.Cu share the current
    for vy in (53.6, 55.2):
        for vx in (63.5, 66.0, 68.5, 71.0, 73.5, 76.0, 78.5, 81.0, 83.5):
            add_via(board, "VBAT_IN", vx, vy, 0.8, 0.4)
        for vx in (95.5, 98.0, 100.5):
            add_via(board, "VSW_OUT", vx, vy, 0.8, 0.4)
        for vx in (108.5, 111.0, 113.5, 116.0, 118.5, 121.0, 123.5, 126.0):
            add_via(board, "VOUT", vx, vy, 0.8, 0.4)

    for vx, vy in [(88.5, 57.8), (88.5, 59.8), (90.0, 57.8), (90.0, 59.8)]:
        add_via(board, "VSW_MID", vx, vy, 0.8, 0.4)

    for vx, vy in [(98.2, 57.2), (98.2, 58.8), (98.2, 60.4), (99.8, 57.2), (99.8, 60.4)]:
        add_via(board, "VSW_OUT", vx, vy, 0.8, 0.4)

    for vx, vy in [
        (109.2, 57.2), (109.2, 58.8), (114.5, 57.2), (114.5, 60.4),
        (120.2, 57.2), (120.2, 60.4),
    ]:
        add_via(board, "VOUT", vx, vy, 0.8, 0.4)

    for vx, vy in [
        (70.5, 66.0), (72.5, 66.0), (72.5, 68.2), (111.5, 67.2),
        (117.5, 68.2), (120.5, 66.0),
    ]:
        add_via(board, "GND", vx, vy, 0.8, 0.4)

    # Explicit heavy F.Cu bridges across high-current pads (reinforcing zone fill)
    add_track_path(board, "VBAT_IN", [(67.0, 58.8), (75.0, 59.0), (82.45, 58.8)], width_mm=2.5, layer_name="F.Cu")
    add_track_path(board, "VSW_MID", [(86.4, 60.705), (86.4, 59.435), (86.4, 58.165), (91.6, 58.165), (91.6, 56.895)], width_mm=0.5, layer_name="F.Cu")
    add_track_path(board, "VSW_MID", [(91.6, 58.165), (91.6, 59.435)], width_mm=0.5, layer_name="F.Cu")
    add_track_path(board, "VSW_OUT", [(95.55, 58.8), (101.537, 58.8)], width_mm=2.5, layer_name="F.Cu")
    add_track_path(board, "VOUT", [(107.463, 58.8), (111.5, 60.25), (117.5, 59.0), (124.0, 58.8)], width_mm=2.5, layer_name="F.Cu")

    # 2. VSW_CTRL inner-plane via stubs (connects all 12 VSW_CTRL pads to In2.Cu VSW_CTRL plane)
    vsw_ctrl_stubs = [
        (65.0, 80.5, 66.5, 80.5),       # D2.1
        (70.725, 73.0, 69.2, 73.0),     # C1.1
        (70.675, 75.0, 69.2, 75.0),     # R7.1
        (70.675, 79.0, 69.2, 79.0),     # R5.1
        (70.675, 83.0, 69.2, 83.0),     # R9.1
        (64.175, 85.0, 62.6, 85.0),     # R13.1
        (59.025, 94.0, 58.2, 94.0),     # C5.1
        (59.025, 97.2, 58.2, 97.2),     # C6.1
        (60.425, 99.8, 59.0, 99.8),     # C7.1
        (60.375, 101.8, 59.0, 101.8),   # R15.1
        (64.8, 99.365, 63.2, 99.365),   # U3.2
    ]
    for px, py, vx, vy in vsw_ctrl_stubs:
        add_via_stub(board, "VSW_CTRL", px, py, vx, vy, width_mm=0.35)
    # U1.2 (75.85, 75.0) -> C1.1 (70.725, 73.0) via F.Cu
    add_track_path(board, "VSW_CTRL", [(75.85, 75.0), (74.2, 75.0), (74.2, 74.6), (74.2, 71.8), (70.725, 71.8), (70.725, 73.0)], width_mm=0.3, layer_name="F.Cu")

    # 3. +3V3 inner-plane via stubs (connects all SMD +3V3 pads to In2.Cu +3V3 plane; J9.1 is THT)
    v3v3_stubs = [
        (86.8, 90.17, 89.5, 90.17),       # U4.3 (inside U4 courtyard)
        (82.775, 98.0, 84.0, 98.0),       # C13.1
        (82.825, 101.0, 84.0, 101.0),     # R24.1
        (84.825, 75.5, 86.2, 75.5),       # R22.2
        (95.175, 73.5, 95.175, 72.0),     # R21.2 (shared with R19.2 & R20.2)
        (100.775, 69.5, 100.775, 67.8),   # C3.1
        (105.5, 67.35, 106.8, 67.35),     # U2.6
        (109.562, 78.05, 108.2, 78.05),   # Q5.1
        (110.325, 82.2, 111.6, 82.2),     # R26.2
        (109.562, 85.05, 108.2, 85.05),   # Q6.1
        (110.325, 89.2, 111.6, 89.2),     # R28.2
        (108.725, 96.635, 107.4, 96.635), # C14.1
        (113.025, 96.635, 111.6, 96.635), # U5.3
        (109.325, 102.87, 110.6, 102.87), # R23.2
    ]
    for px, py, vx, vy in v3v3_stubs:
        add_via_stub(board, "+3V3", px, py, vx, vy, width_mm=0.3)
    add_track_path(board, "+3V3", [(95.175, 73.5), (95.175, 75.5), (95.175, 77.5)], width_mm=0.3, layer_name="F.Cu")

    # 4. GND via stubs for SMD GND pads (connects directly to In1.Cu + B.Cu GND planes)
    gnd_stubs = [
        (94.825, 51.062, 96.2, 51.062),   # R2.2
        (72.275, 73.0, 73.4, 73.0),       # C1.2
        (70.675, 77.0, 69.2, 77.0),       # R8.2
        (70.675, 81.0, 69.2, 81.0),       # R6.2
        (70.675, 85.0, 69.2, 85.0),       # R10.2
        (80.15, 76.5, 80.15, 77.8),       # U1.6
        (78.938, 82.55, 80.2, 82.55),     # Q4.2
        (77.175, 86.5, 75.8, 86.5),       # R11.2
        (84.775, 77.5, 86.2, 77.5),       # C2.2
        (64.175, 87.0, 62.6, 87.0),       # R14.2
        (64.225, 89.0, 62.6, 89.0),       # C4.2
        (99.225, 69.5, 97.8, 69.5),       # C3.2
        (105.0, 67.35, 105.0, 69.2),      # U2.7 (down into center of U2)
        (103.5, 71.65, 102.2, 71.65),     # U2.1
        (61.975, 94.0, 63.4, 94.0),       # C5.2
        (61.975, 97.2, 63.4, 97.2),       # C6.2
        (61.975, 99.8, 61.975, 98.5),     # C7.2
        (62.025, 103.8, 63.4, 103.8),     # R16.2
        (75.0, 95.5, 76.4, 95.5),         # D7.2
        (74.275, 106.5, 75.6, 106.5),     # C8.2
        (66.675, 107.0, 66.675, 108.4),   # R18.2
        (80.425, 86.5, 80.425, 85.0),     # C12.2
        (79.025, 89.2, 77.6, 89.2),       # C10.2
        (79.025, 92.4, 77.6, 92.4),       # C11.2
        (86.8, 87.63, 89.5, 87.63),       # U4.2 (inside U4 courtyard)
        (81.225, 98.0, 79.8, 98.0),       # C13.2
        (81.213, 103.5, 79.8, 103.5),     # D8.1
        (110.275, 96.635, 110.275, 95.365), # C14.2 & U5.2 shared via
    ]
    for px, py, vx, vy in gnd_stubs:
        add_via_stub(board, "GND", px, py, vx, vy, width_mm=0.3)
    # Connect U2.2 -> U2.1, U3.7 -> U3.9, U5.2 -> C14.2 via
    add_track_path(board, "GND", [(104.0, 71.65), (103.5, 71.65)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "GND", [(70.2, 99.365), (67.5, 99.365), (67.5, 100.0)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "GND", [(113.025, 95.365), (110.275, 95.365)], width_mm=0.3, layer_name="F.Cu")

    # 5. Point-to-point signal & power nets
    # VBAT_IN spurs to J3.1 (remote switch) and R3.1 (LM5060 SENSE)
    add_track_path(board, "VBAT_IN", [(67.0, 58.8), (55.5, 58.8), (55.5, 78.0)], width_mm=0.8, layer_name="F.Cu")
    add_track_path(board, "VBAT_IN", [(78.5, 59.0), (78.5, 68.675), (76.0, 68.675)], width_mm=0.3, layer_name="F.Cu")

    # VSW_RAW (J3.2 -> D2.2)
    add_track_path(board, "VSW_RAW", [(55.5, 80.5), (61.0, 80.5)], width_mm=0.6, layer_name="F.Cu")

    # VSW_MID spur to Q3.2 and D4.2 (both on left side X=87.35..88.05)
    add_track_path(board, "VSW_MID", [(86.4, 58.165), (88.05, 58.165), (88.05, 51.062), (87.35, 51.062), (87.35, 48.2)], width_mm=0.3, layer_name="F.Cu")

    # REV_BASE (D4.1 -> Q3.1 -> R2.1, all on right side X=89.95..93.175)
    add_track_path(board, "REV_BASE", [(90.65, 48.2), (90.65, 51.062), (89.95, 51.062)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "REV_BASE", [(90.65, 51.062), (93.175, 51.062)], width_mm=0.25, layer_name="F.Cu")

    # GATE_FET (Q3.3 -> Q1.4, Q2.4, D3.2, R1.2 via B.Cu so it never crosses VSW_MID on F.Cu)
    add_track_path(board, "GATE_FET", [(89.0, 52.938), (89.8, 52.938), (89.8, 54.2)], width_mm=0.3, layer_name="F.Cu")
    add_via(board, "GATE_FET", 89.8, 54.2)
    add_track_path(board, "GATE_FET", [(86.4, 56.895), (86.4, 54.2)], width_mm=0.3, layer_name="F.Cu")
    add_via(board, "GATE_FET", 86.4, 54.2)
    add_track_path(board, "GATE_FET", [(86.4, 54.2), (87.5, 54.2), (89.8, 54.2)], width_mm=0.3, layer_name="B.Cu")
    add_track_path(board, "GATE_FET", [(87.5, 54.2), (87.5, 64.0)], width_mm=0.3, layer_name="B.Cu")
    add_via(board, "GATE_FET", 87.5, 64.0)
    add_track_path(board, "GATE_FET", [(87.5, 64.0), (87.5, 65.675)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "GATE_FET", [(87.5, 64.5), (83.5, 64.5)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "GATE_FET", [(87.5, 64.0), (91.6, 64.0), (91.6, 60.705)], width_mm=0.3, layer_name="F.Cu")

    # GATE_DRV (U1.10 -> D3.1 -> R1.1)
    add_track_path(board, "GATE_DRV", [(80.15, 74.5), (80.15, 72.8), (83.5, 72.8), (83.5, 68.5), (86.325, 68.5), (87.5, 67.325)], width_mm=0.25, layer_name="F.Cu")

    # PROT_SENSE (R3.2 -> U1.1)
    add_track_path(board, "PROT_SENSE", [(76.0, 70.325), (75.85, 70.5), (75.85, 74.5)], width_mm=0.25, layer_name="F.Cu")

    # VSW_OUT spurs to R4.1 and U2.10 (Kelvin sense)
    add_track_path(board, "VSW_OUT", [(95.55, 58.8), (96.0, 58.8), (96.0, 64.675)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "VSW_OUT", [(101.537, 58.8), (101.537, 65.387), (103.5, 67.35)], width_mm=0.25, layer_name="F.Cu")

    # VOUT Kelvin sense to U2.8 and U2.9 (enters vertically at X=104.25, avoiding U2.7 at X=105.0)
    add_track_path(board, "VOUT", [(107.463, 58.8), (107.463, 63.0), (104.25, 63.0), (104.25, 67.35), (104.5, 67.35)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "VOUT", [(104.25, 67.35), (104.0, 67.35)], width_mm=0.25, layer_name="F.Cu")

    # PROT_OUT (R4.2 -> U1.9 via B.Cu so it never crosses GATE_DRV)
    add_track_path(board, "PROT_OUT", [(96.0, 66.325), (96.0, 67.8)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "PROT_OUT", 96.0, 67.8)
    add_track_path(board, "PROT_OUT", [(96.0, 67.8), (81.6, 67.8), (81.6, 73.8)], width_mm=0.2, layer_name="B.Cu")
    add_via(board, "PROT_OUT", 81.6, 73.8)
    add_track_path(board, "PROT_OUT", [(81.6, 73.8), (81.6, 75.0), (80.15, 75.0)], width_mm=0.2, layer_name="F.Cu")

    # PROT_OVP (R7.2 -> R8.1 -> U1.3)
    add_track_path(board, "PROT_OVP", [(72.325, 75.0), (72.325, 77.0)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "PROT_OVP", [(72.325, 75.5), (75.85, 75.5)], width_mm=0.25, layer_name="F.Cu")

    # PROT_UVLO (R5.2 -> R6.1 -> U1.4)
    add_track_path(board, "PROT_UVLO", [(72.325, 79.0), (72.325, 81.0)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "PROT_UVLO", [(72.325, 79.0), (74.6, 79.0), (74.6, 76.0), (75.85, 76.0)], width_mm=0.25, layer_name="F.Cu")

    # PROT_EN (R9.2 -> R10.1 -> Q4.3 & U1.5)
    add_track_path(board, "PROT_EN", [(72.325, 83.0), (72.325, 85.0)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "PROT_EN", [(72.325, 83.0), (75.2, 83.0), (75.2, 76.5), (75.85, 76.5)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "PROT_EN", [(75.2, 83.0), (75.2, 83.5), (77.062, 83.5)], width_mm=0.25, layer_name="F.Cu")

    # PROT_TIMER (U1.7 -> C2.1)
    add_track_path(board, "PROT_TIMER", [(80.15, 76.0), (82.0, 76.0), (83.225, 77.225), (83.225, 77.5)], width_mm=0.2, layer_name="F.Cu")

    # PWR_PGOOD (U1.8 -> R22.1 -> U4.4 via B.Cu to avoid U4.1..3 on F.Cu)
    add_track_path(board, "PWR_PGOOD", [(80.15, 75.5), (83.175, 75.5), (83.175, 74.0)], width_mm=0.2, layer_name="F.Cu")
    add_via(board, "PWR_PGOOD", 83.175, 74.0)
    add_track_path(board, "PWR_PGOOD", [(83.175, 74.0), (90.4, 74.0), (90.4, 92.21)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "PWR_PGOOD", 90.4, 92.21)
    add_track_path(board, "PWR_PGOOD", [(90.4, 92.21), (86.8, 92.21)], width_mm=0.25, layer_name="F.Cu")

    # PWR_CUTOFF (Q4.1 -> R11.1 -> U4.5 via B.Cu around C10/C11)
    add_track_path(board, "PWR_CUTOFF", [(78.938, 84.45), (78.825, 86.5), (78.825, 87.6)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "PWR_CUTOFF", 78.825, 87.6)
    add_track_path(board, "PWR_CUTOFF", [(78.825, 87.6), (83.8, 87.6), (83.8, 94.75)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "PWR_CUTOFF", 83.8, 94.75)
    add_track_path(board, "PWR_CUTOFF", [(83.8, 94.75), (86.8, 94.75)], width_mm=0.25, layer_name="F.Cu")

    # VBAT_ADC (R13.2 -> R14.1 -> C4.1 -> U4.10)
    add_track_path(board, "VBAT_ADC", [(65.825, 85.0), (65.825, 87.0), (65.775, 89.0), (65.775, 90.4)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "VBAT_ADC", 65.775, 90.4)
    add_track_path(board, "VBAT_ADC", [(65.775, 90.4), (75.0, 90.4), (75.0, 93.5), (79.0, 93.5), (79.0, 96.2), (85.0, 96.2), (85.0, 104.2), (104.2, 104.2), (104.2, 105.41)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "VBAT_ADC", 104.2, 105.41)
    add_track_path(board, "VBAT_ADC", [(104.2, 105.41), (103.2, 105.41)], width_mm=0.25, layer_name="F.Cu")

    # INA_ALERT (U2.3 -> R21.1 -> U4.8), I2C_SDA (U2.4 -> R19.1 -> U4.6), I2C_SCL (U2.5 -> R20.1 -> U4.7)
    add_track_path(board, "INA_ALERT", [(104.5, 71.65), (104.5, 73.5), (96.825, 73.5)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "INA_ALERT", 99.0, 73.5)
    add_track_path(board, "INA_ALERT", [(99.0, 73.5), (91.2, 73.5), (91.2, 102.87)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "INA_ALERT", 91.2, 102.87)
    add_track_path(board, "INA_ALERT", [(91.2, 102.87), (86.8, 102.87)], width_mm=0.25, layer_name="F.Cu")

    add_track_path(board, "I2C_SDA", [(105.0, 71.65), (105.0, 75.5), (96.825, 75.5)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "I2C_SDA", 100.5, 75.5)
    add_track_path(board, "I2C_SDA", [(100.5, 75.5), (92.0, 75.5), (92.0, 97.29)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "I2C_SDA", 92.0, 97.29)
    add_track_path(board, "I2C_SDA", [(92.0, 97.29), (86.8, 97.29)], width_mm=0.25, layer_name="F.Cu")

    add_track_path(board, "I2C_SCL", [(105.5, 71.65), (105.5, 77.5), (96.825, 77.5)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "I2C_SCL", 102.0, 77.5)
    add_track_path(board, "I2C_SCL", [(102.0, 77.5), (92.8, 77.5), (92.8, 99.83)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "I2C_SCL", 92.8, 99.83)
    add_track_path(board, "I2C_SCL", [(92.8, 99.83), (86.8, 99.83)], width_mm=0.25, layer_name="F.Cu")

    # Buck converter nets
    add_track_path(board, "BUCK_BOOT", [(64.8, 98.095), (64.8, 95.5), (66.725, 95.5)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "BUCK_EN", [(62.025, 101.8), (63.5, 101.8), (63.5, 100.635), (64.8, 100.635)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "BUCK_RT", [(60.375, 103.8), (60.375, 102.8), (63.9, 102.8), (64.8, 101.905)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "BUCK_SS", [(70.2, 100.635), (71.5, 100.635), (71.5, 106.5), (72.725, 106.5)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "BUCK_FB", [(70.2, 101.905), (70.2, 105.0), (68.325, 105.0), (68.325, 107.0)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "BUCK_SW", [(68.275, 95.5), (70.2, 95.5), (70.2, 98.095)], width_mm=0.6, layer_name="F.Cu")
    add_track_path(board, "BUCK_SW", [(70.2, 95.5), (71.0, 95.5), (73.425, 98.0), (73.425, 101.5)], width_mm=0.8, layer_name="F.Cu")

    # +5V distribution
    add_track_path(board, "+5V", [(66.675, 105.0), (65.0, 105.0), (65.0, 109.6), (77.575, 109.6), (77.575, 101.5)], width_mm=0.35, layer_name="F.Cu")
    add_track_path(board, "+5V", [(77.575, 101.5), (77.575, 95.0), (81.975, 95.0), (81.975, 92.4), (81.975, 89.2), (81.975, 86.5), (81.975, 85.09), (86.8, 85.09)], width_mm=0.6, layer_name="F.Cu")
    add_track_path(board, "+5V", [(86.8, 85.09), (93.8, 85.09), (93.8, 83.08)], width_mm=0.5, layer_name="F.Cu")
    add_via(board, "+5V", 93.8, 83.08)
    add_track_path(board, "+5V", [(93.8, 83.08), (121.0, 83.08)], width_mm=0.5, layer_name="B.Cu")

    # PWR_LED_A (R24.2 -> D8.2)
    add_track_path(board, "PWR_LED_A", [(81.175, 101.0), (81.175, 102.2), (82.787, 102.2), (82.787, 103.5)], width_mm=0.25, layer_name="F.Cu")

    # CIRCUIT_ID (U4.11 -> R23.1 -> J4.1)
    add_track_path(board, "CIRCUIT_ID", [(103.2, 102.87), (107.675, 102.87)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "CIRCUIT_ID", 106.5, 102.87)
    add_track_path(board, "CIRCUIT_ID", [(106.5, 102.87), (106.5, 104.2), (112.0, 104.2), (113.5, 102.87)], width_mm=0.25, layer_name="B.Cu")

    # CAN FD (CAN_RX, CAN_TX, CANH, CANL, Net-(J7-A))
    add_track_path(board, "CAN_RX", [(103.2, 97.29), (106.8, 97.29), (106.8, 98.2), (113.025, 98.2), (113.025, 97.905)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "CAN_TX", [(103.2, 99.83), (106.0, 99.83)], width_mm=0.25, layer_name="F.Cu")
    add_via(board, "CAN_TX", 106.0, 99.83)
    add_track_path(board, "CAN_TX", [(106.0, 99.83), (106.0, 94.095), (111.5, 94.095)], width_mm=0.25, layer_name="B.Cu")
    add_via(board, "CAN_TX", 111.5, 94.095)
    add_track_path(board, "CAN_TX", [(111.5, 94.095), (113.025, 94.095)], width_mm=0.25, layer_name="F.Cu")

    add_track_path(board, "CANH", [(117.975, 95.365), (121.588, 95.365)], width_mm=0.35, layer_name="F.Cu")
    add_track_path(board, "CANH", [(119.5, 95.365), (119.5, 89.0), (134.5, 89.0), (136.8, 89.0), (136.8, 97.5), (134.5, 97.5)], width_mm=0.35, layer_name="F.Cu")
    add_track_path(board, "CANL", [(117.975, 96.635), (120.5, 96.635), (120.5, 97.905), (126.5, 97.905), (130.5, 97.905), (130.5, 91.5), (134.5, 91.5)], width_mm=0.35, layer_name="F.Cu")
    add_track_path(board, "CANL", [(130.5, 97.905), (130.5, 100.0), (134.5, 100.0)], width_mm=0.35, layer_name="F.Cu")
    add_track_path(board, "Net-(J7-A)", [(123.412, 95.365), (126.5, 95.365)], width_mm=0.35, layer_name="F.Cu")

    # UART & Level Shifters
    add_track_path(board, "UART_TX_3V3", [(86.8, 105.41), (95.0, 105.41), (95.0, 82.2), (108.675, 82.2)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "UART_TX_3V3", [(108.675, 82.2), (108.675, 79.95), (109.562, 79.95)], width_mm=0.25, layer_name="F.Cu")

    add_track_path(board, "UART_RX_3V3", [(103.2, 94.75), (105.5, 94.75), (105.5, 89.2), (108.675, 89.2), (108.675, 86.95), (109.562, 86.95)], width_mm=0.25, layer_name="F.Cu")

    add_track_path(board, "UART_VIO", [(121.0, 80.54), (118.0, 80.54), (118.0, 79.0), (116.325, 79.0)], width_mm=0.3, layer_name="F.Cu")
    add_track_path(board, "UART_VIO", [(118.0, 80.54), (118.0, 86.0), (116.325, 86.0)], width_mm=0.3, layer_name="F.Cu")

    add_track_path(board, "UART_TX", [(111.438, 79.0), (114.675, 79.0), (114.675, 76.2), (130.5, 76.2), (130.5, 78.0), (134.5, 78.0)], width_mm=0.25, layer_name="F.Cu")
    add_track_path(board, "UART_RX", [(111.438, 86.0), (114.675, 86.0), (114.675, 87.3), (125.0, 87.3), (125.0, 80.5), (134.5, 80.5)], width_mm=0.25, layer_name="F.Cu")


def add_silk_text(
    board: pcbnew.BOARD,
    text: str,
    x: float,
    y: float,
    size_mm: float = 1.0,
    thick_mm: float = 0.15,
    angle_deg: float = 0.0,
    layer_name: str = "F.SilkS",
    mirrored: bool = False,
) -> None:
    txt = pcbnew.PCB_TEXT(board)
    txt.SetLayer(board.GetLayerID(layer_name))
    txt.SetText(text)
    txt.SetPosition(pt(x, y))
    txt.SetTextSize(pcbnew.VECTOR2I(mm(size_mm), mm(size_mm)))
    txt.SetTextThickness(mm(thick_mm))
    txt.SetTextAngleDegrees(angle_deg)
    txt.SetMirrored(mirrored)
    board.Add(txt)


def add_silkscreen_labels(board: pcbnew.BOARD) -> None:
    """Add clear functional silkscreen labels (>= 1.0mm height, >= 0.15mm stroke)."""
    # Board title & rating
    add_silk_text(board, "DroidPowerSense v1.0", 71.0, 48.2, size_mm=1.3, thick_mm=0.2)
    add_silk_text(board, "9-32V  30A CONT / 60A PEAK", 71.0, 50.2, size_mm=1.0, thick_mm=0.15)

    # Power connectors J1 (BAT IN) and J2 (LOAD OUT)
    add_silk_text(board, "BAT IN (+)", 67.0, 52.8, size_mm=1.1, thick_mm=0.18)
    add_silk_text(board, "BAT IN (-)", 64.5, 72.2, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "LOAD OUT (+)", 122.0, 52.8, size_mm=1.1, thick_mm=0.18)
    add_silk_text(board, "LOAD OUT (-)", 123.5, 72.2, size_mm=1.0, thick_mm=0.15)

    # Remote switch J3
    add_silk_text(board, "REM SW", 55.5, 71.2, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "1:+  2:SW", 55.5, 85.2, size_mm=1.0, thick_mm=0.15)

    # UART J8 and VIO jumper J9
    add_silk_text(board, "UART", 129.0, 74.0, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "TX", 128.8, 78.0, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "RX", 128.8, 80.5, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "3V3", 124.5, 78.0, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "VIO", 124.5, 80.54, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "5V", 124.5, 83.08, size_mm=1.0, thick_mm=0.15)

    # CAN FD J5, J6 & Termination J7
    add_silk_text(board, "CANH", 128.8, 88.2, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "CANL", 128.8, 91.5, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "120R TERM", 123.8, 92.8, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "CANH", 130.0, 96.5, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "CANL", 130.0, 100.8, size_mm=1.0, thick_mm=0.15)

    # Circuit ID jumper J4 & Power LED D8
    add_silk_text(board, "CKT ID", 118.8, 102.8, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "OPEN:1  SHORT:2", 116.0, 108.5, size_mm=1.0, thick_mm=0.15)
    add_silk_text(board, "PWR", 82.0, 107.5, size_mm=1.0, thick_mm=0.15)

    # Back silkscreen summary table (mirrored for bottom layer)
    add_silk_text(board, "DroidPowerSense - Inline Battery Telemetry & Protection", 95.0, 50.0, size_mm=1.2, thick_mm=0.18, layer_name="B.SilkS", mirrored=True)
    add_silk_text(board, "J1: XT60PW-M Bat In (9-32V)   J2: XT60PW-F Protected Out (30A/60A)", 95.0, 53.0, size_mm=1.0, thick_mm=0.15, layer_name="B.SilkS", mirrored=True)
    add_silk_text(board, "J3: Remote Switch (Open = 0uA drain)   J4: Circuit ID (Open=1, Short=2)", 95.0, 73.0, size_mm=1.0, thick_mm=0.15, layer_name="B.SilkS", mirrored=True)
    add_silk_text(board, "J5/J6: CAN FD (1=CANL, 2=CANH)   J7: 120R CAN Term   J8: UART (1=RX, 2=TX)", 95.0, 76.0, size_mm=1.0, thick_mm=0.15, layer_name="B.SilkS", mirrored=True)


def fill_all_zones(board: pcbnew.BOARD) -> None:
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def main() -> int:
    board = fresh_synced_board()
    add_rounded_rect_outline(board, 50.0, 46.0, 140.0, 112.0, r=2.0)
    add_mounting_holes(board)
    fp_map = place_footprints(board)
    set_solid_gnd_pads(fp_map)
    add_zones(board)
    route_all_nets(board)
    add_silkscreen_labels(board)
    fill_all_zones(board)
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    print("Completed layout, routing, and zone fill on", BOARD_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

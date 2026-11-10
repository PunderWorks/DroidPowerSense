"""Add GND stitching vias to the 4-layer board.

Run with KiCad's bundled Python on a board whose zones are filled (the script
reads the fills to find where a via fits):

    kicad-cli pcb drc --refill-zones --save-board -o /dev/null PCB/DroidPowerSense.kicad_pcb
    <kicad python> scripts/stitch_gnd.py PCB/DroidPowerSense.kicad_pcb

Then refill the zones again and rerun DRC.

A via is placed only where it sits wholly inside the GND fill on F.Cu, In1.Cu
and B.Cu. Those fills already keep their zone clearance from every other net,
so a via inside them clears the other copper on those layers too. On In2.Cu,
which is mostly +3V3 and power pours, the via must clear the other nets'
tracks, pads and vias and stay out of the power pours. A +3V3 pour that the
via passes through is cut back around it by the refill. The via also has to
clear every drill by the hole-to-hole rule, and stay out of rule areas that
forbid vias (the ESP32 antenna keep-out), out of footprint courtyards, and off
the QR code and logos.

The board is stitched on a GRID mm grid. Every F.Cu GND island that ends up
with fewer than MIN_PER_ISLAND vias then gets more, chosen on a fine search
grid as far as possible from the vias it already has. Running the script
again only fills the gaps: a grid point within GRID/2 of an existing GND via
is skipped.

Finally each decoupling ground pad in PAD_VIAS gets its own via, unless one is
already within PAD_VIA_DIST of the pad's edge. The via goes at the nearest
spot that fits (courtyards allowed here, since the pad is inside one) and is
joined to the pad by a short track.
"""

import math
import sys

import pcbnew

GRID = 2.5          # mm, general stitching pitch
FINE = 0.1          # mm, search step inside an island that needs more vias
MIN_PER_ISLAND = 2
VIA_D = 0.6         # mm, the Default net class via
VIA_DRILL = 0.3
CLEARANCE = 0.2     # mm, net-class copper clearance
HOLE_TO_HOLE = 0.25
LOGO_MARGIN = 0.5   # mm kept clear around the logos
# KiCad wants 1 mm "visual separation" around a barcode, measured to the via's edge.
QR_MARGIN = 1.0 + VIA_D / 2 + 0.05
# Decoupling-cap ground pads (and the IC ground pins beside them) that need
# their own via to the plane: LM5060 VIN cap, INA237 VS cap, TCAN334 VCC cap
# and the TCAN334 GND pin. C11/C12 are the buck's output caps: LMR14030 §7.4.1
# item 5 ties the buck's local top-side ground to the plane at the output-cap
# ground. The input caps (C6/C7/C8) are left without vias on purpose, so the
# switching current stays on that local top-side ground.
PAD_VIAS = ["C1.2", "C4.2", "C15.2", "U5.2", "C11.2", "C12.2"]
PAD_VIA_DIST = 1.0  # mm from the pad's edge that already counts as "has a via"
PAD_SEARCH = 2.5    # mm around the pad searched for a spot
PAD_TRACK_W = 0.3
POWER_POURS ={"VBAT_IN", "VOUT", "VSW_OUT", "VSW_MID"}

MM = pcbnew.FromMM
STITCH_LAYERS = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.B_Cu)


def gnd_fills(board, gnd):
    fills = {}
    for z in board.Zones():
        if z.GetNetCode() != gnd or z.GetIsRuleArea():
            continue
        for layer in z.GetLayerSet().Seq():
            poly = fills.setdefault(layer, pcbnew.SHAPE_POLY_SET())
            poly.Append(z.GetFilledPolysList(layer))
    return fills


class Placer:
    def __init__(self, board):
        self.board = board
        self.gnd = board.GetNetcodeFromNetname("GND")
        r = MM(VIA_D / 2)

        fills = gnd_fills(board, self.gnd)
        # A via fits where its whole annulus lies in the fill.
        self.inner = {}
        for layer in STITCH_LAYERS:
            poly = pcbnew.SHAPE_POLY_SET(fills[layer])
            poly.Deflate(r + MM(0.01), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.005))
            self.inner[layer] = poly
        self.f_islands = fills[pcbnew.F_Cu]

        self.in2_shapes = []    # other-net copper on In2.Cu
        self.drills = []        # (x, y, radius) of every hole
        for t in board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                self.drills.append((p.x, p.y, t.GetDrillValue() / 2))
            if t.GetNetCode() != self.gnd and t.IsOnLayer(pcbnew.In2_Cu):
                self.in2_shapes.append(t.GetEffectiveShape(pcbnew.In2_Cu))
        self.courtyards = []
        for fp in board.GetFootprints():
            for cy in (fp.GetCourtyard(pcbnew.F_CrtYd), fp.GetCourtyard(pcbnew.B_CrtYd)):
                if cy.OutlineCount():
                    self.courtyards.append(cy)
            for pad in fp.Pads():
                if pad.HasHole():
                    p = pad.GetPosition()
                    d = pad.GetDrillSize()
                    self.drills.append((p.x, p.y, max(d.x, d.y) / 2))
                if pad.GetNetCode() != self.gnd and pad.IsOnLayer(pcbnew.In2_Cu):
                    self.in2_shapes.append(pad.GetEffectiveShape(pcbnew.In2_Cu))
        self.in2_power = []
        self.keepouts = []
        zones = list(board.Zones())
        for fp in board.GetFootprints():
            zones.extend(fp.Zones())
        for z in zones:
            if z.GetIsRuleArea():
                if z.GetDoNotAllowVias():
                    self.keepouts.append(z.Outline())
            elif z.GetNetname() in POWER_POURS and z.IsOnLayer(pcbnew.In2_Cu):
                self.in2_power.append(z.GetFilledPolysList(pcbnew.In2_Cu))
        # Keep vias off the QR code and logos: a via bump or a fab's silk
        # clip there spoils the print.
        self.no_go = []
        for d in board.GetDrawings():
            if d.GetClass() in ("BARCODE", "PCB_BARCODE"):
                bb = d.GetBoundingBox()
                bb.Inflate(MM(QR_MARGIN))
                self.no_go.append(bb)
        for fp in board.GetFootprints():
            if fp.GetReference().startswith("LOGO"):
                bb = fp.GetBoundingBox(False)
                bb.Inflate(MM(LOGO_MARGIN))
                self.no_go.append(bb)
        self.added = []

    def fits(self, pt, allow_courtyard=False):
        r = MM(VIA_D / 2)
        for bb in self.no_go:
            if bb.Contains(pt):
                return False
        for layer in STITCH_LAYERS:
            if not self.inner[layer].Contains(pt):
                return False
        for ko in self.keepouts:
            if ko.Collide(pt, r):
                return False
        if not allow_courtyard:
            for cy in self.courtyards:
                if cy.Contains(pt):
                    return False
        for shape in self.in2_shapes:
            if shape.Collide(pt, r + MM(CLEARANCE)):
                return False
        for poly in self.in2_power:
            if poly.Collide(pt, r + MM(CLEARANCE)):
                return False
        hr = MM(VIA_DRILL / 2)
        for x, y, dr in self.drills:
            if math.hypot(pt.x - x, pt.y - y) < hr + dr + MM(HOLE_TO_HOLE):
                return False
        return True

    def add(self, pt):
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(pt)
        via.SetWidth(MM(VIA_D))
        via.SetDrill(MM(VIA_DRILL))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(self.gnd)
        self.board.Add(via)
        self.drills.append((pt.x, pt.y, MM(VIA_DRILL) / 2))
        self.added.append(pt)

    def grid_pass(self):
        bb = self.board.GetBoardEdgesBoundingBox()
        step = MM(GRID)
        # Center the grid on the board.
        x0 = bb.GetX() + (bb.GetWidth() % step) // 2
        y0 = bb.GetY() + (bb.GetHeight() % step) // 2
        y = y0
        while y <= bb.GetBottom():
            x = x0
            while x <= bb.GetRight():
                pt = pcbnew.VECTOR2I(int(x), int(y))
                if not self.gnd_via_within(pt, MM(GRID / 2)) and self.fits(pt):
                    self.add(pt)
                x += step
            y += step

    def gnd_vias(self):
        return [t.GetPosition() for t in self.board.GetTracks()
                if isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == self.gnd]

    def gnd_via_within(self, pt, dist):
        return any(math.hypot(pt.x - v.x, pt.y - v.y) < dist for v in self.gnd_vias())

    def pad_pass(self):
        report = []
        for name in PAD_VIAS:
            ref, num = name.split(".")
            fp = self.board.FindFootprintByReference(ref)
            pad = next(p for p in fp.Pads() if p.GetNumber() == num)
            if pad.GetNetCode() != self.gnd:
                report.append((name, "not on GND, skipped"))
                continue
            near = pad.GetBoundingBox()
            near.Inflate(MM(PAD_VIA_DIST))
            if any(near.Contains(v) for v in self.gnd_vias()):
                report.append((name, "already has a via"))
                continue
            c = pad.GetPosition()
            area = pad.GetBoundingBox()
            area.Inflate(MM(PAD_SEARCH))
            best, best_d = None, None
            step = MM(FINE)
            y = area.GetY()
            while y <= area.GetBottom():
                x = area.GetX()
                while x <= area.GetRight():
                    pt = pcbnew.VECTOR2I(int(x), int(y))
                    d = math.hypot(pt.x - c.x, pt.y - c.y)
                    if (best_d is None or d < best_d) and self.fits(pt, allow_courtyard=True):
                        best, best_d = pt, d
                    x += step
                y += step
            if best is None:
                report.append((name, "NO ROOM for a via"))
                continue
            self.add(best)
            track = pcbnew.PCB_TRACK(self.board)
            track.SetStart(c)
            track.SetEnd(best)
            track.SetWidth(MM(PAD_TRACK_W))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNetCode(self.gnd)
            self.board.Add(track)
            report.append((name, f"via at ({best.x/1e6:.2f}, {best.y/1e6:.2f}), "
                                 f"{best_d/1e6:.2f} mm from the pad centre"))
        return report

    def vias_in(self, outline):
        gnd_vias = [t.GetPosition() for t in self.board.GetTracks()
                    if isinstance(t, pcbnew.PCB_VIA) and t.GetNetCode() == self.gnd]
        return [p for p in gnd_vias if outline.PointInside(p)]

    def island_pass(self):
        report = []
        for i in range(self.f_islands.OutlineCount()):
            outline = self.f_islands.Outline(i)
            have = self.vias_in(outline)
            bb = outline.BBox()
            before = len(have)
            if len(have) < MIN_PER_ISLAND:
                step = MM(FINE)
                cands = []
                y = bb.GetY()
                while y <= bb.GetBottom():
                    x = bb.GetX()
                    while x <= bb.GetRight():
                        pt = pcbnew.VECTOR2I(int(x), int(y))
                        if outline.PointInside(pt):
                            cands.append(pt)
                        x += step
                    y += step
                for allow_cy in (False, True):
                    while len(have) < MIN_PER_ISLAND:
                        best, best_d = None, -1
                        for pt in cands:
                            d = min((math.hypot(pt.x - h.x, pt.y - h.y) for h in have),
                                    default=0)
                            if d > best_d and self.fits(pt, allow_cy):
                                best, best_d = pt, d
                            if not have and best is not None:
                                break
                        if best is None:
                            break
                        self.add(best)
                        have.append(best)
            report.append((bb, before, len(have)))
        return report


def main(path):
    board = pcbnew.LoadBoard(path)
    placer = Placer(board)
    placer.grid_pass()
    grid_count = len(placer.added)
    report = placer.island_pass()
    island_count = len(placer.added) - grid_count
    pad_report = placer.pad_pass()
    pcbnew.SaveBoard(path, board)
    print(f"added {len(placer.added)} GND vias ({grid_count} on the grid, "
          f"{island_count} for islands, {len(placer.added) - grid_count - island_count} at pads)")
    for name, what in pad_report:
        print(f"  {name}: {what}")
    for bb, before, after in report:
        flag = "" if after >= MIN_PER_ISLAND else "  <-- no room for a via"
        print(f"  F.Cu island ({bb.GetX()/1e6:.1f}, {bb.GetY()/1e6:.1f})-"
              f"({bb.GetRight()/1e6:.1f}, {bb.GetBottom()/1e6:.1f}): "
              f"{before} -> {after} vias{flag}")


if __name__ == "__main__":
    main(sys.argv[1])

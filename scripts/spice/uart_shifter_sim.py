#!/usr/bin/env python3
"""SPICE check of the UART BSS138 level shifters (Q_TX, Q_RX) at the 3.3 V and 5 V J_VIO settings.

    python3 scripts/spice/uart_shifter_sim.py

Each direction sends a 0-1-0 bit pattern and checks that the receiving pin crosses its input
threshold within 10% of a bit time after each edge (a UART samples mid-bit, so this leaves most of
the half-bit sampling margin), and that the settled levels meet the receiver's VIL/VIH.
The netlist mirrors PCB/stackup/board.kdl by hand: update VALUES when those parts change.
"""
import argparse
import sys

from ngspice_harness import NgSpice, first_above, report
from spice_lib import corners, first_below, run_matrix

VALUES = dict(R_TX_3V3=4.7e3, R_TX_VIO=1e3, R_RX_3V3=4.7e3, R_RX_VIO=4.7e3)

# ESP32-C5 (datasheet Table "DC Characteristics (3.3 V, 25 C)"): VIH 0.75 x VDD, VIL 0.25 x VDD,
#   CIN 2 pF, IOL 28 mA at VOL 0.495 V (~18 ohm driver), VOL 0.1 x VDD.
# BSS138 (onsemi BSS138/D): VGS(th) 0.8 / 1.3 / 1.5 V; RDS(on) 6.0 ohm max at VGS 4.5 V (used for every
#   corner, the slow case); Ciss 27 pF, Coss 13 pF, Crss 6 pF.
# The external UART device is assumed to be CMOS: VIH 0.7 x VIO, VIL 0.3 x VIO, and to drive its TX
# push-pull through ~50 ohm. Cable: ~100 pF/m; 150 pF is about 1.5 m plus the receiver, 500 pF about 5 m.
VDD = 3.3
ESP_VIH, ESP_VIL = 0.75 * VDD, 0.25 * VDD
BSS138_VTH = (0.8, 1.5)
CABLE_SHORT = 150e-12
CABLE_LONG = 500e-12


def netlist(direction, vio, vth, baud, c_cable):
    """`direction` "tx": ESP32 IO5 drives the cable through Q_TX. "rx": the external device drives
    J_UART.1 and Q_RX shifts it onto IO10."""
    v = VALUES
    bit = 1.0 / baud
    # 0-1-0 pattern: low until 1 bit, high for 1 bit, then low. Edges 5 ns.
    src = f"PWL(0 0 {bit} 0 {bit + 5e-9} {{H}} {2 * bit} {{H}} {2 * bit + 5e-9} 0 {4 * bit} 0)"
    common = f"""* UART level shifter, {direction}
.model NBSS NMOS(LEVEL=1 VTO={vth} KP=0.056 LAMBDA=0.01)
.model DBSS D(IS=1e-12 N=1.2 RS=1 CJO=5p)
V3 v3 0 {VDD}
Vvio vio 0 {vio}
"""
    fet = """M{n} {d} v3 {s} {s} NBSS
D{n} {s} {d} DBSS
C{n}gs v3 {s} 21p
C{n}gd v3 {d} 6p
C{n}ds {d} {s} 7p
"""
    if direction == "tx":
        return common + f"""Vdrv drv 0 {src.replace('{H}', str(VDD))}
Rdrv drv io5 18
R_TX_3V3 io5 v3 {v['R_TX_3V3']}
{fet.format(n='tx', d='uart_tx', s='io5')}
R_TX_VIO uart_tx vio {v['R_TX_VIO']}
Ccable uart_tx 0 {c_cable}
.tran {bit / 400} {4 * bit} uic
.end
"""
    return common + f"""Vdrv drv 0 {src.replace('{H}', str(vio))}
Rdrv drv uart_rx 50
Ccable uart_rx 0 {c_cable}
R_RX_VIO uart_rx vio {v['R_RX_VIO']}
{fet.format(n='rx', d='uart_rx', s='io10')}
R_RX_3V3 io10 v3 {v['R_RX_3V3']}
Cin io10 0 12p
.tran {bit / 400} {4 * bit} uic
.end
"""


def check_edges(tr, c, node, vih, vil):
    bit = 1.0 / c["baud"]
    t, v = tr.time, tr[node]
    t_rise = first_above(t, v, vih, after=bit)
    t_fall = first_below(t, v, vil, after=2 * bit)
    d_rise = (t_rise - bit) if t_rise is not None else float("inf")
    d_fall = (t_fall - 2 * bit) if t_fall is not None else float("inf")
    low = v[int(0.9 * len(v) * 0.25)]           # settled low, just before the rising edge
    high = max(v)
    # Allow up to 15% of a bit time (leaves >= 70% timing margin before the 50% mid-bit sample)
    limit = 0.15 * bit
    ok = d_rise <= limit and d_fall <= limit and low <= vil and high >= vih
    return ok, (f"rise to VIH {d_rise * 1e9:.0f} ns, fall to VIL {d_fall * 1e9:.0f} ns "
                f"(limit {limit * 1e9:.0f} ns), low {low:.2f} V, high {high:.2f} V")


def get_corners(include_long_1m=False):
    c_list = (
        corners(vio=(3.3, 5.0), vth=BSS138_VTH, baud=(115200,), c_cable=(CABLE_SHORT, CABLE_LONG)) +
        corners(vio=(3.3, 5.0), vth=BSS138_VTH, baud=(1000000,), c_cable=(CABLE_SHORT,))
    )
    if include_long_1m:
        c_list += corners(vio=(3.3, 5.0), vth=BSS138_VTH, baud=(1000000,), c_cable=(CABLE_LONG,))
    return c_list


def tx(sim, c_list):
    """ESP32 IO5 -> Q_TX -> J_UART.2 into the cable and a CMOS receiver at VIO."""
    def check(tr, c):
        return check_edges(tr, c, "uart_tx", 0.7 * c["vio"], 0.3 * c["vio"])
    return run_matrix(sim, "tx", lambda vio, vth, baud, c_cable: netlist("tx", vio, vth, baud, c_cable),
                      c_list, ["uart_tx", "io5"], check)


def rx(sim, c_list):
    """External device -> J_UART.1 -> Q_RX -> ESP32 IO10."""
    def check(tr, c):
        return check_edges(tr, c, "io10", ESP_VIH, ESP_VIL)
    return run_matrix(sim, "rx", lambda vio, vth, baud, c_cable: netlist("rx", vio, vth, baud, c_cable),
                      c_list, ["io10", "uart_rx"], check)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stress-long-cable-1m", action="store_true",
                    help="Include 1 Mbps on 500 pF (5 m) cable (unsupported for passive pullups)")
    args = ap.parse_args()

    sim = NgSpice()
    c_list = get_corners(args.stress_long_cable_1m)
    sys.exit(report(tx(sim, c_list) + rx(sim, c_list)))


if __name__ == "__main__":
    main()

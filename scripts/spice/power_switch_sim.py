#!/usr/bin/env python3
"""SPICE verification of the DroidPowerSense LM5060 + back-to-back CSD18532Q5B high-side switch,
remote switch (J_SW), MCU cutoff override (Q_CUTOFF), and reverse polarity protection circuit.

    python3 scripts/spice/power_switch_sim.py
"""
import argparse
import sys

from ngspice_harness import NgSpice, first_above, report, time_above
from spice_lib import corners, diode, nmos, npn, peak, ramp, run_matrix, switch_model

# Component values (kept in lockstep with PCB/stackup/board.kdl)
VALUES = dict(
    R_EN1="100k",
    R_EN2="47k",
    R_CUTOFF_PD="100k",
    R_UVLO1="33k",
    R_UVLO2="10k",
    R_OVP1="180k",
    R_OVP2="10k",
    R_GATE="2.2k",
    R_REV="47k",
    R_SENSE="22k",
    R_OUT="10k",
    C_TIMER="68n",
    C_PROT_VIN="100n",
)

# Datasheet limits:
# - LM5060 (SNVS628H, Section 6.5):
#     EN rising threshold ENTHH = 2.0 V max (1.5 V typ), falling ENTHL = 0.8 V min, disabled < 0.5 V
#     UVLO rising threshold UVLOTH = 1.60 V typ (1.55..1.65 V), UVLOBIAS = 5.5 uA typ
#     OVP rising threshold OVPTH = 2.00 V typ (1.93..2.06 V)
#     Charge-pump gate source IGATE = 24 uA typ (18..30 uA), clamped 16.8 V above OUT
# - CSD18532Q5B (SLPS322E, Section 4.1):
#     VGS(th) = 1.5..2.2 V (1.8 V typ), VDS max = 60 V, VGS max = +/-20 V
# - BSS138 (BSS138-D):
#     VGS(th) = 0.8..1.5 V
EN_VIH_MAX = 2.0
EN_DISABLED_MAX = 0.5
UVLO_TYP = 1.60
OVP_TYP = 2.00
FET_VTH = (1.5, 2.2)
CUTOFF_VTH = (0.8, 1.5)


def netlist(
    vbat=24.0,
    rise="1m",
    sw_closed=True,
    cutoff_pwl="PWL(0 0 10 0)",
    vth_fet=1.8,
    vth_cutoff=1.1,
    tstop="50m",
    tstep="20u",
):
    v = VALUES
    sw_ctrl = "PWL(0 1 10 1)" if sw_closed else "PWL(0 0 10 0)"
    return f"""* DroidPowerSense high-side switch & protection behavioral model
{nmos('NFET_PWR', vth_fet, kp=50.0)}
{nmos('NFET_CUT', vth_cutoff, kp=0.5)}
{npn('QREV_NPN')}
.model DSCH60 D(IS=2u N=1.05 RS=0.1 CJO=50p BV=60 IBV=10u)
{diode('D1N4148', '1N4148')}
{switch_model('SWM')}

Vbat vbat_in 0 {ramp(vbat, rise)}

* Remote switch J_SW + reverse-blocking 60V Schottky diode D_SW (B160-13-F)
Sjsw vbat_in jsw_out sw_c 0 SWM
Vsw_c sw_c 0 {sw_ctrl}
Dsw jsw_out vsw_ctrl DSCH60
Cvin vsw_ctrl 0 {v['C_PROT_VIN']}
Rleak_ctrl vsw_ctrl 0 10Meg

* EN divider + bias sink (6 uA equivalent) + MCU cutoff N-FET Q_CUTOFF (BSS138)
Ren1 vsw_ctrl en {v['R_EN1']}
Ren2 en 0 {v['R_EN2']}
Ien_bias en 0 6u
Ded_clamp 0 en DSCH60
Vcut cutoff_gpio 0 {cutoff_pwl}
Rcut_pd cutoff_gpio 0 {v['R_CUTOFF_PD']}
Mcut en cutoff_gpio 0 0 NFET_CUT W=1 L=1

* UVLO divider + 5.5 uA bias sink
Ruv1 vsw_ctrl uvlo {v['R_UVLO1']}
Ruv2 uvlo 0 {v['R_UVLO2']}
Iuv_bias uvlo 0 5.5u
Duv_clamp 0 uvlo DSCH60

* OVP divider
Rov1 vsw_ctrl ovp {v['R_OVP1']}
Rov2 ovp 0 {v['R_OVP2']}

* LM5060 smooth behavioral charge pump: 24 uA pull-up toward (v(vsw_mid) + 15V) when enabled,
* pull-down resistor when disabled
B_en_ok en_ok 0 V = 0.5*(1+tanh(20*(v(vsw_ctrl)-5.1))) * 0.5*(1+tanh(20*(v(en)-1.5))) * 0.5*(1+tanh(20*(v(uvlo)-1.6))) * 0.5*(1+tanh(20*(2.0-v(ovp))))
B_cp 0 gate_drv I = v(en_ok) * 24u * 0.5*(1+tanh(2*(v(vsw_mid)+15.0-v(gate_drv)))) - (1-v(en_ok)) * v(gate_drv) / 1k
Rg_clamp gate_drv 0 10Meg
Rgate gate_drv gate_fet {v['R_GATE']}
Dgoff gate_fet gate_drv DSCH60
Cgs1 gate_fet vsw_mid 3.9n
Cgs2 gate_fet vsw_out 0.5n
Rgs_clamp gate_fet vsw_mid 10Meg

* Reverse-polarity VGS clamp (LM5060 Fig. 41: Q3 NPN MMBT3904, D5 1N4148W, R2 47k)
Qrev gate_fet rev_base vsw_mid QREV_NPN
Drev vsw_mid rev_base D1N4148
Rrev rev_base 0 {v['R_REV']}

* Back-to-back 60V N-MOSFETs Q1 (drain=vbat_in, source=vsw_mid) and Q2 (source=vsw_mid, drain=vsw_out)
Mq1 vbat_in gate_fet vsw_mid vsw_mid NFET_PWR W=100 L=1
Dq1_body vsw_mid vbat_in DSCH60
Mq2 vsw_out gate_fet vsw_mid vsw_mid NFET_PWR W=100 L=1
Dq2_body vsw_mid vsw_out DSCH60

* Output load (10 ohm + 100 uF downstream capacitance) and 60V flyback diode D_FLY (B560C-13-F)
Dfly 0 vsw_out DSCH60
Rload vsw_out 0 10
Cload vsw_out 0 100u

.tran {tstep} {tstop} uic
.end
"""


NODES = ["vbat_in", "vsw_ctrl", "en", "uvlo", "ovp", "gate_fet", "vsw_mid", "vsw_out"]


def sw_open_zero_drain(sim):
    """With J_SW open across 9V..32V, VSW_CTRL, EN, and VOUT stay at 0V (zero drain)."""
    def build(vbat, rise):
        return netlist(vbat=vbat, rise=rise, sw_closed=False, tstop="20m", tstep="20u")

    def check(tr, c):
        vout_pk = peak(tr.time, tr["vsw_out"])
        en_pk = peak(tr.time, tr["en"])
        ok = vout_pk < 0.05 and en_pk < 0.05
        return ok, f"VOUT peak {vout_pk*1e3:.1f} mV, EN peak {en_pk*1e3:.1f} mV"

    return run_matrix(sim, "sw_open", build, corners(vbat=(9.0, 24.0, 32.0), rise=("10u", "5m")), NODES, check)


def normal_turn_on(sim):
    """With J_SW closed across 9V..30V, EN > 2.0V, UVLO > 1.6V, OVP < 2.0V, and VOUT ramps to VBAT."""
    def build(vbat, vth):
        return netlist(vbat=vbat, sw_closed=True, vth_fet=vth, tstop="60m", tstep="25u")

    def check(tr, c):
        vbat = c["vbat"]
        en_final = tr["en"][-1]
        uvlo_final = tr["uvlo"][-1]
        ovp_final = tr["ovp"][-1]
        vout_final = tr["vsw_out"][-1]
        vgs_final = tr["gate_fet"][-1] - tr["vsw_mid"][-1]
        ok = (
            en_final >= EN_VIH_MAX
            and uvlo_final >= UVLO_TYP
            and ovp_final < OVP_TYP
            and vout_final >= vbat - 0.2
            and 8.0 <= vgs_final <= 16.5
        )
        return ok, (
            f"EN={en_final:.2f}V UVLO={uvlo_final:.2f}V OVP={ovp_final:.2f}V "
            f"VGS={vgs_final:.1f}V VOUT={vout_final:.2f}V"
        )

    return run_matrix(sim, "turn_on", build, corners(vbat=(9.0, 12.0, 24.0, 30.0), vth=FET_VTH), NODES, check)


def mcu_cutoff_override(sim):
    """When MCU drives PWR_CUTOFF=3.3V at t=30ms, EN drops <0.5V and VOUT turns off cleanly."""
    def build(vbat, vth_cut):
        return netlist(
            vbat=vbat,
            sw_closed=True,
            cutoff_pwl="PWL(0 0 30m 0 30.1m 3.3 10 3.3)",
            vth_cutoff=vth_cut,
            tstop="60m",
            tstep="25u",
        )

    def check(tr, c):
        en_end = tr["en"][-1]
        vout_end = tr["vsw_out"][-1]
        ok = en_end < EN_DISABLED_MAX and vout_end < 0.5
        return ok, f"post-cutoff EN={en_end*1e3:.1f} mV, VOUT={vout_end:.2f} V"

    return run_matrix(sim, "mcu_cutoff", build, corners(vbat=(9.0, 24.0, 30.0), vth_cut=CUTOFF_VTH), NODES, check)


def reverse_polarity(sim):
    """At -30V reverse battery input, D_SW and Q2 block reverse conduction; VOUT stays near 0V."""
    def build(vbat):
        return netlist(vbat=vbat, sw_closed=True, tstop="20m", tstep="20u")

    def check(tr, c):
        vout_min = min(tr["vsw_out"])
        vctrl_min = min(tr["vsw_ctrl"])
        ok = vout_min > -0.1 and vctrl_min > -0.1
        return ok, f"min VOUT={vout_min*1e3:.1f} mV, min VSW_CTRL={vctrl_min*1e3:.1f} mV"

    return run_matrix(sim, "reverse_pol", build, corners(vbat=(-12.0, -24.0, -30.0)), NODES, check)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", choices=["sw_open", "turn_on", "mcu_cutoff", "reverse_pol", "all"], default="all")
    args = ap.parse_args()

    sim = NgSpice()
    results = []
    if args.scenario in ("sw_open", "all"):
        results.extend(sw_open_zero_drain(sim))
    if args.scenario in ("turn_on", "all"):
        results.extend(normal_turn_on(sim))
    if args.scenario in ("mcu_cutoff", "all"):
        results.extend(mcu_cutoff_override(sim))
    if args.scenario in ("reverse_pol", "all"):
        results.extend(reverse_polarity(sim))

    sys.exit(report(results))


if __name__ == "__main__":
    main()

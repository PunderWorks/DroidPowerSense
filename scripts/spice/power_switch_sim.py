#!/usr/bin/env python3
"""SPICE verification of the DroidPowerSense high-side switch: LM5060 + back-to-back CSD18532Q5B,
remote switch (J_SW / D_SW), MCU cutoff (Q_CUTOFF), reverse-polarity clamp (Q_REV), output TVS and
flyback diode.

    python3 scripts/spice/power_switch_sim.py                 # every scenario, as built
    python3 scripts/spice/power_switch_sim.py --scenario inrush
    python3 scripts/spice/power_switch_sim.py --c-gate 0      # remove the proposed gate capacitor

Scenarios and what each asserts are listed in README.md. The netlist mirrors PCB/stackup/board.kdl by
hand: update VALUES whenever a value or the topology there changes.
"""
import argparse
import sys

from ngspice_harness import NgSpice, first_above, report
from soa import CSD18532_SOA_30V, SMBJ33CA_PULSE, fmt_window, soa_margin
from spice_lib import corners, diode, npn, peak, ramp, run_matrix, switch_model

# ── Component values (PCB/stackup/board.kdl) ────────────────────────────────────────────────────
VALUES = dict(
    R_EN1=100e3, R_EN2=47e3, R_CUTOFF_PD=100e3,
    R_UVLO1=33e3, R_UVLO2=10e3,
    R_OVP1=180e3, R_OVP2=10e3,
    R_SENSE=33e3, R_OUT=10e3,
    R_GATE=2.2e3, R_REV=47e3,
    C_TIMER=2.2e-6, C_PROT_VIN=100e-9,
    C_BUCK_IN=20e-6,            # C_BUCK_IN1 + C_BUCK_IN2 (2 x 10 uF)
    R_VBAT=110e3,               # R_VBAT_TOP + R_VBAT_BOT
    R_SHUNT=1e-3,
    C_GATE=220e-9, R_GATE_C=1e3, # gate dV/dt capacitor (220 nF) and its damping resistor
)

# ── Datasheet limits ────────────────────────────────────────────────────────────────────────────
# LM5060 (SNVS628H, Section 6.5 Electrical Characteristics, TJ = -40..125 C):
#   POREN 5.1 V typ / 5.46 V max (VIN rising); IIN-EN 1.4 mA typ
#   ENTHH 2.00 V (min high level); ENBIAS 6 uA typ / 8 uA max
#   UVLOTH 1.45 / 1.6 / 1.75 V; UVLOBIAS 3.8 / 5.5 / 7.2 uA
#   OVPTH 1.88 / 2.0 / 2.12 V; OVPBIAS < 0.5 uA
#   ISENSE 13.6 / 16 / 18 uA; IRATIO ISENSE / IOUT-EN = 1.7 / 2.0 / 2.3; VOFFSET +/-7 mV
#   IGATE 17 / 24 / 31 uA; VGATE (GATE - VIN) 10 / 12 / 14 V; VGATE-CLAMP (GATE - OUT) 16.8 V
#   IGATE-OFF 2.2 mA (EN/UVLO low); IGATE-FLT 80 mA (timer fault)
#   VGATE-TH (GATE - OUT, ends start-up) 3.5 / 5 / 6.5 V
#   VTMRH 2.0 V; VTMRL 0.3 V; ITIMERL (start-up) 4 / 6 / 7 uA; ITIMERH (VDS fault) 8.5 / 11 / 13 uA
#   ITIMERR 6 mA reset discharge
# CSD18532Q5B (SLPS322E Section 4.1): VGS(th) 1.5 / 1.8 / 2.2 V; RDS(on) 2.5 / 3.2 mOhm at VGS 10 V;
#   gfs 143 S at 25 A; Ciss 3900 pF; Crss 13 pF at 30 V; Qgd 6.9 nC; VDS 60 V; VGS +/-20 V
# BSS138 (Q_CUTOFF): VGS(th) 0.8..1.5 V
# SMBJ33CA (D_TVS_OUT): VBR 36.7 V min, VC 53.3 V at IPP 11.3 A; SMCJ33CA (D_TVS_IN): VC 53.3 V at 28.2 A
LM5060_TYP = dict(por=5.1, enth=2.0, enbias=6e-6, uvth=1.6, uvbias=5.5e-6, ovth=2.0, isense=16e-6,
                  iratio=2.0, igate=24e-6, vgate=12.0, vgth=5.0, itl=6e-6, ith=11e-6)
# The corner that makes start-up slowest against the fastest timer (start-up timer fault):
LM5060_SLOW_START = dict(LM5060_TYP, igate=17e-6, vgate=10.0, vgth=6.5, itl=7e-6)
# The corner that charges the gate fastest (highest inrush current):
LM5060_FAST_START = dict(LM5060_TYP, igate=31e-6, vgate=14.0)
# The corner with the longest overcurrent fault delay:
LM5060_SLOW_TRIP = dict(LM5060_TYP, ith=8.5e-6, isense=18e-6, iratio=2.3)

FET_VTH = (1.5, 2.2)
CUTOFF_VTH = (0.8, 1.5)
EN_ON_MIN = 2.0          # ENTHH
EN_OFF_MAX = 0.5         # LM5060 "disabled" test condition (IIN-DIS at EN = 0.5 V)
FET_VDS_MAX = 60.0
CASE_C = 60.0            # case temperature assumed before an event, for SOA derating
TVS_C = 50.0             # TVS temperature assumed before a regen event


def step(expr, k=50.0):
    """Smooth 0..1 step of `expr` (B-source expression) around zero."""
    return f"0.5*(1+tanh({k}*({expr})))"


def netlist(vbat=24.0, rise="1m", sw_closed=True, cutoff_at=None, vth_fet=1.8, vth_cutoff=1.1,
            ic=LM5060_TYP, c_load=100e-6, r_load=100.0, c_gate=None, c_timer=None, r_sense=None,
            short_at=None, r_short=5e-3, regen=None, r_src=15e-3, l_src=0.5e-6, rds_scale=1.0,
            tstop=0.05, tmax=20e-6):
    """Board netlist. `regen` = (start_s, amps, length_s) injects motor regeneration current into
    VOUT; `short_at` closes a `r_short` short across LOAD OUT; `cutoff_at` drives PWR_CUTOFF high;
    `rds_scale` multiplies the FETs' RDS(on) (max part, hot die)."""
    v = dict(VALUES)
    if c_gate is not None:
        v["C_GATE"] = c_gate
    if c_timer is not None:
        v["C_TIMER"] = c_timer
    if r_sense is not None:
        v["R_SENSE"] = r_sense
    sw = "PWL(0 1 100 1)" if sw_closed else "PWL(0 0 100 0)"
    cut = f"PWL(0 0 {cutoff_at} 0 {cutoff_at + 1e-5} 3.3 100 3.3)" if cutoff_at is not None else "0"
    short = f"PWL(0 0 {short_at} 0 {short_at + 1e-7} 1 100 1)" if short_at is not None else "PWL(0 0 100 0)"
    if regen:
        t0, amps, length = regen
        regen_src = f"Iregen 0 vout PWL(0 0 {t0} 0 {t0 + 1e-4} {amps} {t0 + length / 2} {amps} {t0 + length} 0 100 0)"
    else:
        regen_src = ""
    gate_cap = (f"Rgc gate_fet gc {v['R_GATE_C']}\nCgate gc 0 {v['C_GATE']}" if v["C_GATE"] > 0 else "")
    # run: VIN, EN and UVLO all high. Only these reset the fault latch (SNVS628H 8.1.2, 8.1.6);
    # OVP holds the gate off and discharges the timer but does not clear a latched fault.
    run = "*".join((step(f"v(vsw_ctrl)-{ic['por']}", 20), step(f"v(en)-{ic['enth']}"),
                    step(f"v(uvlo)-{ic['uvth']}")))
    ovok = step(f"{ic['ovth']}-v(ovp)")
    return f"""* DroidPowerSense high-side switch
.model NPWR NMOS(LEVEL=1 VTO={vth_fet} KP={409 / rds_scale} RD={1.1e-3 * rds_scale} RS={1.1e-3 * rds_scale} LAMBDA=0.002)
.model NCUT NMOS(LEVEL=1 VTO={vth_cutoff} KP=0.5)
.model DBODY D(IS=1e-9 N=1.3 RS=2m CJO=1n)
.model DSCH60 D(IS=2u N=1.05 RS=0.05 CJO=50p BV=60 IBV=10u)
.model DTVS_B D(IS=1e-12 N=1.5 RS=1.47 BV=36.7 IBV=1m)
.model DTVS_C D(IS=1e-12 N=1.5 RS=0.59 BV=36.7 IBV=1m)
{diode('D1N4148', '1N4148')}
{npn('QREV_NPN')}
{switch_model('SWM')}
.model SWSHORT SW(RON={r_short} ROFF=1G VT=0.5 VH=0.1)

* Battery: ideal source behind pack + wiring resistance and inductance (an assumption, see README)
Vbat vbat_src 0 {ramp(vbat, rise)}
Rsrc vbat_src vbat_l {r_src}
Lsrc vbat_l vbat_in {l_src}
* D_TVS_IN (SMCJ33CA, bidirectional)
Dtvsi1 vbat_in tvsi DTVS_C
Dtvsi2 0 tvsi DTVS_C

* J_SW remote switch + D_SW (B160) -> VSW_CTRL, its bulk load (buck input caps, LM5060, ADC divider)
Sjsw vbat_in jsw_out sw_c 0 SWM
Vsw_c sw_c 0 {sw}
Dsw jsw_out vsw_ctrl DSCH60
Cvin vsw_ctrl 0 {v['C_PROT_VIN']}
Cbuck vsw_ctrl 0 {v['C_BUCK_IN']}
Rbuck vsw_ctrl 0 330
Rvbat vsw_ctrl 0 {v['R_VBAT']}
Bvin vsw_ctrl 0 I = 1.4m*{step('v(vsw_ctrl)-1', 5)}

* EN divider, EN bias sink, Q_CUTOFF (BSS138) driven by PWR_CUTOFF
Ren1 vsw_ctrl en {v['R_EN1']}
Ren2 en 0 {v['R_EN2']}
Ien en 0 {ic['enbias']}
Ded 0 en DSCH60
Vcut cutoff_gpio 0 {cut}
Rcut_pd cutoff_gpio 0 {v['R_CUTOFF_PD']}
Mcut en cutoff_gpio 0 0 NCUT

* UVLO divider + bias sink, OVP divider
Ruv1 vsw_ctrl uvlo {v['R_UVLO1']}
Ruv2 uvlo 0 {v['R_UVLO2']}
Iuv uvlo 0 {ic['uvbias']}
Duv 0 uvlo DSCH60
Rov1 vsw_ctrl ovp {v['R_OVP1']}
Rov2 ovp 0 {v['R_OVP2']}

* SENSE and OUT pins: VDS fault when OUT < SENSE (SENSE = VBAT_IN - ISENSE * R_SENSE)
Rsense vbat_in sense {v['R_SENSE']}
Isense sense 0 {ic['isense']}
Rout vsw_out outp {v['R_OUT']}
Iout outp 0 {ic['isense'] / ic['iratio']}
Bvds vdsflt 0 V = {step('v(sense)-v(outp)', 2000)}

* LM5060 core (behavioural): enable, start-up latch, timer, fault latch
Brun run 0 V = {run}
Bovok ovok 0 V = {ovok}
Benok en_ok 0 V = v(run)*v(ovok)
* sud: start-up done, set once GATE - OUT > VGATE-TH while enabled
Bsud 0 sud I = 1m*v(en_ok)*{step(f"v(gate_drv)-v(outp)-{ic['vgth']}", 20)}*(1-v(sud)) - 1m*(1-v(run))*v(sud)
Csud sud 0 1n
Rsud sud 0 1G
* rst: ~100 us pulse after sud rises, discharges the timer to VTMRL (0.3 V). Timer discharge is the
* 6 mA ITIMERR; once latched, the fault holds the timer (the latch, not the timer, keeps the gate off).
Rsd sud sud_d 100k
Csd sud_d 0 1n
Brst rst 0 V = max(v(sud)-v(sud_d), 0)
Btmr 0 timer I = v(en_ok)*(1-v(flt))*((1-v(sud))*{ic['itl']} + v(sud)*(v(vdsflt)*{ic['ith']} - (1-v(vdsflt))*6m*tanh(v(timer)/0.05))) - v(rst)*6m*tanh((v(timer)-0.3)/0.05) - (1-v(en_ok))*(1-v(flt))*6m*tanh(v(timer)/0.05)
Ctimer timer 0 {v['C_TIMER']}
Rtimer timer 0 1G
* flt: timer reached VTMRH (2.0 V); latched until EN, UVLO or VIN drops
Bflt 0 flt I = 100m*{step('v(timer)-2.0 + 0.5*v(flt)', 1000)}*(1-v(flt)) - 10m*(1-v(run))*v(flt)
Cflt flt 0 1n
Rflt flt 0 1G
* GATE: IGATE source toward VIN + VGATE; 2.2 mA sink when off; 80 mA sink on fault; GATE-OUT clamp
Bgate 0 gate_drv I = v(en_ok)*(1-v(flt))*{ic['igate']}*{step(f"v(vsw_ctrl)+{ic['vgate']}-v(gate_drv)", 3)} - (1-v(en_ok))*{step('v(vsw_ctrl)-3', 5)}*2.2m*tanh(v(gate_drv)/0.3) - {step('v(flt)-0.5', 50)}*80m*tanh(v(gate_drv)/0.3) - 0.05*ln(1+exp(20*(v(gate_drv)-v(outp)-16.8)))
Rgdrv gate_drv 0 100Meg

* Gate network: R_GATE, D_GOFF (B160) fast-off bypass, optional gate dV/dt capacitor
Rgate gate_drv gate_fet {v['R_GATE']}
Dgoff gate_fet gate_drv DSCH60
{gate_cap}

* Reverse-polarity VGS clamp: Q_REV (MMBT3904), D_REV (1N4148W), R_REV
Qrev gate_fet rev_base vsw_mid QREV_NPN
Drev vsw_mid rev_base D1N4148
Rrev rev_base 0 {v['R_REV']}

* Q1 (drain VBAT_IN, source VSW_MID) and Q2 (source VSW_MID, drain VSW_OUT), with zero-volt
* sources to measure each FET's current (body diode included)
Vq1 vbat_in q1d 0
Mq1 q1d gate_fet vsw_mid vsw_mid NPWR
Dq1 vsw_mid q1d DBODY
Cgs1 gate_fet vsw_mid 3.9n
Cgd1 gate_fet q1d 230p
Mq2 q2d gate_fet vsw_mid vsw_mid NPWR
Dq2 vsw_mid q2d DBODY
Cgs2 gate_fet vsw_mid 3.9n
Cgd2 gate_fet q2d 230p
Vq2 q2d vsw_out 0
Bpq1 pq1 0 V = (v(q1d)-v(vsw_mid))*i(Vq1)
Bpq2 pq2 0 V = (v(vsw_mid)-v(q2d))*i(Vq2)
Bid iq1 0 V = i(Vq1)

* R_SHUNT, LOAD OUT: D_FLY (B560C), D_TVS_OUT (SMBJ33CA), load capacitance with ESR, idle load
Rshunt vsw_out vout {v['R_SHUNT']}
Dfly 0 vout DSCH60
Vitvs vout tvs_a 0
Dtvso1 tvs_a tvso DTVS_B
Dtvso2 0 tvso DTVS_B
Btvs ptvs 0 V = abs(v(vout)*i(Vitvs))
Cload vout cl {c_load}
Resr cl 0 10m
Rload vout 0 {r_load}
Sshort vout 0 sh_c 0 SWSHORT
Vsh_c sh_c 0 {short}
{regen_src}

.tran {tmax} {tstop} 0 {tmax} uic
.end
"""


NODES = ["vbat_in", "vsw_ctrl", "en", "uvlo", "ovp", "gate_fet", "vsw_mid", "vsw_out", "vout",
         "timer", "flt", "sud", "pq1", "pq2", "iq1", "ptvs"]

THRESHOLD_WORST = dict(LM5060_TYP, enbias=8e-6, uvth=1.75, uvbias=7.2e-6, ovth=1.88)
DESIGN = {}  # --c-gate / --c-timer overrides, applied to every scenario


def build(**kw):
    return netlist(**{**DESIGN, **kw})


def on_time(vbat, ic=LM5060_TYP):
    """Time for the output to be fully on: the gate (plus any gate capacitor) charged to VBAT +
    VGATE-TH + 2 V by IGATE, with 30% margin."""
    c_gate = DESIGN.get("c_gate", VALUES["C_GATE"])
    return max(0.03, 1.3 * (vbat + ic["vgth"] + 2.0) * (c_gate + 10e-9) / ic["igate"] + 0.01)


def fault_delay(ic=LM5060_TYP):
    """VDS fault delay: C_TIMER charged from VTMRL (0.3 V) to VTMRH (2.0 V) by ITIMERH."""
    return DESIGN.get("c_timer", VALUES["C_TIMER"]) * 1.7 / ic["ith"]


def vgs_peak(tr):
    return max(abs(g - m) for g, m in zip(tr["gate_fet"], tr["vsw_mid"]))


def q_soa(tr, node="pq1", after=0.0):
    """Derated SOA margin of a FET's power waveform, counting only samples from `after` on."""
    pts = [(t, abs(x)) for t, x in zip(tr.time, tr[node]) if t >= after]
    ratio, window, avg, limit = soa_margin([t for t, _ in pts], [x for _, x in pts], CASE_C, CSD18532_SOA_30V)
    return ratio, f"{node[1:].upper()} SOA {ratio:.2f}x ({avg:.0f} W avg over {fmt_window(window)}, limit {limit:.0f} W)"


def started(tr, vbat):
    """Start-up finished: no timer fault and VOUT within 0.5 V of the battery."""
    return tr["flt"][-1] < 0.5 and tr["vout"][-1] >= vbat - 0.5


# ── Scenarios ───────────────────────────────────────────────────────────────────────────────────

def sw_open(sim):
    """J_SW open: VSW_CTRL, EN and VOUT stay at 0 V on battery insertion (zero drain)."""
    def check(tr, c):
        vout_pk, en_pk = peak(tr.time, tr["vout"]), peak(tr.time, tr["en"])
        return vout_pk < 0.05 and en_pk < 0.05, f"VOUT peak {vout_pk * 1e3:.1f} mV, EN peak {en_pk * 1e3:.1f} mV"
    return run_matrix(sim, "sw_open", lambda vbat, rise: build(vbat=vbat, rise=rise, sw_closed=False, tstop=0.02),
                      corners(vbat=(9.0, 24.0, 32.0), rise=("10u", "5m")), NODES, check)


def turn_on(sim):
    """J_SW closed, worst-case EN/UVLO/OVP thresholds and biases: EN > 2.0 V, UVLO above and OVP below
    their thresholds, start-up completes, VGS in 8..16.8 V and never above the 20 V rating."""
    def check(tr, c):
        ic = THRESHOLD_WORST
        en, uv, ov = tr["en"][-1], tr["uvlo"][-1], tr["ovp"][-1]
        vgs = tr["gate_fet"][-1] - tr["vsw_mid"][-1]
        ok = (en >= EN_ON_MIN and uv >= ic["uvth"] and ov < ic["ovth"] and started(tr, c["vbat"])
              and 8.0 <= vgs <= 16.8 and vgs_peak(tr) < 20.0)
        return ok, f"EN={en:.2f}V UVLO={uv:.2f}V OVP={ov:.2f}V VGS={vgs:.1f}V VOUT={tr['vout'][-1]:.2f}V"
    def b(vbat, vth, ic):
        return build(vbat=vbat, vth_fet=vth, ic=ic, tstop=on_time(vbat, ic) + 0.02, tmax=50e-6)
    return run_matrix(sim, "turn_on", lambda vbat, vth: b(vbat, vth, THRESHOLD_WORST),
                      corners(vbat=(9.0, 12.0, 24.0, 32.0), vth=FET_VTH), NODES, check)


def mcu_cutoff(sim):
    """PWR_CUTOFF driven high at 30 ms: EN < 0.5 V and the FET gates discharge (VGS < 1 V)."""
    def check(tr, c):
        en = tr["en"][-1]
        vgs = tr["gate_fet"][-1] - tr["vsw_mid"][-1]
        return en < EN_OFF_MAX and vgs < 1.0, f"EN={en * 1e3:.1f} mV, VGS={vgs:.2f} V after cutoff"
    return run_matrix(sim, "mcu_cutoff",
                      lambda vbat, vth_cut: build(vbat=vbat, vth_cutoff=vth_cut, cutoff_at=on_time(vbat),
                                                  tstop=on_time(vbat) + 0.03, tmax=50e-6),
                      corners(vbat=(9.0, 24.0, 32.0), vth_cut=CUTOFF_VTH), NODES, check)


def reverse_pol(sim):
    """Reverse battery with J_SW closed and 1000 uF on LOAD OUT: no reverse current to VOUT or
    VSW_CTRL, Q2 VGS within +/-20 V, Q1/Q2 VDS within 60 V."""
    def check(tr, c):
        vout_min, vctrl_min = min(tr["vout"]), min(tr["vsw_ctrl"])
        vds = max(max(abs(d - m), abs(o - m)) for d, m, o in zip(tr["vbat_in"], tr["vsw_mid"], tr["vsw_out"]))
        ok = vout_min > -0.7 and vctrl_min > -0.5 and vgs_peak(tr) < 20.0 and vds < FET_VDS_MAX
        return ok, f"min VOUT={vout_min:.2f} V, min VSW_CTRL={vctrl_min:.2f} V, |VGS| {vgs_peak(tr):.1f} V, |VDS| {vds:.1f} V"
    return run_matrix(sim, "reverse_pol", lambda vbat: build(vbat=vbat, c_load=1000e-6, tstop=0.02),
                      corners(vbat=(-12.0, -24.0, -32.0)), NODES, check)


INRUSH_LOADS = (100e-6, 1000e-6, 4700e-6, 10000e-6)
INRUSH_CORNERS = {"fast": LM5060_FAST_START, "slow": LM5060_SLOW_START}


def inrush(sim):
    """Turn-on into LOAD OUT capacitance: start-up completes before the start-up timer faults, and
    Q1 stays inside its derated SOA. 'fast' = highest gate current (worst inrush), 'slow' = slowest
    gate against the fastest timer (worst for a start-up fault)."""
    def b(c_load, vbat, corner):
        c_gate = DESIGN.get("c_gate", VALUES["C_GATE"])
        ic = INRUSH_CORNERS[corner]
        ramp_s = (vbat + ic["vgth"]) * (c_gate + 10e-9) / ic["igate"]
        tstop = min(1.5, max(0.08, 2.0 * ramp_s + 0.03))
        return build(vbat=vbat, c_load=c_load, ic=ic, tstop=tstop, tmax=5e-6 if c_gate == 0 else 50e-6)

    def check(tr, c):
        ok_start = started(tr, c["vbat"])
        ratio, soa_txt = q_soa(tr)
        ipk = peak(tr.time, tr["iq1"])
        t90 = first_above(tr.time, tr["vout"], 0.9 * c["vbat"])
        rise = f"{t90 * 1e3:.1f} ms" if t90 is not None else "never"
        state = "started" if ok_start else ("TIMER FAULT" if tr["flt"][-1] > 0.5 else "not up")
        return ok_start and ratio <= 1.0, f"{state}, VOUT 90% at {rise}, peak {ipk:.1f} A, {soa_txt}"
    return run_matrix(sim, "inrush", lambda c_load, vbat, corner: b(c_load, vbat, corner),
                      corners(c_load=INRUSH_LOADS, vbat=(12.0, 32.0), corner=tuple(INRUSH_CORNERS)), NODES, check)


def overcurrent(sim):
    """Overload and dead short on LOAD OUT after turn-on: the LM5060 latches off, and Q1/Q2 stay inside
    their derated SOA through the fault delay. The short's current depends on the assumed battery and
    wiring impedance (r_src)."""
    ic = LM5060_SLOW_TRIP

    def b(vbat, fault):
        r_short = vbat / 120.0 if fault == "120A" else 5e-3
        return build(vbat=vbat, ic=ic, short_at=on_time(vbat, ic), r_short=r_short, c_load=1000e-6,
                     tstop=on_time(vbat, ic) + 1.5 * fault_delay(ic) + 0.05, tmax=10e-6)

    def check(tr, c):
        t_on = on_time(c["vbat"], ic)
        tripped = tr["flt"][-1] > 0.5
        t_trip = first_above(tr.time, tr["flt"], 0.5)
        delay = f"{(t_trip - t_on) * 1e3:.1f} ms" if t_trip is not None else "no trip"
        ratio, soa_txt = q_soa(tr, after=t_on)
        ipk = peak(tr.time, tr["iq1"], start=t_on)
        return tripped and ratio <= 1.0, f"trip after {delay}, peak {ipk:.0f} A, {soa_txt}"
    return run_matrix(sim, "overcurrent", b, corners(vbat=(12.0, 32.0), fault=("120A", "short")), NODES, check)


def regen(sim):
    """Motor regeneration into LOAD OUT while the output is cut off (PWR_CUTOFF at 30 ms, regen starts
    at the same moment): VOUT stays under Q2's 60 V VDS rating and the LM5060 OUT pin's 75 V, and
    D_TVS_OUT stays inside its pulse rating. With the output on, regen flows back into the battery."""
    t0 = on_time(32.0)

    def b(amps, state):
        cut = t0 if state == "cutoff" else None
        return build(vbat=32.0, c_load=1000e-6, cutoff_at=cut, regen=(t0, amps, 0.1), tstop=t0 + 0.15, tmax=10e-6)

    def check(tr, c):
        vpk = peak(tr.time, tr["vout"])
        vds = max(o - m for o, m in zip(tr["vsw_out"], tr["vsw_mid"]))
        ratio, window, avg, limit = soa_margin(tr.time, tr["ptvs"], TVS_C, SMBJ33CA_PULSE)
        ok = vds < FET_VDS_MAX and vpk < 75.0 and ratio <= 1.0
        return ok, (f"VOUT peak {vpk:.1f} V, Q2 VDS {vds:.1f} V, TVS {ratio:.2f}x of rating "
                    f"({avg:.0f} W avg over {fmt_window(window)}, limit {limit:.0f} W)")
    return run_matrix(sim, "regen", b, corners(amps=(5.0, 15.0, 30.0), state=("cutoff", "on")), NODES, check)


# RDS(on) scale for a hot die: 1.55x at TC = 100 C (CSD18532Q5B Fig. 4-8), on a typical (2.5 mOhm)
# and a maximum (3.2 mOhm) part. The README's still-air estimate puts the FETs 65-90 C above ambient.
HOT_RDS = {"typ_100C": 1.55, "max_100C": 1.55 * 3.2 / 2.5}
LM5060_LOW_TRIP = dict(LM5060_TYP, isense=13.6e-6, iratio=1.7)   # lowest VDS threshold (offset ignored)


def hot_30a(sim):
    """30 A continuous (the board's rating) with hot FETs: the LM5060 VDS comparator must not trip.
    VDS threshold = ISENSE x R_SENSE - IOUT x R_OUT, compared across Q1 + Q2 in series."""
    def b(vbat, rds, threshold):
        ic = LM5060_LOW_TRIP if threshold == "low" else LM5060_TYP
        t_on = on_time(vbat, ic)
        return build(vbat=vbat, ic=ic, rds_scale=HOT_RDS[rds], short_at=t_on, r_short=vbat / 30.0,
                     tstop=t_on + 1.5 * fault_delay(ic) + 0.01, tmax=50e-6)

    def check(tr, c):
        vds = tr["vbat_in"][-1] - tr["vsw_out"][-1] if tr["flt"][-1] < 0.5 else float("nan")
        tripped = tr["flt"][-1] > 0.5
        return not tripped, ("TRIPPED at 30 A" if tripped else f"no trip, VDS(Q1+Q2) = {vds * 1e3:.0f} mV")
    return run_matrix(sim, "hot_30a", b, corners(vbat=(24.0,), rds=tuple(HOT_RDS), threshold=("typ", "low")),
                      NODES, check)


SCENARIOS = dict(sw_open=sw_open, turn_on=turn_on, mcu_cutoff=mcu_cutoff, reverse_pol=reverse_pol,
                 inrush=inrush, overcurrent=overcurrent, hot_30a=hot_30a, regen=regen)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    ap.add_argument("--recommended", action="store_true",
                    help="Use recommended values: C_GATE=220nF, C_TIMER=2.2uF, R_SENSE=33k")
    ap.add_argument("--c-gate", type=float, help="gate dV/dt capacitor in farads (board value by default)")
    ap.add_argument("--c-timer", type=float, help="C_TIMER in farads (board value by default)")
    ap.add_argument("--r-sense", type=float, help="R_SENSE in ohms (board value by default)")
    args = ap.parse_args()
    if args.recommended:
        DESIGN.setdefault("c_gate", 220e-9)
        DESIGN.setdefault("c_timer", 2.2e-6)
        DESIGN.setdefault("r_sense", 33e3)
    if args.c_gate is not None:
        DESIGN["c_gate"] = args.c_gate
    if args.c_timer is not None:
        DESIGN["c_timer"] = args.c_timer
    if args.r_sense is not None:
        DESIGN["r_sense"] = args.r_sense
    print(f"C_GATE = {DESIGN.get('c_gate', VALUES['C_GATE']) * 1e9:g} nF, "
          f"C_TIMER = {DESIGN.get('c_timer', VALUES['C_TIMER']) * 1e9:g} nF, "
          f"R_SENSE = {DESIGN.get('r_sense', VALUES['R_SENSE']) / 1e3:g} k\n")

    sim = NgSpice()
    results = []
    for name, fn in SCENARIOS.items():
        if args.scenario in (name, "all"):
            results.extend(fn(sim))
    sys.exit(report(results))


if __name__ == "__main__":
    main()

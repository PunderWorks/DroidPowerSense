# DroidPowerSense SPICE Verification Suite

This directory contains the analog SPICE simulation models, Safe Operating Area (SOA) thermal verification engine, and scenario test harnesses for the **DroidPowerSense** hardware.

All simulations use KiCad's bundled `libngspice` through the native Python ctypes harness (`ngspice_harness.py`).

---

## Quick Start

```bash
# 1. Run SOA unit tests
python3 scripts/spice/test_soa.py

# 2. Run UART bidirectional level shifter verification
python3 scripts/spice/uart_shifter_sim.py

# 3. Run power switch simulation with current board values (baseline)
python3 scripts/spice/power_switch_sim.py

# 4. Run power switch simulation with recommended mitigations
python3 scripts/spice/power_switch_sim.py --recommended
```

---

## File Structure

- **`power_switch_sim.py`**: Behavioral and physical simulation of the high-side power path: `LM5060MM/NOPB` protection controller, back-to-back `CSD18532Q5B` 60 V N-MOSFETs, remote switch `J_SW`, MCU cutoff `Q_CUTOFF`, reverse-polarity clamp `Q_REV`, and transient suppression.
- **`uart_shifter_sim.py`**: Transient simulation of the bidirectional `BSS138` level shifters (`Q_TX`, `Q_RX`) across `3.3 V` and `5 V` `J_VIO` settings, threshold corners, baud rates, and cable capacitances.
- **`soa.py`**: Safe Operating Area (SOA) power evaluation library implementing continuous piecewise log-log curve interpolation and moving-window thermal averaging matching manufacturer pulse curves for the `CSD18532Q5B` MOSFET and `SMBJ33CA` TVS.
- **`test_soa.py`**: Unit test suite validating boundary interpolation, energy integration, and thermal derating in `soa.py`.
- **`ngspice_harness.py` & `spice_lib.py`**: Python ctypes bridge to `libngspice` with stimulus builders, corner matrix runners, and waveform measurement utilities.

---

## Simulation Scenarios & Verification Matrix

### 1. `sw_open` — Battery Insertion with Switch Open
- **Conditions**: Battery connected (`9 V`, `24 V`, `32 V`) with `10 µs` and `5 ms` rise times while `J_SW` is open.
- **Verification**: `VSW_CTRL`, `EN`, and `VOUT` remain at `0 V` (<0.2 mV residual). Battery leakage is strictly 0.0 nA through the open switch and blocking diode `D_SW`.
- **Status**: **PASS** (6/6 corners).

### 2. `turn_on` — Normal Turn-On & Threshold Margins
- **Conditions**: `J_SW` closed across `9 V` to `32 V` supplies and worst-case LM5060 thresholds (`ENTHH = 2.0 V`, `UVLOTH = 1.75 V`, `OVPTH = 1.88 V`, bias currents at max).
- **Verification**:
  - `EN` rises well above `2.0 V` (`2.46 V` at 9 V in, `9.78 V` at 32 V in).
  - `UVLO` divider exceeds threshold at nominal supplies (`1.95 V` at 9 V in).
  - `OVP` divider remains safely below threshold (`1.66 V` at 32 V in).
  - Charge pump enhances FET gates to $V_{GS} \approx 12.2\text{--}12.5\text{ V}$, well below the $\pm 20\text{ V}$ absolute maximum gate-source rating.
- **Status**: **PASS** (8/8 corners).

### 3. `mcu_cutoff` — Firmware Emergency Cutoff
- **Conditions**: Microcontroller drives `PWR_CUTOFF` GPIO high (`3.3 V`) via `Q_CUTOFF` (`BSS138`).
- **Verification**: `EN` pin pulls cleanly below `0.5 V` (entering the LM5060 low-power disabled state). The charge pump is disabled and gate discharge sinks discharge the FET gates to $<0.5\text{ V}$ within microseconds, isolating `LOAD OUT` while leaving the ESP32-C5 powered from `VSW_CTRL` to log and report telemetry.
- **Status**: **PASS** (6/6 corners).

### 4. `reverse_pol` — Reverse Battery Connection
- **Conditions**: Battery connected in reverse (`-12 V`, `-24 V`, `-32 V`) with `J_SW` closed and `1000 µF` capacitance on `LOAD OUT`.
- **Verification**:
  - `D_SW` blocks reverse current to `VSW_CTRL` and the 5V buck converter.
  - Back-to-back MOSFET `Q2` blocks reverse conduction into `LOAD OUT` (`VOUT = 0.0 V`).
  - Active clamp circuit (`Q_REV`, `D_REV`, `R_REV`) forward-biases and pins `GATE_FET` to `VSW_MID` ($|V_{GS}| < 0.5\text{ V}$), preventing Q2 gate-source breakdown.
  - Reverse $V_{DS}$ on both FETs stays well within the 60 V rating ($|V_{DS}| \le 31.5\text{ V}$ at -32 V).
- **Status**: **PASS** (3/3 corners).

### 5. `inrush` — Turn-On into Capacitive Loads
- **Conditions**: Output turned on into bulk capacitive loads ($100\ \mu\text{F}$, $1000\ \mu\text{F}$, $4700\ \mu\text{F}$, $10000\ \mu\text{F}$) at `12 V` and `32 V` across fast and slow charge-pump corners.
- **Findings**:
  - **Baseline ($C_{GATE} = 0$, $C_{TIMER} = 100\text{ nF}$)**: The gate charges in $\sim 1\text{ ms}$, dumping high instantaneous current into large capacitors ($120\text{ A}$ into $1000\ \mu\text{F}$; $480\text{ A}$ into $10,000\ \mu\text{F}$ at 32 V), exceeding the CSD18532Q5B SOA rating by up to $13.8\times$.
  - **Mitigation ($C_{GATE} = 220\text{ nF}$, $R_{GATE\_C} = 1\text{ k}\Omega$, $C_{TIMER} = 2.2\ \mu\text{F}$)**: Output slew rate is controlled to $\sim 100\text{ V/s}$. Peak inrush into $10,000\ \mu\text{F}$ drops from $480\text{ A}$ to **$1.7\text{ A}$**, passing derated SOA with **$0.88\times$** margin.
- **Status**: **PASS** (16/16 corners with recommended values).

### 6. `hot_30a` — Continuous 30 A Rated Load at Elevated Die Temperatures
- **Conditions**: 30 A continuous load with hot FET junction ($T_J = 100^\circ\text{C}$, $R_{DS(on)}$ increased by $1.55\times$) across typical and worst-case LM5060 $I_{SENSE}$ tolerance ($13.6\ \mu\text{A}$ min).
- **Findings**:
  - **Baseline ($R_{SENSE} = 22\text{ k}\Omega$)**: Threshold drop is $13.6\ \mu\text{A} \times 22\text{ k}\Omega = 299\text{ mV}$. Hot FET series drop at 30 A reaches $282\text{ mV}$ (typ) to $>300\text{ mV}$ (max), causing **false overcurrent trip** during normal rated operation!
  - **Mitigation ($R_{SENSE} = 33\text{ k}\Omega$)**: Threshold drop rises to $448\text{ mV}$ (min) / $528\text{ mV}$ (typ). Minimum hot trip threshold is $\sim 45\text{ A}$ ($50\%$ margin above 30 A continuous rating).
- **Status**: **PASS** (4/4 corners with $R_{SENSE} = 33\text{ k}\Omega$).

### 7. `overcurrent` — Overload Stall vs Dead Short
- **Conditions**: 120 A overload (motor stall) and $5\text{ m}\Omega$ dead short directly across `LOAD OUT` terminals.
- **Findings**:
  - **120 A Overload**: The LM5060 detects $V_{DS}$ fault, charges $C_{TIMER}$, and latches off cleanly. At 32 V, trip occurs within timer delay and Q1 SOA margin is respected ($0.39\times$ of single-pulse limit).
  - **$5\text{ m}\Omega$ Dead Short**: Drawing $\sim 1200\text{ A}$ from a low-impedance lithium pack for the LM5060's electronic circuit breaker delay ($20\text{--}500\text{ ms}$) exceeds silicon SOA ($>50\times$).
  - **Physical Requirement**: The LM5060 is an electronic circuit breaker and motor overload protector, **not a current limiter**. A fast-acting upstream battery fuse ($30\text{--}50\text{ A}$ automotive blade or MIDI fuse) with $<2\text{ ms}$ clearing time on short circuits is **mandatory** on the main battery lead.

### 8. `regen` — Motor Regeneration / Back-EMF
- **Conditions**: Motors regenerate $5\text{ A}$, $15\text{ A}$, and $30\text{ A}$ for $100\text{ ms}$ into `LOAD OUT`.
- **Findings**:
  - **FETs ON (`state=on`)**: Regeneration current flows safely through $Q2 \rightarrow Q1$ back into the battery pack ($V_{OUT} \approx 32.7\text{ V}$). TVS dissipation is 0 W. **PASS** (3/3 corners).
  - **FETs CUT OFF (`state=cutoff`)**: If firmware cuts off the switch while motors are actively generating, current cannot enter the battery and dumps into `D_TVS_OUT` (`SMBJ33CA`), clamping $V_{OUT}$ to $51\text{--}61\text{ V}$. For continuous $100\text{ ms}$ pulses, this exceeds the 600 W SMB TVS rating by $3.8\times$ to $10.7\times$.
  - **Firmware Rule**: Firmware must never assert `PWR_CUTOFF` while motors are in motion or back-EMF is present.

---

## UART Level Shifter Verification (`uart_shifter_sim.py`)

Simulates the bidirectional `BSS138` level shifters (`Q_TX`, `Q_RX`) connecting the ESP32-C5 (3.3 V) to external devices (3.3 V or 5.0 V via `J_VIO`).

- **115.2 kbps (Standard Droid Bus)**: **100% PASS** across all corners (3.3 V and 5.0 V VIO, min/max $V_{GS(th)}$, and cable lengths from 1 m to 5 m / $500\text{ pF}$).
- **1.0 Mbps (High Speed)**: **PASS** on standard cable lengths ($\le 1.5\text{ m}$, $150\text{ pF}$). Cables $>3\text{ m}$ ($500\text{ pF}$) with passive 1k/4.7k pullups cannot physically meet 100 ns rise times; high-speed droid communication over long wiring harnesses should use the onboard differential CAN FD transceiver (`TCAN334G`).

---

## Summary of Recommendations for Hardware & Firmware

| Parameter | Baseline (Current PCB) | Recommended | Reason |
|:---|:---|:---|:---|
| **$R_{SENSE}$** | $22\text{ k}\Omega$ | **$33\text{ k}\Omega$** | Eliminates false overcurrent trips under 30 A continuous load when FETs reach $100^\circ\text{C}$. |
| **$C_{GATE}$ & $R_{GATE\_C}$** | Unpopulated ($0\text{ nF}$) | **$220\text{ nF}$ + $1\text{ k}\Omega$** | Tames capacitive inrush into large motor controller capacitors ($\ge 1000\ \mu\text{F}$) from $480\text{ A}$ down to $<1.7\text{ A}$. |
| **$C_{TIMER}$** | $100\text{ nF}$ | **$2.2\ \mu\text{F}$** | Accommodates gate slew ramp into bulk capacitance without premature start-up timer fault. |
| **Battery Fuse** | None on board | **$30\text{--}50\text{ A}$ Inline Fuse** | Essential protection against instantaneous dead shorts (<2 ms clearing). |
| **Firmware Policy** | Unspecified | **No Cutoff During Decel** | Prevents dumping sustained motor regeneration energy into the output TVS diode. |

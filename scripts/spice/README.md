# DroidPowerSense SPICE Verification

`power_switch_sim.py` simulates the high-side protection and power switching path (`LM5060MM/NOPB` + back-to-back `CSD18532Q5B` N-MOSFETs + remote switch `J_SW` + MCU cutoff `Q_CUTOFF`) across voltage and threshold corners using KiCad's bundled `libngspice`.

## Running

```bash
python3 scripts/spice/power_switch_sim.py
```

## Scenarios covered

- `sw_open`: Remote switch `J_SW` open at `9 V`, `24 V`, and `32 V` with fast (`10 µs`) and slow (`5 ms`) battery insertion — verifies `VSW_CTRL`, `EN`, and `VOUT` remain at `0 V` with zero battery drain.
- `turn_on`: Remote switch `J_SW` closed from `9 V` to `30 V` across MOSFET $V_{GS(\text{th})}$ corners (`1.5 V` to `2.2 V`) — verifies `EN >= 2.0 V`, `UVLO >= 1.60 V`, `OVP < 2.00 V`, charge-pump gate enhancement ($V_{GS} \approx 15\text{ V}$), and soft-start into capacitive load.
- `mcu_cutoff`: Firmware drives `PWR_CUTOFF` high (`3.3 V`) via `Q_CUTOFF` (`BSS138`) — verifies `EN < 0.5 V` (disabled mode) and clean load turn-off while keeping `VSW_CTRL` alive for telemetry.
- `reverse_pol`: Reverse battery connection (`-12 V`, `-24 V`, `-30 V`) with `J_SW` closed — verifies `D_SW` and back-to-back `Q2` block reverse conduction to both control rail and load output (`VOUT`).

# Firmware requirements from the hardware

What the DroidPowerSense board needs from its firmware (Rust, ESP32-C5 on a Waveshare
ESP32-C5-Zero-M). Each item comes from the hardware design and its review. The design details are in
[PCB/README.md](../PCB/README.md), the netlist in [PCB/stackup/board.kdl](../PCB/stackup/board.kdl),
and the simulations in [scripts/spice/](../scripts/spice/README.md). Datasheet page and table
references point to the files in [PCB/datasheets/](../PCB/datasheets/).

## Safety-critical (the hardware relies on firmware for these)

1. **Overcurrent cutoff is firmware's job.**
   - **Why:** the LM5060's hardware V_DS trip is only a backstop. It trips at roughly 45 A with hot
     FETs and roughly 105 A cold, after a 0.34 s typical / 0.65 s worst-case delay. Between 30 A and
     that trip point, the hardware alone never opens the switch. The simulation shows a 104 A overload
     at 12 V never tripping.
   - **Do:** set the INA237's shunt over-voltage limit (SOVL) as the over-current threshold and watch
     ALERT on **IO4**. When it fires, assert **PWR_CUTOFF (IO1 high)** within a few milliseconds.
   - **Threshold:** pick it above the rated 30 A continuous and the expected peaks; 40 A is a starting
     point to tune on the bench.
   - **Backup:** a mandatory 30–50 A fuse in the battery lead, upstream of the board, clears dead
     shorts.
   - **Bench:** confirm the cutoff time on the first board (PCB README bench step 6a).
2. **Never assert PWR_CUTOFF while the motors are regenerating.**
   - **Why:** with the switch off, regenerated current can't return to the battery. It dumps into the
     output TVS (D_TVS_OUT, SMBJ33CA) at 3.8–10.7× its rating (simulated at 5–30 A).
   - **Do:** detect regen as negative current on the INA237 and hold off a *non-emergency* cutoff
     until it stops.
   - **Open decision:** an overcurrent cutoff (item 1) while regen is happening is an unresolved
     conflict. Decide the policy before writing it.
3. **Clearing a hardware fault latch.**
   - **Behaviour:** when the LM5060 trips on V_DS, it latches the FETs off "until either the EN pin,
     the UVLO pin, or the VIN pin is toggled low and then high" (LM5060 datasheet, TIMER pin
     description).
   - **Do:** clear it by pulsing PWR_CUTOFF high and then low, which pulls EN low and releases it. The
     output then soft-starts again (about 40–250 ms in simulation, longest at 32 V).
   - **Policy:** decide when an automatic retry is allowed, if ever.

## Pin map (ESP32-C5-Zero-M)

| GPIO | Net | Use | Notes |
|---|---|---|---|
| IO0 | PWR_PGOOD | LM5060 nPGD input | Open-drain, 10 k pull-up. **Low = OK, high = fault** (or switch off). |
| IO1 | PWR_CUTOFF | Load cutoff output | **High = load off.** 100 k pull-down keeps the load on through boot and reset. |
| IO2 | I2C_SDA | INA237 | 4.7 k pull-up. Strapping pin (MTMS), harmless here. |
| IO3 | I2C_SCL | INA237 | 4.7 k pull-up. Strapping pin (MTDI), harmless here. |
| IO4 | INA_ALERT | INA237 ALERT input | Open-drain, 10 k pull-up, **active low** by default. |
| IO5 | UART_TX_3V3 | UART1 TX → J8 pin 2 | Through a BSS138 level shifter. |
| IO6 | VBAT_ADC | ADC1 battery voltage | VSW_CTRL ÷ 11 (100 k / 10 k, 100 nF). |
| IO7 | CIRCUIT_ID | Input | 10 k pull-up. **High = circuit 1, low (jumper on) = circuit 2.** JTAG-source strap: don't burn EFUSE_JTAG_SEL_ENABLE. |
| IO8 | CAN_TX | TWAI TX → TCAN334G | |
| IO9 | CAN_RX | TWAI RX ← TCAN334G | |
| IO10 | UART_RX_3V3 | UART1 RX ← J8 pin 1 | Through a BSS138 level shifter. |
| IO11 | — | U0TXD | Left free for the ROM boot log. |
| IO12 | SW_LED_EN | Lit remote-switch LED | 10 k pull-up: **on by default**, drive low to turn off or blink. Also U0RXD, so don't enable UART0 RX. |
| IO13/IO14 | — | USB D−/D+ | Module USB-C: programming and console (USB-Serial-JTAG). |
| GPIO26 | (module internal) | Antenna RF switch | See *Radio* below. |
| GPIO27 | (module internal) | WS2812B RGB LED on the module | |
| GPIO28 | (module internal) | BOOT button on the module | |

GPIO26, 27 and 28 are strapping pins wired inside the module (module schematic); don't reassign them.

## Peripherals

### Circuit ID
- Read IO7 at boot and tag all telemetry with it (AGENTS.md).
- One board serves each circuit; droids with two circuits use two boards.

### INA237 current and voltage monitor
- I²C address **0x40** (A1 = A0 = GND; INA237 datasheet Table 7-2).
- **Use the INA237 register map.** The board started with an INA226; the INA237 replaced it for its
  85 V input rating, and its registers differ.
- **Shunt:** R_SHUNT = 1 mΩ, between VSW_OUT and VOUT.
- **Range:** with **ADCRANGE = 0** (±163.84 mV), the full scale is ±163.84 A.
- **Calibration:** SHUNT_CAL = 819.2 × 10⁶ × CURRENT_LSB × R_SHUNT (INA237 datasheet Equation 1, for
  ADCRANGE = 0; multiply by 4 for ADCRANGE = 1).
  - With CURRENT_LSB = 163.84 A / 2¹⁵ = 5 mA, SHUNT_CAL = 4096 (0x1000), which is the reset value.
  - Re-derive it if you change ADCRANGE or CURRENT_LSB.
- **SOVL threshold** for the overcurrent alert: shunt voltage at 5 µV/LSB when ADCRANGE = 0. For
  example, 40 A × 1 mΩ = 40 mV → 8000 (0x1F40).
- **ALERT options:** ALATCH (latch until DIAG_ALRT is read), APOL (polarity, default active low) and
  SLOWALERT (compare averaged values: slower, fewer false trips). Choose with item 1's response time
  in mind.
- **Accuracy:** shunt offset ±50 µV max (= ±50 mA), gain ±0.3 % max (datasheet, Electrical
  Characteristics).
- **Bus voltage:** VBUS is measured on **VOUT**, the load side, so it reads 0 V while the switch is
  off.
- **Powered off:** the INA237 tolerates bus voltage while its supply (+3V3) is off (datasheet §7.3).

### Battery voltage
- IO6 reads VSW_CTRL ÷ 11 (ADC1). It works with the FETs off, but only while the remote switch is on
  (the board has no power otherwise).
- VSW_CTRL is the battery voltage minus the D_SW Schottky drop, a few hundred mV depending on load.
  Calibrate or compensate it.
- At 32 V the ADC pin sees about 2.9 V. Choose an ADC attenuation whose range covers that and verify
  it against the ESP32-C5 ADC specification.
- **Low-voltage cutoff:**
  - The LM5060 UVLO (about 7.5 V rising) is the hardware floor.
  - Chemistry-specific cutoffs (12 V lead-acid, 18/20 V tool packs, 24 V LiPo / LiFePO4) are
    firmware's job. Make them configurable per pack.

### Load switch behaviour
- Closing the remote switch powers the board. The LM5060 then turns the load on by itself, with a soft
  start, **without firmware**.
- Firmware can only turn the load off (PWR_CUTOFF) and back on.
- PWR_PGOOD reads high until the FETs are fully on and whenever a fault is latched.

### Lit remote switch (J3)
- The light is on whenever the board is on (pull-up on IO12). Drive IO12 low to turn it off or to
  blink it, for example on a fault, cutoff or low battery.

### CAN FD
- TWAI on IO8 (TX) and IO9 (RX), through a TCAN334G that is held in normal mode by its internal
  pull-downs. There are no transceiver control pins.
- J5 (CAN IN) and J6 (CAN OUT) are wired in parallel.
- Termination: 120 Ω via the J7 jumper. Fit it only on the boards at each end of the bus.

### UART
- UART1 on IO5 (TX) and IO10 (RX), level-shifted to 3.3 V or 5 V by the J9 jumper.
- Simulated timing: good to 115.2 kbps on cables up to 5 m (500 pF), and 1 Mbps on cables up to
  1.5 m. For faster, longer links, use CAN.

### Radio
- The module has both an onboard ceramic antenna and a U.FL connector, selected by an RF switch on
  internal **GPIO26** (ANT_Ctrl, 200 k pull-up to 3V3; module schematic).
- **Drive GPIO26 to select the onboard antenna.** Waveshare doesn't document which level selects which
  antenna, so verify on the first board.

### Programming and debug
- Program and debug over the module's USB-C, using USB-Serial-JTAG on IO13/IO14. The ROM boot log
  goes to U0TXD (IO11).
- The module plugs into sockets, so it can be removed for programming.

## Useful extras
- The INA237 has a die temperature sensor. The FETs and shunt have no sensor, and their temperature
  at 30 A is still to be measured (PCB README bench step 6). If the bench shows they run hot, consider
  time-based current derating.
- Telemetry worth reporting: current, VOUT, battery voltage, PWR_PGOOD state, cutoff and fault events
  with their cause, and the circuit ID.

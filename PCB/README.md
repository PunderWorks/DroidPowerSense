# DroidPowerSense hardware

The electrical design is Stackup KDL in [`stackup/`](stackup/) (`board.kdl`, plus the local parts in
`parts.kdl`). The KiCad board `DroidPowerSense.kicad_pcb` is synced from it through
`DroidPowerSense.stackup_sch`. Manufacturer datasheets are in [`datasheets/`](datasheets/), with
their source URLs and hashes in `datasheets/manifest.json`.

```sh
stackup check PCB/stackup/board.kdl --locked     # check the design
stackup bom PCB/stackup/board.kdl --locked -o bom.csv
python3 scripts/spice/power_switch_sim.py          # power-switch SPICE corners (23 checks)
```

After changing the KDL, use **Sync PCB from stackup** in KiCad's PCB editor, or sync headless with
the board closed:

```sh
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
  <stackup checkout>/kicad-plugin/sync_headless.py PCB/DroidPowerSense.kicad_pcb
```

Commit the synced PCB with the KDL. CI fails if syncing would change the committed PCB.

## Requirements

| Area | Requirement |
|---|---|
| Position | Inline between the battery and the droid, before its fuses. One board per circuit; droids with two circuits use two boards. |
| Batteries | 9-32 V: 12 V lead-acid, 18 V / 20 V Max power-tool packs, 24 V LiPo / LiFePO4. |
| Current | < 1 A to 30 A continuous, 60 A peak, measured in both ranges. |
| Power connectors | Polarized, high-current: XT60PW-M in (mates with the battery's female XT60), XT60PW-F out. |
| Switching | MOSFET switch so a fitted battery draws nothing while the droid is off. Switched by a remote low-power switch on a 4-pin JST-XH (switch + lit-switch LED). |
| Lit switch | Support lit-when-on switches: 3-terminal (+ / ACC / GND) and separate-LED-terminal types. The light is on whenever the board is on, firmware can blink it, and it adds no off-state drain. |
| Protection | Reverse polarity, input/output TVS, output flyback diode, over/under-voltage, overcurrent/short trip. |
| Upstream fuse | **Required:** an XT60 battery lead with an in-line blade fuse (30 A, 40 A max) ahead of J_PWR_IN, and the remote-switch lead in 22 AWG or heavier. The LM5060 is a circuit breaker with a 0.3-0.65 s fault delay, not a current limiter: only the fuse clears a dead short, and it backs up sustained overloads. |
| Overcurrent | **Firmware is the primary overload protection:** INA237 ALERT (IO4) set to the over-current limit, firmware asserts PWR_CUTOFF. The LM5060 V_DS trip (~45 A hot / ~105 A cold) is the hardware backstop; between 30 A and the trip point the hardware alone does not open the switch. |
| Load capacitance | Up to 4.7 mF on LOAD OUT at 32 V (Q1 stays within its SOA during turn-on; larger banks at 32 V exceed it). |
| MCU | ESP32-C5 (CAN FD + firmware) on a plug-in module (sockets), serviceable and programmable in place over its USB-C. Firmware in Rust. |
| Comms | CAN FD (two 3-pin JST-XH for daisy-chain, jumper termination), UART (3-pin JST-XH, 3.3 V / 5 V jumper). Pin 1 of each is a ground reference, tied to board GND through a PTC so it can never carry the load's return current. |
| Circuit ID | Firmware must tell circuit 1 from circuit 2. |
| Board | 76 × 58 mm, 4 layers, 1 oz copper, with three layers for the high-current path and a solid ground plane, components on one side. Back-side area for a user-fitted heatsink, recommended above about 15 A continuous. |
| Sourcing | Mouser and DigiKey first; LCSC numbers recorded but JLCPCB is not the planned assembler. |

## Circuit

| Block | Parts | Notes |
|---|---|---|
| Power in/out | J_PWR_IN (XT60PW-M), J_PWR_OUT (XT60PW-F), D_TVS_IN (SMCJ33CA), D_TVS_OUT (SMBJ33CA), D_FLY (B560C) | Bidirectional TVS on both sides; D_FLY clamps inductive kick from motors on the output. |
| Remote switch | J_SW (JST-XH 4-pin), D_SW (B160) | J_SW 1-2 connects VBAT_IN to VSW_CTRL. Open = the only path from the battery is TVS/MOSFET leakage (< 1 µA). D_SW blocks reverse polarity into the control rail. |
| Lit switch | J_SW.3/.4, Q_LED (BSS138), R_LED_PU 10 k | J_SW.4 = +5V for separate-terminal LEDs; J_SW.3 = LED return, switched to GND by Q_LED. R_LED_PU holds the gate on from +3V3, so the light is on as soon as the board is; IO12 low turns it off (blink). |
| High-side switch | U_PROT (LM5060), Q1/Q2 (CSD18532Q5B, back-to-back, 2.5 mΩ each), R_GATE, D_GOFF, C_GATE (100 nF 100 V), R_GATE_C (1 k), Q_REV + D_REV + R_REV | Common-source back-to-back N-FETs so the switch blocks both directions. Q_REV clamps V_GS during reverse polarity (LM5060 Fig. 41). C_GATE + R_GATE_C slows the output (~240 V/s typ) to limit inrush into capacitive loads. C_GATE is sized against the start-up timer: worst case at 32 V the gate needs 0.25 s and the timer allows 0.48 s (LM5060 IGATE 17 µA, VGATE-TH 6.5 V, ITIMERL 7 µA, VTMRH 1.70 V, ±10 % parts). 220 nF needed 0.55 s and could latch a start-up fault. |
| Protection thresholds | R_SENSE 33 k, R_OUT 10 k, C_TIMER 2.2 µF, UVLO 33 k/10 k, OVP 180 k/10 k | V_DS trip ~528 mV across 5 mΩ ≈ 105 A cold / ~45 A at 100 °C (clears 30 A continuous rating); UVLO ≈ 7.5 V rising; OVP ≈ 38 V; C_TIMER 2.2 µF: start-up window ≥ 0.48 s, V_DS fault delay 0.34 s typ / 0.65 s max. |
| MCU cutoff | Q_CUTOFF (BSS138), R_CUTOFF_PD 100 k | Firmware drives PWR_CUTOFF high to pull LM5060 EN low: load off, MCU stays powered from VSW_CTRL to report the fault. Pull-down keeps the load on through MCU boot/reset. |
| Sensing | R_SHUNT (CSS2H-2512R-1L00F, 1 mΩ 5 W), U_INA (INA237), C_INA_VS | INA237: 85 V common-mode/VBUS (VOUT reaches 42 V before D_TVS_OUT conducts, 53 V clamped; the INA226's limit was 40 V). ADCRANGE 0: ±163.84 A at 5 mA/LSB; offset ±50 mA, gain ±0.3 % max. A0/A1 to GND: I²C address 0x40. Shunt 0.9 W at 30 A, 3.6 W at 60 A (short-time overload 25 W for 5 s). Bus voltage measured on VOUT. |
| Battery ADC | R_VBAT_TOP 100 k / R_VBAT_BOT 10 k, C_VBAT_ADC | VSW_CTRL ÷ 11 into IO6, so battery voltage is readable with the MOSFETs off. |
| 5 V | U_BUCK (LMR14030, 4-40 V), R_BUCK_IN 3.3 Ω, L_BUCK 10 µH, D_BUCK (B360A) | 400 kHz, FB 56.2 k/10 k → 4.97 V. Feeds the module's 5 V pin and the UART 5 V option. R_BUCK_IN with C_BUCK_IN1/2 (BUCK_VIN) low-passes the buck input (~66 µs, ~25 µs after X5R DC-bias loss): VSW_CTRL can reach 37-53 V in an input surge, above the LMR14030's 44 V VIN/EN absolute maximum. Drop 0.76 V / 0.17 W at the worst load (0.23 A at 9 V). R_BUCK_EN pulls EN from BUCK_VIN. |
| MCU | U_MCU (Waveshare ESP32-C5-Zero-M), J_MCU_L/J_MCU_R sockets | The module plugs into two 1x9 sockets. The module's own buck makes +3V3 for the carrier (pin 3). USB-C on the module is the programming path. The module has both an onboard ceramic antenna (J2, OA-W03) and an IPEX-1/U.FL connector (J3), chosen by an RF switch on internal GPIO26 (ANT_Ctrl, 200 k pull-up to 3V3; module schematic). Firmware must drive GPIO26 to select the onboard antenna. No U.FL-free variant exists (the -M SKU only adds headers). |
| CAN FD | U_CAN (TCAN334GDR), J_CAN1/J_CAN2, R_TERM + J_TERM, F_CAN_GND | 3.3 V transceiver, normal mode (STB/SHDN internal pull-downs). Connectors: pin 1 CAN_GND, 2 CANL, 3 CANH. CAN_GND runs straight from J_CAN1 to J_CAN2 (the bus ground daisy-chains) and reaches board GND through F_CAN_GND (see Comms ground pins below). |
| UART | J_UART, J_VIO, Q_TX/Q_RX (BSS138) + pull-ups, F_UART_GND | ESP32-C5 pins are not 5 V tolerant, so both directions are level-shifted. J_UART: pin 1 UART_GND (to GND through F_UART_GND), 2 RX, 3 TX. |
| Circuit ID | J_CIRCUIT, R_CIRCUIT_PU | Open = circuit 1, shorted = circuit 2. |
| Indicator | D_PWR_LED + 1 k | On when +3V3 is up (remote switch closed). |

Jumpers: **J_VIO** (silkscreen "UART V") 1-2 = 3.3 V UART, 2-3 = 5 V UART. **J_TERM** (silkscreen "TERM")
fitted = 120 Ω terminator.
**J_CIRCUIT** no jumper = circuit 1, jumper on = circuit 2. The three shunts are in the BOM
(SH_VIO / SH_TERM / SH_CIRCUIT, Würth 60900213421) as BOM-only parts with outline-only footprints.

**Not in the BOM (user-supplied):** the heatsink (recommended above about 15 A continuous) and its electrically insulating thermal
pad (see Layout), M3 mounting hardware, and the upstream battery fuse.

Silkscreen convention: every JST connector has its pin functions printed in line with each pin
(J3 `BAT+`/`SW`/`LED-`/`LED+`, J5/J6 `CANH`/`CANL`/`GND`, J8 `GND`/`RX`/`TX`), not pin numbers. J5 is marked CAN IN and J6
CAN OUT (vertical text beside their pin labels); they are wired in parallel, so the marking is a cabling convention, not a direction the bus
needs. The labels sit over the tracks that run into each pin, which prints legibly over soldermask.

## Remote switch wiring (J3)

| J3 pin | Silkscreen | Net | Plain switch | 3-terminal lit switch (+ / ACC / GND) | Separate-LED-terminal switch |
|---|---|---|---|---|---|
| 1 | `BAT+` | VBAT_IN | one side | + | one contact |
| 2 | `SW` | VSW_RAW | other side | ACC (output) | other contact |
| 3 | `LED-` | SW_LED_K (Q_LED drain) | — | GND | LED − |
| 4 | `LED+` | +5V | — | — | LED + |

- **3-terminal switches** light their LED from the battery, so buy one rated for the pack (12 V for
  lead-acid, 24 V or "12-24 V" for 18-24 V packs). Their LED also sees the full reverse voltage if the
  battery is reversed; that relies on the switch's own protection.
- **Separate-terminal switches**: buy the **5 V or 6 V LED** version. It runs from the board's 5 V, so
  the same switch suits every battery from 12 V to 32 V.
- Battery pins (1-2) are at one end, so a slipped wire can short BAT+ to SW (just turns the board on)
  but never puts the battery on +5V.

## GPIO table (Waveshare ESP32-C5-Zero)

Firmware-side requirements (overcurrent cutoff, regen rule, INA237 setup, antenna select) are in
[docs/firmware-requirements.md](../docs/firmware-requirements.md).

| GPIO | Net | Function | Notes |
|---|---|---|---|
| IO0 | PWR_PGOOD | LM5060 nPGD (open drain) | 10 k pull-up. |
| IO1 | PWR_CUTOFF | Load cutoff | High = load off. 100 k pull-down. |
| IO2 | I2C_SDA | INA237 | 4.7 k pull-up. Strapping pin MTMS (SDIO edge only; harmless). |
| IO3 | I2C_SCL | INA237 | 4.7 k pull-up. Strapping pin MTDI (SDIO edge only; harmless). |
| IO4 | INA_ALERT | INA237 ALERT (open drain): firmware over-current cutoff | 10 k pull-up. |
| IO5 | UART_TX_3V3 | UART TX | Via Q_TX to J_UART.3. |
| IO6 | VBAT_ADC | ADC1 | Battery ÷ 11. |
| IO7 | CIRCUIT_ID | Input | 10 k pull-up. Strapping pin for JTAG source, only read if EFUSE_JTAG_SEL_ENABLE is burnt (default not). |
| IO8 | CAN_TX | TWAI/CAN FD TX | |
| IO9 | CAN_RX | TWAI/CAN FD RX | |
| IO10 | UART_RX_3V3 | UART RX | Via Q_RX from J_UART.2. |
| IO11 | — | U0TXD | Left free for the ROM boot log. |
| IO12 | SW_LED_EN | Lit-switch LED (Q_LED gate) | 10 k pull-up: light on by default; drive low to blink. U0RXD, not a strapping pin (ESP32-C5 datasheet p. 27); input with weak pull-up at reset (p. 20). The J_UART port is unaffected: it uses UART1 on IO5/IO10. |
| IO13/IO14 | — | USB D-/D+ | Module USB-C. |

## Layout

**76 × 58 mm**, 4 layers (F.Cu parts and routing / In1.Cu solid GND / In2.Cu power pours, +3V3 pour
and VSW_CTRL routing / B.Cu heatsink copper, GND and short routes), all parts on the top side.
`scripts/layout_4layer.py` converted the hand-placed 70 × 50 mm 6-layer layout: it moved parts and
silkscreen by region, rebuilt the outline, pours and stitching vias, and deleted the old routing.
Signals were then routed by hand in KiCad; the script refuses to run on anything but the 6-layer
board, so it can't overwrite the routing. GND stitching and the decoupling-cap ground vias come from
`scripts/stitch_gnd.py` (see Pours below). The DRC's `silk_edge_clearance` check is set to ignore because the
J1/J2 XT60 silkscreen overhangs the board edge by design; check any new edge-mounted part by eye.

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │ J1 XT60 │D1│ Q1 │ Q2 │ R13 │ D6 │ D5 │ J2 XT60   power row (y 0-19)        │
 │  in     ├──┴─ gate clamp, LM5060, INA237 ──┤  out                         │
 │ ○ PWR LED, dividers               CIRCUIT ID   ○                         │
 │ J3 switch │ ESP32-C5-Zero-M │ VIO  U5 CAN  TERM   J5 CAN IN              │
 │ buck      │ on sockets,     │ level shift   F1    J6 CAN OUT             │
 │ ○         │ antenna at edge │ F2  J8 UART          ○                     │
 └────────────────────────────────────────────────────────────────────────┘
```

- **XT60 overhang.** Both XT60PW bodies overhang the side edges by about 5 mm; the pins and both
  support pegs stay on the board (the datasheet land pattern fixes only the pins and the pegs 6 mm in
  front of them). This is what lets D_TVS_IN, Q1, Q2, R_SHUNT, D_TVS_OUT and D_FLY fit in one row
  between the connectors (0.2-0.4 mm between courtyards). DRC's silk-to-edge warnings on J1/J2 are
  this overhang.
- **ESP32 on sockets.** U_MCU is the ESP32-C5-Zero-M (headers pre-soldered) in two 1x9 sockets
  (J_MCU_L/J_MCU_R, Sullins PPPC091LFBN-RC, 8.5 mm). The module sits ~11 mm up, so the USB-C plug
  clears everything, low parts sit under the module (pull-ups, cutoff FET, ADC divider), and the
  module can be swapped. The sockets are pinless BOM parts: their pins use U_MCU's holes. They carry KiCad's stock
  1x09 socket 3D model (the module's STEP already includes its own headers), so the 3D view shows the
  full stack. The antenna
  end keeps its all-layer copper and footprint keep-out at the bottom edge.
- **Logo:** `DroidPowerSense:PunderWorks_Logo_10mm` / `_14mm` / `_18mm` are board-only silkscreen
  footprints (no pads, excluded from BOM and placement), generated by `scripts/make_logo_footprint.py`
  from `libraries/logos/PunderWorks-black.png`. Minimum stroke 0.31 / 0.44 / 0.56 mm. Place from the
  footprint library; flip to put it on the back. Regenerate another size with
  `python3 scripts/make_logo_footprint.py PCB/libraries/logos/PunderWorks-black.png <width_mm> <out.kicad_mod>`.
- **Mounting holes:** four M3, at the bottom corners and on the side edges just below the XT60s (the
  top corners are under the connectors).
- **Heatsink area (back, 43 × 16 mm under D_TVS_IN … D_FLY).** The back copper there is the
  VBAT_IN / VSW_OUT / VOUT pours plus GND, under soldermask, tied to the top pours by stitching vias.
  No through-hole tails land in it. A stick-on heatsink is recommended for continuous loads above
  about 15 A (see FET heat below) and must go on with an **electrically insulating** thermal pad or
  tape: bare metal would short the three power nets and bypass the switch.
  The area is marked with corner brackets and a note on B.SilkS.
- **5 V buck (U_BUCK, bottom left)** follows the LMR14030 layout example (datasheet §7.4.1,
  Fig. 7-10 on p. 23). The input caps stand left of U_BUCK with their + pads level with VIN (pin 2)
  and their GND pads up. D_BUCK lies flat above the IC, its cathode over SW (pin 8) and its anode
  over the input caps' ground. L_BUCK stands upright beside D_BUCK's cathode with its output pad up
  next to the output caps, which sit above D_BUCK. All of their ground pads, U_BUCK pin 7 and the
  SS/RT/FB parts share one top-side GND area. That area ties to the plane at the output-cap ground
  (two vias, at C_BUCK_OUT1/2) and through U_BUCK's thermal-pad vias; the input caps
  deliberately have no vias of their own, so the switching current stays on the top-side ground.
  Keep it that way if the buck is re-routed. The feedback divider sits at the FB pin.

**Fab spec: 1.6 mm, 4 layers, 1 oz copper on all layers** (0.245 mm prepreg, 0.95 mm core in the
board file; the fab sets its own stackup). v1 was ordered this way from PCBWay (2026-11-10). 2 oz
outer copper doubled the price, and a droid's average load is under 1 A, with 30 A continuous a rare
ceiling. On the 30 A path, 1 oz against 2 oz outer copper (estimates from copper sheet resistance
and IPC-2221, not measured):

| | 2 oz outer | 1 oz outer |
|---|---|---|
| Power-path copper resistance | 0.31 mΩ | 0.51 mΩ |
| Copper heat at 30 A | 0.27 W | 0.46 W |
| Narrowest section (VSW_OUT) | 1.51 mm² | 0.90 mm² |
| Q1-Q2 link (VSW_MID) | 0.06 mΩ | 0.12 mΩ |

The copper carries 30 A either way: the extra ~0.2 W is small next to the FETs' 5-8 W. What 1 oz
loses is heat spreading around Q1, Q2 and R_SHUNT, which is why the heatsink is recommended for
sustained high current. Order 2 oz outer only if bench step 6 shows the board runs too hot at the
loads it will really see.

Pours (added by `scripts/layout_4layer.py`):
- VBAT_IN, VSW_OUT and VOUT on F.Cu, In2.Cu and B.Cu along the power row (y 44.4-55.6, about 11.2 mm
  tall), priority 3, pads connected solidly; 183 stitching vias (0.8 / 0.4 mm, 1.27 mm grid, kept
  0.4 mm off every pad). The 11.2 mm row was sized so three layers with 2 oz outer copper
  (2 + 1 + 2 oz) matched the 6-layer board's four layers × 8.7 mm. With the 1 oz copper ordered, the
  narrowest cross-sections as routed are VBAT_IN 1.18 mm², VSW_OUT 0.90 mm², VOUT 1.18 mm² (1.96,
  1.5 and 1.96 mm² at 2 oz outer). Each of the Q1/Q2 drain tabs and
  R_SHUNT pads has 5-12 of these vias within 2.5 mm to carry the current between layers.
- VSW_MID (Q1 sources to Q2 sources) is F.Cu only, across the 0.95 mm gap between the two rows of
  source pins; the gap is too narrow for a via. **Nothing may be routed through that gap.** The
  GATE_FET link from Q1's gate (top of its row) to Q2's gate (bottom of its row) goes around the
  outside of Q2's source pins instead, leaving the gap as solid copper about 3.9 mm wide
  (~0.06 mΩ). An earlier route ran the gate track down the gap and left 0.11 mm² for the full load
  current (~270 A/mm² at 30 A); the 2026-11-09 review caught it.
- Ground planes (priority 0) on all 4 layers: In1.Cu is the solid reference plane. J1/J2
  GND pins and the D1/D5/D6 GND pads connect solidly (thermal spokes would choke 30 A); the XT60 GND
  pins need a large iron to hand-solder.
- GND stitching and decoupling vias (0.6 / 0.3 mm, tented) come from `scripts/stitch_gnd.py`: a
  2.5 mm grid wherever a via fits wholly inside the GND fill on F.Cu, In1.Cu and B.Cu (clear of the
  In2 power pours, courtyards, the antenna keep-out, the QR code and the logos), at least two vias on
  every F.Cu GND island, and a via with a short track at each ground pad in its `PAD_VIAS` list
  (C_PROT_VIN, C_INA_VS, the TCAN334G's VCC cap and GND pin, and the buck output caps). Refill the
  zones, run it with KiCad's Python, refill again. It skips spots near existing GND vias, so it is
  safe to rerun after routing changes.
- In2.Cu is the internal signal layer (referenced to the In1.Cu GND plane). It carries the power-row
  pours, a +3V3 pour (priority 1) under the module, CAN and UART (y 61.5 to the bottom edge, x ≥ 76.2),
  and a GND fill elsewhere. VSW_CTRL runs on it as 0.35-0.5 mm tracks (LM5060, dividers, buck input),
  not a pour. Keep In2 tracks short where they cut the +3V3 pour; +3V3 can also run as Power-class
  tracks on F.Cu.

Net classes (Board Setup → Net Classes, assigned by net-name pattern in `DroidPowerSense.kicad_pro`):

| Class | Track | Clearance | Via | Nets |
|---|---|---|---|---|
| HighCurrent | 3.0 mm | 0.2 mm | 0.8 / 0.4 | VBAT_IN, VSW_MID, VSW_OUT, VOUT |
| Power | 0.5 mm | 0.2 mm | 0.6 / 0.3 | GND, VSW_CTRL, VSW_RAW, +5V, +3V3, BUCK_SW, UART_VIO, CAN_GND, UART_GND |
| GateDrive | 0.3 mm | 0.2 mm | 0.6 / 0.3 | GATE_FET, GATE_DRV, REV_BASE |
| CAN | 0.35 mm | 0.2 mm | 0.6 / 0.3 | CANH, CANL, Net-(J7-A) |
| Default | 0.25 mm | 0.2 mm | 0.6 / 0.3 | all other signals |

Stackup 0.3.0 doesn't derive net classes, so these are plain KiCad classes (no `stackup:` prefix)
and the sync leaves them alone. Expected exceptions when routing: the HighCurrent nets' thin
branches (Kelvin sense to U2, VBAT_IN sense to R4 R_SENSE, the VSW_MID spur to the reverse clamp; all carry
mA or less) and neck-downs where Power tracks meet the 0.5 mm-pitch pins of U1 and U2.
0.2 mm clearance is well above what 32 V needs.

`scripts/layout_4layer.py` made this layout from the 70 × 50 mm 6-layer one; the board file is now
the source of truth. `scripts/layout_compact.py` (70 × 50 mm, 6 layers) and `scripts/layout_pcb.py`
(90 × 66 mm, 4 layers) are kept for their helpers and history; their reference designators no longer
match the board.

**Why 4 layers at 76 × 58 mm (2026-11-09).** At 70 × 50 mm the board needed 6 layers: 4 layers
there could not be routed cleanly, because the band under the power row (gate clamp, LM5060,
INA237, dividers) is where every left-to-right signal crosses, and the power row blocks every layer
above it. The 6-layer board used only F.Cu, In2.Cu and B.Cu for signals; In3.Cu (+3V3 plane and a
fourth power pour) and In4.Cu (second GND plane) were planes. Going to 4 layers loses one 1 oz
power layer (made up by an 11.2 mm instead of 8.7 mm power row), the +3V3 plane (now an In2 pour
and tracks) and some heat spreading (partly made up by 26 % more board area). The extra 6 mm of
width spreads the gate-drive cluster and the CAN/UART column; the extra 8 mm of height goes to the
power row (2.5 mm), the routing band below it (3 mm) and the bottom edge (2.5 mm). 76 × 58 is
about 52 % component density, against ~65 % at 70 × 50; going below about 74 × 56 brings back the
routing problem, and above 80 × 60 the board is bigger than it needs to be. The 90 × 66 mm 4-layer
original was larger than needed because its parts were not yet compacted (module on sockets with
parts under it, XT60 overhang).

Status (2026-11-09): routed on 4 layers. DRC (all severities, zones refilled) 0 violations / 0
unconnected; `stackup check` 84 parts / 48 nets, 0/0/0; PCB sync clean. 433 tracks, 312 vias (101
GND). Minimum track width is 0.25 mm and minimum clearance 0.2 mm; the 0.5 mm-pitch U1/U2 pads
have 0.2 mm gaps. 0.2 mm / 0.2 mm is within standard 1 oz rules.

**Fab files** are in [`production/`](production/): Gerbers + job file (1.6 mm) and PTH/NPTH
drills with maps in `production/gerbers/`; the purchasing BOM (`stackup bom`) and the placement file in
`production/bom/`. The placement file lists only assembler-placed parts (69 on the 4-layer board): the BOM's hand-soldered
parts (connectors, module, sockets, loose jumper shunts) are left out to match its DNP column. The
sync marks every `hand=#true` footprint *Exclude from position files* and *Exclude from BOM*, so
`kicad-cli` and the PCBWay plugin leave them out on their own.
Regenerate both after any board change. **Refill and save the pours first:** the exporters plot the
fills stored in the board file, and a script or sync that edits copper without refilling leaves stale
fills that would go to the fab (this happened once; the fix was this refill).

```sh
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli; B=PCB/DroidPowerSense.kicad_pcb
$K pcb drc --refill-zones --save-board --severity-all -o /tmp/drc.rpt $B   # refill, save, and check
$K pcb export gerbers --board-plot-params -o PCB/production/gerbers/ $B
$K pcb export drill --excellon-separate-th --generate-map --map-format gerberx2 -o PCB/production/gerbers/ $B
$K pcb export pos --format csv --units mm --side both -o PCB/production/bom/DroidPowerSense-pos.csv $B
stackup bom PCB/stackup/board.kdl --locked -o PCB/production/bom/DroidPowerSense-bom.csv
```

## Verification

- `scripts/spice/power_switch_sim.py`: switch open (no drain), turn-on across 9-32 V and V_GS(th)
  corners, MCU cutoff, reverse polarity (-12 to -32 V), capacitive inrush (100 µF to 4.7 mF; the
  slow corner stacks the LM5060 start-up limits with ±10 % C_GATE / C_TIMER and VTMRH 1.70 V),
  hot-FET 30 A continuous margin, overcurrent stall vs dead short, and motor regeneration.
  See [`scripts/spice/README.md`](../scripts/spice/README.md).
- `scripts/spice/uart_shifter_sim.py`: bidirectional BSS138 level shifter verification across 3.3 V
  and 5.0 V VIO, threshold corners, and cable capacitances up to 500 pF.
- `scripts/spice/test_soa.py`: unit tests for the Safe Operating Area and moving-window thermal
  integrator library (`scripts/spice/soa.py`). All 10 tests pass.

## Accepted risks and known gaps

- **Upstream battery fuse is required for dead-short protection.** The LM5060 acts as an electronic
  circuit breaker with a 0.34 s typical (0.65 s worst) fault delay, not a current limiter. A dead short (<10 mΩ) directly on
  the output draws >1000 A from low-impedance lithium batteries, which violates FET single-pulse SOA
  before the LM5060 timer elapses. An upstream fast-acting fuse (30-50 A blade or MIDI fuse) on the main
  battery feed is required to clear dead shorts (<2 ms).
- **The remote-switch lead (J3 `BAT+`) relies on the battery fuse.** `BAT+` is tied straight to
  VBAT_IN; a chafed switch lead shorted to chassis draws ~75-100 A at 32 V through 1 m of thin wire.
  The in-line battery fuse clears that, provided the wire outlasts the fuse: by the Onderdonk
  estimate 26 AWG melts at ~52 A in 0.5 s, 22 AWG at ~133 A, hence 22 AWG or heavier and a fuse no
  larger than 40 A. On-board protection was evaluated and set aside (2026-11-08): small 60 V PTCs
  interrupt only 10-40 A (TE/Littelfuse SMD050F: 10 A at 60 V), and an eFuse before the switch is
  always powered (TI TPS2660: 300 µA on, 20 µA off), which breaks the zero-drain requirement. A v2
  could make the switch lead a low-current control signal instead of battery +.
- **Inrush into capacitive loads.** With no C_GATE, charging large capacitor banks at 32 V produces
  peak currents >120 A. C_GATE = 100 nF limits inrush into 4.7 mF at 32 V to 1.9 A (Q1 at 0.72x SOA at
  the fast corner). 10 mF at 32 V exceeds the SOA (1.4-1.5x); a larger C_GATE needs a larger C_TIMER,
  which lengthens the overload delay, so the board is rated for 4.7 mF at 32 V.
- **Overloads between 30 A and the V_DS trip.** The trip sits at ~45 A hot / ~105 A cold. At 12 V a
  104 A overload (battery-limited) never trips and puts Q1 at 1.1x its 1 s SOA; at 32 V a 117 A
  overload trips after 0.65 s worst case with Q1 at 1.05x. No C_TIMER value fixes this without breaking
  start-up (one timer serves both). Firmware cutoff on INA237 ALERT and the upstream fuse are the
  protection; the simulation reports these cases as failures on purpose.
- **Input surges and the 5 V buck.** D_TVS_IN (SMCJ33CA, `datasheets/SMCJ.pdf` p. 3) has V_BR
  36.7-40.6 V and clamps at 53.3 V max at 28.1 A, rated on the 10/1000 µs waveform (Fig. 4); its
  dynamic resistance is ~0.45 Ω, so VBAT_IN passes the LMR14030's 44 V limit once ~7.5-16 A flows in
  it. R_BUCK_IN (≥ 25 µs with C_BUCK_IN after DC-bias loss) covers the events a battery system
  produces: the battery-lead inductance kick when the FETs open under load (~1 µH × 30 A = 0.45 mJ in
  ~3 µs, ~1 V rise on BUCK_VIN) and hot-plug ringing. A full-energy 1 ms surge on the battery lead
  would charge through it; that needs an external source on the lead (a battery can't push current
  into a 33 V-standoff TVS, and regen with the switch off lands on VOUT, not VBAT_IN).
- **Hot-FET overcurrent threshold margin.** At 100 °C junction temperature, R_DS(on) rises 1.55x.
  With R_SENSE = 22 kΩ and minimum I_SENSE (13.6 µA), the LM5060 will false-trip at 30 A continuous.
  Increasing R_SENSE to 33 kΩ raises the hot threshold to ~45 A, safely clearing 30 A continuous.
- **Motor regeneration into cutoff FETs.** When the FETs are ON, motor regen flows safely back into
  the battery pack (VOUT ~32.7 V). If firmware shuts off the FETs or asserts `PWR_CUTOFF` while motors
  are actively generating, current dumps into D_TVS_OUT (SMBJ33CA), exceeding its continuous pulse
  rating. Firmware policy: never assert cutoff while motors are spinning.
- **High-speed UART over long cables.** The BSS138 passive pull-ups pass timing up to 115.2 kbps on
  cables up to 5 m (500 pF) and up to 1 Mbps on cables under 1.5 m (150 pF). For 1 Mbps over long droid
  wiring harnesses, use the onboard TCAN334G CAN FD transceiver instead.

- **Copper temperature at 30 A is calculated, not measured.** Measure the shunt, FETs and the XT60
  pins at 30 A continuous on the first board (bench step 6).
- **Pre-fab review (2026-11-08).** Placement was generated, routing done by hand. Reviewed: footprints
  against the package drawings (Q1/Q2 use KiCad's TDSON-8-1: pin-compatible with TI's DNK land
  pattern, drain pad ~0.2 mm larger), diode and transistor orientation by net, Kelvin sense routing
  (each U_INA sense track leaves from inside its own shunt pad), DRC, and the SPICE suite.
- **Pre-fab review of the 4-layer board (2026-11-09).** Checked: every pad's net against the
  Stackup design (sync check); the LM5060, INA237, LMR14030 (SO-8) and TCAN334 pin numbers against
  their datasheet pin tables; the ESP32-C5-Zero-M header order against the module schematic
  (pin 17 = IO12/U0RXD, 18 = IO11/U0TXD); transistor and diode pins by net; Kelvin sense (unchanged
  from the 6-layer review); copper cross-sections along the 30 A path; decoupling placement and
  ground vias. Fixed from the review: the GATE_FET track that cut VSW_MID (see Pours), the buck
  layout (its top-side ground was split into five islands joined only through In1, and the catch
  diode sat 6-8 mm from the SW pin; now re-placed after TI's layout example, see Layout), ground
  vias at the LM5060, INA237 and TCAN334G decoupling caps, and C_BUCK_OUT2 moved off the board
  edge (it was 0.4 mm from it, parallel, where depaneling can crack an MLCC). Not changed: the
  ESP32 module's own decoupling is on the module, and the board's C_3V3_1 / C_BUCK_OUT3 sit at its
  3V3 and 5V pins.
- **Comms ground pins (2026-11-09).** J_CAN1/J_CAN2/J_UART pin 1 is a ground reference: UART is
  single-ended and needs one whenever the other end isn't on the same battery (a USB adapter, a
  separately powered board), and a CAN ground wire keeps nodes within the TCAN334G's common-mode
  range and gives CANH/CANL a defined return. Each reaches board GND through a Bourns
  MF-MSMF014/60X-2 PTC (F_CAN_GND, F_UART_GND) so it can't become the load's return path: if this
  board's battery-negative XT60 comes off while a cable stays connected, the return current would
  otherwise flow through a 3 A JST contact and thin signal wire. A plain series resistor can't do
  this (10 Ω would dissipate ~100 W at 32 V). The fault current is bounded by the load current
  (firmware INA237 cutoff ~30 A, 30-40 A fuse), inside the PTC's Imax 40 A at Vmax 60 V
  (`datasheets/MF-MSMF.pdf` p. 1). Rejected: MF-MSMF010/014 without the X suffix (not recommended
  for new designs), MF-MSMF010/60X (barely stocked), and the Bel 0ZCJ0010FF2E 1206 (60 V but Imax
  only 10 A, `datasheets/0ZCJ.pdf`). Signal-reference current is about 1 mA (UART pull-ups), so R1max 6 Ω adds ~6 mV.
  The KiCad 1812 fuse footprint doesn't match Bourns' Style 2 land pattern, so the board uses
  `DroidPowerSense:Bourns_MF-MSMF_1812_Style2` (1.68 × 2.95 mm pads, 3.1 mm gap, p. 7). Stock
  2026-11-09: Mouser 3,560, DigiKey 3,613; not at LCSC. The B3B-XH-A(LF)(SN) has no DigiKey listing
  and Mouser is at 0 with stock on order; LCSC has 175k.
- **Reversed power with CAN/UART grounds connected.** A reversed battery with another board's
  ground connected through a comms cable drives current through that ground pin; the PTC trips and
  limits it to tens of mA (tripped dissipation ~0.8 W, `datasheets/MF-MSMF.pdf` p. 1).
- **PTC fault current above Imax.** With no load resistance at all, 32 V across Rmin 0.40 Ω would be
  80 A, above the 40 A Imax. In practice the load sets the current and firmware and the fuse cap it
  near 30-40 A; a PTC pushed past Imax can fail open.
- **Mounting holes have no MPN** (drill only).
- **J_SW has no DigiKey number.** B4B-XH-A(LF)(SN): Mouser 306-B4BXHALFSN (49,815), LCSC C144395
  (636k), checked 2026-11-08. DigiKey lists only a different plating variant (B4B-XH-A).
- **INA237 stock and accuracy.** INA237AIDGSR: LCSC 9,895, Mouser 27, DigiKey 0 (2026-11-08); the
  pin-compatible INA238 (±0.1 % gain) was out of stock everywhere. Offset ±50 µV
  max is ±50 mA on the 1 mΩ shunt, coarser than the INA226's ±10 mA. Firmware uses the INA237
  register map (not the INA226's).
- **Q_LED is a 50 V part on a node that can see the input TVS clamp.** With a 3-terminal switch and
  the light blinked off, a surge clamped by D_TVS_IN (SMCJ33CA, up to ~53 V at full surge current)
  reaches Q_LED's drain through the switch LED and its resistor, which limit the current. Accepted:
  the window is short and the current small. A 60 V FET would remove it, but 2N7002-class parts
  have V_GS(th) up to 2.5 V, too close to a 3.3 V gate drive.
- **J_SW miswiring:** shorting SW (battery, when on) to LED- while Q_LED is on overloads Q_LED (it
  fails; the board otherwise survives). Shorting LED+ to anything grounded trips the buck's
  current limit and resets the MCU until removed.
- **FET heat at high continuous current, in still air.** Each CSD18532Q5B dissipates ~2.3 W typical
  (2.5 mΩ at 25 °C) to ~3.4 W hot at 30 A, plus ~0.9 W in the shunt: about 5.4-7.7 W on a
  76 × 58 mm board. Heat goes with the square of the current. By a still-air rule of thumb (not
  simulated), the rise above ambient is about:

  | Continuous load | FET + shunt heat | Rise above ambient |
  |---|---|---|
  | 1 A (typical average) | ~6-9 mW | negligible |
  | 10 A | ~0.6-0.9 W | ~10 °C |
  | 15 A | ~1.4-1.9 W | ~20-25 °C |
  | 20 A | ~2.4-3.4 W | ~30-40 °C |
  | 30 A | ~5.4-7.7 W | ~65-90 °C |

  The rule of thumb was worked out for 2 oz outer copper; the 1 oz board spreads heat less well and
  runs somewhat hotter. Hence the guidance: **fit the heatsink for continuous loads above about
  15 A** (held for more than a minute or so). Short peaks such as motor starts and stalls are
  absorbed by the copper's and FETs' thermal mass. Measure FET and shunt temperatures on the first
  board with and without a heatsink (bench step 6) and move the 15 A line to match.
- **XT60 bodies overhang the board edge ~5 mm** (pins and pegs on board). Plug forces go into the
  pins and pegs, which is what they are rated for; the front of the plastic body is unsupported.
- **The module stands ~11 mm tall on 18 socket contacts.** In a vibrating droid, add a dab of hot
  glue or a cable tie at the antenna end.
- **ESP32-C5-Zero-M is bought from Waveshare** (SKU 34598); Mouser, DigiKey and LCSC don't list it
  (checked 2026-11-08). The socket height is confirmed: PPPC091LFBN-RC
  (PP polyester / phosphor bronze, P gold flash, C 0.100", 09 positions, 1 row, LFB straight, N no
  mounting) has a .335" [8.50 mm] insulator and 6.0 mm insertion depth, with a Ø1.02 mm recommended
  hole (`datasheets/Sullins-FemaleHeader.pdf`, catalog p. 114-115; the footprint drills 1.0 mm). The
  ~11 mm module height adds the -M module's own header plastic, which Waveshare doesn't dimension.
- **Reference designators shifted** when Q_LED/R_LED_PU were added (Stackup assigns them in KDL
  order): the UART FETs are now Q6/Q7 and the former R25-R29 are R26-R30.

## Bench checklist (first board)

1. Before power: check orientation of Q1/Q2, U_PROT, U_INA, U_BUCK, U_CAN, and every diode band.
2. Current-limited 12 V on J_PWR_IN with J_SW open: input current < 1 µA, VOUT 0 V.
3. Close J_SW: +5V ≈ 4.97 V, +3V3 ≈ 3.3 V, VOUT follows input after the soft start.
3a. Start-up margin: at 32 V into ~4.7 mF on LOAD OUT, scope GATE and TIMER. The gate must reach
   VOUT + 5 V while TIMER is still well under 2.0 V (simulated worst case 0.25 s vs 0.48 s); record
   the TIMER voltage at the end of the ramp.
3b. Buck: at 9 V and 32 V in, with the module running Wi-Fi, scope the SW node (U_BUCK pin 8,
   ground the probe tip at C_BUCK_OUT's ground) for ringing below ground and above VIN, and +5V for
   ripple. Check the module's RSSI against a module on a bench supply.
4. Reverse 12 V on J_PWR_IN (current-limited): no current into VSW_CTRL or VOUT.
5. Drive IO1 high: VOUT drops, MCU stays up.
5a. J3 lit switch: with a 5 V separate-terminal switch on pins 3-4, the light comes on with the board
   and goes off when IO12 is driven low. Repeat with a 3-terminal switch on pins 1-3.
6. Load steps 0.5 A → 30 A: INA237 reading vs. a reference meter; shunt and FET temperatures, with
   and without the heatsink.
6a. Firmware over-current cutoff: set the INA237 limit (e.g. 40 A), apply a current-limited overload
   and confirm PWR_CUTOFF opens the switch within a few ms, well inside the LM5060 fault delay.
7. CAN: exchange FD frames with a known node; 60 Ω across the bus with both ends terminated.
8. UART loopback at the 3.3 V and 5 V J_VIO settings.
9. Comms grounds: continuity from J5.1, J6.1 and J8.1 to GND (a few ohms through the PTCs), and
   J5.1 to J6.1 directly. With J_PWR_IN's negative disconnected and a current-limited load on LOAD
   OUT returning through a CAN cable's ground, F_CAN_GND trips and the current falls to mA.

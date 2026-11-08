# DroidPowerSense

## Design principles

This device is a PCB designed to sense battery power levels from droid build batteries. This could include 24v, 18v, 20v Max, 24v LiPo batteries with higher capacity, power tool batteries, and even lead acid. Additionally, this board provides safety features for users, like built in flyback diodes, high capacity polarized connectors for power passthrough, both serial and CAN support for communication of data, and a MOSFET to fully prevent power leakage while also allowing for low power switches to be used.

Requirements and the decisions behind them are recorded in [PCB/README.md](PCB/README.md). Read it
before changing the hardware, and add to it rather than re-deciding something already settled there.

## Repository layout

- `PCB/` — hardware. `PCB/stackup/` holds the Stackup design, `PCB/datasheets/` the manufacturer
  datasheets (fetched with the `pcb-design` skill's `datasheet.py`), and the KiCad project
  (`DroidPowerSense.*`) lives beside them. `PCB/libraries/` holds the custom footprints
  (ESP32-C5-Zero-M socketed module, socket outline, XT60PW-M/F).
- `ci/` — the Cargo-locked Stackup CLI (`ci/stackup/`) and the PCB sync check (`check_pcb_sync.py`).
- `scripts/spice/` — ngspice verification of the power switch; `scripts/layout_compact.py` — placement
  and pours for the 70 × 50 mm board (do not re-run once the board is hand-routed);
  `scripts/layout_pcb.py` — the earlier 90 × 66 mm generator, kept for its helpers.
- `src/` — firmware (Rust, ESP32-C5). Not started yet.

## Git workflow

**All changes go through pull requests — never push directly to `main`.** History is linear: rebase,
never merge. Land PRs with `gh pr merge --rebase`. The remote is `thePunderWoman`.

Because PRs land by rebase, `git branch -d` and `--merged` won't recognize a landed branch. Confirm
via `git log --oneline` or `gh pr view <branch> --json state`, then `git branch -D <branch>`.

## Hardware design (Stackup)

The electrical design is Stackup KDL — `PCB/stackup/board.kdl` and `PCB/stackup/parts.kdl` — not
KiCad schematics (there are none). Hardware work follows the `pcb-design` skill.

- Check the design with `stackup check PCB/stackup/board.kdl --locked` (CLI 0.2.0; the Cargo-locked
  copy in `ci/stackup/` is the reference version). The parts library is pinned by commit in
  `manifest.kdl`.
- After any change to the KDL, sync `PCB/DroidPowerSense.kicad_pcb` from it with the Stackup KiCad
  plugin (never edit footprint nets by hand) and commit the PCB with the KDL. Footprints record their
  `board.kdl` line, so even reordering lines needs a resync.
- Mounting holes and logos are KiCad `board_only` footprints; the sync leaves them alone.
- Source parts from Mouser and DigiKey first (LCSC numbers are recorded but JLCPCB is not the
  planned assembler). Connectors, headers and the ESP32 module sockets are hand-soldered.
- CI (`.github/workflows/ci.yml`) runs the Stackup check, BOM check and PCB sync check on PCB
  changes only; firmware jobs (ESP32 build + unit tests) run only on firmware changes. The
  only required check on `main` should be `CI Result`; add any new job to its `needs` list.

## Firmware (once it exists)

Rust on the ESP32-C5. Each board reads its circuit ID (IO7 jumper) and tags all telemetry with it.

**Read [docs/firmware-requirements.md](docs/firmware-requirements.md) first.** It lists what the
hardware relies on firmware for (overcurrent cutoff via INA237 ALERT, no cutoff during regen, fault
latch reset), the pin map, INA237 setup (address 0x40, its own register map, SHUNT_CAL), the antenna
select on GPIO26, and the open policy decisions.

**Test coverage**
- All new logic gets unit tests that run on the host (`cargo test`) with no hardware.
- Keep hardware-touching code (TWAI/UART/I2C/ADC wrappers) thin; put framing, scaling and
  protection logic in plain, hardware-agnostic code that is covered on the host.
- Every bug fix gets a regression test that would have caught it.

**Build verification**
- Verify the real ESP32-C5 firmware build locally before pushing. Fix a broken build before
  opening or merging a PR.

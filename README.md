# DroidPowerSense

An inline battery power sensor and protection board for droid builds. It sits between the battery
and the rest of the droid (before the fuses), switches and protects the passthrough power, and
reports battery voltage and current over CAN FD and UART.

- 9-32 V batteries (12 V lead-acid, 18 V / 20 V Max tool packs, 24 V LiPo / LiFePO4)
- < 1 A to 30 A continuous / 60 A peak, XT60 in and out
- Zero drain while the remote low-power switch is off (back-to-back MOSFETs under an LM5060)
- Reverse-polarity, TVS, flyback, over/under-voltage and short-circuit protection
- INA226 current/voltage monitor on a 1 mΩ shunt
- Waveshare ESP32-C5-Zero (CAN FD, firmware in Rust), CAN FD + level-shifted UART
- Circuit ID jumper for droids with two circuits (one board each)

Hardware design, requirements and decisions: [PCB/README.md](PCB/README.md).
Firmware (`src/`) is not started yet.

# 3D models

| File | Part | Source | Placement in the footprint |
|---|---|---|---|
| `ESP32-C5-Zero.step` | Waveshare ESP32-C5-Zero | Waveshare | see `Waveshare_ESP32-C5-Zero_Castellated.kicad_mod` |
| `AMASS_XT60PW-M.step` | Amass XT60PW-M (J_PWR_IN) | LCSC/EasyEDA C98732 | offset (3.6, 7.1, 0) mm, rotate z 90° |
| `AMASS_XT60PW-F.step` | Amass XT60PW-F (J_PWR_OUT) | LCSC/EasyEDA C428722 | offset (-3.6, 6.8, 0) mm |

KiCad's footprints for the XT60PW parts reference `Connector_AMASS.3dshapes/AMASS_XT60PW-*` STEP files
that the KiCad 3D library doesn't ship, so the XT60PW models come from LCSC's EasyEDA library:

```sh
uvx easyeda2kicad --3d --lcsc_id=C98732  --output /tmp/xt60/C98732
uvx easyeda2kicad --3d --lcsc_id=C428722 --output /tmp/xt60/C428722
```

The offsets were derived from the pin positions in the STEP files and checked against the drilled
holes in a KiCad render. Polarity was checked too: the chamfered housing corners (XT60 negative) sit
on the GND pin of both connectors.

# 3D Printing Workspace

## Overview

This directory contains STL files, gcode, slicer configs, and printer configuration for a Creality CR-10 V3 running Klipper.

## Directory Layout

- `orca-cli/` — OrcaSlicer CLI config files (filament profiles, etc.)
- `gcode/` — Generated gcode files
- `calibration/` — Calibration prints
- `klipper/` — Klipper-related configs
- `models/` — Organized model files
- `printer.cfg` — Klipper printer configuration

## Printer

- **CR-10 V3** at `192.168.1.5`, Moonraker API on `:7125`
- Klipper firmware

## Common Workflows

### Slice an STL
```bash
# PLA
flatpak run --command=orca-slicer com.bambulab.OrcaSlicer --slice 1 --orient 1 \
  --load-filaments orca-cli/filament-pla.json \
  --outputdir . model.stl

# PETG
flatpak run --command=orca-slicer com.bambulab.OrcaSlicer --slice 1 --orient 1 \
  --load-filaments orca-cli/filament-petg.json \
  --outputdir . model.stl
```

### Upload and print
```bash
# Upload gcode to printer
curl -F "file=@plate_1.gcode" http://192.168.1.5:7125/server/files/upload

# Start print
curl -X POST http://192.168.1.5:7125/printer/print/start?filename=plate_1.gcode

# Check status
curl http://192.168.1.5:7125/printer/objects/query?print_stats
```

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CAP Generator converts TAS Baseball/Softball season statistics XML files into binary .CAP files. The .CAP format is a fixed-size binary format used by sports statistics software.

## Running the Tool

```bash
# Run from a directory containing XML stat files
python cap_generator.py

# Or run directly
./cap_generator.py
```

The tool processes all `.xml` files in the current working directory and outputs corresponding `.cap` files.

## Binary Format Specification

### Header (292 bytes)
- `[0:20]` Team name (ASCII, space-padded)
- `[21:29]` Team ID (ASCII, space-padded)
- `[30:38]` Date (MM/DD/YY format)
- `[40:292]` Constant tail (copied from reference format)

### Player Record (216 bytes each)
- `[0:8]` Team ID (ASCII, space-padded)
- `[9:21]` Player name (12 chars, from `player@name` attribute, truncated)
- `[23]` Player type flag: `0x03` = hitter, `0x01` = pitcher
- `[24:216]` 96 little-endian uint16 stat values

## Key Implementation Details

- Player names always come from the `player@name` XML attribute (not `checkname`), preserving exact capitalization
- Players are identified as pitchers if `pos="P"` or if they have a `<pitching>` child element
- Pair fields (e.g., `w2outs="7,28"`) are parsed as `made,opp` and stored in separate u16 slots
- All numeric values are clamped to uint16 range (0-65535)
- The `MAP_U16` dictionary defines which XML stat maps to which u16 index in the record

## Reference Files

The `reference/` directory contains:
- `OM.XML` - Example input XML file (TAS Baseball format)
- `OM.CAP` - Expected output for validation

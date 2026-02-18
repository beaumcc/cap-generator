# CAP Generator

Converts TAS Baseball/Softball season statistics XML files into binary `.CAP` files.

## Requirements

- Python 3.10 or later

No external dependencies required (uses only Python standard library).

## Usage

### Run from command line

```bash
# Process all XML files in the current directory
python cap_generator.py

# Process specific files
python cap_generator.py team1.xml team2.xml

# Process all XML files in a directory
python cap_generator.py /path/to/stats/
```

### Drag-and-drop (Windows/Mac)

- **Windows:** Drag one or more `.xml` files (or folders containing XML files) onto `cap_generator.exe`.
- **Mac:** Drag files onto the `.app` bundle (see "Creating a Mac .app Bundle" below).

### Running directly on Mac/Linux

```bash
# Make the script executable (first time only)
chmod +x cap_generator.py

# Run directly
./cap_generator.py
```

## Creating Executables

### Windows Executable (PyInstaller)

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

2. Build the executable:
   ```bash
   pyinstaller --onefile --name cap_generator cap_generator.py
   ```

3. The executable will be created in the `dist/` folder.

### Mac Executable (PyInstaller)

1. Install PyInstaller:
   ```bash
   pip install pyinstaller
   ```

2. Build the executable:
   ```bash
   pyinstaller --onefile --name cap_generator cap_generator.py
   ```

3. The executable will be created in the `dist/` folder.

### Mac .app Bundle (py2app)

Creates a native Mac application with drag-and-drop support:

1. Install py2app:
   ```bash
   pip install py2app
   ```

2. Generate setup.py:
   ```bash
   py2applet --make-setup cap_generator.py
   ```

3. Build the .app bundle:
   ```bash
   python setup.py py2app
   ```

4. The `.app` bundle will be created in the `dist/` folder. You can drag XML files directly onto the app icon.


## Binary Format

### Header (292 bytes)

| Offset | Size | Description |
|--------|------|-------------|
| 0-19 | 20 | Team name (ASCII, space-padded) |
| 21-28 | 8 | Team ID (ASCII, space-padded) |
| 30-37 | 8 | Date (MM/DD/YY format) |
| 40-41 | 2 | Player count (uint16 LE) |
| 42-43 | 2 | Record size (uint16 LE) |
| 44-45 | 2 | Games played (uint16 LE) |
| 76-99 | 24 | Opponent pseudo-record header |
| 100-291 | 192 | Opponent stats (96 x uint16 LE) |

### Player Record (216 bytes)

| Offset | Size | Description |
|--------|------|-------------|
| 0-7 | 8 | Team ID (ASCII, space-padded) |
| 8 | 1 | Null byte |
| 9-20 | 12 | Player name (ASCII, space-padded) |
| 21 | 1 | Null byte |
| 22 | 1 | 0x20 |
| 23 | 1 | Type flag (0x02) |
| 24-215 | 192 | Stats (96 x uint16 little-endian) |

## Stat Mapping Reference

Stats are stored as 96 consecutive uint16 (2-byte) little-endian values starting at byte offset 24 in each player record.

**Byte offset formula:** `24 + (index × 2)`

### Core Batting Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 0 | 24 | `gp` | Games Played |
| 1 | 26 | `gs` | Games Started |
| 2 | 28 | `ab` | At Bats |
| 3 | 30 | `r` | Runs |
| 4 | 32 | `h` | Hits |
| 5 | 34 | `rbi` | Runs Batted In |
| 6 | 36 | `double` | Doubles |
| 7 | 38 | `triple` | Triples |
| 8 | 40 | `hr` | Home Runs |
| 9 | 42 | `bb` | Walks |
| 10 | 44 | `sb` | Stolen Bases |
| 11 | 46 | `cs` | Caught Stealing |
| 12 | 48 | `hbp` | Hit By Pitch |
| 13 | 50 | `sh` | Sacrifice Hits |
| 14 | 52 | `sf` | Sacrifice Flies |
| 16 | 56 | `so` | Strikeouts |
| 17 | 58 | `kl` | Strikeouts Looking |
| 18 | 60 | `gdp` | Ground into Double Play |
| 19 | 62 | `hitdp` | Hit into Double Play |

### Fielding Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 27 | 78 | `po` | Putouts |
| 28 | 80 | `a` | Assists |
| 29 | 82 | `e` | Errors |
| 30 | 84 | `pb` | Passed Balls |
| 31 | 86 | `indp` | Induced Double Plays |
| 33 | 90 | `csb` | Caught Stealing By |
| 34 | 92 | `sba` | Stolen Base Attempts |

### Hitting Situational Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 22 | 68 | `rcherr` | Reached on Error |
| 23 | 70 | `rchfc` | Reached on Fielder's Choice |
| 24 | 72 | `ground` | Ground Balls |
| 25 | 74 | `fly` | Fly Balls |
| 79 | 182 | `adv` | Advances |
| 80 | 184 | `lob` | Left on Base |
| 85 | 194 | `rbi-2out` | RBI with 2 Outs |

### Hitting Situational Pair Stats

Pair stats are parsed from XML format `"made,opp"`.

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 67 | 158 | `w2outs` (opp) | With 2 Outs - Opportunities |
| 68 | 160 | `w2outs` (made) | With 2 Outs - Made |
| 69 | 162 | `wrunners` (opp) | With Runners - Opportunities |
| 70 | 164 | `wrunners` (made) | With Runners - Made |
| 71 | 166 | `wrbiops` (opp) | RBI Opportunities - Total |
| 72 | 168 | `wrbiops` (made) | RBI Opportunities - Made |
| 73 | 170 | `vsleft` (opp) | Vs Left - Opportunities |
| 74 | 172 | `vsleft` (made) | Vs Left - Made |
| 75 | 174 | `rbi3rd` (opp) | RBI from 3rd - Opportunities |
| 76 | 176 | `rbi3rd` (made) | RBI from 3rd - Made |
| 77 | 178 | `advops` (opp) | Advance Opportunities - Total |
| 78 | 180 | `advops` (made) | Advance Opportunities - Made |
| 81 | 186 | `leadoff` (opp) | Leadoff - Opportunities |
| 82 | 188 | `leadoff` (made) | Leadoff - Made |
| 83 | 190 | `pinchhit` (opp) | Pinch Hit - Opportunities |
| 84 | 192 | `pinchhit` (made) | Pinch Hit - Made |
| 92 | 208 | `wloaded` (opp) | Bases Loaded - Opportunities |
| 93 | 210 | `wloaded` (made) | Bases Loaded - Made |

### Pitching Stats (Pitchers & Opponent Record)

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 26 | 76 | `sh` | Sacrifice Hits (opponent duplicate) |
| 36 | 96 | `appear` | Appearances |
| 37 | 98 | `win` | Wins |
| 38 | 100 | `loss` | Losses |
| 42 | 108 | `bf` | Batters Faced |
| 43 | 110 | `ab` | At Bats Against |
| 45 | 114 | `loss` | Losses (duplicate) |
| 47 | 118 | `ip` | Innings Pitched (as outs: IP × 3) |
| 48 | 120 | `h` | Hits Allowed |
| 49 | 122 | `r` | Runs Allowed |
| 50 | 124 | `er` | Earned Runs |
| 51 | 126 | `bb` | Walks |
| 52 | 128 | `k` | Strikeouts |
| 53 | 130 | `kl` | Strikeouts Looking |
| 54 | 132 | `gdp` | Ground into DP Induced |
| 56 | 136 | `hbp` | Hit Batters |
| 57 | 138 | `wp` | Wild Pitches (× 256, high byte) |
| 58 | 140 | `double` | Doubles Allowed |
| 60 | 144 | `hr` | Home Runs Allowed |

### Pitching Situational Stats

| Index | Byte Offset | XML Attribute | Description |
|-------|-------------|---------------|-------------|
| 61 | 146 | `ground` | Ground Balls |
| 62 | 148 | `fly` | Fly Balls |
| 86 | 196 | `leadoff` (opp) | Leadoff - Opportunities |
| 87 | 198 | `leadoff` (made) | Leadoff - Made |
| 88 | 200 | `wrunners` (opp) | With Runners - Opportunities |
| 89 | 202 | `wrunners` (made) | With Runners - Made |
| 90 | 204 | `vsleft` (opp) | Vs Left - Opportunities |
| 91 | 206 | `vsleft` (made) | Vs Left - Made |
| 94 | 212 | `w2outs` (opp) | With 2 Outs - Opportunities |
| 95 | 214 | `w2outs` (made) | With 2 Outs - Made |

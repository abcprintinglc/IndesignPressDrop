# PressDrop Bleed Fixer (v2.0 v0.1)

A small standalone tool (Python) that can generate:

- **Press-ready PDFs** (works without InDesign)
- **Optional INDDs** (only on machines with InDesign)

Inputs supported: **PDF, PNG, JPG/JPEG**

## What it does
- Creates a new PDF whose **page size includes bleed** (MediaBox = trim + bleed)
- Sets:
  - **TrimBox** = trim area
  - **BleedBox** = full page (includes bleed)
  - **CropBox** = full page
- Places your input content using one of the fit modes
- Optional crop marks

## Fit modes (v0.1)
- `fit_trim_proportional` — fit inside **Trim** proportionally (no cropping)
- `fit_bleed_proportional` — fit inside **Bleed** proportionally (no cropping)
- `fill_bleed_proportional` — **cover Bleed** proportionally (center-crop by default)
- `stretch_trim` — distort to fill **Trim**
- `stretch_bleed` — distort to fill **Bleed**

> Tip: `fill_bleed_proportional` is usually what you want when an incoming PDF has **no bleed**.

## Quick start (Windows)
1) Install Python 3.10+ (recommended)
   - If your PC has Python 3.14, this project requires Pillow 12+ (included in requirements). If you see pip trying to *build Pillow from source*, install Python 3.12 or 3.13 x64 instead.

2) Open a terminal in this folder
3) Install requirements:

```bat
python -m pip install -r requirements.txt
```

4) Run the GUI:

```bat
python src\pressdrop_gui.py
```

Or run the CLI:

```bat
python src\pressdrop_cli.py --input "C:\in\file.pdf" --pages 1-3 --size 4x6in --bleed 0.125 --fit fill_bleed_proportional --out "C:\out" --crop_marks
```

## Presets
Edit `presets/presets.json` to add your shop sizes. The GUI reads this file.

## Image output for Generative Fill (optional)
The desktop GUI can export **PNG images** from the generated press PDF so you can open them directly in InDesign for Generative Fill.

The desktop GUI includes:
- **InDesign App Path** (optional) — set this if auto-open does not work on your machine.
- **Open output PDF in InDesign (no script)** — opens the PDF in InDesign.
- **Export PNGs for Generative Fill** — rasterizes the press PDF into PNGs at the chosen DPI.
- **Export DPI (PNG)** — default 1200 DPI.
- **Save Default** — stores your current GUI settings to `presets/defaults.json` for next launch.
- **Save Preset** — saves trim/bleed/fit/anchor settings into `presets/presets.json`.

> Note: PNG export from PDFs requires Ghostscript or Poppler on your system.

## Build an EXE (optional)
If you want a portable EXE:

```bat
python -m pip install pyinstaller
pyinstaller --onefile --noconsole src\pressdrop_gui.py --name PressDropBleedFixer
```

The EXE will be created in `dist\PressDropBleedFixer.exe`.

## Notes / limitations (v2.0)
- Multi-page PDFs are supported.
- `fill_bleed_proportional` for PDFs uses **source clipping** (center crop) to preserve vectors.
- Auto-rotate is available in the job schema but not turned on by default (keep false for now).
- This is a v2.0 to validate workflow & UI. Next upgrades would include batch queues, more anchors, per-side bleed, mirror/smear bleed extensions, and a “watch folder” for the InDesign station.


## v2.0: Edge-Extend Bleed
- New option: **Bleed Generator** = none / mirror / smear.
- When enabled, the tool places content into trim, then fills bleed margins by extending edge slices.
  - Mirror: flips edge strips outward
  - Smear: stretches edge strips outward
- Works for PDFs (keeps vectors) and raster images.

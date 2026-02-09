#!/usr/bin/env python
"""Command-line runner.

Examples:
  python src/pressdrop_cli.py --input in.pdf --pages 1-2 --size 4x6in --bleed 0.125 --fit fill_bleed_proportional --out out
  python src/pressdrop_cli.py --input in.png --size 3.5x2in --bleed 0.125 --fit fit_trim_proportional --crop_marks

Fit modes:
  fit_trim_proportional
  fit_bleed_proportional
  fill_bleed_proportional   (proportional cover via centered crop)
  stretch_trim
  stretch_bleed

Anchors:
  center, top, bottom, left, right,
  top_left, top_right, bottom_left, bottom_right
"""

import argparse
import os

from core import build_press_pdf, make_job


def main():
    p = argparse.ArgumentParser(description="PressDrop Bleed Fixer (v2.0)")
    p.add_argument("--input", required=True, help="Input file: pdf/png/jpg/jpeg")
    p.add_argument("--pages", default="1", help="PDF pages, 1-based. Examples: 1, 1-4, 1,3,5-7. Default=1")
    p.add_argument("--pdf_box", default="auto", choices=["auto", "trim", "crop", "media"], help="Which PDF box to use as source")
    p.add_argument("--size", required=True, help="Trim size, e.g. 4x6in, 3.5x2in, 101.6x152.4mm")
    p.add_argument("--bleed", default="0.125", help="Bleed in same unit as size. Either single value or 't,r,b,l'")
    p.add_argument("--bleed_generator", default="none", choices=["none","mirror","smear"], help="Fill bleed by extending edges (mirror/smear). For PDFs, stays vector.")
    p.add_argument("--fit", default="fill_bleed_proportional", choices=[
        "fit_trim_proportional",
        "fit_bleed_proportional",
        "fill_bleed_proportional",
        "stretch_trim",
        "stretch_bleed",
    ])
    p.add_argument("--anchor", default="center", choices=[
        "center","top","bottom","left","right",
        "top_left","top_right","bottom_left","bottom_right"
    ])
    p.add_argument("--crop_marks", action="store_true", help="Draw crop marks")
    p.add_argument("--out", required=True, help="Output folder")
    p.add_argument("--basename", default=None, help="Base filename (default = input filename)")
    p.add_argument("--emit_job", action="store_true", help="Also write a job.json next to output PDF (for InDesign JSX)")

    args = p.parse_args()

    os.makedirs(args.out, exist_ok=True)
    job = make_job(
        input_path=args.input,
        pages_spec=args.pages,
        pdf_box=args.pdf_box,
        trim_size_spec=args.size,
        bleed_spec=args.bleed,
        fit_mode=args.fit,
        anchor=args.anchor,
        bleed_generator=args.bleed_generator,
        crop_marks=args.crop_marks,
        out_dir=args.out,
        basename=args.basename,
        emit_job=args.emit_job,
    )

    outputs = build_press_pdf(job)
    for path in outputs:
        print(f"Wrote: {path}")

    if args.emit_job:
        print(f"Wrote job: {job['output']['job_json_path']}")
        print("Run InDesign JSX: indesign/PressDrop_Import.job.jsx (from Scripts panel).")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Minimal Tkinter GUI for the prototype.

This GUI is intentionally simple: pick a file, pick a preset or custom trim/bleed, choose fit mode, run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# Rasterize PDFs to PNGs when needed
from PIL import Image

from core import MM_PER_INCH, POINTS_PER_INCH, build_press_pdf, load_presets, make_job, parse_bleed, parse_size


def resource_path(rel: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, rel))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PressDrop Bleed Fixer (v2.2 Pro)")
        self.geometry("900x700")
        self.minsize(820, 620)

        self.presets = load_presets(resource_path("../presets/presets.json"))  # dict name->settings
        self.presets_path = resource_path("../presets/presets.json")
        self.defaults_path = resource_path("../presets/defaults.json")
        self.input_path = tk.StringVar(value="")
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop"))
        self.size = tk.StringVar(value="4x6in")
        self.bleed = tk.StringVar(value="0.125")
        self.pages = tk.StringVar(value="all")
        self.fit_mode = tk.StringVar(value="fit_trim_proportional")
        self.anchor = tk.StringVar(value="center")
        self.bleed_generator = tk.StringVar(value="none")
        self.crop_marks = tk.BooleanVar(value=True)
        self.make_indd = tk.BooleanVar(value=False)
        self.launch_indesign = tk.BooleanVar(value=False)
        self.open_output_in_indesign = tk.BooleanVar(value=False)
        self.export_png = tk.BooleanVar(value=False)
        self.export_dpi = tk.StringVar(value="1200")
        self.panel_split = tk.StringVar(value="none")
        self.panel_margin = tk.StringVar(value="0.125")
        self.indesign_app = tk.StringVar(value=os.environ.get("INDESIGN_APP", ""))

        self._load_defaults()
        self._build()

    
    def _build(self):
        # Match the "blue + cyan bars" style mockup.
        BG = "#1f5f96"
        BAR = "#1aa7e1"
        BTN = "#1aa7e1"
        TXT = "#ffffff"

        self.configure(bg=BG)

        pad_y = 10
        pad_x = 14

        scroll_container = tk.Frame(self, bg=BG)
        scroll_container.pack(fill="both", expand=True, padx=pad_x, pady=pad_y)

        canvas = tk.Canvas(scroll_container, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        container = tk.Frame(canvas, bg=BG)
        canvas_window = canvas.create_window((0, 0), window=container, anchor="nw")

        def make_label(row, text):
            lbl = tk.Label(
                container,
                text=text,
                bg=BAR,
                fg=TXT,
                padx=10,
                pady=6,
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            )
            lbl.grid(row=row, column=0, sticky="w", pady=6)
            return lbl

        def make_entry(row, var):
            ent = tk.Entry(
                container,
                textvariable=var,
                bg=BAR,
                fg=TXT,
                insertbackground=TXT,
                relief="flat",
                font=("Segoe UI", 10),
                width=60,
            )
            ent.grid(row=row, column=1, sticky="ew", padx=(14, 10), pady=6)
            return ent

        def make_button(row, text, cmd):
            btn = tk.Button(
                container,
                text=text,
                command=cmd,
                bg=BTN,
                fg=TXT,
                activebackground=BTN,
                activeforeground=TXT,
                relief="flat",
                padx=14,
                pady=6,
                font=("Segoe UI", 10, "bold"),
            )
            btn.grid(row=row, column=2, sticky="e", pady=6)
            return btn

        row = 0
        make_label(row, "Input (PDF/PNG/JPG):")
        make_entry(row, self.input_path)
        make_button(row, "Browse", self.pick_input)

        row += 1
        make_label(row, "Output Folder:")
        make_entry(row, self.output_dir)
        make_button(row, "Browse", self.pick_output)

        row += 1
        make_label(row, "Preset:")
        preset_names = sorted(list(self.presets.keys()))
        self.preset_combo = ttk.Combobox(container, values=["(custom)"] + preset_names, state="readonly")
        self.preset_combo.current(0)
        self.preset_combo.grid(row=row, column=1, sticky="ew", padx=(14, 10), pady=6)
        self.preset_combo.bind("<<ComboboxSelected>>", self.apply_preset)

        row += 1
        make_label(row, "Preset Actions:")
        preset_actions = tk.Frame(container, bg=BG)
        preset_actions.grid(row=row, column=1, sticky="w", padx=(14, 10), pady=6)
        tk.Button(
            preset_actions,
            text="Save Preset",
            command=self.save_preset,
            bg=BTN,
            fg=TXT,
            activebackground=BTN,
            activeforeground=TXT,
            relief="flat",
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            preset_actions,
            text="Save Default",
            command=self.save_default,
            bg=BTN,
            fg=TXT,
            activebackground=BTN,
            activeforeground=TXT,
            relief="flat",
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        row += 1
        make_label(row, "Trim Size WxH: (e.g., 4x6in, 101.6x152.4mm):")
        make_entry(row, self.size)

        row += 1
        make_label(row, "Bleed (single value or t,r,b,l) in same unit:")
        make_entry(row, self.bleed)

        row += 1
        make_label(row, "Pages (PDF) e.g., 1 or 1-4 or 1,3,5, or all:")
        make_entry(row, self.pages)

        row += 1
        make_label(row, "Fit mode:")
        fit_values = [
            "fit_trim_proportional",
            "fit_bleed_proportional",
            "fill_bleed_proportional",
            "stretch_trim",
            "stretch_bleed",
        ]
        ttk.Combobox(container, values=fit_values, textvariable=self.fit_mode, state="readonly").grid(
            row=row, column=1, sticky="ew", padx=(14, 10), pady=6
        )

        row += 1
        make_label(row, "Anchor (used for Fill/Cropping):")
        anchor_values = ["center", "top", "bottom", "left", "right", "top_left", "top_right", "bottom_left", "bottom_right"]
        ttk.Combobox(container, values=anchor_values, textvariable=self.anchor, state="readonly").grid(
            row=row, column=1, sticky="ew", padx=(14, 10), pady=6
        )

        row += 1
        make_label(row, "Bleed Generator (none/mirror/smear):")
        ttk.Combobox(container, values=["none", "mirror", "smear"], textvariable=self.bleed_generator, state="readonly").grid(
            row=row, column=1, sticky="ew", padx=(14, 10), pady=6
        )

        row += 1
        # checkboxes
        cb1 = tk.Checkbutton(
            container,
            text="Add crop marks",
            variable=self.crop_marks,
            bg=BG,
            fg=TXT,
            activebackground=BG,
            activeforeground=TXT,
            selectcolor=BG,
            font=("Segoe UI", 10),
        )
        cb1.grid(row=row, column=1, sticky="w", padx=(14, 10), pady=(10, 2))

        row += 1
        make_label(row, "InDesign App Path (optional):")
        make_entry(row, self.indesign_app)

        row += 1
        cb_output = tk.Checkbutton(
            container,
            text="Open output PDF in InDesign (no script)",
            variable=self.open_output_in_indesign,
            bg=BG,
            fg=TXT,
            activebackground=BG,
            activeforeground=TXT,
            selectcolor=BG,
            font=("Segoe UI", 10),
        )
        cb_output.grid(row=row, column=1, sticky="w", padx=(14, 10), pady=(2, 4))

        row += 1
        cb_png = tk.Checkbutton(
            container,
            text="Export PNGs for Generative Fill",
            variable=self.export_png,
            bg=BG,
            fg=TXT,
            activebackground=BG,
            activeforeground=TXT,
            selectcolor=BG,
            font=("Segoe UI", 10),
        )
        cb_png.grid(row=row, column=1, sticky="w", padx=(14, 10), pady=(2, 4))

        row += 1
        make_label(row, "Export DPI (PNG):")
        make_entry(row, self.export_dpi)

        row += 1
        make_label(row, "Panel Split (optional):")
        ttk.Combobox(container, values=["none", "trifold", "quadfold"], textvariable=self.panel_split, state="readonly").grid(
            row=row, column=1, sticky="ew", padx=(14, 10), pady=6
        )

        row += 1
        make_label(row, "Panel Text Margin (in):")
        make_entry(row, self.panel_margin)

        row += 1
        run_btn = tk.Button(
            container,
            text="Run",
            command=self.run,
            bg=BTN,
            fg=TXT,
            activebackground=BTN,
            activeforeground=TXT,
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        run_btn.grid(row=row, column=2, sticky="e", pady=10)

        container.columnconfigure(1, weight=1)

        def _on_frame_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        container.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

    def _export_pdf_to_png(self, pdf_path: str, dpi: int) -> list[str]:
        outputs: list[str] = []
        try:
            with Image.open(pdf_path) as img:
                total_frames = getattr(img, "n_frames", 1)
                for idx in range(total_frames):
                    img.seek(idx)
                    rgb = img.convert("RGB")
                    suffix = f"_page_{idx + 1:03d}" if total_frames > 1 else ""
                    out_path = os.path.splitext(pdf_path)[0] + f"{suffix}.png"
                    rgb.save(out_path, dpi=(dpi, dpi))
                    outputs.append(out_path)
        except Exception as exc:
            raise RuntimeError(
                "Could not export PNGs. PDF rasterization requires Ghostscript or Poppler."
            ) from exc
        return outputs

    def _to_inches(self, value: float, unit: str) -> float:
        unit = (unit or "in").lower().strip()
        if unit in ("in", "inch", "inches"):
            return float(value)
        if unit in ("mm", "millimeter", "millimeters"):
            return float(value) / MM_PER_INCH
        if unit in ("pt", "pts", "point", "points"):
            return float(value) / POINTS_PER_INCH
        raise ValueError(f"Unsupported unit: {unit}")

    def _split_panels(
        self,
        png_path: str,
        panel_count: int,
        trim_w_in: float,
        trim_h_in: float,
        bleed: dict,
        margin_in: float,
    ) -> tuple[list[str], list[str]]:
        panel_outputs: list[str] = []
        safe_outputs: list[str] = []
        bleed_left = float(bleed["left"])
        bleed_right = float(bleed["right"])
        bleed_top = float(bleed["top"])
        bleed_bottom = float(bleed["bottom"])
        total_w_in = trim_w_in + bleed_left + bleed_right
        total_h_in = trim_h_in + bleed_top + bleed_bottom
        panel_trim_w = trim_w_in / panel_count

        with Image.open(png_path) as img:
            img = img.convert("RGB")
            px_per_in_x = img.width / total_w_in
            px_per_in_y = img.height / total_h_in
            for idx in range(panel_count):
                x0_in = bleed_left + panel_trim_w * idx
                x1_in = bleed_left + panel_trim_w * (idx + 1)
                if idx == 0:
                    x0_in = 0
                if idx == panel_count - 1:
                    x1_in = total_w_in
                y0_in = 0
                y1_in = total_h_in

                crop = img.crop(
                    (
                        int(round(x0_in * px_per_in_x)),
                        int(round(y0_in * px_per_in_y)),
                        int(round(x1_in * px_per_in_x)),
                        int(round(y1_in * px_per_in_y)),
                    )
                )
                panel_path = os.path.splitext(png_path)[0] + f"_panel_{idx + 1}.png"
                crop.save(panel_path)
                panel_outputs.append(panel_path)

                if margin_in > 0:
                    safe_x0 = bleed_left + panel_trim_w * idx + margin_in
                    safe_x1 = bleed_left + panel_trim_w * (idx + 1) - margin_in
                    safe_y0 = bleed_top + margin_in
                    safe_y1 = bleed_top + trim_h_in - margin_in
                    safe = img.crop(
                        (
                            int(round(safe_x0 * px_per_in_x)),
                            int(round(safe_y0 * px_per_in_y)),
                            int(round(safe_x1 * px_per_in_x)),
                            int(round(safe_y1 * px_per_in_y)),
                        )
                    )
                    safe_path = os.path.splitext(png_path)[0] + f"_panel_{idx + 1}_safe.png"
                    safe.save(safe_path)
                    safe_outputs.append(safe_path)
        return panel_outputs, safe_outputs

    def _launch_indesign_file(self, file_path: str) -> None:
        app_path = self.indesign_app.get().strip()
        try:
            if app_path:
                subprocess.Popen([app_path, file_path])
                return
            if sys.platform.startswith("darwin"):
                subprocess.Popen(["open", "-a", "Adobe InDesign", file_path])
                return
            if os.name == "nt":
                path_candidate = shutil.which("InDesign.exe")
                if path_candidate:
                    subprocess.Popen([path_candidate, file_path])
                    return
                common_paths = [
                    r"C:\\Program Files\\Adobe\\Adobe InDesign 2026\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign 2025\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign 2024\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign 2023\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign 2022\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign 2021\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign 2020\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CC 2019\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CC 2018\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CC 2017\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CC 2016\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CC 2015\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CC 2014\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CC\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CS6\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CS5\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CS4\\InDesign.exe",
                    r"C:\\Program Files\\Adobe\\Adobe InDesign CS3\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign 2024\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign 2023\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign 2022\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign 2021\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign 2020\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CC 2019\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CC 2018\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CC 2017\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CC 2016\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CC 2015\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CC 2014\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CC\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CS6\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CS5\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CS4\\InDesign.exe",
                    r"C:\\Program Files (x86)\\Adobe\\Adobe InDesign CS3\\InDesign.exe",
                ]
                for candidate in common_paths:
                    if os.path.exists(candidate):
                        subprocess.Popen([candidate, file_path])
                        return
                raise RuntimeError("InDesign executable not found. Set the InDesign App Path.")
            subprocess.Popen(["xdg-open", file_path])
        except Exception as exc:
            raise RuntimeError(
                "Could not open the output in InDesign. Provide the InDesign App Path or open manually."
            ) from exc

    def _load_defaults(self) -> None:
        if not os.path.exists(self.defaults_path):
            return
        try:
            with open(self.defaults_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self._apply_settings(data, include_input=False)

    def _apply_settings(self, data: dict, include_input: bool = True) -> None:
        if include_input and "input_path" in data:
            self.input_path.set(data["input_path"])
        if "output_dir" in data:
            self.output_dir.set(data["output_dir"])
        if "size" in data:
            self.size.set(data["size"])
        if "bleed" in data:
            self.bleed.set(str(data["bleed"]))
        if "pages" in data:
            self.pages.set(data["pages"])
        if "fit_mode" in data:
            self.fit_mode.set(data["fit_mode"])
        if "anchor" in data:
            self.anchor.set(data["anchor"])
        if "bleed_generator" in data:
            self.bleed_generator.set(data["bleed_generator"])
        if "crop_marks" in data:
            self.crop_marks.set(bool(data["crop_marks"]))
        if "make_indd" in data:
            self.make_indd.set(bool(data["make_indd"]))
        if "launch_indesign" in data:
            self.launch_indesign.set(bool(data["launch_indesign"]))
        if "open_output_in_indesign" in data:
            self.open_output_in_indesign.set(bool(data["open_output_in_indesign"]))
        if "export_png" in data:
            self.export_png.set(bool(data["export_png"]))
        if "export_dpi" in data:
            self.export_dpi.set(str(data["export_dpi"]))
        if "panel_split" in data:
            self.panel_split.set(str(data["panel_split"]))
        if "panel_margin" in data:
            self.panel_margin.set(str(data["panel_margin"]))
        if "indesign_app" in data:
            self.indesign_app.set(data["indesign_app"])

    def _collect_defaults(self) -> dict:
        return {
            "output_dir": self.output_dir.get().strip(),
            "size": self.size.get().strip(),
            "bleed": self.bleed.get().strip(),
            "pages": self.pages.get().strip(),
            "fit_mode": self.fit_mode.get().strip(),
            "anchor": self.anchor.get().strip(),
            "bleed_generator": self.bleed_generator.get().strip(),
            "crop_marks": bool(self.crop_marks.get()),
            "make_indd": bool(self.make_indd.get()),
            "launch_indesign": bool(self.launch_indesign.get()),
            "open_output_in_indesign": bool(self.open_output_in_indesign.get()),
            "export_png": bool(self.export_png.get()),
            "export_dpi": self.export_dpi.get().strip(),
            "panel_split": self.panel_split.get().strip(),
            "panel_margin": self.panel_margin.get().strip(),
            "indesign_app": self.indesign_app.get().strip(),
        }

    def save_default(self) -> None:
        data = self._collect_defaults()
        try:
            os.makedirs(os.path.dirname(self.defaults_path), exist_ok=True)
            with open(self.defaults_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Defaults Saved", f"Defaults saved to:\n{self.defaults_path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save defaults:\n{exc}")

    def save_preset(self) -> None:
        name = simpledialog.askstring("Save Preset", "Preset name:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        preset = {
            "trim": self.size.get().strip(),
            "bleed": self.bleed.get().strip(),
            "fit": self.fit_mode.get().strip(),
            "anchor": self.anchor.get().strip(),
            "bleed_generator": self.bleed_generator.get().strip(),
            "crop_marks": bool(self.crop_marks.get()),
        }
        try:
            with open(self.presets_path, "r", encoding="utf-8") as f:
                presets = json.load(f)
        except Exception:
            presets = {}
        presets[name] = preset
        try:
            with open(self.presets_path, "w", encoding="utf-8") as f:
                json.dump(presets, f, indent=2)
            self.presets = presets
            self.preset_combo["values"] = ["(custom)"] + sorted(self.presets.keys())
            messagebox.showinfo("Preset Saved", f"Preset saved:\n{name}")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save preset:\n{exc}")

    def pick_input(self):
        path = filedialog.askopenfilename(
            title="Select input file",
            filetypes=[
                ("Supported", "*.pdf *.png *.jpg *.jpeg"),
                ("PDF", "*.pdf"),
                ("Images", "*.png *.jpg *.jpeg"),
                ("All", "*.*"),
            ],
        )
        if path:
            self.input_path.set(path)

    def pick_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self.output_dir.set(d)

    def apply_preset(self, _evt=None):
        name = self.preset_combo.get()
        if name == "(custom)":
            return
        p = self.presets.get(name)
        if not p:
            return
        if "trim" in p:
            self.size.set(p["trim"])
        if "bleed" in p:
            self.bleed.set(str(p["bleed"]))
        if "fit" in p:
            self.fit_mode.set(p["fit"])
        if "anchor" in p:
            self.anchor.set(p["anchor"])
        if "bleed_generator" in p:
            self.bleed_generator.set(p["bleed_generator"])
        if "crop_marks" in p:
            self.crop_marks.set(bool(p["crop_marks"]))

    def run(self):
        inp = self.input_path.get().strip()
        outdir = self.output_dir.get().strip()
        if not inp or not os.path.exists(inp):
            messagebox.showerror("Error", "Please select a valid input file.")
            return
        if not outdir or not os.path.isdir(outdir):
            messagebox.showerror("Error", "Please select a valid output folder.")
            return

        base = os.path.splitext(os.path.basename(inp))[0] + "_PressDrop"

        try:
            # 1. Create the job structure (BUT don't write JSON yet: emit_job=False)
            job = make_job(
                input_path=inp,
                pages_spec=self.pages.get().strip() or "1",
                pdf_box="auto",
                trim_size_spec=self.size.get().strip(),
                bleed_spec=self.bleed.get().strip(),
                fit_mode=self.fit_mode.get().strip(),
                anchor=self.anchor.get().strip(),
                bleed_generator=self.bleed_generator.get().strip(),
                crop_marks=bool(self.crop_marks.get()),
                out_dir=outdir,
                basename=base,
                emit_job=False,  # <--- CHANGED: Wait until file is built
            )

            # 2. Build the PDF (This generates the file with the mirror/bleed applied)
            outputs = build_press_pdf(job)
            
            msg = "Created:\n" + "\n".join(outputs)
            
            png_outputs: list[str] = []
            if self.export_png.get():
                dpi_value = int(self.export_dpi.get().strip() or "1200")
                png_outputs = self._export_pdf_to_png(outputs[0], dpi_value)
                msg += "\n\nPNGs:\n" + "\n".join(png_outputs)
                split_mode = self.panel_split.get().strip().lower()
                if split_mode in ("trifold", "quadfold"):
                    trim_w, trim_h, unit = parse_size(self.size.get().strip())
                    bleed_vals = parse_bleed(self.bleed.get().strip(), unit)
                    trim_w_in = self._to_inches(trim_w, unit)
                    trim_h_in = self._to_inches(trim_h, unit)
                    margin_in = float(self.panel_margin.get().strip() or "0")
                    panel_count = 3 if split_mode == "trifold" else 4
                    for png_path in png_outputs:
                        panels, safe_panels = self._split_panels(
                            png_path,
                            panel_count,
                            trim_w_in,
                            trim_h_in,
                            {
                                "left": self._to_inches(bleed_vals["left"], unit),
                                "right": self._to_inches(bleed_vals["right"], unit),
                                "top": self._to_inches(bleed_vals["top"], unit),
                                "bottom": self._to_inches(bleed_vals["bottom"], unit),
                            },
                            margin_in,
                        )
                        msg += "\n\nPanels:\n" + "\n".join(panels)
                        if safe_panels:
                            msg += "\n\nSafe Areas:\n" + "\n".join(safe_panels)

            if self.open_output_in_indesign.get():
                to_open = png_outputs[0] if png_outputs else outputs[0]
                self._launch_indesign_file(to_open)
                msg += f"\n\nOpening in InDesign:\n{to_open}"

            messagebox.showinfo("Done", msg)
            
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    App().mainloop()

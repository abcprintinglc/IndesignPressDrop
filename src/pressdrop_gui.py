#!/usr/bin/env python
"""Minimal Tkinter GUI for the prototype.

This GUI is intentionally simple: pick a file, pick a preset or custom trim/bleed, choose fit mode, run.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Import write_job_json so we can save the ticket AFTER generating the file
from core import build_press_pdf, load_presets, make_job, write_job_json


def resource_path(rel: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, rel))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PressDrop Bleed Fixer (v2.2 Pro)")
        self.geometry("880x540")

        self.presets = load_presets(resource_path("../presets/presets.json"))  # dict name->settings
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

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=pad_x, pady=pad_y)

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
        cb2 = tk.Checkbutton(
            container,
            text="Also create an INDD job ticket (finish via InDesign JSX)",
            variable=self.make_indd,
            bg=BG,
            fg=TXT,
            activebackground=BG,
            activeforeground=TXT,
            selectcolor=BG,
            font=("Segoe UI", 10),
        )
        cb2.grid(row=row, column=1, sticky="w", padx=(14, 10), pady=(2, 10))

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
            
            # 3. NOW create the JSON pointing to the *Processed* file
            if self.make_indd.get():
                if outputs:
                    # Point the InDesign JSON to the NEW file (outputs[0])
                    # This ensures InDesign places the file WITH the bleed/mirror, 
                    # not the original.
                    job["inputs"][0]["path"] = outputs[0]
                    
                    # Update page count (Generated PDF is usually 1 page per file in this tool)
                    job["inputs"][0]["pages"] = "1" 
                    
                job_json_path = os.path.join(outdir, f"{base}.job.json")
                job["output"]["job_json_path"] = job_json_path
                
                # Use the imported helper to write it
                write_job_json(job, job_json_path)

                msg += f"\n\nJob ticket:\n{job_json_path}"
                msg += "\n\n--> Now run the script in InDesign!"

            messagebox.showinfo("Done", msg)
            
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    App().mainloop()
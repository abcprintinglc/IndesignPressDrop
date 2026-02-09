#!/usr/bin/env python
"""Minimal Tkinter GUI for the prototype.

This GUI is intentionally simple: pick a file, pick a preset or custom trim/bleed, choose fit mode, run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# Import write_job_json so we can save the ticket AFTER generating the file
from core import build_press_pdf, load_presets, make_job, write_job_json


def resource_path(rel: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, rel))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PressDrop Bleed Fixer (v2.2 Pro)")
        self.geometry("880x620")

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
        self.auto_generative_fill = tk.BooleanVar(value=False)
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
        make_label(row, "InDesign App Path (optional):")
        make_entry(row, self.indesign_app)

        row += 1
        cb3 = tk.Checkbutton(
            container,
            text="Launch InDesign + run job script",
            variable=self.launch_indesign,
            bg=BG,
            fg=TXT,
            activebackground=BG,
            activeforeground=TXT,
            selectcolor=BG,
            font=("Segoe UI", 10),
        )
        cb3.grid(row=row, column=1, sticky="w", padx=(14, 10), pady=(2, 4))

        row += 1
        cb4 = tk.Checkbutton(
            container,
            text="Auto-trigger Generative Fill (if available)",
            variable=self.auto_generative_fill,
            bg=BG,
            fg=TXT,
            activebackground=BG,
            activeforeground=TXT,
            selectcolor=BG,
            font=("Segoe UI", 10),
        )
        cb4.grid(row=row, column=1, sticky="w", padx=(14, 10), pady=(2, 10))

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

    def _write_indesign_launcher(self, job_json_path: str) -> str:
        script_src = resource_path("../indesign/PressDropBleedFixer.jsx")
        launcher_dir = os.path.dirname(job_json_path)
        launcher_path = os.path.join(launcher_dir, "PressDropBleedFixer_Run.jsx")
        with open(launcher_path, "w", encoding="utf-8") as f:
            f.write('var PRESSDROP_JOB_JSON_PATH = "' + job_json_path.replace("\\", "\\\\") + '";\n')
            f.write("var PRESSDROP_AUTO_GENERATIVE_FILL = " + ("true" if self.auto_generative_fill.get() else "false") + ";\n")
            f.write('#include "' + script_src.replace("\\", "\\\\") + '"\n')
        return launcher_path

    def _launch_indesign_script(self, script_path: str) -> None:
        app_path = self.indesign_app.get().strip()
        try:
            if app_path:
                subprocess.Popen([app_path, "-script", script_path])
                return
            if sys.platform.startswith("darwin"):
                subprocess.Popen(["open", "-a", "Adobe InDesign", script_path])
                return
            if os.name == "nt":
                os.startfile(script_path)  # type: ignore[attr-defined]
                return
            subprocess.Popen(["xdg-open", script_path])
        except Exception as exc:
            raise RuntimeError(
                "Could not launch InDesign. Provide the InDesign App Path or run the JSX script manually."
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
        if "auto_generative_fill" in data:
            self.auto_generative_fill.set(bool(data["auto_generative_fill"]))
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
            "auto_generative_fill": bool(self.auto_generative_fill.get()),
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
            should_emit_job = bool(self.make_indd.get() or self.launch_indesign.get())
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
                auto_generative_fill=bool(self.auto_generative_fill.get()),
                emit_job=False,  # <--- CHANGED: Wait until file is built
            )

            # 2. Build the PDF (This generates the file with the mirror/bleed applied)
            outputs = build_press_pdf(job)
            
            msg = "Created:\n" + "\n".join(outputs)
            
            # 3. NOW create the JSON pointing to the *Processed* file
            if should_emit_job:
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

                if self.launch_indesign.get():
                    launcher_path = self._write_indesign_launcher(job_json_path)
                    self._launch_indesign_script(launcher_path)
                    msg += "\n\nLaunching InDesign..."

            messagebox.showinfo("Done", msg)
            
        except Exception as e:
            messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    App().mainloop()

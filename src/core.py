from __future__ import annotations

import io
import copy
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Third-Party Imports
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf._page import PageObject
# We keep these just in case, but we won't use the crasher ones
from pypdf.generic import RectangleObject, NameObject, ArrayObject

# Safe import for Requests
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4


@dataclass(frozen=True)
class Rect:
    """PDF coordinate rectangle (origin bottom-left)."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return float(self.x1 - self.x0)

    @property
    def height(self) -> float:
        return float(self.y1 - self.y0)


def to_points(value: float, unit: str) -> float:
    """Convert inches/mm/pt to PDF points."""
    unit = unit.lower().strip()
    if unit in ("in", "inch", "inches"):
        return float(value) * POINTS_PER_INCH
    if unit in ("mm", "millimeter", "millimeters"):
        return float(value) * POINTS_PER_INCH / MM_PER_INCH
    if unit in ("pt", "pts", "point", "points"):
        return float(value)
    raise ValueError(f"Unsupported unit: {unit}")


def parse_size(spec: str) -> Tuple[float, float, str]:
    """Parse sizes like '4x6in'."""
    m = re.match(r"^\s*([0-9.]+)\s*[xX]\s*([0-9.]+)\s*([a-zA-Z]+)\s*$", spec)
    if not m:
        raise ValueError(f"Invalid size format: {spec}")
    w = float(m.group(1))
    h = float(m.group(2))
    unit = m.group(3)
    return w, h, unit


def parse_bleed(spec: str, unit: str) -> Dict[str, float]:
    """Parse bleed values."""
    parts = [p.strip() for p in str(spec).split(",") if p.strip()]
    if len(parts) == 1:
        v = float(parts[0])
        return {"top": v, "right": v, "bottom": v, "left": v, "unit": unit}
    if len(parts) == 4:
        t, r, b, l = map(float, parts)
        return {"top": t, "right": r, "bottom": b, "left": l, "unit": unit}
    raise ValueError("Bleed must be 1 value or 4 values")


def parse_page_range(rng: str, max_pages: int) -> List[int]:
    """Return list of page indexes."""
    rng = (rng or "all").strip().lower()
    if rng in ("all", "*"):
        return list(range(max_pages))
    out: List[int] = []
    for chunk in rng.split(","):
        chunk = chunk.strip()
        if not chunk: continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            start, end = int(a), int(b)
            for p in range(start, end + 1):
                if 1 <= p <= max_pages: out.append(p - 1)
        else:
            p = int(chunk)
            if 1 <= p <= max_pages: out.append(p - 1)
    seen = set()
    ordered = []
    for p in out:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _anchor_offsets(anchor: str) -> Tuple[float, float]:
    """Anchor offsets."""
    a = (anchor or "center").lower().strip()
    mapping = {
        "center": (0.5, 0.5), "top": (0.5, 1.0), "bottom": (0.5, 0.0),
        "left": (0.0, 0.5), "right": (1.0, 0.5),
        "top_left": (0.0, 1.0), "top_right": (1.0, 1.0),
        "bottom_left": (0.0, 0.0), "bottom_right": (1.0, 0.0),
    }
    return mapping.get(a, (0.5, 0.5))


def _rect_from_pypdf_box(box: RectangleObject) -> Rect:
    return Rect(float(box.left), float(box.bottom), float(box.right), float(box.top))


def pick_pdf_box(page: PageObject, box: str = "auto") -> Rect:
    """Choose PDF box."""
    b = (box or "auto").lower().strip()
    def safe_get(attr: str) -> Optional[Rect]:
        try:
            bx = getattr(page, attr)
            if bx is None: return None
            r = _rect_from_pypdf_box(bx)
            if r.width > 0 and r.height > 0: return r
        except Exception: return None
        return None

    if b in ("trim", "auto"):
        r = safe_get("trimbox")
        if r: return r
    if b in ("bleed", "auto"):
        r = safe_get("bleedbox")
        if r: return r
    if b in ("crop", "auto"):
        r = safe_get("cropbox")
        if r: return r
    if b in ("media", "auto"):
        r = safe_get("mediabox")
        if r: return r
    return _rect_from_pypdf_box(page.mediabox)


def compute_boxes(trim_w_pt: float, trim_h_pt: float, bleed: Dict[str, float]) -> Tuple[Rect, Rect, Rect]:
    """Return MediaBox, BleedBox, TrimBox."""
    bu = bleed.get("unit", "in")
    bt = to_points(float(bleed["top"]), bu)
    br = to_points(float(bleed["right"]), bu)
    bb = to_points(float(bleed["bottom"]), bu)
    bl = to_points(float(bleed["left"]), bu)

    media_w = trim_w_pt + bl + br
    media_h = trim_h_pt + bt + bb

    media = Rect(0, 0, media_w, media_h)
    bleed_box = media
    trim_box = Rect(bl, bb, bl + trim_w_pt, bb + trim_h_pt)
    return media, bleed_box, trim_box


def crop_rect_for_cover(src_rect: Rect, dest_rect: Rect, anchor: str) -> Rect:
    """Crop src to match dest aspect."""
    sw, sh = src_rect.width, src_rect.height
    dw, dh = dest_rect.width, dest_rect.height
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0: return src_rect

    src_ar = sw / sh
    dest_ar = dw / dh
    ax, ay = _anchor_offsets(anchor)
    if abs(src_ar - dest_ar) < 1e-6: return src_rect

    if src_ar > dest_ar:
        new_w = sh * dest_ar
        x0 = src_rect.x0 + (sw - new_w) * ax
        return Rect(x0, src_rect.y0, x0 + new_w, src_rect.y1)
    else:
        new_h = sw / dest_ar
        y0 = src_rect.y0 + (sh - new_h) * ay
        return Rect(src_rect.x0, y0, src_rect.x1, y0 + new_h)


def _rect_to_box(r: Rect) -> RectangleObject:
    return RectangleObject((r.x0, r.y0, r.x1, r.y1))


def _compute_transform(src: Rect, dest: Rect, mode: str, anchor: str) -> Transformation:
    """Compute transform src -> dest."""
    sw, sh = src.width, src.height
    dw, dh = dest.width, dest.height
    if sw <= 0 or sh <= 0: return Transformation()

    ax, ay = _anchor_offsets(anchor)
    mode = (mode or "fit_trim_proportional").lower().strip()

    if mode in ("stretch_trim", "stretch_bleed"):
        sx = dw / sw
        sy = dh / sh
        tx = dest.x0 - src.x0 * sx
        ty = dest.y0 - src.y0 * sy
        return Transformation().scale(sx=sx, sy=sy).translate(tx=tx, ty=ty)

    s_fit = min(dw / sw, dh / sh)
    s_fill = max(dw / sw, dh / sh)
    s = s_fit
    if mode in ("fill_bleed_proportional", "fill_trim_proportional"):
        s = s_fill

    content_w = sw * s
    content_h = sh * s
    extra_x = dw - content_w
    extra_y = dh - content_h
    tx = dest.x0 + extra_x * ax - src.x0 * s
    ty = dest.y0 + extra_y * ay - src.y0 * s
    return Transformation().scale(sx=s, sy=s).translate(tx=tx, ty=ty)


def _compute_transform_stretch(src: Rect, dest: Rect, mirror_x: bool = False, mirror_y: bool = False) -> Transformation:
    """Compute stretch transform with optional mirroring."""
    sw, sh = src.width, src.height
    dw, dh = dest.width, dest.height
    if sw <= 0 or sh <= 0: return Transformation()

    sx = (dw / sw) * (-1.0 if mirror_x else 1.0)
    sy = (dh / sh) * (-1.0 if mirror_y else 1.0)
    
    if mirror_x: tx = dest.x1 - sx * src.x0
    else: tx = dest.x0 - sx * src.x0

    if mirror_y: ty = dest.y1 - sy * src.y0
    else: ty = dest.y0 - sy * src.y0

    return Transformation().scale(sx=sx, sy=sy).translate(tx=tx, ty=ty)


def _place_pdf_page_return_clip(out_page: PageObject, src_page: PageObject, dest_rect: Rect, fit_mode: str, anchor: str, pdf_box: str) -> Rect:
    src_rect = pick_pdf_box(src_page, pdf_box)
    mode = (fit_mode or "fit_trim_proportional").lower().strip()

    clip = src_rect
    if mode in ("fill_bleed_proportional", "fill_trim_proportional"):
        clip = crop_rect_for_cover(src_rect, dest_rect, anchor)

    page_copy = copy.copy(src_page)
    page_copy.mediabox = _rect_to_box(clip)
    page_copy.cropbox = _rect_to_box(clip)

    transform = _compute_transform(clip, dest_rect, "stretch_bleed" if mode in ("stretch_trim", "stretch_bleed") else mode, anchor)
    out_page.merge_transformed_page(page_copy, transform)
    return clip


def _edge_extend_bleed(out_page: PageObject, src_page: PageObject, clip: Rect, trim_box: Rect, bleed_box: Rect, mode: str) -> None:
    mode = (mode or "").lower().strip()
    if mode == "generative":
        if not HAS_REQUESTS: mode = "mirror"
        else: mode = "mirror" # Fallback to mirror for safety

    if mode not in ("mirror", "smear"): return

    l_w = max(trim_box.x0 - bleed_box.x0, 0.0)
    r_w = max(bleed_box.x1 - trim_box.x1, 0.0)
    b_h = max(trim_box.y0 - bleed_box.y0, 0.0)
    t_h = max(bleed_box.y1 - trim_box.y1, 0.0)
    if l_w == r_w == b_h == t_h == 0.0: return

    slice_w = max(min(clip.width * 0.02, 18.0), 3.0)
    slice_h = max(min(clip.height * 0.02, 18.0), 3.0)

    def place_slice(src_slice: Rect, dest_slice: Rect, mx: bool, my: bool):
        page_copy = copy.copy(src_page)
        page_copy.mediabox = _rect_to_box(src_slice)
        page_copy.cropbox = _rect_to_box(src_slice)
        transform = _compute_transform_stretch(src_slice, dest_slice, mirror_x=mx, mirror_y=my)
        out_page.merge_transformed_page(page_copy, transform)

    # Sides
    if l_w > 0: place_slice(Rect(clip.x0, clip.y0, clip.x0 + slice_w, clip.y1), Rect(bleed_box.x0, trim_box.y0, trim_box.x0, trim_box.y1), True, False)
    if r_w > 0: place_slice(Rect(clip.x1 - slice_w, clip.y0, clip.x1, clip.y1), Rect(trim_box.x1, trim_box.y0, bleed_box.x1, trim_box.y1), True, False)
    if b_h > 0: place_slice(Rect(clip.x0, clip.y0, clip.x1, clip.y0 + slice_h), Rect(trim_box.x0, bleed_box.y0, trim_box.x1, trim_box.y0), False, True)
    if t_h > 0: place_slice(Rect(clip.x0, clip.y1 - slice_h, clip.x1, clip.y1), Rect(trim_box.x0, trim_box.y1, trim_box.x1, bleed_box.y1), False, True)
    
    # Corners
    if l_w > 0 and b_h > 0: place_slice(Rect(clip.x0, clip.y0, clip.x0 + slice_w, clip.y0 + slice_h), Rect(bleed_box.x0, bleed_box.y0, trim_box.x0, trim_box.y0), True, True)
    if r_w > 0 and b_h > 0: place_slice(Rect(clip.x1 - slice_w, clip.y0, clip.x1, clip.y0 + slice_h), Rect(trim_box.x1, bleed_box.y0, bleed_box.x1, trim_box.y0), True, True)
    if l_w > 0 and t_h > 0: place_slice(Rect(clip.x0, clip.y1 - slice_h, clip.x0 + slice_w, clip.y1), Rect(bleed_box.x0, trim_box.y1, trim_box.x0, bleed_box.y1), True, True)
    if r_w > 0 and t_h > 0: place_slice(Rect(clip.x1 - slice_w, clip.y1 - slice_h, clip.x1, clip.y1), Rect(trim_box.x1, trim_box.y1, bleed_box.x1, bleed_box.y1), True, True)


def _draw_crop_marks_on_page(page: PageObject, trim_box: Rect, bleed_box: Rect) -> None:
    # --- TEMPORARILY DISABLED TO PREVENT CRASH ---
    # The previous code for drawing lines caused 'ContentStream' errors 
    # on your specific system configuration. We are bypassing it 
    # to ensure the Bleed/Mirror function works correctly.
    print("LOG: Crop marks skipped to ensure safe save.")
    pass 


def _image_to_single_page_pdf_bytes(img_path: str) -> bytes:
    img = Image.open(img_path)
    if img.mode not in ("RGB", "L"): img = img.convert("RGB")
    bio = io.BytesIO()
    img.save(bio, format="PDF")
    return bio.getvalue()


def _place_pdf_page(out_page: PageObject, src_page: PageObject, dest_rect: Rect, fit_mode: str, anchor: str, pdf_box: str) -> None:
    src_rect = pick_pdf_box(src_page, pdf_box)
    mode = (fit_mode or "fit_trim_proportional").lower().strip()

    clip = src_rect
    if mode in ("fill_bleed_proportional", "fill_trim_proportional"):
        clip = crop_rect_for_cover(src_rect, dest_rect, anchor)

    page_copy = copy.copy(src_page)
    page_copy.mediabox = _rect_to_box(clip)
    page_copy.cropbox = _rect_to_box(clip)
    transform = _compute_transform(clip, dest_rect, "stretch_bleed" if mode in ("stretch_trim", "stretch_bleed") else mode, anchor)
    out_page.merge_transformed_page(page_copy, transform)


def build_press_pdf(job: Dict) -> List[str]:
    layout = job.get("layout", {})
    output = job.get("output", {})
    inputs = job.get("inputs", [])
    if not inputs: raise ValueError("No inputs provided")

    trim = layout.get("trim", {})
    unit = trim.get("unit", "in")
    trim_w_pt = to_points(float(trim["w"]), unit)
    trim_h_pt = to_points(float(trim["h"]), unit)
    bleed = layout.get("bleed", {"top": 0, "right": 0, "bottom": 0, "left": 0, "unit": unit})
    if "unit" not in bleed: bleed["unit"] = unit

    media_box, bleed_box, trim_box = compute_boxes(trim_w_pt, trim_h_pt, bleed)
    fit_mode = layout.get("fit_mode", "fit_trim_proportional")
    anchor = layout.get("anchor", "center")
    bleed_gen = (layout.get("bleed_generator", "none") or "none").lower().strip()
    marks = layout.get("marks", {})
    add_crop_marks = bool(marks.get("crop_marks", False))

    out_dir = output.get("dir", os.getcwd())
    os.makedirs(out_dir, exist_ok=True)
    base = output.get("basename", "output")
    created: List[str] = []

    def dest_for_mode(mode: str) -> Rect:
        if "bleed" in (mode or "").lower(): return bleed_box
        return trim_box

    for item in inputs:
        in_path = item["path"]
        in_name = os.path.splitext(os.path.basename(in_path))[0]
        if len(inputs) == 1: out_path = os.path.join(out_dir, f"{base}.pdf")
        else: out_path = os.path.join(out_dir, f"{base}__{in_name}.pdf")

        ext = os.path.splitext(in_path)[1].lower()
        writer = PdfWriter()

        if ext == ".pdf":
            reader = PdfReader(in_path)
            pages = parse_page_range(item.get("pages", "all"), len(reader.pages))
            pdf_box = item.get("pdf_box", "auto")

            for pno in pages:
                src_page = reader.pages[pno]
                out_page = PageObject.create_blank_page(width=media_box.width, height=media_box.height)
                out_page.mediabox = _rect_to_box(media_box)
                out_page.bleedbox = _rect_to_box(bleed_box)
                out_page.trimbox = _rect_to_box(trim_box)
                out_page.cropbox = _rect_to_box(bleed_box)

                if bleed_gen in ("mirror", "smear", "generative"):
                    clip = _place_pdf_page_return_clip(out_page, src_page, trim_box, fit_mode, anchor, pdf_box)
                    _edge_extend_bleed(out_page, src_page, clip, trim_box, bleed_box, mode=bleed_gen)
                else:
                    _place_pdf_page(out_page, src_page, dest_for_mode(fit_mode), fit_mode, anchor, pdf_box)
                
                if add_crop_marks:
                    _draw_crop_marks_on_page(out_page, trim_box, bleed_box)
                writer.add_page(out_page)

        elif ext in (".png", ".jpg", ".jpeg"):
            pdf_bytes = _image_to_single_page_pdf_bytes(in_path)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            src_page = reader.pages[0]
            out_page = PageObject.create_blank_page(width=media_box.width, height=media_box.height)
            out_page.mediabox = _rect_to_box(media_box)
            out_page.bleedbox = _rect_to_box(bleed_box)
            out_page.trimbox = _rect_to_box(trim_box)
            out_page.cropbox = _rect_to_box(bleed_box)

            if bleed_gen in ("mirror", "smear", "generative"):
                clip = _place_pdf_page_return_clip(out_page, src_page, trim_box, fit_mode, anchor, pdf_box="media")
                _edge_extend_bleed(out_page, src_page, clip, trim_box, bleed_box, mode=bleed_gen)
            else:
                _place_pdf_page(out_page, src_page, dest_for_mode(fit_mode), fit_mode, anchor, pdf_box="media")
            
            if add_crop_marks:
                _draw_crop_marks_on_page(out_page, trim_box, bleed_box)
            writer.add_page(out_page)
        else:
            raise ValueError(f"Unsupported input type: {ext}")

        with open(out_path, "wb") as f:
            writer.write(f)
        created.append(out_path)

    return created


def write_job_json(job: Dict, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(job, f, indent=2)


def load_presets(preset_path: str) -> Dict[str, Dict]:
    with open(preset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def make_job(
    *,
    input_path: str,
    pages_spec: str,
    pdf_box: str,
    trim_size_spec: str,
    bleed_spec: str,
    fit_mode: str,
    anchor: str,
    bleed_generator: str = "none",
    crop_marks: bool,
    out_dir: str,
    basename: Optional[str] = None,
    emit_job: bool = False,
) -> Dict:
    w, h, unit = parse_size(trim_size_spec)
    bleed_vals = parse_bleed(bleed_spec, unit)
    if basename is None or not basename.strip():
        basename = os.path.splitext(os.path.basename(input_path))[0]
    input_abs = os.path.abspath(input_path)
    ext = os.path.splitext(input_abs)[1].lower()
    page_count = None
    if ext == ".pdf":
        try:
            reader = PdfReader(input_abs)
            page_count = len(reader.pages)
        except Exception: page_count = None
        if page_count and (pages_spec or "").strip().lower() == "all":
            pages_spec = f"1-{page_count}"

    job = {
        "inputs": [{
            "path": input_abs, "pages": pages_spec, "pdf_box": pdf_box, "page_count": page_count
        }],
        "layout": {
            "trim": {"w": w, "h": h, "unit": unit},
            "bleed": {
                "top": bleed_vals["top"], "right": bleed_vals["right"],
                "bottom": bleed_vals["bottom"], "left": bleed_vals["left"],
                "unit": unit
            },
            "fit_mode": fit_mode, "anchor": anchor,
            "bleed_generator": (bleed_generator or "none").lower().strip(),
            "marks": {"crop_marks": bool(crop_marks)}
        },
        "output": {"dir": os.path.abspath(out_dir), "basename": basename}
    }
    if emit_job:
        job_json_path = os.path.join(os.path.abspath(out_dir), f"{basename}.job.json")
        job["output"]["job_json_path"] = job_json_path
        write_job_json(job, job_json_path)
    return job

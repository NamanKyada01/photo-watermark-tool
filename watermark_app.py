import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

# ── Constants ─────────────────────────────────────────────────────────────────
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
POSITIONS        = ["Bottom Right", "Bottom Left", "Top Right", "Top Left", "Center"]

# Preview canvas dimensions (DSLR ratios: 3:2 landscape, 2:3 portrait)
PREV_LAND_W, PREV_LAND_H = 238, 158
PREV_PORT_W, PREV_PORT_H = 108, 162

DEFAULT_SETTINGS = {
    "watermark_text": "© My Photos",
    "position":       "Bottom Right",
    "color":          "#FFFFFF",
    "opacity":        175,
    "font_size_pct":  3.5,
}


# ── Path helpers ──────────────────────────────────────────────────────────────
def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def get_config_path() -> Path:
    return get_base_dir() / "watermark_config.json"


# ── Settings persistence ──────────────────────────────────────────────────────
def load_settings() -> dict:
    path = get_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings: dict):
    try:
        with open(get_config_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ── Font loader ───────────────────────────────────────────────────────────────
def load_font(size: int):
    for name in ["arial.ttf", "segoeui.ttf", "calibri.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ── Color helper ──────────────────────────────────────────────────────────────
def hex_to_rgba(hex_color: str, opacity: int) -> tuple:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), opacity)


# ── Position calculator ───────────────────────────────────────────────────────
def compute_xy(img_w, img_h, text_w, text_h, bbox, margin, position):
    x0, y0 = bbox[0], bbox[1]
    if   position == "Bottom Right": return img_w - text_w - margin - x0, img_h - text_h - margin - y0
    elif position == "Bottom Left":  return margin - x0,                   img_h - text_h - margin - y0
    elif position == "Top Right":    return img_w - text_w - margin - x0, margin - y0
    elif position == "Top Left":     return margin - x0,                   margin - y0
    else:                            return (img_w - text_w) // 2 - x0,   (img_h - text_h) // 2 - y0


# ── Core watermark renderer (shared by preview + file processing) ─────────────
def render_watermark(img: Image.Image, settings: dict) -> Image.Image:
    text     = settings.get("watermark_text") or "© My Photos"
    position = settings.get("position", "Bottom Right")
    color    = settings.get("color", "#FFFFFF")
    opacity  = int(settings.get("opacity", 175))
    pct      = float(settings.get("font_size_pct", 3.5))

    font_size = max(8, int(img.width * pct / 100))
    font      = load_font(font_size)

    rgba  = img.convert("RGBA")
    layer = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    draw  = ImageDraw.Draw(layer)

    bbox   = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    margin = max(4, int(img.width * 0.025))

    x, y  = compute_xy(img.width, img.height, text_w, text_h, bbox, margin, position)

    r, g, b, a = hex_to_rgba(color, opacity)
    draw.text((x + 1, y + 1), text, font=font, fill=(255 - r, 255 - g, 255 - b, 80))
    draw.text((x,     y    ), text, font=font, fill=(r, g, b, a))

    return Image.alpha_composite(rgba, layer)


# ── File processing ───────────────────────────────────────────────────────────
def apply_watermark(img_path: Path, output_path: Path, settings: dict):
    with Image.open(img_path) as raw:
        img    = ImageOps.exif_transpose(raw)
        result = render_watermark(img, settings)
        ext    = output_path.suffix.lower()
        if ext in ('.jpg', '.jpeg', '.bmp'):
            final = result.convert("RGB")
            final.save(output_path, **({"quality": 95, "subsampling": 0} if ext != '.bmp' else {}))
        else:
            result.save(output_path)


# ── Sample photo generator for live preview ───────────────────────────────────
def _lerp(a, b, t):
    return a + (b - a) * t

def make_sample_photo(width: int, height: int) -> Image.Image:
    """Render a convincing fake DSLR landscape/portrait photo for preview."""
    img  = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    sky_h = int(height * 0.52)

    # Sky — blue-to-light gradient
    for y in range(sky_h):
        t = y / max(sky_h, 1)
        draw.line([(0, y), (width, y)],
                  fill=(int(_lerp(72, 148, t)),
                        int(_lerp(130, 190, t)),
                        int(_lerp(210, 235, t))))

    # Ground — earthy green gradient
    for y in range(sky_h, height):
        t = (y - sky_h) / max(height - sky_h, 1)
        draw.line([(0, y), (width, y)],
                  fill=(int(_lerp(52, 72, t)),
                        int(_lerp(88, 60, t)),
                        int(_lerp(42, 28, t))))

    # Sun glow
    sx, sy = int(width * 0.78), int(height * 0.16)
    sr     = max(5, int(min(width, height) * 0.07))
    # soft halo
    for halo in range(sr + 8, sr, -1):
        alpha = int(30 + (sr + 8 - halo) * 15)
        draw.ellipse([sx - halo, sy - halo, sx + halo, sy + halo],
                     fill=(255, 230, 90))
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 240, 120))

    # Mountain silhouette
    pts = [
        (0,             height),
        (0,             int(height * 0.62)),
        (int(width*.18),int(height * 0.35)),
        (int(width*.30),int(height * 0.50)),
        (int(width*.52),int(height * 0.28)),
        (int(width*.65),int(height * 0.44)),
        (int(width*.80),int(height * 0.56)),
        (width,         int(height * 0.62)),
        (width,         height),
    ]
    draw.polygon(pts, fill=(35, 57, 35))

    # Snow caps
    cap_pts = [
        (int(width*.52), int(height * 0.28)),
        (int(width*.46), int(height * 0.38)),
        (int(width*.58), int(height * 0.38)),
    ]
    draw.polygon(cap_pts, fill=(220, 230, 240))

    return img


# ── Main Application ──────────────────────────────────────────────────────────
class WatermarkApp:

    def __init__(self, root: tk.Tk):
        self.root     = root
        self.base_dir = get_base_dir()
        self.settings = load_settings()
        self.is_busy  = False

        self._color_hex     = self.settings.get("color", "#FFFFFF")
        self._preview_job   = None   # debounce handle
        self._tk_land       = None   # hold ImageTk reference (prevent GC)
        self._tk_port       = None

        # Pre-render sample photos at preview resolution
        self._sample_land = make_sample_photo(PREV_LAND_W, PREV_LAND_H)
        self._sample_port = make_sample_photo(PREV_PORT_W, PREV_PORT_H)

        self._build_window()
        self._build_ui()
        self._load_into_ui()
        self._schedule_preview()   # render initial preview

    # ── Window ───────────────────────────────────────────────────────────────
    def _build_window(self):
        self.root.title("📷 Photo Watermark Tool")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f172a")
        self.root.update_idletasks()
        W, H = 760, 520
        sw   = self.root.winfo_screenwidth()
        sh   = self.root.winfo_screenheight()
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

    # ── UI Builder ───────────────────────────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Green.Horizontal.TProgressbar",
                         thickness=10, troughcolor="#1e293b", background="#22c55e")
        style.configure("TCombobox",
                         fieldbackground="#0f172a", background="#0f172a",
                         foreground="#f1f5f9", selectbackground="#334155",
                         arrowcolor="#94a3b8")
        style.map("TCombobox", fieldbackground=[("readonly","#0f172a")])

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg="#0f172a")
        hdr.pack(fill="x", padx=22, pady=(16, 0))
        tk.Label(hdr, text="📷  Photo Watermark Tool",
                 font=("Segoe UI", 15, "bold"),
                 bg="#0f172a", fg="#f1f5f9").pack(side="left")
        tk.Label(hdr, text="Settings auto-saved  •  Live preview updates instantly",
                 font=("Segoe UI", 8),
                 bg="#0f172a", fg="#475569").pack(side="right", anchor="s", pady=(6,0))

        tk.Frame(self.root, bg="#1e293b", height=1).pack(fill="x", padx=22, pady=(8, 0))

        # ── Body (left settings + right preview) ──────────────────────────
        body = tk.Frame(self.root, bg="#0f172a")
        body.pack(fill="both", expand=True, padx=22, pady=(10, 0))

        self._build_settings(body)
        self._build_preview_panel(body)

        # ── Bottom bar ────────────────────────────────────────────────────
        tk.Frame(self.root, bg="#1e293b", height=1).pack(fill="x", padx=22, pady=(6, 0))
        btm = tk.Frame(self.root, bg="#0f172a")
        btm.pack(fill="x", padx=22, pady=(6, 0))

        self.status_lbl = tk.Label(btm, text="Ready — drop this .exe into any photo folder.",
                                   font=("Segoe UI", 8), bg="#0f172a", fg="#64748b", anchor="w")
        self.status_lbl.pack(fill="x")

        self.progress = ttk.Progressbar(btm, orient="horizontal",
                                        mode="determinate", style="Green.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(4, 0))

        self.start_btn = tk.Button(
            self.root, text="▶   Start Watermarking",
            font=("Segoe UI", 12, "bold"),
            bg="#22c55e", fg="#ffffff",
            activebackground="#16a34a", activeforeground="#ffffff",
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=self._start
        )
        self.start_btn.pack(fill="x", padx=22, pady=(8, 16))

    # ── Left: Settings panel ──────────────────────────────────────────────
    def _build_settings(self, parent):
        left = tk.Frame(parent, bg="#0f172a", width=330)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        card = tk.Frame(left, bg="#1e293b")
        card.pack(fill="both", expand=True)

        def lbl(text):
            return tk.Label(card, text=text, font=("Segoe UI", 8, "bold"),
                            bg="#1e293b", fg="#94a3b8", anchor="w")

        def row(pady=(0, 8)):
            f = tk.Frame(card, bg="#1e293b")
            f.pack(fill="x", padx=12, pady=pady)
            return f

        # Watermark Text
        lbl("✏️   Watermark Text").pack(anchor="w", padx=12, pady=(12, 2))
        r = row((0, 8))
        self.text_var = tk.StringVar()
        self.text_var.trace_add("write", lambda *_: self._schedule_preview())
        tk.Entry(r, textvariable=self.text_var,
                 font=("Segoe UI", 10), bg="#0f172a", fg="#f1f5f9",
                 insertbackground="#22c55e", relief="flat", bd=6).pack(fill="x")

        # Position
        lbl("📍   Position").pack(anchor="w", padx=12, pady=(0, 2))
        r = row()
        self.pos_var = tk.StringVar()
        self.pos_var.trace_add("write", lambda *_: self._schedule_preview())
        cb = ttk.Combobox(r, textvariable=self.pos_var,
                          values=POSITIONS, state="readonly",
                          font=("Segoe UI", 9))
        cb.pack(fill="x")

        # Font Size
        self._fs_lbl = lbl("🔠   Font Size  —  3.5%  (~42 px on 1200px image)")
        self._fs_lbl.pack(anchor="w", padx=12, pady=(0, 2))
        r = row()
        self.fs_var = tk.DoubleVar(value=3.5)
        tk.Scale(r, from_=1.0, to=8.0, resolution=0.1,
                 orient="horizontal", variable=self.fs_var,
                 bg="#1e293b", fg="#f1f5f9", troughcolor="#0f172a",
                 highlightthickness=0, activebackground="#22c55e",
                 sliderrelief="flat", showvalue=False,
                 command=self._on_fs_change).pack(fill="x")

        # Color
        lbl("🎨   Color").pack(anchor="w", padx=12, pady=(0, 2))
        clr_row = row((0, 4))
        self.color_preview = tk.Label(clr_row, text="   ██  ",
                                      bg=self._color_hex, relief="flat",
                                      cursor="hand2", font=("Segoe UI", 10))
        self.color_preview.pack(side="left")
        self.color_preview.bind("<Button-1>", lambda e: self._pick_color())
        self.color_hex_lbl = tk.Label(clr_row, text=self._color_hex,
                                      font=("Segoe UI", 8),
                                      bg="#1e293b", fg="#94a3b8")
        self.color_hex_lbl.pack(side="left", padx=(8, 0))
        tk.Label(clr_row, text="← click to change",
                 font=("Segoe UI", 7, "italic"),
                 bg="#1e293b", fg="#475569").pack(side="left", padx=(6, 0))

        # Quick presets
        lbl("⚡   Quick Presets").pack(anchor="w", padx=12, pady=(0, 2))
        pr = row((0, 8))
        for hex_val, name, fg in [("#FFFFFF","White","#000"), ("#000000","Black","#fff"),
                                   ("#FACC15","Yellow","#000"), ("#EF4444","Red","#fff"),
                                   ("#3B82F6","Blue","#fff")]:
            tk.Button(pr, text=name, bg=hex_val, fg=fg,
                      font=("Segoe UI", 8, "bold"),
                      relief="flat", cursor="hand2", bd=0, padx=6, pady=3,
                      command=lambda h=hex_val: self._set_color(h)
                      ).pack(side="left", padx=(0, 4))

        # Opacity
        self._op_lbl = lbl("🔆   Opacity  —  175")
        self._op_lbl.pack(anchor="w", padx=12, pady=(0, 2))
        r = row((0, 12))
        self.opacity_var = tk.IntVar(value=175)
        tk.Scale(r, from_=20, to=255, orient="horizontal",
                 variable=self.opacity_var,
                 bg="#1e293b", fg="#f1f5f9", troughcolor="#0f172a",
                 highlightthickness=0, activebackground="#22c55e",
                 sliderrelief="flat", showvalue=False,
                 command=self._on_opacity_change).pack(fill="x")

    # ── Right: Live preview panel ─────────────────────────────────────────
    def _build_preview_panel(self, parent):
        right = tk.Frame(parent, bg="#0f172a")
        right.pack(side="right", fill="both", expand=True)

        # Panel title
        tk.Label(right, text="🖼️  Live Preview",
                 font=("Segoe UI", 9, "bold"),
                 bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(0, 6))

        # Canvases row
        canv_row = tk.Frame(right, bg="#0f172a")
        canv_row.pack(anchor="w")

        # Landscape canvas
        land_col = tk.Frame(canv_row, bg="#0f172a")
        land_col.pack(side="left", padx=(0, 12))
        tk.Label(land_col, text="Landscape (3:2)",
                 font=("Segoe UI", 7, "bold"), bg="#0f172a", fg="#475569"
                 ).pack(anchor="w", pady=(0, 3))
        self.land_canvas = tk.Canvas(land_col,
                                     width=PREV_LAND_W, height=PREV_LAND_H,
                                     bg="#111827", highlightthickness=1,
                                     highlightbackground="#334155")
        self.land_canvas.pack()

        # Portrait canvas
        port_col = tk.Frame(canv_row, bg="#0f172a")
        port_col.pack(side="left")
        tk.Label(port_col, text="Portrait (2:3)",
                 font=("Segoe UI", 7, "bold"), bg="#0f172a", fg="#475569"
                 ).pack(anchor="w", pady=(0, 3))
        self.port_canvas = tk.Canvas(port_col,
                                     width=PREV_PORT_W, height=PREV_PORT_H,
                                     bg="#111827", highlightthickness=1,
                                     highlightbackground="#334155")
        self.port_canvas.pack()

        # Info note
        tk.Label(right,
                 text="Preview updates as you change any setting above.",
                 font=("Segoe UI", 7, "italic"),
                 bg="#0f172a", fg="#334155").pack(anchor="w", pady=(8, 0))

        tk.Label(right,
                 text="Actual watermark size scales with real photo dimensions.",
                 font=("Segoe UI", 7, "italic"),
                 bg="#0f172a", fg="#334155").pack(anchor="w")

    # ── Setting callbacks ─────────────────────────────────────────────────
    def _on_fs_change(self, val):
        pct = float(val)
        px  = int(1200 * pct / 100)
        self._fs_lbl.config(text=f"🔠   Font Size  —  {pct:.1f}%  (~{px}px on 1200px image)")
        self._schedule_preview()

    def _on_opacity_change(self, val):
        self._op_lbl.config(text=f"🔆   Opacity  —  {int(float(val))}")
        self._schedule_preview()

    def _pick_color(self):
        result = colorchooser.askcolor(color=self._color_hex, title="Choose Watermark Color")
        if result and result[1]:
            self._set_color(result[1].upper())

    def _set_color(self, hex_val: str):
        self._color_hex = hex_val
        self.color_preview.config(bg=hex_val)
        self.color_hex_lbl.config(text=hex_val)
        self._schedule_preview()

    # ── Settings helpers ──────────────────────────────────────────────────
    def _load_into_ui(self):
        self.text_var.set(self.settings.get("watermark_text", "© My Photos"))
        self.pos_var.set(self.settings.get("position", "Bottom Right"))
        self.fs_var.set(float(self.settings.get("font_size_pct", 3.5)))
        self._set_color(self.settings.get("color", "#FFFFFF"))
        self.opacity_var.set(int(self.settings.get("opacity", 175)))
        self._on_fs_change(self.fs_var.get())
        self._on_opacity_change(self.opacity_var.get())

    def _gather(self) -> dict:
        return {
            "watermark_text": self.text_var.get().strip() or "© My Photos",
            "position":       self.pos_var.get() or "Bottom Right",
            "color":          self._color_hex,
            "opacity":        self.opacity_var.get(),
            "font_size_pct":  round(self.fs_var.get(), 1),
        }

    # ── Live preview ──────────────────────────────────────────────────────
    def _schedule_preview(self):
        """Debounce: cancel pending render and reschedule 250ms later."""
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(250, self._render_preview)

    def _render_preview(self):
        self._preview_job = None
        settings = self._gather()

        try:
            # Landscape preview
            wm_land = render_watermark(self._sample_land.copy(), settings)
            self._tk_land = ImageTk.PhotoImage(wm_land)
            self.land_canvas.delete("all")
            self.land_canvas.create_image(0, 0, anchor="nw", image=self._tk_land)

            # Portrait preview
            wm_port = render_watermark(self._sample_port.copy(), settings)
            self._tk_port = ImageTk.PhotoImage(wm_port)
            self.port_canvas.delete("all")
            self.port_canvas.create_image(0, 0, anchor="nw", image=self._tk_port)
        except Exception:
            pass  # Ignore preview errors (e.g. empty text mid-type)

    # ── Thread-safe UI updates ────────────────────────────────────────────
    def _set_status(self, text: str):
        self.root.after(0, lambda: self.status_lbl.config(text=text))

    def _set_progress(self, value: int, maximum: int):
        self.root.after(0, lambda: (
            self.progress.__setitem__("maximum", maximum),
            self.progress.__setitem__("value", value)
        ))

    # ── Start processing ──────────────────────────────────────────────────
    def _start(self):
        if self.is_busy:
            return

        settings = self._gather()
        save_settings(settings)

        photos = [f for f in self.base_dir.iterdir()
                  if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]

        if not photos:
            messagebox.showwarning(
                "No Photos Found",
                f"No supported images were found in:\n\n{self.base_dir}\n\n"
                "Place this program in the same folder as your photos."
            )
            return

        out_dir = self.base_dir / "watermark"
        try:
            out_dir.mkdir(exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create 'watermark' folder:\n{e}")
            return

        self.is_busy = True
        self.start_btn.config(state="disabled", bg="#475569", cursor="arrow",
                              text="⏳  Processing...")
        self.progress["value"] = 0

        threading.Thread(target=self._process,
                         args=(photos, out_dir, settings), daemon=True).start()

    def _process(self, photos, out_dir: Path, settings: dict):
        total, done, failed = len(photos), 0, []
        for i, photo in enumerate(photos, 1):
            self._set_status(f"Processing {i} of {total}:  {photo.name}")
            try:
                apply_watermark(photo, out_dir / photo.name, settings)
                done += 1
            except Exception as e:
                failed.append(f"{photo.name}  ({e})")
            self._set_progress(i, total)

        self.root.after(0, lambda: self._finish(done, total, failed, out_dir))

    def _finish(self, done: int, total: int, failed: list, out_dir: Path):
        self.is_busy = False
        self.start_btn.config(state="normal", bg="#22c55e", cursor="hand2",
                              text="▶   Start Watermarking")
        self._set_status(f"✅  Done!  {done} of {total} photo(s) watermarked successfully.")

        if failed:
            messagebox.showwarning(
                "Completed with errors",
                f"✅  {done} photo(s) watermarked.\n"
                f"❌  {len(failed)} failed:\n\n" + "\n".join(failed)
            )
        else:
            messagebox.showinfo(
                "All Done! ✅",
                f"All {done} photo(s) watermarked successfully!\n\n"
                f"Saved to:\n{out_dir}"
            )


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    WatermarkApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

import sys
import os
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

# Enable High-DPI awareness on Windows so Tkinter UI renders crisp and clear
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ── Constants ─────────────────────────────────────────────────────────────────
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
POSITIONS        = ["Bottom Right", "Bottom Left", "Top Right", "Top Left", "Center"]

# High resolution internal rendering for crisp anti-aliased live previews
RENDER_LAND_W, RENDER_LAND_H = 720, 480
RENDER_PORT_W, RENDER_PORT_H = 480, 720

# UI Display dimensions for live preview canvases
DISP_LAND_W, DISP_LAND_H = 360, 240
DISP_PORT_W, DISP_PORT_H = 160, 240

DEFAULT_SETTINGS = {
    "watermark_text": "© My Photos",
    "position":       "Bottom Right",
    "color":          "#FFFFFF",
    "opacity":        175,
    "font_size_pct":  3.5,
}


# ── Path & Config Helpers ──────────────────────────────────────────────────────
def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_config_path() -> Path:
    r"""
    Store config in C:\Users\<User>\AppData\Roaming\PhotoWatermark\watermark_config.json
    """
    appdata = os.getenv('APPDATA')
    if appdata:
        config_dir = Path(appdata) / "PhotoWatermark"
    else:
        config_dir = Path.home() / ".photo_watermark"
    
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "watermark_config.json"
    except Exception:
        return get_base_dir() / "watermark_config.json"


# ── Settings Persistence ──────────────────────────────────────────────────────
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


# ── Font & Scaling Helpers ────────────────────────────────────────────────────
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


def get_fitted_font(text: str, img_w: int, img_h: int, font_pct: float, margin: int):
    """
    Dynamically scale font size and auto-fit so text NEVER clips or overflows
    on narrow or vertical (portrait) DSLR images.
    """
    target_size = max(10, int(img_w * font_pct / 100))
    font = load_font(target_size)
    max_w = img_w - (2 * margin)
    if max_w <= 0:
        return font
    
    # Use getlength for pure horizontal width (more reliable than textbbox for scaling)
    text_w = font.getlength(text)
    
    if text_w > max_w:
        scale_factor = max_w / text_w
        fitted_size = max(8, int(target_size * scale_factor))
        font = load_font(fitted_size)
        
    return font


def hex_to_rgba(hex_color: str, opacity: int) -> tuple:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), opacity)


def compute_xy_and_anchor(img_w, img_h, margin, position):
    if   position == "Bottom Right": return img_w - margin, img_h - margin, "rd"
    elif position == "Bottom Left":  return margin, img_h - margin, "ld"
    elif position == "Top Right":    return img_w - margin, margin, "rt"
    elif position == "Top Left":     return margin, margin, "lt"
    else:                            return img_w // 2, img_h // 2, "mm"


# ── Core Watermark Renderer ───────────────────────────────────────────────────
def render_watermark(img: Image.Image, settings: dict) -> Image.Image:
    text     = settings.get("watermark_text") or "© My Photos"
    position = settings.get("position", "Bottom Right")
    color    = settings.get("color", "#FFFFFF")
    opacity  = int(settings.get("opacity", 175))
    pct      = float(settings.get("font_size_pct", 3.5))

    margin = max(6, int(img.width * 0.025))
    font   = get_fitted_font(text, img.width, img.height, pct, margin)

    rgba  = img.convert("RGBA")
    layer = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
    draw  = ImageDraw.Draw(layer)

    x, y, anchor = compute_xy_and_anchor(img.width, img.height, margin, position)

    r, g, b, a = hex_to_rgba(color, opacity)
    # Subtle dark outline shadow for high contrast on light backgrounds
    draw.text((x + 1, y + 1), text, font=font, fill=(255 - r, 255 - g, 255 - b, 80), anchor=anchor)
    draw.text((x,     y    ), text, font=font, fill=(r, g, b, a), anchor=anchor)

    return Image.alpha_composite(rgba, layer)


# ── File Processing ───────────────────────────────────────────────────────────
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


# ── Sample Photo Generator for Live Preview ───────────────────────────────────
def _lerp(a, b, t):
    return a + (b - a) * t

def make_sample_photo(width: int, height: int) -> Image.Image:
    """Render a vibrant HD sample DSLR photo for preview."""
    img  = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    sky_h = int(height * 0.52)

    # Rich sky gradient
    for y in range(sky_h):
        t = y / max(sky_h, 1)
        draw.line([(0, y), (width, y)],
                  fill=(int(_lerp(60, 140, t)),
                        int(_lerp(120, 185, t)),
                        int(_lerp(215, 240, t))))

    # Earthy ground gradient
    for y in range(sky_h, height):
        t = (y - sky_h) / max(height - sky_h, 1)
        draw.line([(0, y), (width, y)],
                  fill=(int(_lerp(45, 65, t)),
                        int(_lerp(80, 55, t)),
                        int(_lerp(38, 25, t))))

    # Sun glow
    sx, sy = int(width * 0.76), int(height * 0.16)
    sr     = max(10, int(min(width, height) * 0.08))
    for halo in range(sr + 16, sr, -1):
        draw.ellipse([sx - halo, sy - halo, sx + halo, sy + halo], fill=(255, 225, 90))
    draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 242, 130))

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
    draw.polygon(pts, fill=(30, 52, 32))

    # Snow caps
    cap_pts = [
        (int(width*.52), int(height * 0.28)),
        (int(width*.46), int(height * 0.38)),
        (int(width*.58), int(height * 0.38)),
    ]
    draw.polygon(cap_pts, fill=(225, 235, 245))

    return img


# ── Main Application ──────────────────────────────────────────────────────────
class WatermarkApp:

    def __init__(self, root: tk.Tk):
        self.root     = root
        self.base_dir = get_base_dir()
        self.settings = load_settings()
        self.is_busy  = False

        self._color_hex   = self.settings.get("color", "#FFFFFF")
        self._preview_job = None
        self._tk_land     = None
        self._tk_port     = None

        # Pre-render high-resolution sample photos
        self._sample_land = make_sample_photo(RENDER_LAND_W, RENDER_LAND_H)
        self._sample_port = make_sample_photo(RENDER_PORT_W, RENDER_PORT_H)

        self._build_window()
        self._build_ui()
        self._load_into_ui()
        self._schedule_preview()

    # ── Window Setup ─────────────────────────────────────────────────────────
    def _build_window(self):
        self.root.title("📷 Photo Watermark Tool")
        self.root.resizable(False, False)
        self.root.configure(bg="#0b1329")
        self.root.update_idletasks()
        
        W, H = 1040, 700
        sw   = self.root.winfo_screenwidth()
        sh   = self.root.winfo_screenheight()
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

    # ── UI Builder ───────────────────────────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Green.Horizontal.TProgressbar",
                         thickness=16, troughcolor="#162036", background="#22c55e")
        style.configure("TCombobox",
                         fieldbackground="#0d1527", background="#162036",
                         foreground="#f8fafc", selectbackground="#1e293b",
                         arrowcolor="#38bdf8", bordercolor="#243456")
        style.map("TCombobox", fieldbackground=[("readonly","#0d1527")])

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg="#0b1329")
        hdr.pack(fill="x", padx=30, pady=(22, 0))
        
        title_box = tk.Frame(hdr, bg="#0b1329")
        title_box.pack(side="left")
        tk.Label(title_box, text="📷   Photo Watermark Tool",
                 font=("Segoe UI", 21, "bold"),
                 bg="#0b1329", fg="#f8fafc").pack(anchor="w")
        tk.Label(title_box, text="Professional Batch Watermarking for DSLR & Mobile Photos",
                 font=("Segoe UI", 10),
                 bg="#0b1329", fg="#38bdf8").pack(anchor="w", pady=(2, 0))

        tk.Label(hdr, text="Global Memory (C: Drive)  •  Live Auto-Fit Preview",
                 font=("Segoe UI", 10, "bold"),
                 bg="#0b1329", fg="#64748b").pack(side="right", anchor="s", pady=(8,0))

        tk.Frame(self.root, bg="#162036", height=2).pack(fill="x", padx=30, pady=(14, 0))

        # ── Body (left settings + right preview) ──────────────────────────
        body = tk.Frame(self.root, bg="#0b1329")
        body.pack(fill="both", expand=True, padx=30, pady=(16, 0))

        self._build_settings(body)
        self._build_preview_panel(body)

        # ── Bottom bar ────────────────────────────────────────────────────
        tk.Frame(self.root, bg="#162036", height=2).pack(fill="x", padx=30, pady=(12, 0))
        btm = tk.Frame(self.root, bg="#0b1329")
        btm.pack(fill="x", padx=30, pady=(8, 0))

        self.status_lbl = tk.Label(btm, text="Ready — place this program into any photo folder.",
                                   font=("Segoe UI", 10, "bold"), bg="#0b1329", fg="#94a3b8", anchor="w")
        self.status_lbl.pack(fill="x")

        self.progress = ttk.Progressbar(btm, orient="horizontal",
                                        mode="determinate", style="Green.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(6, 0))

        self.start_btn = tk.Button(
            self.root, text="▶   Start Watermarking",
            font=("Segoe UI", 14, "bold"),
            bg="#22c55e", fg="#ffffff",
            activebackground="#16a34a", activeforeground="#ffffff",
            relief="flat", cursor="hand2", pady=12, bd=0,
            command=self._start
        )
        self.start_btn.pack(fill="x", padx=30, pady=(12, 22))

    # ── Left: Modern Settings Panel ───────────────────────────────────────
    def _build_settings(self, parent):
        left = tk.Frame(parent, bg="#0b1329", width=440)
        left.pack(side="left", fill="y", padx=(0, 18))
        left.pack_propagate(False)

        card = tk.Frame(left, bg="#162036", highlightbackground="#243456", highlightthickness=1)
        card.pack(fill="both", expand=True)

        def section_hdr(icon, title):
            f = tk.Frame(card, bg="#162036")
            f.pack(fill="x", padx=16, pady=(14, 4))
            tk.Label(f, text=f"{icon}  {title}", font=("Segoe UI", 10, "bold"),
                     bg="#162036", fg="#38bdf8").pack(anchor="w")

        def row(pady=(0, 10)):
            f = tk.Frame(card, bg="#162036")
            f.pack(fill="x", padx=16, pady=pady)
            return f

        # Watermark Text Box
        section_hdr("✏️", "Watermark Text")
        r = row((0, 10))
        self.text_var = tk.StringVar()
        self.text_var.trace_add("write", lambda *_: self._schedule_preview())
        
        text_entry_frame = tk.Frame(r, bg="#243456", padx=1, pady=1)
        text_entry_frame.pack(fill="x")
        self.text_entry = tk.Entry(text_entry_frame, textvariable=self.text_var,
                                   font=("Segoe UI", 12, "bold"), bg="#0d1527", fg="#f8fafc",
                                   insertbackground="#38bdf8", relief="flat", bd=6)
        self.text_entry.pack(fill="x")

        # Position Selector
        section_hdr("📍", "Position")
        r = row((0, 10))
        self.pos_var = tk.StringVar()
        self.pos_var.trace_add("write", lambda *_: self._schedule_preview())
        cb = ttk.Combobox(r, textvariable=self.pos_var,
                          values=POSITIONS, state="readonly",
                          font=("Segoe UI", 11, "bold"))
        cb.pack(fill="x")

        # Font Size Slider
        self._fs_lbl = tk.Label(card, text="🔠  Font Size  —  3.5% (~42px on 1200px photo)",
                                font=("Segoe UI", 10, "bold"), bg="#162036", fg="#38bdf8", anchor="w")
        self._fs_lbl.pack(fill="x", padx=16, pady=(12, 4))
        r = row((0, 10))
        self.fs_var = tk.DoubleVar(value=3.5)
        tk.Scale(r, from_=1.0, to=8.0, resolution=0.1,
                 orient="horizontal", variable=self.fs_var,
                 bg="#162036", fg="#f8fafc", troughcolor="#0d1527",
                 highlightthickness=0, activebackground="#38bdf8",
                 sliderrelief="flat", showvalue=False,
                 width=18, sliderlength=32, bd=0,
                 command=self._on_fs_change).pack(fill="x", pady=(2, 4))

        # Color Selection
        section_hdr("🎨", "Color & Opacity")
        clr_row = row((0, 6))
        
        self.color_preview = tk.Label(clr_row, text="    ███   ",
                                      bg=self._color_hex, relief="flat",
                                      cursor="hand2", font=("Segoe UI", 11, "bold"))
        self.color_preview.pack(side="left")
        self.color_preview.bind("<Button-1>", lambda e: self._pick_color())
        
        self.color_hex_lbl = tk.Label(clr_row, text=self._color_hex,
                                      font=("Segoe UI", 10, "bold"),
                                      bg="#162036", fg="#f8fafc")
        self.color_hex_lbl.pack(side="left", padx=(10, 0))
        
        tk.Label(clr_row, text="← click color box",
                 font=("Segoe UI", 9, "italic"),
                 bg="#162036", fg="#64748b").pack(side="left", padx=(8, 0))

        # Quick Color Presets
        pr = row((0, 10))
        for hex_val, name, fg in [("#FFFFFF","White","#000"), ("#000000","Black","#fff"),
                                   ("#FACC15","Yellow","#000"), ("#EF4444","Red","#fff"),
                                   ("#3B82F6","Blue","#fff")]:
            tk.Button(pr, text=name, bg=hex_val, fg=fg,
                      font=("Segoe UI", 9, "bold"),
                      relief="flat", cursor="hand2", bd=0, padx=10, pady=5,
                      command=lambda h=hex_val: self._set_color(h)
                      ).pack(side="left", padx=(0, 6))

        # Opacity Slider
        self._op_lbl = tk.Label(card, text="🔆  Opacity  —  175",
                                font=("Segoe UI", 10, "bold"), bg="#162036", fg="#38bdf8", anchor="w")
        self._op_lbl.pack(fill="x", padx=16, pady=(8, 4))
        r = row((0, 16))
        self.opacity_var = tk.IntVar(value=175)
        tk.Scale(r, from_=20, to=255, orient="horizontal",
                 variable=self.opacity_var,
                 bg="#162036", fg="#f8fafc", troughcolor="#0d1527",
                 highlightthickness=0, activebackground="#38bdf8",
                 sliderrelief="flat", showvalue=False,
                 width=18, sliderlength=32, bd=0,
                 command=self._on_opacity_change).pack(fill="x", pady=(2, 4))

    # ── Right: Live Preview Panel ─────────────────────────────────────────
    def _build_preview_panel(self, parent):
        right = tk.Frame(parent, bg="#0b1329")
        right.pack(side="right", fill="both", expand=True)

        # Panel title
        tk.Label(right, text="🖼️   Live Preview (DSLR Formats)",
                 font=("Segoe UI", 11, "bold"),
                 bg="#0b1329", fg="#f8fafc").pack(anchor="w", pady=(0, 8))

        # Canvases row
        canv_row = tk.Frame(right, bg="#0b1329")
        canv_row.pack(anchor="w")

        # Landscape canvas card
        land_col = tk.Frame(canv_row, bg="#0b1329")
        land_col.pack(side="left", padx=(0, 18))
        tk.Label(land_col, text="🌄  Landscape (3:2)",
                 font=("Segoe UI", 9, "bold"), bg="#0b1329", fg="#38bdf8"
                 ).pack(anchor="w", pady=(0, 5))
        
        land_card = tk.Frame(land_col, bg="#162036", highlightbackground="#243456", highlightthickness=1)
        land_card.pack()
        self.land_canvas = tk.Canvas(land_card,
                                     width=DISP_LAND_W, height=DISP_LAND_H,
                                     bg="#0d1527", highlightthickness=0)
        self.land_canvas.pack(padx=2, pady=2)

        # Portrait canvas card
        port_col = tk.Frame(canv_row, bg="#0b1329")
        port_col.pack(side="left")
        tk.Label(port_col, text="📱  Portrait (2:3)",
                 font=("Segoe UI", 9, "bold"), bg="#0b1329", fg="#38bdf8"
                 ).pack(anchor="w", pady=(0, 5))
        
        port_card = tk.Frame(port_col, bg="#162036", highlightbackground="#243456", highlightthickness=1)
        port_card.pack()
        self.port_canvas = tk.Canvas(port_card,
                                     width=DISP_PORT_W, height=DISP_PORT_H,
                                     bg="#0d1527", highlightthickness=0)
        self.port_canvas.pack(padx=2, pady=2)

        # Helpful notes
        tk.Label(right,
                 text="✨ Live preview updates instantly as you type or adjust sliders.",
                 font=("Segoe UI", 9, "italic"),
                 bg="#0b1329", fg="#94a3b8").pack(anchor="w", pady=(14, 0))

        tk.Label(right,
                 text="📐 Auto-fit technology prevents watermark text from ever clipping on vertical/portrait photos.",
                 font=("Segoe UI", 9, "italic"),
                 bg="#0b1329", fg="#94a3b8").pack(anchor="w", pady=(3, 0))

    # ── Setting Callbacks ─────────────────────────────────────────────────
    def _on_fs_change(self, val):
        pct = float(val)
        px  = int(1200 * pct / 100)
        self._fs_lbl.config(text=f"🔠  Font Size  —  {pct:.1f}% (~{px}px on 1200px photo)")
        self._schedule_preview()

    def _on_opacity_change(self, val):
        self._op_lbl.config(text=f"🔆  Opacity  —  {int(float(val))}")
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

    # ── Settings Helpers ──────────────────────────────────────────────────
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

    # ── Live Preview Renderer ──────────────────────────────────────────────
    def _schedule_preview(self):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(200, self._render_preview)

    def _render_preview(self):
        self._preview_job = None
        settings = self._gather()

        try:
            # Render Landscape preview at HD resolution then scale down smoothly
            raw_land = render_watermark(self._sample_land.copy(), settings)
            disp_land = raw_land.resize((DISP_LAND_W, DISP_LAND_H), Image.Resampling.LANCZOS)
            self._tk_land = ImageTk.PhotoImage(disp_land)
            self.land_canvas.delete("all")
            self.land_canvas.create_image(0, 0, anchor="nw", image=self._tk_land)

            # Render Portrait preview at HD resolution then scale down smoothly
            raw_port = render_watermark(self._sample_port.copy(), settings)
            disp_port = raw_port.resize((DISP_PORT_W, DISP_PORT_H), Image.Resampling.LANCZOS)
            self._tk_port = ImageTk.PhotoImage(disp_port)
            self.port_canvas.delete("all")
            self.port_canvas.create_image(0, 0, anchor="nw", image=self._tk_port)
        except Exception:
            pass

    # ── Thread-Safe UI Updates ────────────────────────────────────────────
    def _set_status(self, text: str):
        self.root.after(0, lambda: self.status_lbl.config(text=text))

    def _set_progress(self, value: int, maximum: int):
        self.root.after(0, lambda: (
            self.progress.__setitem__("maximum", maximum),
            self.progress.__setitem__("value", value)
        ))

    # ── Start Batch Watermarking ───────────────────────────────────────────
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
                              text="⏳   Watermarking Photos...")
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


# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    root = tk.Tk()
    WatermarkApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

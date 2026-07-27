# ============================================================
#  EASY WATERMARK - Just double-click me!
#  No buttons. No CMD. Fully automatic.
#  Drop this file into any photo folder and double-click.
# ============================================================

import sys
from pathlib import Path
from tkinter import messagebox
import tkinter as tk

# ── Pillow import with friendly error if not installed ──────
try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing Library",
        "Pillow is not installed.\n\n"
        "Please ask someone to run this command once:\n\n"
        "   pip install pillow\n\n"
        "Then double-click this file again."
    )
    sys.exit(1)

# ── Supported image formats ─────────────────────────────────
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

# ── Watermark text — change this to whatever you want ───────
WATERMARK_TEXT = "© My Photos"


def get_script_folder() -> Path:
    """Always returns the folder this script is sitting in."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_font(size: int):
    """Load best available font, fall back gracefully."""
    for name in ["arial.ttf", "segoeui.ttf", "calibri.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def add_watermark(src: Path, dst: Path):
    """Stamp watermark text onto an image and save to dst."""
    with Image.open(src) as raw:
        img = ImageOps.exif_transpose(raw)          # fix camera rotation

        # Dynamic font size — ~3.5% of image width
        font_size = max(14, int(img.width * 0.035))
        font = load_font(font_size)

        # Work in RGBA so we can use transparency
        rgba = img.convert("RGBA")
        layer = Image.new("RGBA", rgba.size, (255, 255, 255, 0))
        draw  = ImageDraw.Draw(layer)

        # Calculate bottom-right position
        bbox   = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = max(10, int(img.width * 0.02))
        x = img.width  - tw - margin - bbox[0]
        y = img.height - th - margin - bbox[1]

        # Shadow + white text for visibility on any background
        draw.text((x + 1, y + 1), WATERMARK_TEXT, font=font, fill=(0,   0,   0,   90))
        draw.text((x,     y    ), WATERMARK_TEXT, font=font, fill=(255, 255, 255, 175))

        result = Image.alpha_composite(rgba, layer)

        # Save — convert back to RGB for JPEG/BMP
        ext = dst.suffix.lower()
        if ext in ('.jpg', '.jpeg', '.bmp'):
            final = result.convert("RGB")
            if ext in ('.jpg', '.jpeg'):
                final.save(dst, quality=95, subsampling=0)
            else:
                final.save(dst)
        else:
            result.save(dst)


def main():
    # ── Hide the Tkinter root window (we only use it for popups) ──
    root = tk.Tk()
    root.withdraw()

    folder = get_script_folder()

    # ── Find all photos in this folder ─────────────────────────
    photos = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not photos:
        messagebox.showwarning(
            "No Photos Found",
            "No photos were found in this folder.\n\n"
            "Make sure this file is in the same folder as your photos, "
            "then double-click it again."
        )
        return

    # ── Create the watermark output folder ─────────────────────
    output_folder = folder / "watermark"
    output_folder.mkdir(exist_ok=True)

    # ── Process every photo silently ────────────────────────────
    done   = 0
    failed = []

    for photo in photos:
        try:
            add_watermark(photo, output_folder / photo.name)
            done += 1
        except Exception as e:
            failed.append(f"{photo.name}  ({e})")

    # ── Final result popup ──────────────────────────────────────
    if failed:
        fail_list = "\n".join(failed)
        messagebox.showwarning(
            "Done (with some errors)",
            f"✅  {done} photo(s) watermarked successfully.\n"
            f"❌  {len(failed)} photo(s) could not be processed:\n\n"
            f"{fail_list}\n\n"
            f"Saved watermarked photos to:\n./watermark/"
        )
    else:
        messagebox.showinfo(
            "All Done! ✅",
            f"All {done} photo(s) have been watermarked!\n\n"
            f"Your watermarked photos are saved here:\n"
            f"{output_folder}"
        )


if __name__ == "__main__":
    main()

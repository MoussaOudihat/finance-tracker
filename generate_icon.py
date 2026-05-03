"""
Génère l'icône FinTrack (Option D) en .ico multi-résolution.
Couleurs : Indigo #4F46E5, graphe ligne+barres blanc.
Tailles  : 16, 32, 48, 64, 128, 256 px

Usage :
    python generate_icon.py

Dépendance : Pillow  →  pip install Pillow
"""
from PIL import Image, ImageDraw
import os

HERE       = os.path.dirname(os.path.abspath(__file__))
ICON_PATH  = os.path.join(HERE, "fintrack.ico")
PNG_PATH   = os.path.join(HERE, "fintrack_256.png")

BG_COLOR = (79, 70, 229)   # #4F46E5 — indigo
WHITE    = (255, 255, 255)


# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────
def _rounded_rect_mask(size: int, radius: int) -> Image.Image:
    """Retourne un masque L (blanc = opaque) avec coins arrondis."""
    m  = Image.new("L", (size, size), 0)
    d  = ImageDraw.Draw(m)
    x2 = size - 1
    d.rectangle([radius, 0, x2 - radius, x2], fill=255)
    d.rectangle([0, radius, x2, x2 - radius], fill=255)
    d.ellipse([0,          0,          radius * 2, radius * 2], fill=255)
    d.ellipse([x2 - radius * 2, 0,          x2, radius * 2], fill=255)
    d.ellipse([0,          x2 - radius * 2, radius * 2, x2], fill=255)
    d.ellipse([x2 - radius * 2, x2 - radius * 2, x2, x2], fill=255)
    return m


# ──────────────────────────────────────────────────────────────
#  Dessin principal
# ──────────────────────────────────────────────────────────────
def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # ── Fond indigo arrondi ───────────────────────────────────
    radius = max(2, int(size * 0.22))
    mask   = _rounded_rect_mask(size, radius)
    bg     = Image.new("RGBA", (size, size), (*BG_COLOR, 255))
    img.paste(bg, mask=mask)

    # ── Icône simplifiée pour 16 px ───────────────────────────
    if size <= 16:
        d = ImageDraw.Draw(img)
        pad = 3
        d.line([(pad, size - pad - 2), (size - pad, pad + 1)],
               fill=WHITE, width=2)
        return img

    # ── Paramètres de la zone graphe ─────────────────────────
    pad     = int(size * 0.16)
    chart_t = int(size * 0.20)
    chart_b = int(size * 0.66)
    chart_l = pad
    chart_r = size - pad
    W       = chart_r - chart_l

    # ── Points de la courbe (5 points, tendance haussière) ───
    xs = [chart_l + W * f for f in (0.0, 0.27, 0.50, 0.73, 1.0)]
    ys = [
        chart_b - (chart_b - chart_t) * 0.28,
        chart_b - (chart_b - chart_t) * 0.56,
        chart_b - (chart_b - chart_t) * 0.46,
        chart_b - (chart_b - chart_t) * 0.74,
        chart_b - (chart_b - chart_t) * 0.94,
    ]
    pts = [(int(x), int(y)) for x, y in zip(xs, ys)]

    # ── Ligne ────────────────────────────────────────────────
    lw = max(1, int(size * 0.055))
    d  = ImageDraw.Draw(img)
    d.line(pts, fill=WHITE, width=lw, joint="curve")

    # ── Dots ─────────────────────────────────────────────────
    dr = max(1, int(size * 0.055))
    for (x, y) in pts:
        d.ellipse([x - dr, y - dr, x + dr, y + dr], fill=WHITE)

    # ── Barres semi-transparentes en bas ─────────────────────
    bar_b   = int(size * 0.84)
    bar_ref = int(size * 0.70)
    bw      = max(2, int(size * 0.07))
    bgap    = max(1, int(size * 0.025))
    fracs   = [0.30, 0.50, 0.38, 0.65]
    n       = len(fracs)
    bx0     = (size - n * bw - (n - 1) * bgap) // 2

    for i, frac in enumerate(fracs):
        bx  = bx0 + i * (bw + bgap)
        bh  = max(2, int((bar_b - bar_ref) * frac))
        by  = bar_b - bh
        bar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        bd  = ImageDraw.Draw(bar)
        bd.rectangle([bx, by, bx + bw, bar_b], fill=(*WHITE, 110))
        img = Image.alpha_composite(img, bar)

    return img


# ──────────────────────────────────────────────────────────────
#  Génération
# ──────────────────────────────────────────────────────────────
def main():
    sizes  = [16, 32, 48, 64, 128, 256]
    frames = []

    print("Génération des résolutions…")
    for s in sizes:
        f = draw_icon(s)
        frames.append(f)
        print(f"  ✓ {s:>3}×{s}px")

    # .ico multi-résolution
    frames[0].save(
        ICON_PATH,
        format="ICO",
        append_images=frames[1:],
        sizes=[(s, s) for s in sizes],
    )
    print(f"\n✅  {ICON_PATH}")

    # PNG 256 px séparé (installeur, README, etc.)
    frames[-1].save(PNG_PATH, format="PNG")
    print(f"✅  {PNG_PATH}")


if __name__ == "__main__":
    main()

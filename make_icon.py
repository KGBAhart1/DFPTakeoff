"""
Generate icon.ico for DFP TakeoffPro using PyQt5 (already installed).
Run:  python make_icon.py
"""
import sys, struct, os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPainter, QColor, QPixmap, QPolygon, QFont, QImage
from PyQt5.QtCore import Qt, QPoint

app = QApplication.instance() or QApplication(sys.argv)

BG     = QColor("#232728")
ORANGE = QColor("#ff7002")
CREAM  = QColor("#efe6e1")


def draw_frame(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    s = size

    # Background rounded rect
    p.setBrush(BG); p.setPen(Qt.NoPen)
    radius = max(2, s // 8)
    p.drawRoundedRect(0, 0, s, s, radius, radius)

    # Top accent bar
    bar = max(2, s // 18)
    p.setBrush(ORANGE)
    p.drawRoundedRect(0, 0, s, bar, radius, radius)
    p.drawRect(0, bar // 2, s, bar // 2)   # flatten bottom half

    # Bottom accent bar
    p.drawRect(0, s - bar, s, bar)
    p.drawRoundedRect(0, s - bar, s, bar, radius, radius)
    p.drawRect(0, s - bar, s, bar // 2)   # flatten top half

    # Shield
    cx  = s // 2
    sy  = int(s * 0.16)
    sw  = int(s * 0.36)
    sh  = int(s * 0.54)

    shield = QPolygon([
        QPoint(cx - sw, sy),
        QPoint(cx + sw, sy),
        QPoint(cx + sw, sy + int(sh * 0.58)),
        QPoint(cx,      sy + sh),
        QPoint(cx - sw, sy + int(sh * 0.58)),
    ])
    p.setBrush(ORANGE); p.setPen(Qt.NoPen)
    p.drawPolygon(shield)

    # Inner dark cutout
    pad = max(2, s // 20)
    isw = sw - pad
    ish = sh - int(pad * 1.5)
    isy = sy + pad
    inner = QPolygon([
        QPoint(cx - isw, isy),
        QPoint(cx + isw, isy),
        QPoint(cx + isw, isy + int(ish * 0.58)),
        QPoint(cx,       isy + ish),
        QPoint(cx - isw, isy + int(ish * 0.58)),
    ])
    p.setBrush(BG)
    p.drawPolygon(inner)

    # Flame
    fw  = max(3, int(s * 0.19))
    fcy = isy + int(ish * 0.35)
    flame = QPolygon([
        QPoint(cx,            fcy - int(fw * 0.85)),
        QPoint(cx - fw,       fcy + int(fw * 0.28)),
        QPoint(cx - fw // 3,  fcy - int(fw * 0.08)),
        QPoint(cx + fw // 3,  fcy + int(fw * 0.52)),
        QPoint(cx + fw,       fcy + int(fw * 0.28)),
    ])
    p.setBrush(ORANGE)
    p.drawPolygon(flame)

    # "DFP" label at bottom (only for larger sizes)
    if size >= 48:
        fs = max(5, s // 9)
        font = QFont("Arial", fs, QFont.Bold)
        p.setFont(font)
        p.setPen(ORANGE)
        p.drawText(0, s - bar - fs - max(1, s//28),
                   s, fs + 4, Qt.AlignHCenter, "DFP")

    p.end()
    return pm.toImage().convertToFormat(QImage.Format_ARGB32)


def image_to_png_bytes(img):
    from PyQt5.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def build_ico(sizes):
    """Manually assemble a valid .ico file."""
    images = []
    for sz in sizes:
        img  = draw_frame(sz)
        data = image_to_png_bytes(img)
        images.append((sz, data))

    # ICO header
    header = struct.pack("<HHH", 0, 1, len(images))   # reserved, type=1 (ICO), count

    # Directory entries (16 bytes each)
    offset = 6 + 16 * len(images)
    entries = b""
    for sz, data in images:
        w = sz if sz < 256 else 0
        h = sz if sz < 256 else 0
        entries += struct.pack("<BBBBHHII",
            w, h,       # width, height (0 = 256)
            0, 0,       # colour count, reserved
            1, 32,      # planes, bit count
            len(data),  # size of image data
            offset,     # offset from start of file
        )
        offset += len(data)

    raw = header + entries + b"".join(d for _, d in images)
    return raw


sizes = [16, 24, 32, 48, 64, 128, 256]
ico_data = build_ico(sizes)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
with open(out, "wb") as f:
    f.write(ico_data)

print(f"Saved: {out}  ({len(ico_data):,} bytes, {len(sizes)} sizes)")

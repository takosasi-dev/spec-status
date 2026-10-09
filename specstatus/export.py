# 今の表の行を CSV の文字列にする(列は表と同じ+メモ・AC・脆弱な依存)のと、部品の範囲を PNG に撮る(Windows の PrintWindow)。
# CSV はファイルに書かない(書く側が utf-8-sig で書く)。撮る処理は ctypes で、Windows 以外では OSError。
from __future__ import annotations

import csv
import io

from . import pngutil, render
from . import strings as S
from .guilogic import row_values
from .model import ProjectStatus

EXTRA_COLUMNS = ("メモ", "AC", "脆弱な依存")
VULNS_CELL = "{count} 件: {packages}"
PW_RENDERFULLCONTENT = 2


def header() -> list[str]:
    return [title for _key, title in S.COLUMNS] + list(EXTRA_COLUMNS)


def _vulns_cell(ps: ProjectStatus) -> str:
    v = ps.vulns
    if not v or not v.get("count"):
        return ""
    return VULNS_CELL.format(count=v["count"], packages=" / ".join(v.get("packages") or []))


def to_csv(rows: list[ProjectStatus]) -> str:
    """見出し+1件1行。改行は \\r\\n(Excel 向け)。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header())
    for ps in rows:
        w.writerow(list(row_values(ps)) + [ps.folded.note or "", render.ac_text(ps), _vulns_cell(ps)])
    return buf.getvalue()


def crop_bgra(buf: bytes, width: int, x: int, y: int, w: int, h: int) -> bytes:
    """上から下へ並んだ BGRA(1行 width 画素)から (x, y, w, h) を切り出して RGBA(不透明)にする。"""
    out = bytearray(w * h * 4)
    for r in range(h):
        s = ((y + r) * width + x) * 4
        src = buf[s: s + w * 4]
        d = r * w * 4
        line = bytearray(w * 4)
        line[0::4], line[1::4], line[2::4] = src[2::4], src[1::4], src[0::4]
        line[3::4] = b"\xff" * w
        out[d: d + w * 4] = line
    return bytes(out)


def capture_png(widget, path: str) -> None:
    """widget の見えている範囲を PNG で path に書く。窓の後ろに隠れていても PrintWindow で描かせる。失敗は OSError。"""
    import ctypes
    from ctypes import wintypes as wt

    try:
        user32, gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")    # 自分用の実体(argtypes を他に響かせない)
    except (AttributeError, OSError) as e:
        raise OSError(f"Windows でだけ撮れます: {e}") from e
    user32.GetDC.restype = wt.HDC
    user32.GetDC.argtypes = [wt.HWND]
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
    gdi32.CreateCompatibleDC.restype = wt.HDC
    gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT]
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wt.HDC]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                    ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    widget.update_idletasks()
    top = widget.winfo_toplevel()
    hwnd = int(top.wm_frame(), 16)                   # 枠付きの本当の窓(winfo_id は中の子窓)
    rect = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise OSError("窓の位置を取れませんでした")
    W, H = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, W, H)
    old = gdi32.SelectObject(mem, bmp)
    try:
        if not user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT):
            raise OSError("PrintWindow で描けませんでした")
        bih = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=W, biHeight=-H,   # 負 = 上から下
                               biPlanes=1, biBitCount=32, biCompression=0)
        buf = (ctypes.c_ubyte * (W * H * 4))()
        gdi32.SelectObject(mem, old)                 # GetDIBits は選んでいない bitmap で呼ぶ
        if gdi32.GetDIBits(mem, bmp, 0, H, buf, ctypes.byref(bih), 0) != H:
            raise OSError("画素を読めませんでした")
    finally:
        gdi32.SelectObject(mem, old)                 # 選んだままの bitmap は消せない
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)

    x, y = widget.winfo_rootx() - rect.left, widget.winfo_rooty() - rect.top
    x, y = max(0, min(x, W - 1)), max(0, min(y, H - 1))
    w, h = min(widget.winfo_width(), W - x), min(widget.winfo_height(), H - y)
    with open(path, "wb") as f:
        f.write(pngutil.encode(w, h, crop_bgra(bytes(buf), W, x, y, w, h)))

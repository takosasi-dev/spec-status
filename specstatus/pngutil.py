# 標準ライブラリだけで PNG を読み・縮め・書く(アイコンを一覧の行の大きさにするため。Tk は整数分の1の間引きしかできない)。
# 読めるのは 8 ビット・インターレース無しのグレー/RGB/パレット/透過つき。ICO は中に入っている PNG だけを取り出す。
from __future__ import annotations

import struct
import zlib

SIG = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def size_of(data: bytes) -> tuple[int, int] | None:
    """PNG の幅と高さ(IHDR だけ読む)。PNG でなければ None。"""
    if data[:8] != SIG or len(data) < 24:
        return None
    return struct.unpack(">II", data[16:24])


def png_from_ico(data: bytes) -> bytes | None:
    """ICO の中の PNG のうち一番大きい物(BMP の物は扱わない)。"""
    if data[:4] != b"\x00\x00\x01\x00":
        return None
    best, best_size = None, -1
    for i in range(struct.unpack("<H", data[4:6])[0]):
        e = data[6 + 16 * i: 22 + 16 * i]
        if len(e) < 16:
            break
        length, offset = struct.unpack("<II", e[8:16])
        blob = data[offset: offset + length]
        s = size_of(blob)
        if s and s[0] > best_size:
            best, best_size = blob, s[0]
    return best


def _unfilter(raw: bytes, w: int, h: int, bpp: int) -> bytearray:
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        ft = raw[pos]
        line = bytearray(raw[pos + 1: pos + 1 + stride])
        pos += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif ft != 0:
            raise ValueError(f"PNG のフィルタ {ft} は知らない")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def decode(data: bytes) -> tuple[int, int, bytearray]:
    """(幅, 高さ, RGBA の並び)。扱えない形なら ValueError。"""
    if data[:8] != SIG:
        raise ValueError("PNG ではない")
    pos, idat, plte, trns, hdr = 8, [], b"", b"", None
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8: pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if hdr is None:
        raise ValueError("IHDR が無い")
    w, h, depth, ctype, _c, _f, interlace = hdr
    if depth != 8 or interlace or ctype not in CHANNELS:
        raise ValueError(f"扱えない PNG(ビット {depth}・色 {ctype}・インターレース {interlace})")
    bpp = CHANNELS[ctype]
    px = _unfilter(zlib.decompress(b"".join(idat)), w, h, bpp)
    if ctype == 6:
        return w, h, px
    out = bytearray(w * h * 4)
    for i in range(w * h):
        if ctype == 2:
            r, g, b = px[i * 3: i * 3 + 3]
            a = 255
        elif ctype == 0:
            r = g = b = px[i]
            a = 255
        elif ctype == 4:
            r = g = b = px[i * 2]
            a = px[i * 2 + 1]
        else:   # パレット
            k = px[i]
            r, g, b = plte[k * 3: k * 3 + 3] if k * 3 + 3 <= len(plte) else (0, 0, 0)
            a = trns[k] if k < len(trns) else 255
        out[i * 4: i * 4 + 4] = bytes((r, g, b, a))
    return w, h, out


def resize(w: int, h: int, rgba: bytearray, size: int) -> bytearray:
    """縦横比を保って size×size に収め(余白は透明)、面積の平均で縮める。透明の縁が黒ずまないよう α を掛けてから平均する。"""
    scale = min(size / w, size / h)
    ow, oh = max(1, round(w * scale)), max(1, round(h * scale))
    ox, oy = (size - ow) // 2, (size - oh) // 2
    acc = [[0.0, 0.0, 0.0, 0.0, 0.0] for _ in range(ow * oh)]
    for y in range(h):
        ty = min(oh - 1, int(y * oh / h))
        row = y * w * 4
        for x in range(w):
            r, g, b, a = rgba[row + x * 4: row + x * 4 + 4]
            cell = acc[ty * ow + min(ow - 1, int(x * ow / w))]
            cell[0] += r * a
            cell[1] += g * a
            cell[2] += b * a
            cell[3] += a
            cell[4] += 1
    out = bytearray(size * size * 4)
    for y in range(oh):
        for x in range(ow):
            r, g, b, a, n = acc[y * ow + x]
            i = ((oy + y) * size + ox + x) * 4
            if a:
                out[i: i + 4] = bytes((round(r / a), round(g / a), round(b / a), round(a / n)))
    return out


def encode(w: int, h: int, rgba: bytes) -> bytes:
    """RGBA を PNG にする(フィルタ無し)。"""
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def thumbnail(data: bytes, size: int) -> bytes:
    """PNG か ICO のバイト列を size×size の PNG にする。扱えなければ ValueError。"""
    png = png_from_ico(data) if data[:4] == b"\x00\x00\x01\x00" else data
    if not png:
        raise ValueError("ICO の中に PNG が無い")
    w, h, rgba = decode(png)
    return encode(size, size, resize(w, h, rgba, size))

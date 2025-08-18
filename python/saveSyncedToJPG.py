import os
import math
import struct
import cv2
import numpy as np

# =========================
# Parametry użytkownika
# =========================
BASE_PATH = "/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test9/"
file1 = os.path.join(BASE_PATH, "camera1/cam_40334460_20250811_144135386.raw")
file2 = os.path.join(BASE_PATH, "camera2/cam_40334462_20250811_144135388.raw")

# maks. różnica czasu po normalizacji (w ns jednostek cam A)
MAX_TIME_DIFF_NS = 30_000_000  # 30 ms
# opcjonalny flip drugiej kamery: None (bez), 0 (pionowy), 1 (poziomy)
FLIP_MODE_B = 0

# Wyjście
OUTPUT_DIR = os.path.join(BASE_PATH, "synced_jpgs_new")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# Format pliku (musi pasować do recorder'a)
# =========================
# SessionHeader (packed, little-endian):
# quint32 magic 'RAWS' (0x52415753)
# quint16 version
# quint16 headerBytes (sizeof)
# quint16 width
# quint16 height
# quint16 pixelType (0=Mono8,1=BayerRG8,2=RGB8,3=BGR8,10=Mono12,11=BayerRG12)
# quint16 bitDepth (8,12,16)
# char[16] serial (zero-padded)
# quint64 sessionStartNs
SESSION_HDR_FMT  = "<IHHHHHH16sQ"
SESSION_HDR_SIZE = struct.calcsize(SESSION_HDR_FMT)

# FrameHeader:
# quint32 magic 'FRAM' (0x4652414D)
# quint64 timestampNs
# quint64 frameCounter
# quint32 dataBytes
FRAME_HDR_FMT    = "<IQQI"
FRAME_HDR_SIZE   = struct.calcsize(FRAME_HDR_FMT)

MAGIC_RAWE = 0x52415753  # 'RAWS'
MAGIC_FRAM = 0x4652414D  # 'FRAM'

PIXELTYPE = {0:"Mono8",1:"BayerRG8",2:"RGB8",3:"BGR8",10:"Mono12",11:"BayerRG12"}

# =========================
# I/O nagłówków
# =========================
def read_session_header(f):
    f.seek(0, os.SEEK_SET)
    data = f.read(SESSION_HDR_SIZE)
    if len(data) != SESSION_HDR_SIZE:
        raise RuntimeError("Plik za krótki na SessionHeader")
    (magic, version, headerBytes, w, h, pixelType, bitDepth, serial_bytes, sessionStartNs) = struct.unpack(
        SESSION_HDR_FMT, data
    )
    if magic != MAGIC_RAWE:
        raise RuntimeError(f"Zły magic w SessionHeader: {hex(magic)}")
    serial = serial_bytes.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
    return {
        "version": version,
        "headerBytes": headerBytes,
        "width": w,
        "height": h,
        "pixelType": pixelType,
        "bitDepth": bitDepth,
        "serial": serial,
        "sessionStartNs": sessionStartNs,
    }

def iter_frames_meta(path):
    """Generator: (data_offset, dataBytes, timestampNs, frameCounter)"""
    with open(path, "rb") as f:
        sess = read_session_header(f)
        f.seek(sess["headerBytes"], os.SEEK_SET)
        while True:
            hdr = f.read(FRAME_HDR_SIZE)
            if not hdr:
                break
            if len(hdr) != FRAME_HDR_SIZE:
                break
            magic, ts_ns, fc, nbytes = struct.unpack(FRAME_HDR_FMT, hdr)
            if magic != MAGIC_FRAM:
                raise RuntimeError(f"Zły magic FrameHeader @ {f.tell()-FRAME_HDR_SIZE}")
            data_off = f.tell()
            f.seek(nbytes, os.SEEK_CUR)
            yield (data_off, nbytes, ts_ns, fc)

def read_frame_data_at(path, data_off, data_bytes):
    with open(path, "rb") as f:
        f.seek(data_off, os.SEEK_SET)
        data = f.read(data_bytes)
        if len(data) != data_bytes:
            return None
        return data

# =========================
# Konwersje Bayer
# =========================
def bayer_rg8_to_rgb(frame_data, w, h):
    bayer = np.frombuffer(frame_data, dtype=np.uint8)
    if bayer.size != w * h:
        return None
    bayer = bayer.reshape((h, w))
    rgb = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
    return rgb  # uint8

def unpack_bayer12p_row_to_16u(row_bytes):
    # 3 bajty -> 2 piksele; utnij do wielokrotności 3
    n = (len(row_bytes) // 3) * 3
    rb = np.frombuffer(row_bytes[:n], np.uint8)
    b0 = rb[0::3].astype(np.uint16)
    b1 = rb[1::3].astype(np.uint16)
    b2 = rb[2::3].astype(np.uint16)
    p0 = (b0 | ((b1 & 0x0F) << 8))
    p1 = ((b1 >> 4) | (b2 << 4))
    out = np.empty(b0.size + p1.size, dtype=np.uint16)
    out[0::2] = p0
    out[1::2] = p1
    return out

def unpack_bayer12p_to_16u(buf, w, h, nbytes=None):
    """
    Rozpakowuje Bayer 12-bit 'packed' z możliwym paddingiem wierszy.
    Każdy wiersz czytamy osobno; stride wyznaczamy z całkowitej długości bufora.
    """
    data = np.frombuffer(buf, np.uint8)
    min_row = math.ceil(w * 12 / 8.0)         # minimalna liczba bajtów/pikseli bez paddingu
    # stride (bajty/wiersz) – oszacuj z nbytes/h; jeśli za mały, użyj min_row
    stride = int(len(data) // h) if h > 0 else len(data)
    if stride < min_row:
        stride = min_row
    out = np.empty((h, w), dtype=np.uint16)
    off = 0
    for y in range(h):
        row = data[off:off+stride]
        useful = row[:min_row]                 # reszta to padding
        vals = unpack_bayer12p_row_to_16u(useful)
        # dopasuj długość dokładnie do w
        if vals.size < w:
            vals = np.pad(vals, (0, w - vals.size), mode='edge')
        elif vals.size > w:
            vals = vals[:w]
        out[y, :] = vals
        off += stride
    return out

def to_rgb_from_meta(path, sess, meta, prefer_rgb8=True):
    """meta=(off,nbytes,ts,fc) -> RGB8 (lub RGB16 jeśli prefer_rgb8=False i dane 12/16-bit)"""
    off, nbytes, ts, _ = meta
    raw = read_frame_data_at(path, off, nbytes)
    if raw is None:
        return None

    w = sess["width"]; h = sess["height"]; pt = sess["pixelType"]; bd = sess["bitDepth"]

    if pt == 1 and bd == 8:   # BayerRG8
        return bayer_rg8_to_rgb(raw, w, h)

    if pt == 11 and bd in (12, 16):  # BayerRG12 (packed/unpacked)
        packed_bytes   = int(math.ceil(w*h*12/8.0))
        unpacked_bytes = w*h*2

        if nbytes == unpacked_bytes:
            b16 = np.frombuffer(raw, np.uint16).reshape((h, w))
        else:
            # traktuj jako packed z paddingiem wierszy
            b16 = unpack_bayer12p_to_16u(raw, w, h, nbytes=nbytes)

        rgb16 = cv2.cvtColor(b16, cv2.COLOR_BayerRG2RGB)
        if prefer_rgb8:
            return (rgb16 >> 4).astype(np.uint8)  # szybki podgląd
        return rgb16

    if pt == 0 and bd == 8:   # Mono8
        g = np.frombuffer(raw, np.uint8).reshape((h, w))
        return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)

    raise RuntimeError(f"Nieobsługiwany pixelType={pt} bitDepth={bd} (nbytes={nbytes})")

# =========================
# Parowanie po czasie (ze skalowaniem)
# =========================
def load_session(path):
    with open(path, "rb") as f:
        sess = read_session_header(f)
    frames = list(iter_frames_meta(path))
    return sess, frames

def robust_median_step(ts):
    if len(ts) < 2:
        return 1.0
    d = np.diff(np.array(ts, dtype=np.float64))
    d = d[d > 0]
    if d.size == 0:
        return 1.0
    return float(np.median(d))

def pair_by_scaled_time(frA, frB, max_diff_ns):
    tA = np.array([x[2] for x in frA], dtype=np.float64)
    tB = np.array([x[2] for x in frB], dtype=np.float64)
    # usuń offset
    tA -= tA[0]; tB -= tB[0]
    # skala (robusta)
    sA = robust_median_step(tA)
    sB = robust_median_step(tB)
    scale = 1.0 if (sA <= 0 or sB <= 0) else (sA / sB)
    tB_scaled = tB * scale

    i = j = 0
    pairs = []
    while i < len(tA) and j < len(tB_scaled):
        diff = tA[i] - tB_scaled[j]
        ad = abs(diff)
        if ad <= max_diff_ns:
            pairs.append((i, j, int(tA[i]), int(tB_scaled[j]), int(ad)))
            i += 1; j += 1
        elif diff > 0:
            j += 1
        else:
            i += 1
    return pairs, scale, sA, sB

# =========================
# Start
# =========================
print("== Sesja A ==")
sessA, framesA = load_session(file1)
print(f"A: {file1}")
print(f"  {sessA['width']}x{sessA['height']}  pixelType={PIXELTYPE.get(sessA['pixelType'], sessA['pixelType'])}  bitDepth={sessA['bitDepth']}  frames={len(framesA)}")

print("== Sesja B ==")
sessB, framesB = load_session(file2)
print(f"B: {file2}")
print(f"  {sessB['width']}x{sessB['height']}  pixelType={PIXELTYPE.get(sessB['pixelType'], sessB['pixelType'])}  bitDepth={sessB['bitDepth']}  frames={len(framesB)}")

print("== Parowanie z auto-skalą czasu ==")
pairs, scale, sA, sB = pair_by_scaled_time(framesA, framesB, MAX_TIME_DIFF_NS)
print(f"  median step A: {sA:.1f}, median step B: {sB:.1f}, scale B->A: {scale:.6f}")
print(f"  znalezione pary: {len(pairs)} w oknie ±{MAX_TIME_DIFF_NS/1e6:.1f} ms")

if not pairs:
    raise SystemExit("Brak par — zwiększ okno albo sprawdź timestampy w RAW.")

saved = 0
for k, (iA, iB, tAs, tBs, diff) in enumerate(pairs):
    rgbA = to_rgb_from_meta(file1, sessA, framesA[iA], prefer_rgb8=True)
    rgbB = to_rgb_from_meta(file2, sessB, framesB[iB], prefer_rgb8=True)
    if rgbA is None or rgbB is None:
        print(f"[WARN] para {k}: nie udało się wczytać/konwertować")
        continue

    if FLIP_MODE_B is not None:
        rgbB = cv2.flip(rgbB, FLIP_MODE_B)

    if rgbA.shape != rgbB.shape:
        rgbB = cv2.resize(rgbB, (rgbA.shape[1], rgbA.shape[0]))

    combined = cv2.hconcat([rgbA, rgbB])
    fn = f"{k:04d}_tA_{tAs}_tB_{tBs}_diff_{int(diff/1e6)}ms.jpg"
    cv2.imwrite(os.path.join(OUTPUT_DIR, fn), combined)
    saved += 1

print(f"Saved {saved} synchronized JPEGs to {OUTPUT_DIR}")

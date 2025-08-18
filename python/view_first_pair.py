import os, math, struct, cv2, numpy as np

# === ŚCIEŻKI (Twoje) ===
BASE_PATH = "/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test9/"
A_PATH = os.path.join(BASE_PATH, "camera1/cam_40334460_20250811_144135386.raw")
B_PATH = os.path.join(BASE_PATH, "camera2/cam_40334462_20250811_144135388.raw")
OUT_DIR = os.path.join(BASE_PATH, "first_pair_view")
os.makedirs(OUT_DIR, exist_ok=True)

FLIP_MODE_B = 0            # pionowy flip dla B
MAX_TIME_DIFF_NS = 30_000_000

# === Nagłówki RAW ===
SESSION_HDR_FMT  = "<IHHHHHH16sQ"
FRAME_HDR_FMT    = "<IQQI"
SESSION_HDR_SIZE = struct.calcsize(SESSION_HDR_FMT)
FRAME_HDR_SIZE   = struct.calcsize(FRAME_HDR_FMT)
MAGIC_RAWE = 0x52415753
MAGIC_FRAM = 0x4652414D

def read_session_header(f):
    f.seek(0, os.SEEK_SET)
    b = f.read(SESSION_HDR_SIZE)
    if len(b) != SESSION_HDR_SIZE: raise RuntimeError("SessionHeader too short")
    magic, ver, hdrB, w, h, pt, bd, serialB, startNs = struct.unpack(SESSION_HDR_FMT, b)
    if magic != MAGIC_RAWE: raise RuntimeError("Bad RAWS magic")
    serial = serialB.split(b"\x00",1)[0].decode("utf-8","ignore")
    return {"ver":ver,"hdrB":hdrB,"w":w,"h":h,"pt":pt,"bd":bd,"serial":serial,"startNs":startNs}

def iter_frames_meta(path):
    with open(path,"rb") as f:
        s = read_session_header(f)
        f.seek(s["hdrB"], os.SEEK_SET)
        while True:
            h = f.read(FRAME_HDR_SIZE)
            if not h: break
            if len(h) != FRAME_HDR_SIZE: break
            magic, ts, fc, nbytes = struct.unpack(FRAME_HDR_FMT, h)
            if magic != MAGIC_FRAM: raise RuntimeError("Bad FRAM magic")
            data_off = f.tell()
            f.seek(nbytes, os.SEEK_CUR)
            yield (data_off, nbytes, ts, fc)

def read_frame_data_at(path, off, nbytes):
    with open(path,"rb") as f:
        f.seek(off, os.SEEK_SET)
        b = f.read(nbytes)
        return b if len(b)==nbytes else None

# === Bayer12p z paddingiem wierszy → 16-bit ===
def unpack_bayer12p_row_to_16u(row_bytes):
    n = (len(row_bytes)//3)*3
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

def unpack_bayer12p_to_16u(buf, w, h):
    data = np.frombuffer(buf, np.uint8)
    min_row = math.ceil(w*12/8.0)
    stride = int(len(data)//h) if h>0 else len(data)
    if stride < min_row: stride = min_row
    out = np.empty((h, w), dtype=np.uint16)
    off = 0
    for y in range(h):
        row = data[off:off+stride]
        vals = unpack_bayer12p_row_to_16u(row[:min_row])
        if vals.size < w: vals = np.pad(vals, (0, w-vals.size), mode='edge')
        elif vals.size > w: vals = vals[:w]
        out[y,:] = vals
        off += stride
    return out

def to_gray8_from_meta(path, sess, meta):
    off, nbytes, ts, _ = meta
    raw = read_frame_data_at(path, off, nbytes)
    if raw is None: return None
    w, h, pt, bd = sess["w"], sess["h"], sess["pt"], sess["bd"]

    if pt == 11 and bd in (12,16):  # BayerRG12 (packed/unpacked)
        if nbytes == w*h*2:
            b16 = np.frombuffer(raw, np.uint16).reshape((h,w))
        else:
            b16 = unpack_bayer12p_to_16u(raw, w, h)
        rgb16 = cv2.cvtColor(b16, cv2.COLOR_BayerRG2RGB)
        gray16 = cv2.cvtColor(rgb16, cv2.COLOR_RGB2GRAY)
        gray8 = (gray16 >> 4).astype(np.uint8)
        return gray8
    elif pt == 1 and bd == 8:  # BayerRG8
        bayer = np.frombuffer(raw, np.uint8).reshape((h,w))
        rgb = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    elif pt == 0 and bd == 8:  # Mono8
        return np.frombuffer(raw, np.uint8).reshape((h,w))
    else:
        raise RuntimeError(f"Unsupported pixelType={pt} bitDepth={bd}")

def load_session(path):
    with open(path,"rb") as f:
        s = read_session_header(f)
    frames = list(iter_frames_meta(path))
    return s, frames

def robust_median_step(ts):
    if len(ts) < 2: return 1.0
    d = np.diff(np.asarray(ts, dtype=np.float64)); d = d[d>0]
    return float(np.median(d)) if d.size else 1.0

def pair_by_scaled_time(frA, frB, max_diff_ns):
    tA = np.array([x[2] for x in frA], dtype=np.float64)
    tB = np.array([x[2] for x in frB], dtype=np.float64)
    tA -= tA[0]; tB -= tB[0]
    sA = robust_median_step(tA); sB = robust_median_step(tB)
    scale = 1.0 if (sA<=0 or sB<=0) else (sA/sB)
    tB_sc = tB * scale
    i=j=0; pairs=[]
    while i < len(tA) and j < len(tB_sc):
        diff = tA[i]-tB_sc[j]
        if abs(diff) <= max_time_diff_ns:
            pairs.append((i,j,int(tA[i]),int(tB_sc[j]),int(abs(diff))))
            i+=1; j+=1
        elif diff>0: j+=1
        else: i+=1
    return pairs

# ——— RUN ———
sessA, framesA = load_session(A_PATH)
sessB, framesB = load_session(B_PATH)
max_time_diff_ns = MAX_TIME_DIFF_NS

pairs = pair_by_scaled_time(framesA, framesB, max_time_diff_ns)
if not pairs:
    raise SystemExit("Brak par (czas)!")

iA, iB, tA, tB, diff = pairs[0]
gA = to_gray8_from_meta(A_PATH, sessA, framesA[iA])
gB = to_gray8_from_meta(B_PATH, sessB, framesB[iB])

cv2.imwrite(os.path.join(OUT_DIR, "A_gray.png"), gA)
cv2.imwrite(os.path.join(OUT_DIR, "B_gray.png"), gB)

if FLIP_MODE_B is not None:
    gBf = cv2.flip(gB, FLIP_MODE_B)
else:
    gBf = gB.copy()
cv2.imwrite(os.path.join(OUT_DIR, "B_gray_flipped.png"), gBf)

# side-by-side
sb = cv2.hconcat([gA, gBf])
cv2.imwrite(os.path.join(OUT_DIR, "pair_side_by_side.png"), sb)

# checkerboard overlay (A vs B_flipped)
h, w = gA.shape
tiles = 64
mask = ((np.indices((h,w)).sum(axis=0) // tiles) % 2).astype(np.uint8)
checker = (mask*gBf + (1-mask)*gA).astype(np.uint8)
cv2.imwrite(os.path.join(OUT_DIR, "pair_checker.png"), checker)

print("Zapisane do:", OUT_DIR)
print(f"Użyta para: A[{iA}] ts={tA}  B[{iB}] ts={tB}  |Δ|={diff/1e6:.1f} ms")

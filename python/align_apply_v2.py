# align_apply.py
import os, math, struct, cv2, numpy as np
import glob

# ====== ŚCIEŻKI ======
BASE_PATH = "/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test11/"

# Szukamy pierwszego (i jedynego) pliku .raw w folderze camera1
a_files = glob.glob(os.path.join(BASE_PATH, "camera1", "*.raw"))
b_files = glob.glob(os.path.join(BASE_PATH, "camera2", "*.raw"))

# Pobieramy pierwszy znaleziony
A_PATH = a_files[0] if a_files else None
B_PATH = b_files[0] if b_files else None
OUT_DIR = os.path.join(BASE_PATH, "align_out")
ALIGN_PATH = os.path.join(BASE_PATH, "align_out/alignment.npz")

OUT_DIR   = os.path.join(BASE_PATH, "aligned_pairs")
OUT_A2B   = os.path.join(OUT_DIR, "A_to_B")          # A przemapowane do geometrii B (RGB)
OUT_A     = os.path.join(OUT_DIR, "A")               # oryginalna klatka A (RGB)
OUT_B     = os.path.join(OUT_DIR, "B")               # prawdziwa klatka B (RGB, po flipie jeśli był)
OUT_CONC  = os.path.join(OUT_DIR, "concat_B_AtoB")   # [B | A->B] (RGB)
for d in (OUT_DIR, OUT_A2B, OUT_A, OUT_B, OUT_CONC):
    os.makedirs(d, exist_ok=True)

# ====== Parametry ======
MAX_TIME_DIFF_NS = 30_000_000
SAVE_FORMAT = "png"   # "png" lub "jpg"

# ====== Nagłówki RAW ======
SESSION_HDR_FMT  = "<IHHHHHH16sQ"
FRAME_HDR_FMT    = "<IQQI"
SESSION_HDR_SIZE = struct.calcsize(SESSION_HDR_FMT)
FRAME_HDR_SIZE   = struct.calcsize(FRAME_HDR_FMT)
MAGIC_RAWE = 0x52415753
MAGIC_FRAM = 0x4652414D
PIXELTYPE = {0:"Mono8",1:"BayerRG8",2:"RGB8",3:"BGR8",10:"Mono12",11:"BayerRG12"}

# ---------- RAW IO ----------
def read_session_header(f):
    f.seek(0, os.SEEK_SET)
    b = f.read(SESSION_HDR_SIZE)
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

# ---------- Bayer 12p (z paddingiem) ----------
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

def to_rgb8_from_meta(path, sess, meta):
    off, nbytes, ts, _ = meta
    raw = read_frame_data_at(path, off, nbytes)
    if raw is None: return None
    w, h, pt, bd = sess["w"], sess["h"], sess["pt"], sess["bd"]

    if pt == 1 and bd == 8:   # BayerRG8
        bayer = np.frombuffer(raw, np.uint8).reshape((h,w))
        rgb = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
        return rgb

    if pt == 11 and bd in (12,16):  # BayerRG12
        if nbytes == w*h*2:
            b16 = np.frombuffer(raw, np.uint16).reshape((h,w))
        else:
            b16 = unpack_bayer12p_to_16u(raw, w, h)
        rgb16 = cv2.cvtColor(b16, cv2.COLOR_BayerRG2RGB)
        rgb8 = (rgb16 >> 4).astype(np.uint8)
        return rgb8

    if pt == 0 and bd == 8:   # Mono8 → RGB
        g = np.frombuffer(raw, np.uint8).reshape((h,w))
        return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)

    raise RuntimeError(f"Unsupported pixelType={pt} bitDepth={bd} nbytes={nbytes}")

# ---------- Parowanie po czasie ----------
def load_session(path):
    with open(path,"rb") as f:
        sess = read_session_header(f)
    frames = list(iter_frames_meta(path))
    return sess, frames

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
        if abs(diff) <= max_diff_ns:
            pairs.append((i,j,int(tA[i]),int(tB_sc[j]),int(abs(diff))))
            i+=1; j+=1
        elif diff>0: j+=1
        else: i+=1
    return pairs

# ---------- MAIN ----------
print("== Wczytuję alignment ==")
al = np.load(ALIGN_PATH, allow_pickle=True)
H_B2A = al["H_B2A"]
H_A2B = al["H_A2B"] if "H_A2B" in al else np.linalg.inv(H_B2A)
flipB = int(al["flipB"]) if "flipB" in al else 0

sessA, framesA = load_session(A_PATH)
sessB, framesB = load_session(B_PATH)

pairs = pair_by_scaled_time(framesA, framesB, MAX_TIME_DIFF_NS)
print(f"Par do przetworzenia: {len(pairs)}")

saved = 0
for k,(iA,iB,_,_,_) in enumerate(pairs):
    # RGB8 z RAW
    rgbA = to_rgb8_from_meta(A_PATH, sessA, framesA[iA])
    rgbB = to_rgb8_from_meta(B_PATH, sessB, framesB[iB])
    if rgbA is None or rgbB is None:
        print(f"[{k}] brak obrazu"); continue

    # flip B (tak jak przy estymacji)
    if flipB is not None:
        rgbB = cv2.flip(rgbB, flipB)

    # A -> B (RGB, bez konwersji do BGR)
    A2B = cv2.warpPerspective(rgbA, H_A2B, (sessB["w"], sessB["h"]),
                              flags=cv2.INTER_LANCZOS4,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    # konkatenacja: B | A→B (w RGB)
    concat = cv2.hconcat([A2B, rgbB])

    fn = f"{k:04d}.{SAVE_FORMAT}"
    cv2.imwrite(os.path.join(OUT_A2B, fn), A2B)
    cv2.imwrite(os.path.join(OUT_A,   fn), rgbA)
    cv2.imwrite(os.path.join(OUT_B,   fn), rgbB)
    cv2.imwrite(os.path.join(OUT_CONC,fn), concat)

    saved += 1

print(f"Zapisano {saved} par do {OUT_DIR}")

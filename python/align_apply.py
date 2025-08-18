# align_apply.py
import os, math, struct, cv2, numpy as np

# ====== ŚCIEŻKI ======
BASE_PATH = "/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test9/"
A_PATH = os.path.join(BASE_PATH, "camera1/cam_40334460_20250812_113148569.raw")
B_PATH = os.path.join(BASE_PATH, "camera2/cam_40334462_20250812_113148571.raw")
ALIGN_PATH = os.path.join(BASE_PATH, "align_out/alignment.npz")

OUT_DIR = os.path.join(BASE_PATH, "aligned_pairs")
OUT_A   = os.path.join(OUT_DIR, "A")
OUT_B   = os.path.join(OUT_DIR, "B")
OUT_B2A = os.path.join(OUT_DIR, "B_to_A")
OUT_MSK = os.path.join(OUT_DIR, "mask")
for d in (OUT_DIR, OUT_A, OUT_B, OUT_B2A, OUT_MSK): os.makedirs(d, exist_ok=True)

# ====== Parametry ======
MAX_TIME_DIFF_NS = 30_000_000
SAVE_FORMAT = "png"  # "png" (bezstratny) albo "jpg"
PNG_16BIT = False     # jeżeli True i masz 16-bit pipeline (tu robimy 8-bit podgląd)

# ====== Opcjonalny warp A_to_B (homografia + optical flow) ======
USE_OPTICAL_FLOW = False
OUT_A2B = os.path.join(OUT_DIR, "A_to_B")
if USE_OPTICAL_FLOW:
    os.makedirs(OUT_A2B, exist_ok=True)
# flow może być w kierunku A2B->B (forward) lub B->A2B (backward)
FLOW_DIR = os.path.join(OUT_DIR, "flows_numpy")  # np. z run_gma_on_aligned_v2.py
FLOW_DIRECTION = "A2B_to_B"  # "A2B_to_B" (forward splat) lub "B_to_A2B" (backward remap)
FLOW_BORDER_MODE = cv2.BORDER_CONSTANT
FLOW_BORDER_VALUE = (0,0,0)

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

# ---------- OF utils (dla A2B) ----------
def _natural_name(idx):
    return f"{idx:04d}.npy"

def _load_flow(path):
    try:
        f = np.load(path)
        if f.ndim==3 and f.shape[2]==2:
            return f.astype(np.float32)
    except Exception:
        pass
    return None

def _resize_flow(flow, W, H):
    if flow is None: return None
    h, w = flow.shape[:2]
    if (w, h) == (W, H):
        return flow
    sx = float(W)/max(w,1)
    sy = float(H)/max(h,1)
    u = cv2.resize(flow[...,0], (W, H), interpolation=cv2.INTER_LINEAR) * sx
    v = cv2.resize(flow[...,1], (W, H), interpolation=cv2.INTER_LINEAR) * sy
    return np.dstack([u,v]).astype(np.float32)

def _forward_splat(img, flow):
    # splatting A2B->B: każdy piksel p=(x,y) z A2B trafia do (x+u,y+v) w B
    H, W = img.shape[:2]
    out = np.zeros_like(img, dtype=np.float32)
    weight = np.zeros((H, W), dtype=np.float32)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    xs_t = xs + flow[...,0]
    ys_t = ys + flow[...,1]
    x0 = np.floor(xs_t).astype(np.int32)
    y0 = np.floor(ys_t).astype(np.int32)
    dx = xs_t - x0
    dy = ys_t - y0
    for oy in (0,1):
        for ox in (0,1):
            w = ((1-dx) if ox==0 else dx) * ((1-dy) if oy==0 else dy)
            xi = np.clip(x0+ox, 0, W-1)
            yi = np.clip(y0+oy, 0, H-1)
            w3 = w[...,None]
            out[yi, xi] += img.astype(np.float32) * w3
            weight[yi, xi] += w
    weight_safe = np.maximum(weight, 1e-6)
    out = (out / weight_safe[...,None]).astype(np.uint8)
    return out

# ---------- MAIN ----------
print("== Wczytuję alignment ==")
al = np.load(ALIGN_PATH, allow_pickle=True)
H_B2A = al["H_B2A"]
H_A2B = al["H_A2B"] if "H_A2B" in al else np.linalg.inv(H_B2A)
flipB = int(al["flipB"])
A_h, A_w = al["A_shape"][0], al["A_shape"][1]

sessA, framesA = load_session(A_PATH)
sessB, framesB = load_session(B_PATH)
pairs = pair_by_scaled_time(framesA, framesB, MAX_TIME_DIFF_NS)
print(f"Par do przetworzenia: {len(pairs)}")

# maska ważności: warp pełno-1 na siatkę A
onesB = np.ones((sessB["h"], sessB["w"]), np.uint8)*255

saved = 0
for k,(iA,iB,_,_,_) in enumerate(pairs):
    rgbA = to_rgb8_from_meta(A_PATH, sessA, framesA[iA])
    rgbB = to_rgb8_from_meta(B_PATH, sessB, framesB[iB])
    if rgbA is None or rgbB is None: 
        print(f"[{k}] brak obrazu"); continue

    if flipB is not None:
        rgbB = cv2.flip(rgbB, flipB)

    # warp B→A (jak dotąd)
    B2A = cv2.warpPerspective(rgbB, H_B2A, (A_w, A_h), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    msk = cv2.warpPerspective(np.ones((sessB["h"], sessB["w"]), np.uint8)*255, H_B2A, (A_w, A_h), flags=cv2.INTER_NEAREST,  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    msk = (msk > 0).astype(np.uint8)*255

    # opcjonalnie: warp A→B (A_to_B) + refinacja optical flow (A2B vs B)
    if USE_OPTICAL_FLOW:
        # A_to_B z homografii
        A2B = cv2.warpPerspective(rgbA, H_A2B, (sessB["w"], sessB["h"]), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        if flipB is not None:
            A2B = cv2.flip(A2B, flipB)  # utrzymaj tę samą orientację co B
        flow_path = os.path.join(FLOW_DIR, f"{k:04d}.npy")
        flow = _load_flow(flow_path)
        if flow is None:
            print(f"[{k}] brak flow: {flow_path}")
            A2B_ref = A2B
        else:
            flow = _resize_flow(flow, sessB["w"], sessB["h"])
            if FLOW_DIRECTION == "A2B_to_B":
                A2B_ref = _forward_splat(A2B, flow)
            else:  # B->A2B (backward remap)
                Ht, Wt = A2B.shape[:2]
                xs, ys = np.meshgrid(np.arange(Wt, dtype=np.float32), np.arange(Ht, dtype=np.float32))
                map_x = xs + flow[...,0]
                map_y = ys + flow[...,1]
                A2B_ref = cv2.remap(A2B, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=FLOW_BORDER_MODE, borderValue=FLOW_BORDER_VALUE)
        # zapis A_to_B (z lub bez OF)
        cv2.imwrite(os.path.join(OUT_A2B, f"{k:04d}.{SAVE_FORMAT}"), cv2.cvtColor(A2B_ref, cv2.COLOR_RGB2BGR))

    fn = f"{k:04d}.{SAVE_FORMAT}"
    cv2.imwrite(os.path.join(OUT_A, fn),  cv2.cvtColor(rgbA, cv2.COLOR_RGB2BGR))
    cv2.imwrite(os.path.join(OUT_B, fn),  cv2.cvtColor(rgbB, cv2.COLOR_RGB2BGR))
    cv2.imwrite(os.path.join(OUT_B2A, fn), cv2.cvtColor(B2A, cv2.COLOR_RGB2BGR))
    cv2.imwrite(os.path.join(OUT_MSK, fn), msk)
    saved += 1

print(f"Zapisano {saved} par do {OUT_DIR}")

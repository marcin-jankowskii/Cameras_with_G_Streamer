# align_estimate.py (rev. improved)
import os, math, struct, cv2, numpy as np
from datetime import datetime
import importlib.util, sys
import csv
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
os.makedirs(OUT_DIR, exist_ok=True)

# ====== Parametry ======
FLIP_MODE_B = 0         # None, 0(pion), 1(poziom) — u Ciebie pion
MAX_TIME_DIFF_NS = 30_000_000
NUM_PAIRS = 12          # ile par do estymacji (rozłożonych równomiernie)
RATIO_TEST = 0.80       # lekko luźniej przy multi-scale
MIN_MATCHES = 1        # minimalna liczba dopasowań po ratio
REPROJ_THRESH = 3.0     # px dla RANSAC/USAC
SEED = 42
np.random.seed(SEED)

# Multi-scale dla A (A widzi szerzej) — dopasowania liczymy dla kilku skal
MULTISCALE_S = [1.0]

# ====== ROI dla obrazu A (x, y, w, h) ======
A_ROI = (1236, 780, 1091, 465)
DEBUG_SEG_FULL_A = False  # gdy True, segmentuj pełne A (do diagnozy)

# ====== Sterowanie filtrowaniem outlierów (False = bez odrzucania) ======
OUTLIER_REJECTION = True
REJECTION_IQR_K = 3.0
MIN_KEEP_FRACTION = 0.7
MIN_KEEP_COUNT = 6
TOP_FRACTION_AFTER_FILTER = 1.0

# ====== Ulepszenia cech/szczegółów ======
USE_CLAHE_ENHANCE = False
CLAHE_CLIP = 2.0
CLAHE_TILE = (8,8)
UNSHARP_SIGMA = 1.0
UNSHARP_AMOUNT = 0.5  # 0..1
SIFT_NFEATURES = 8000
SIFT_CONTRAST = 0.03
SIFT_EDGE = 5
SIFT_SIGMA = 1.2

# ====== Sterowanie RANSAC/USAC przy homografii ======
USE_RANSAC_IN_H = False          # False -> użyj WSZYSTKICH dopasowań (method=0)
USE_INLIERS_FOR_METRICS = False  # False -> metryki liczone po wszystkich dopasowaniach

# ====== Konfiguracja segmentacji (SSSeg) ======
SSSEG_CFG = "/home/marcin/Documents/Projects/sssegmentation/ssseg/configs/vident_deeplabv3plus/exp09_adam_cosine_lr0001.py"
SSSEG_CKPT = "/home/marcin/Documents/Outputs/Ssseg_outputs/PLGRID_deeplabv3plus_exp09_adamW_cosine_lr001_gb30_s1-10_pm5_c95-105_s100-100_g10_CrossEntropyLoss_AUG+Sampler_v1_minlr1e-6_only_teeth/checkpoints-epoch-33.pth"

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

# ---------- Bayer 12p (z paddingiem wierszy) ----------
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
    """Zwraca 8-bit mono (kanał G/luma) z klatki (z debayer)."""
    off, nbytes, ts, _ = meta
    raw = read_frame_data_at(path, off, nbytes)
    if raw is None: return None
    w, h, pt, bd = sess["w"], sess["h"], sess["pt"], sess["bd"]

    if pt == 1 and bd == 8:   # BayerRG8
        bayer = np.frombuffer(raw, np.uint8).reshape((h,w))
        rgb = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        return gray

    if pt == 11 and bd in (12,16):  # BayerRG12 (packed/unpacked)
        if nbytes == w*h*2:
            b16 = np.frombuffer(raw, np.uint16).reshape((h,w))
        else:
            b16 = unpack_bayer12p_to_16u(raw, w, h)
        rgb16 = cv2.cvtColor(b16, cv2.COLOR_BayerRG2RGB)
        gray16 = cv2.cvtColor(rgb16, cv2.COLOR_RGB2GRAY)
        gray8 = (gray16 >> 4).astype(np.uint8)
        return gray8

    if pt == 0 and bd == 8:   # Mono8
        return np.frombuffer(raw, np.uint8).reshape((h,w))

    raise RuntimeError(f"Unsupported pixelType={pt} bitDepth={bd} nbytes={nbytes}")

def to_rgb8_from_meta(path, sess, meta):
    """Zwraca 8-bit RGB z klatki RAW (jak w align_apply_v2, bez WB/gamma)."""
    off, nbytes, ts, _ = meta
    raw = read_frame_data_at(path, off, nbytes)
    if raw is None: return None
    w, h, pt, bd = sess["w"], sess["h"], sess["pt"], sess["bd"]

    if pt == 1 and bd == 8:   # BayerRG8
        bayer = np.frombuffer(raw, np.uint8).reshape((h,w))
        rgb = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
        return rgb

    if pt == 11 and bd in (12,16):  # BayerRG12 (packed/unpacked)
        if nbytes == w*h*2:
            b16 = np.frombuffer(raw, np.uint16).reshape((h,w))
        else:
            b16 = unpack_bayer12p_to_16u(raw, w, h)
        rgb16 = cv2.cvtColor(b16, cv2.COLOR_BayerRG2RGB)
        rgb8 = (rgb16 >> 4).astype(np.uint8)
        return rgb8

    if pt == 0 and bd == 8:   # Mono8 -> RGB
        gray = np.frombuffer(raw, np.uint8).reshape((h,w))
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

    raise RuntimeError(f"Unsupported pixelType={pt} bitDepth={bd} nbytes={nbytes}")

# ---------- Parowanie po czasie (z auto-skalą) ----------
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
    return pairs, scale, sA, sB

# ---------- Cechy i Homografia ----------

def save_keypoints(img, kps, path):
    vis = cv2.drawKeypoints(img, kps, None, flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
    cv2.imwrite(path, vis)

def save_matches(imgA, imgB, kpA, kpB, matches, path, max_show=200):
    ms = sorted(matches, key=lambda m: m.distance)[:max_show]
    vis = cv2.drawMatches(imgA, kpA, imgB, kpB, ms, None,
                          flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    cv2.imwrite(path, vis)

def save_inlier_matches(imgA, imgB, kpA, kpB, matches, inlier_mask, path, max_show=200):
    if inlier_mask is None:
        return
    inl = [m for m, keep in zip(matches, inlier_mask.ravel().tolist()) if keep]
    if not inl:
        return
    inl = inl[:max_show]
    vis = cv2.drawMatches(imgA, kpA, imgB, kpB, inl, None,
                          matchColor=(0,255,0),
                          singlePointColor=(255,0,0),
                          flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    cv2.imwrite(path, vis)

def build_feature_extractor():
    # Preferuj SIFT -> AKAZE -> ORB
    sift = None
    try:
        sift = cv2.SIFT_create()
    except Exception:
        sift = None
    if sift is not None:
        return ("SIFT", sift)
    try:
        akaze = cv2.AKAZE_create()
        return ("AKAZE", akaze)
    except Exception:
        pass
    orb = cv2.ORB_create(nfeatures=4000, fastThreshold=7)
    return ("ORB", orb)

def _symmetric_ratio_matches(desA, desB, kind):
    if desA is None or desB is None or len(desA)==0 or len(desB)==0:
        return []
    if kind == "SIFT":
        index_params = dict(algorithm=1, trees=5)
        search_params = dict(checks=64)
        matcher = cv2.FlannBasedMatcher(index_params, search_params)
        matchesAB = matcher.knnMatch(desA, desB, k=2)
        matchesBA = matcher.knnMatch(desB, desA, k=2)
    else:
        # AKAZE/ORB -> Hamming
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        matchesAB = bf.knnMatch(desA, desB, k=2)
        matchesBA = bf.knnMatch(desB, desA, k=2)
    goodAB = {}
    for pair in matchesAB:
        if len(pair) < 2: continue
        m, n = pair
        if m.distance < RATIO_TEST * n.distance:
            goodAB[m.queryIdx] = m
    goodBA = {}
    for pair in matchesBA:
        if len(pair) < 2: continue
        m, n = pair
        if m.distance < RATIO_TEST * n.distance:
            goodBA[m.queryIdx] = m
    mutual = []
    for qIdx, mAB in goodAB.items():
        tIdx = mAB.trainIdx
        mBA = goodBA.get(tIdx, None)
        if mBA is not None and mBA.trainIdx == qIdx:
            mutual.append(mAB)
    return mutual

def detect_and_match(imgA, imgB, kind, extractor, maskA=None, maskB=None):
    kpA, desA = extractor.detectAndCompute(imgA, maskA)
    kpB, desB = extractor.detectAndCompute(imgB, maskB)
    if desA is None or desB is None: return [], [], None
    if kind == "SIFT":
        good = _symmetric_ratio_matches(desA, desB, kind="SIFT")
    else:
        good = _symmetric_ratio_matches(desA, desB, kind="AKAZE/ORB")
    return kpA, kpB, good

def choose_usac_method():
    # preferencja: USAC_MAGSAC -> USAC_ACCURATE -> RHO -> RANSAC
    for name in ["USAC_MAGSAC", "USAC_ACCURATE", "RHO", "RANSAC"]:
        m = getattr(cv2, name, None)
        if m is not None:
            return m
    return cv2.RANSAC

def estimate_H_from_matches(kpA, kpB, good):
    if good is None or len(good) < max(MIN_MATCHES, 4):
        return None, None
    ptsA = np.float32([kpA[m.queryIdx].pt for m in good])
    ptsB = np.float32([kpB[m.trainIdx].pt for m in good])
    if USE_RANSAC_IN_H:
        method = getattr(cv2, "USAC_MAGSAC", cv2.RANSAC)
        H, mask = cv2.findHomography(ptsA, ptsB, method=method, ransacReprojThreshold=REPROJ_THRESH, maxIters=5000, confidence=0.999)
    else:
        # użyj wszystkich dopasowań (bez RANSAC)
        H, mask = cv2.findHomography(ptsA, ptsB, method=0)
        if mask is None:
            mask = np.ones((len(good), 1), dtype=np.uint8)
    return H, mask

def reproj_error(H, ptsA, ptsB, inlierMask):
    if H is None or inlierMask is None: return 1e9
    inlA = ptsA[inlierMask.ravel().astype(bool)]
    inlB = ptsB[inlierMask.ravel().astype(bool)]
    if inlA.size == 0: return 1e9
    ptsA_h = cv2.convertPointsToHomogeneous(inlA)[:,0,:]
    proj = (H @ ptsA_h.T).T
    proj = proj[:, :2] / proj[:, 2:3]
    err = np.linalg.norm(proj - inlB, axis=1)
    return float(np.median(err)) if err.size else 1e9

def normalize_H(H):
    if H is None: return None
    if not np.isfinite(H).all(): return H
    if abs(H[2,2]) < 1e-12:
        # fallback – normalizacja przez normę Frobeniusa
        n = np.linalg.norm(H)
        return H / (n if n>0 else 1.0)
    return H / H[2,2]

def robust_aggregate_H(H_list):
    # (pozostawiam jako rezerwę – domyślnie użyjemy globalnego DLT na inlierach)
    Hs = [normalize_H(H) for H in H_list if H is not None and np.all(np.isfinite(H))]
    if not Hs: return None
    Hstack = np.stack(Hs, axis=0)  # N x 3 x 3
    Hmed = np.median(Hstack, axis=0)
    return normalize_H(Hmed)

def refine_homography_ecc(grayA, grayB, H_init, maskB=None, max_iters=200, eps=1e-6):
    # UWAGA: ECC szuka transformacji, która mapuje template -> input
    # Chcemy A->B, więc template=A, input=B
    try:
        H0 = normalize_H(H_init).astype(np.float32)
        gA32 = (grayA.astype(np.float32) / 255.0)
        gB32 = (grayB.astype(np.float32) / 255.0)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, int(max_iters), float(eps))
        if maskB is not None and hasattr(cv2, 'findTransformECC'):
            try:
                cc, H_ref = cv2.findTransformECC(gA32, gB32, H0, cv2.MOTION_HOMOGRAPHY, criteria, maskB)
            except Exception:
                cc, H_ref = cv2.findTransformECC(gA32, gB32, H0, cv2.MOTION_HOMOGRAPHY, criteria)
        else:
            cc, H_ref = cv2.findTransformECC(gA32, gB32, H0, cv2.MOTION_HOMOGRAPHY, criteria)
        return normalize_H(H_ref)
    except Exception:
        return normalize_H(H_init)

# ---------- QA ----------
def save_qa_images(A_gray, B_gray, H_A2B, out_prefix):
    h, w = A_gray.shape[:2]
    # warp A->B i B->A (dla podglądu)
    A2B = cv2.warpPerspective(A_gray, H_A2B, (B_gray.shape[1], B_gray.shape[0]), flags=cv2.INTER_LANCZOS4)
    H_B2A = np.linalg.inv(H_A2B)
    B2A = cv2.warpPerspective(B_gray, H_B2A, (w, h), flags=cv2.INTER_LANCZOS4)

    # false-color overlay
    overlay_A2B = np.zeros((B_gray.shape[0], B_gray.shape[1], 3), np.uint8)
    overlay_A2B[..., 1] = A2B  # G
    overlay_A2B[..., 2] = B_gray  # R
    cv2.imwrite(out_prefix + "_overlay_A2B.jpg", overlay_A2B)

    # checkerboard (A vs B2A)
    tiles = 32
    mask = np.indices((h,w)).sum(axis=0) // tiles % 2
    checker = (mask*B2A + (1-mask)*A_gray).astype(np.uint8)
    cv2.imwrite(out_prefix + "_checker_B2A.jpg", checker)

    # diff abs (po B2A)
    diff = cv2.absdiff(A_gray, B2A)
    cv2.imwrite(out_prefix + "_diff_B2A.jpg", diff)

    # split view (połowa A, połowa B2A)
    mid = w//2
    split = np.concatenate([A_gray[:, :mid], B2A[:, mid:]], axis=1)
    cv2.imwrite(out_prefix + "_split_B2A.jpg", split)

# ---------- Integracja segmentacji ----------
# Ładujemy 'ssseg/inference copy.py' jako moduł 'ssseg.inference_copy' mimo spacji w nazwie pliku
_INF_MOD = None
def _load_infer_module():
    global _INF_MOD
    if _INF_MOD is not None:
        return _INF_MOD
    mod_name = 'ssseg.inference_copy'
    root_dir = os.path.dirname(os.path.dirname(__file__)) if '__file__' in globals() else os.getcwd()
    mod_path = os.path.join(root_dir, 'inference copy.py')
    if not os.path.exists(mod_path):
        print(f"[SEG] Brak pliku inferencji: {mod_path}")
        return None
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    if spec is None or spec.loader is None:
        print("[SEG] Nie można utworzyć spec loadera")
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        __import__('ssseg')
    except Exception:
        pass
    try:
        spec.loader.exec_module(module)  # type: ignore
    except Exception as e:
        print(f"[SEG] Ładowanie modułu nie powiodło się: {e}")
        return None
    _INF_MOD = module
    return _INF_MOD

def ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def write_temp_png(img, path):
    ensure_dir(path)
    # Zapis „as-is” (jak w align_apply_v2) – bez zmiany kolejności kanałów
    cv2.imwrite(path, img)
    return path

# Prosty cache masek (klucz: ('A' lub 'B', frame_idx))
_SEG_CACHE = {}

def compute_teeth_mask_for_B(img_for_seg, key=None):
    mod = _load_infer_module()
    if mod is None or not hasattr(mod, 'infer_mask'):
        return None
    if key is not None and key in _SEG_CACHE:
        return _SEG_CACHE[key]
    tmp_path = os.path.join(OUT_DIR, "tmp_B.png")
    write_temp_png(img_for_seg, tmp_path)
    try:
        mask = mod.infer_mask(tmp_path, SSSEG_CFG, SSSEG_CKPT, ema=False, annpath=None)
    except Exception as e:
        print(f"[SEG] B infer fail: {e}")
        mask = None
    if key is not None:
        _SEG_CACHE[key] = mask
    return mask

def compute_teeth_mask_for_A_roi(img_full_A, roi, key=None):
    mod = _load_infer_module()
    if mod is None or not hasattr(mod, 'infer_mask'):
        return None, roi
    if key is not None and key in _SEG_CACHE:
        return _SEG_CACHE[key], roi
    x, y, w, h = roi
    h_img, w_img = img_full_A.shape[:2]
    x = max(0, min(x, w_img-1))
    y = max(0, min(y, h_img-1))
    w = max(1, min(w, w_img - x))
    h = max(1, min(h, h_img - y))
    roi_img = img_full_A[y:y+h, x:x+w]
    tmp_path = os.path.join(OUT_DIR, "tmp_A_roi.png")
    write_temp_png(roi_img, tmp_path)
    try:
        mask_roi = mod.infer_mask(tmp_path, SSSEG_CFG, SSSEG_CKPT, ema=False, annpath=None)
    except Exception as e:
        print(f"[SEG] A ROI infer fail: {e}")
        mask_roi = None
    if key is not None:
        _SEG_CACHE[key] = mask_roi
    return mask_roi, (x, y, w, h)

def to_binary_mask(mask):
    if mask is None:
        return None
    return (mask != 0).astype(np.uint8) * 255

def roi_mask_to_full(image_shape, mask_roi, roi):
    if mask_roi is None:
        return None
    x, y, w, h = roi
    full = np.zeros(image_shape, dtype=np.uint8)
    bin_roi = to_binary_mask(mask_roi)
    full[y:y+h, x:x+w] = bin_roi[:h, :w]
    return full

def filter_matches_by_masks(kpA, kpB, matches, maskA_full, maskB_full):
    if matches is None or len(matches) == 0:
        return []
    if maskA_full is None and maskB_full is None:
        return matches
    filtered = []
    for m in matches:
        ptA = kpA[m.queryIdx].pt
        ptB = kpB[m.trainIdx].pt
        keep = True
        if maskA_full is not None:
            ax = int(round(ptA[0])); ay = int(round(ptA[1]))
            if ay < 0 or ax < 0 or ay >= maskA_full.shape[0] or ax >= maskA_full.shape[1]:
                keep = False
            else:
                keep = keep and (maskA_full[ay, ax] != 0)
        if keep and maskB_full is not None:
            bx = int(round(ptB[0])); by = int(round(ptB[1]))
            if by < 0 or bx < 0 or by >= maskB_full.shape[0] or bx >= maskB_full.shape[1]:
                keep = False
            else:
                keep = keep and (maskB_full[by, bx] != 0)
        if keep:
            filtered.append(m)
    return filtered

# --- Morfologia i fallbacki masek ---
def count_nonzero_mask(mask):
    if mask is None:
        return 0
    return int(np.count_nonzero(mask))

def dilate_mask(mask, ksize=21, iterations=1):
    if mask is None:
        return None
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    return cv2.dilate(mask, k, iterations=iterations)

def erode_mask(mask, ksize=9, iterations=1):
    if mask is None:
        return None
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    return cv2.erode(mask, k, iterations=iterations)

def rectangle_roi_mask(image_shape, roi):
    x, y, w, h = roi
    mask = np.zeros(image_shape, dtype=np.uint8)
    mask[y:y+h, x:x+w] = 255
    return mask

def ensure_nonempty_mask(mask, fallback_mask=None, min_pixels=2000):
    if mask is None:
        return fallback_mask
    if count_nonzero_mask(mask) >= min_pixels:
        return mask
    # spróbuj dylatacji
    m2 = dilate_mask(mask, ksize=31, iterations=2)
    if count_nonzero_mask(m2) >= min_pixels:
        return m2
    return fallback_mask

def save_mask_overlay(img, mask, path, color=(0,255,0), alpha=0.5):
    if mask is None:
        if img.ndim == 2:
            cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
        else:
            cv2.imwrite(path, img)
        return
    base = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    overlay = base.copy()
    m = mask > 0
    if m.any():
        color_arr = np.zeros_like(base, dtype=np.uint8)
        # parametr color jako RGB, obraz BGR – zamień kolejność
        color_arr[..., 0] = color[2]
        color_arr[..., 1] = color[1]
        color_arr[..., 2] = color[0]
        overlay[m] = (overlay[m] * (1.0 - alpha) + color_arr[m] * alpha).astype(np.uint8)
    cv2.imwrite(path, overlay)

# ================== MAIN ==================
print("== Wczytuję sesje ==")
sessA, framesA = load_session(A_PATH)
sessB, framesB = load_session(B_PATH)
print(f"A: {sessA['w']}x{sessA['h']}  pt={PIXELTYPE.get(sessA['pt'],sessA['pt'])}  bd={sessA['bd']}  frames={len(framesA)}")
print(f"B: {sessB['w']}x{sessB['h']}  pt={PIXELTYPE.get(sessB['pt'],sessB['pt'])}  bd={sessB['bd']}  frames={len(framesB)}")

pairs, scale, sA, sB = pair_by_scaled_time(framesA, framesB, MAX_TIME_DIFF_NS)
print(f"Par: {len(pairs)} (scale {scale:.6f})")
if not pairs: raise SystemExit("Brak par!")

# wybierz N par równomiernie
idxs = np.linspace(0, len(pairs)-1, num=min(NUM_PAIRS, len(pairs)), dtype=int)
sel_pairs = [pairs[i] for i in idxs]
print(f"Używam {len(sel_pairs)} par do estymacji.")

kind, extractor = build_feature_extractor()
print("Cechy:", kind)

Hs = []
stats = []
all_ptsA, all_ptsB = [], []

# CLAHE do preproc
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))

for k,(iA,iB,_,_,_) in enumerate(sel_pairs):
    gA = to_gray8_from_meta(A_PATH, sessA, framesA[iA])
    gB = to_gray8_from_meta(B_PATH, sessB, framesB[iB])
    cA = to_rgb8_from_meta(A_PATH, sessA, framesA[iA])
    cB = to_rgb8_from_meta(B_PATH, sessB, framesB[iB])
    if gA is None or gB is None:
        print(f"[{k}] brak obrazu"); 
        continue

    if FLIP_MODE_B is not None:
        gB = cv2.flip(gB, FLIP_MODE_B)
        if cB is not None:
            cB = cv2.flip(cB, FLIP_MODE_B)

    # --- segmentacja: B pełny, A tylko ROI ---
    srcB_for_seg = cB if cB is not None else cv2.cvtColor(gB, cv2.COLOR_GRAY2RGB)
    srcA_for_seg_full = cA if cA is not None else cv2.cvtColor(gA, cv2.COLOR_GRAY2RGB)

    maskB = compute_teeth_mask_for_B(srcB_for_seg, key=("B", iB))
    if DEBUG_SEG_FULL_A:
        tmp_path_fullA = os.path.join(OUT_DIR, f"dbg_pair_{k:02d}_A_full_for_seg.png")
        write_temp_png(srcA_for_seg_full, tmp_path_fullA)
        mod = _load_infer_module()
        if mod is not None and hasattr(mod, 'infer_mask'):
            maskA_roi = mod.infer_mask(tmp_path_fullA, SSSEG_CFG, SSSEG_CKPT, ema=False, annpath=None)
        else:
            maskA_roi = None
        rx, ry, rw, rh = 0, 0, srcA_for_seg_full.shape[1], srcA_for_seg_full.shape[0]
    else:
        maskA_roi, (rx, ry, rw, rh) = compute_teeth_mask_for_A_roi(srcA_for_seg_full, A_ROI, key=("A", iA))

    maskB_full = to_binary_mask(maskB)
    maskA_full = roi_mask_to_full(gA.shape[:2], maskA_roi, (rx, ry, rw, rh))

    # fallback: jeśli maski puste, A=prostokątny ROI, B=bez maski
    rectA = rectangle_roi_mask(gA.shape[:2], (rx, ry, rw, rh))
    maskA_full = ensure_nonempty_mask(maskA_full, fallback_mask=rectA, min_pixels=1000)
    maskB_full = ensure_nonempty_mask(maskB_full, fallback_mask=None, min_pixels=1000)

    # unikamy krawędzi masek (eroduj ~4px)
    maskA_full = erode_mask(maskA_full, ksize=9, iterations=1)
    maskB_full = erode_mask(maskB_full, ksize=9, iterations=1)

    # debug overlay masek
    dbg_pref = os.path.join(OUT_DIR, f"dbg_pair_{k:02d}")
    os.makedirs(OUT_DIR, exist_ok=True)
    save_mask_overlay(srcA_for_seg_full, maskA_full, dbg_pref + "_A_mask_overlay.jpg", color=(0,255,0), alpha=0.5)
    save_mask_overlay(srcB_for_seg, maskB_full, dbg_pref + "_B_mask_overlay.jpg", color=(0,0,255), alpha=0.5)
    cv2.imwrite(dbg_pref + "_A_infer_input.png", cv2.cvtColor(srcA_for_seg_full, cv2.COLOR_RGB2BGR))
    cv2.imwrite(dbg_pref + "_B_infer_input.png", cv2.cvtColor(srcB_for_seg, cv2.COLOR_RGB2BGR))

    # Preproc: CLAHE + lekki blur
    # gA_c = clahe.apply(gA)
    # gB_c = clahe.apply(gB)
    gA_c = gA
    gB_c = gB
    gA_p = cv2.GaussianBlur(gA_c, (3,3), 0)
    gB_p = cv2.GaussianBlur(gB_c, (3,3), 0)

    # ===== Multi-scale dla A =====
    best = None  # (inliers, -err, H_full, kpA_s, kpB_s, good_s, s_used, gA_s, inlier_mask)
    for s in MULTISCALE_S:
        if abs(s-1.0) < 1e-3:
            gA_s = gA_p
            sc_H = np.eye(3, dtype=np.float32)
            maskA_s = maskA_full
        else:
            gA_s = cv2.resize(gA_p, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s<1.0 else cv2.INTER_CUBIC)
            maskA_s = None
            if maskA_full is not None:
                maskA_s = cv2.resize(maskA_full, (gA_s.shape[1], gA_s.shape[0]), interpolation=cv2.INTER_NEAREST)
            sc_H = np.array([[1/s, 0, 0],[0, 1/s, 0],[0, 0, 1]], dtype=np.float32)  # potem przeskalujemy H do oryg. A

        kpA_s, kpB_s, good_s = detect_and_match(gA_s, gB_p, kind, extractor, maskA=maskA_s, maskB=maskB_full)
        good_s = filter_matches_by_masks(kpA_s, kpB_s, good_s, maskA_s, maskB_full)

        if good_s is None or len(good_s) < MIN_MATCHES:
            continue

        H_s, mask_s = estimate_H_from_matches(kpA_s, kpB_s, good_s)
        if H_s is None or mask_s is None:
            continue

        # Rozważ affine/similarity jako stabilniejszy model
        ptsA_s = np.float32([kpA_s[m.queryIdx].pt for m in good_s])
        ptsB_s = np.float32([kpB_s[m.trainIdx].pt for m in good_s])
        try:
            H_aff2, mask_aff = cv2.estimateAffine2D(ptsA_s, ptsB_s,
                                                    method=choose_usac_method(),
                                                    ransacReprojThreshold=REPROJ_THRESH,
                                                    maxIters=5000, confidence=0.999)
            H_aff = None if H_aff2 is None else normalize_H(np.vstack([H_aff2, [0,0,1]]))
        except Exception:
            H_aff = None
            mask_aff = None

        def _err_of(Htest, msk):
            if Htest is None or msk is None: return 1e9
            return reproj_error(Htest, ptsA_s, ptsB_s, msk)

        err_H = _err_of(H_s, mask_s)
        err_A = _err_of(H_aff, mask_aff)
        if err_A + 0.2 < err_H:
            H_use, mask_use, err_use = H_aff, mask_aff, err_A
        else:
            H_use, mask_use, err_use = H_s,   mask_s,   err_H

        # przeskaluj H_use do układu oryginalnego A
        H_full = normalize_H(H_use @ sc_H)
        inl_s = int(mask_use.sum()) if mask_use is not None else 0
        cand = (inl_s, -err_use, H_full, kpA_s, kpB_s, good_s, s, gA_s, mask_use)
        if best is None or cand > best:
            best = cand

    if best is None:
        print(f"[{k}] Za mało dopasowań po multi-scale")
        continue

    inl, neg_err, H, kpA_s, kpB_s, good, s_used, gA_used, inlier_mask = best

    # === DEBUG WIZUALIZACJE CECH ===
    save_keypoints(gA_used, kpA_s, dbg_pref + "_A_keypoints.jpg")
    save_keypoints(gB_p,   kpB_s, dbg_pref + "_B_keypoints.jpg")
    if good is not None and len(good) > 0:
        save_matches(gA_used, gB_p, kpA_s, kpB_s, good, dbg_pref + "_matches_ratio.jpg", max_show=200)

    # zapis dopasowań: inliers lub wszystkie (gdy USE_RANSAC_IN_H=False)
    eff_mask = inlier_mask if (USE_RANSAC_IN_H and inlier_mask is not None) else np.ones((len(good),1), dtype=np.uint8)
    save_inlier_matches(gA_used, gB_p, kpA_s, kpB_s, good, eff_mask, dbg_pref + "_matches_inliers.jpg", max_show=200)

    # metryki
    ptsA = np.float32([kpA_s[m.queryIdx].pt for m in good])
    ptsB = np.float32([kpB_s[m.trainIdx].pt for m in good])
    metr_mask = inlier_mask if (USE_INLIERS_FOR_METRICS and inlier_mask is not None) else np.ones((len(good),1), dtype=np.uint8)
    err = reproj_error(H, ptsA, ptsB, metr_mask)
    inl = int(inlier_mask.sum()) if (USE_RANSAC_IN_H and inlier_mask is not None) else len(good)

    print(f"[{k}] inliers={inl}/{len(good)}  median_err={err:.2f}px  scale_used={s_used:.2f}")
    Hs.append(H)
    stats.append((k, inl, err))

    # zbierz inliery do globalnego re-estymatora
    if inlier_mask is not None:
        inmask = inlier_mask.ravel().astype(bool)
        if inmask.any():
            all_ptsA.append(ptsA[inmask])
            all_ptsB.append(ptsB[inmask])

# wybór robust H*
if not Hs:
    raise SystemExit("Nie udało się policzyć żadnej H.")

# odrzuć outliery wg błędu (opcjonalnie)
if OUTLIER_REJECTION:
    errs = np.array([e for _,_,e in stats])
    med = np.median(errs)
    irq = np.percentile(errs,75) - np.percentile(errs,25)
    thr = med + REJECTION_IQR_K*irq
    keep_idx = [i for i,(k,_,e) in enumerate(stats) if e <= thr]
    if not keep_idx:
        keep_idx = list(range(len(Hs)))
    min_keep = max(int(np.ceil(MIN_KEEP_FRACTION*len(Hs))), MIN_KEEP_COUNT)
    if len(keep_idx) < min_keep:
        order_err = np.argsort(errs)
        for idx in order_err:
            if idx not in keep_idx:
                keep_idx.append(idx)
            if len(keep_idx) >= min_keep:
                break
    if TOP_FRACTION_AFTER_FILTER < 1.0:
        inliers_list = np.array([stats[i][1] for i in keep_idx])
        order = np.argsort(-inliers_list)
        top_n = int(np.ceil(TOP_FRACTION_AFTER_FILTER * len(keep_idx)))
        top_n = max(1, top_n)
        sel = [keep_idx[i] for i in order[:top_n]]
        keep = [Hs[i] for i in sel]
    else:
        keep = [Hs[i] for i in keep_idx]
else:
    keep = Hs

# Globalny re-DLT na sklejonych inlierach (preferowane)
if all_ptsA and all_ptsB:
    A_cat = np.vstack(all_ptsA)
    B_cat = np.vstack(all_ptsB)
    H_star, _ = cv2.findHomography(A_cat, B_cat, method=0)  # DLT (bez RANSAC – mamy już inliery)
    H_star = normalize_H(H_star)
else:
    H_star = normalize_H(robust_aggregate_H(keep))

H_inv  = np.linalg.inv(H_star)

print("Wybrana H*:\n", H_star)

# QA na środkowej parze
iA,iB,_,_,_ = sel_pairs[len(sel_pairs)//2]
gA = to_gray8_from_meta(A_PATH, sessA, framesA[iA])
gB = to_gray8_from_meta(B_PATH, sessB, framesB[iB])
if FLIP_MODE_B is not None:
    gB = cv2.flip(gB, FLIP_MODE_B)
qa_prefix = os.path.join(OUT_DIR, "qa")
save_qa_images(gA, gB, H_star, qa_prefix)

# lokalna refinacja H* metodą ECC na parze QA (A->B, poprawiona kolejność)
try:
    H_star_ref = refine_homography_ecc(gA, gB, H_star, maskB=None, max_iters=300, eps=1e-7)
    if np.all(np.isfinite(H_star_ref)):
        H_star = H_star_ref
        H_inv  = np.linalg.inv(H_star)
        save_qa_images(gA, gB, H_star, qa_prefix + "_refined")
except Exception as e:
    print(f"[ECC] Refinement error: {e}")

# zapis alignmentu
np.savez(os.path.join(OUT_DIR, "alignment.npz"),
         H_A2B=H_star, H_B2A=H_inv,
         flipB=FLIP_MODE_B,
         A_shape=(sessA["h"], sessA["w"]),
         B_shape=(sessB["h"], sessB["w"]),
         stats=np.array(stats, dtype=object))

# CSV statystyk par
with open(os.path.join(OUT_DIR, "pair_stats.csv"), "w", newline="") as f:
    wcsv = csv.writer(f)
    wcsv.writerow(["pair_k","inliers","median_err_px"])
    for (k,inl,err) in stats:
        wcsv.writerow([k,inl,err])

print("Zapisano:", os.path.join(OUT_DIR, "alignment.npz"))
print("QA zapisane z prefiksem:", qa_prefix)

import os
import math
import struct
import argparse
import numpy as np
import cv2
import torch

# ====== RAW nagłówki ======
SESSION_HDR_FMT  = "<IHHHHHH16sQ"
FRAME_HDR_FMT    = "<IQQI"
SESSION_HDR_SIZE = struct.calcsize(SESSION_HDR_FMT)
FRAME_HDR_SIZE   = struct.calcsize(FRAME_HDR_FMT)
MAGIC_RAWE = 0x52415753
MAGIC_FRAM = 0x4652414D
PIXELTYPE = {0:"Mono8",1:"BayerRG8",2:"RGB8",3:"BGR8",10:"Mono12",11:"BayerRG12"}

# ====== Parametry domyślne ======
FLIP_MODE_B = 0   # None, 0(pion), 1(poziom) — zgodnie z align_estimate
MAX_TIME_DIFF_NS = 30_000_000
# Stały ROI A (x,y,w,h) jak w align_estimate
A_ROI = (1236, 780, 1091, 465)
FULL_MAX_WH = 1280  # maksymalny dłuższy bok przy liczeniu full-frame flow (dla prędkości)
ROI_MAX_WH = 1024   # maksymalny dłuższy bok ROI dla liczenia flow (downscale→flow→upscale)

# ====== IO RAW ======
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

# ====== Bayer 12p ======
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

# ====== Konwersje obrazów ======
def to_rgb8_from_meta(path, sess, meta):
    off, nbytes, ts, _ = meta
    raw = read_frame_data_at(path, off, nbytes)
    if raw is None: return None
    w, h, pt, bd = sess["w"], sess["h"], sess["pt"], sess["bd"]
    if pt == 1 and bd == 8:
        bayer = np.frombuffer(raw, np.uint8).reshape((h,w))
        rgb = cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)
        return rgb
    if pt == 11 and bd in (12,16):
        if nbytes == w*h*2:
            b16 = np.frombuffer(raw, np.uint16).reshape((h,w))
        else:
            b16 = unpack_bayer12p_to_16u(raw, w, h)
        rgb16 = cv2.cvtColor(b16, cv2.COLOR_BayerRG2RGB)
        rgb8 = (rgb16 >> 4).astype(np.uint8)
        return rgb8
    if pt == 0 and bd == 8:
        g = np.frombuffer(raw, np.uint8).reshape((h,w))
        return cv2.cvtColor(g, cv2.COLOR_GRAY2RGB)
    raise RuntimeError(f"Unsupported pixelType={pt} bitDepth={bd} nbytes={nbytes}")

# ====== Parowanie po czasie ======
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

# ====== Segmentacja (ssseg) ======
import importlib.util, sys
_INF_MOD = None

def _load_infer_module(root_dir):
    global _INF_MOD
    if _INF_MOD is not None:
        return _INF_MOD
    mod_name = 'ssseg.inference_copy'
    mod_path = os.path.join(root_dir, 'inference copy.py')
    if not os.path.exists(mod_path):
        return None
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore
    except Exception:
        return None
    _INF_MOD = module
    return _INF_MOD

def infer_mask_once(infer_mod, image_bgr, cfg, ckpt):
    tmp = "_tmp_seg.png"
    cv2.imwrite(tmp, image_bgr)
    try:
        mask = infer_mod.infer_mask(tmp, cfg, ckpt, ema=False, annpath=None)
    except Exception:
        mask = None
    try:
        os.remove(tmp)
    except Exception:
        pass
    return mask

# ====== Ptlflow (GMA) ======
def build_gma_model(ckpt_path, device):
    import ptlflow
    model = ptlflow.get_model('gma')
    model = model.to(device).eval()
    # elastyczne wczytanie ckpt
    obj = torch.load(ckpt_path, map_location=device)
    if isinstance(obj, dict):
        cand = ["state_dict","model","model_state_dict","network","net","gma","module","weights"]
        sd=None
        for k in cand:
            if k in obj and isinstance(obj[k], dict):
                sd = obj[k]; break
        if sd is None and all(torch.is_tensor(v) for v in obj.values()):
            sd = obj
    else:
        raise RuntimeError("Nieobsługiwany format ckpt")
    # strip 'module.'
    new_sd={}
    for k,v in sd.items(): new_sd[k[7:]] = v if k.startswith('module.') else v
    missing, unexpected = model.load_state_dict(new_sd, strict=False)
    return model

# ====== Flow -> remap ======
def resize_flow(flow, target_wh):
    Hf, Wf = flow.shape[:2]
    Wt, Ht = target_wh
    if (Wf, Hf) == (Wt, Ht):
        return flow
    scale_x = float(Wt) / max(Wf, 1)
    scale_y = float(Ht) / max(Hf, 1)
    u = cv2.resize(flow[...,0], (Wt, Ht), interpolation=cv2.INTER_LINEAR) * scale_x
    v = cv2.resize(flow[...,1], (Wt, Ht), interpolation=cv2.INTER_LINEAR) * scale_y
    out = np.dstack([u, v]).astype(np.float32)
    return out

def warp_A_to_B_with_flow(A_rgb, B_rgb, flow_B_to_A, sign=+1.0, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0)):
    H, W = B_rgb.shape[:2]
    flow_r = resize_flow(flow_B_to_A, (W, H))
    u = flow_r[...,0]*float(sign)
    v = flow_r[...,1]*float(sign)
    grid_x, grid_y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    map_x = grid_x + u
    map_y = grid_y + v
    warped = cv2.remap(A_rgb, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=borderMode, borderValue=borderValue)
    valid = (map_x >= 0) & (map_x <= (W-1)) & (map_y >= 0) & (map_y <= (H-1))
    return warped, valid.astype(np.uint8)

def compute_resize_shape(h, w, max_wh):
    if max(h, w) <= max_wh:
        return (w, h)
    scale = float(max_wh) / float(max(h, w))
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    return (max(1, new_w), max(1, new_h))

# ====== Crop utils ======
def bbox_from_mask(mask, pad=20):
    if mask is None or np.count_nonzero(mask)==0:
        return None
    ys, xs = np.where(mask>0)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    return (x0-pad, y0-pad, (x1-x0)+1+2*pad, (y1-y0)+1+2*pad)

def clamp_roi(roi, w, h):
    if roi is None: return None
    x,y,W,H=roi
    x = max(0, min(x, w-1))
    y = max(0, min(y, h-1))
    W = max(1, min(W, w-x))
    H = max(1, min(H, h-y))
    return (x,y,W,H)

def bbox_center(bbox):
    x,y,w,h = bbox
    return (x + 0.5*w, y + 0.5*h)

def build_similarity_from_bboxes(bboxA, bboxB):
    # izotropowa skala + translacja na podstawie bboxów masek
    xA,yA,wA,hA = bboxA; xB,yB,wB,hB = bboxB
    if wA<=1 or hA<=1: return None
    s = 0.5*((wB/float(wA)) + (hB/float(hA)))
    cAx, cAy = bbox_center(bboxA)
    cBx, cBy = bbox_center(bboxB)
    tx = cBx - s*cAx
    ty = cBy - s*cAy
    M = np.array([[s, 0.0, tx],
                  [0.0, s, ty]], dtype=np.float32)
    return M

def warp_affine_to_size(img, M, size_wh, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0)):
    W,H = size_wh
    return cv2.warpAffine(img, M, (W,H), flags=cv2.INTER_LINEAR, borderMode=borderMode, borderValue=borderValue)

# ====== CLI ======
def parse_args():
    ap = argparse.ArgumentParser(description="Flow-only alignment with segmentation-based ROI")
    ap.add_argument('--base', default='/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test10', help='Katalog bazowy z RAW-ami (zawiera camera1/, camera2/)')
    ap.add_argument('--a_raw', default=None, help='Ścieżka do RAW A (jeśli brak camera1/)')
    ap.add_argument('--b_raw', default=None, help='Ścieżka do RAW B (jeśli brak camera2/)')
    ap.add_argument('--outdir', default=None, help='Katalog wyjściowy (domyślnie base/flow_only_out)')
    # segmentacja
    ap.add_argument('--ssseg_cfg', default='/home/marcin/Documents/Projects/sssegmentation/ssseg/configs/vident_deeplabv3plus/exp09_adam_cosine_lr0001.py', help='Config segmentacji')
    ap.add_argument('--ssseg_ckpt', default='/home/marcin/Documents/Outputs/Ssseg_outputs/PLGRID_deeplabv3plus_exp09_adamW_cosine_lr001_gb30_s1-10_pm5_c95-105_s100-100_g10_CrossEntropyLoss_AUG+Sampler_v1_minlr1e-6_only_teeth/checkpoints-epoch-33.pth', help='Checkpoint segmentacji')
    # optical flow (PTLFlow GMA)
    ap.add_argument('--gma_ckpt', default='/home/marcin/Documents/Projects/sssegmentation/ssseg/alligment/checkpoints/10000_dental_real_GMA_Step0_Vident_synth_bs_6_02_11.pth', help='Checkpoint GMA (.pth)')
    ap.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    # wybór par i ROI
    ap.add_argument('--max_pairs', type=int, default=24, help='Maks liczba par (równomiernie)')
    ap.add_argument('--pad', type=int, default=40, help='Padding do bbox z maski')
    ap.add_argument('--feather', type=int, default=12, help='Feather dla blendu w cropie')
    return ap.parse_args()

# ====== main ======
def main():
    args = parse_args()
    base = args.base
    A_RAW = args.a_raw if args.a_raw else os.path.join(base, 'camera1')
    if os.path.isdir(A_RAW):
        # wybierz pierwszy plik RAW z camera1
        cands = [p for p in os.listdir(A_RAW) if p.lower().endswith('.raw')]
        if not cands: raise SystemExit('Brak RAW w camera1')
        A_RAW = os.path.join(A_RAW, sorted(cands)[0])
    B_RAW = args.b_raw if args.b_raw else os.path.join(base, 'camera2')
    if os.path.isdir(B_RAW):
        cands = [p for p in os.listdir(B_RAW) if p.lower().endswith('.raw')]
        if not cands: raise SystemExit('Brak RAW w camera2')
        B_RAW = os.path.join(B_RAW, sorted(cands)[0])
    OUT_DIR = args.outdir if args.outdir else os.path.join(base, 'flow_only_out')
    OUT_WARP = os.path.join(OUT_DIR, 'A_to_B_flow')
    OUT_A2B = os.path.join(OUT_DIR, 'A_to_B')  # docelowy zapis A->B
    OUT_BDIR = os.path.join(OUT_DIR, 'B')      # oryginalny B
    OUT_OVER = os.path.join(OUT_DIR, 'overlay')
    os.makedirs(OUT_WARP, exist_ok=True)
    os.makedirs(OUT_A2B, exist_ok=True)
    os.makedirs(OUT_BDIR, exist_ok=True)
    os.makedirs(OUT_OVER, exist_ok=True)

    # wczytaj sesje i pary
    sessA, framesA = None, None
    with open(A_RAW, 'rb') as f: sessA = read_session_header(f)
    framesA = list(iter_frames_meta(A_RAW))
    sessB, framesB = None, None
    with open(B_RAW, 'rb') as f: sessB = read_session_header(f)
    framesB = list(iter_frames_meta(B_RAW))
    pairs = pair_by_scaled_time(framesA, framesB, MAX_TIME_DIFF_NS)
    if not pairs: raise SystemExit('Brak par po czasie')
    # potnij do max_pairs równomiernie
    idxs = np.linspace(0, len(pairs)-1, num=min(args.max_pairs, len(pairs)), dtype=int)
    sel_pairs = [pairs[i] for i in idxs]

    # inferencja segmentacji – moduł
    root_dir = os.path.dirname(os.path.dirname(__file__))
    infer_mod = _load_infer_module(root_dir)
    if infer_mod is None:
        raise SystemExit('Brak modułu inferencji ssseg/inference copy.py')

    # GMA
    model = build_gma_model(args.gma_ckpt, args.device)
    from ptlflow.utils.io_adapter import IOAdapter

    for k,(iA,iB,_,_,_) in enumerate(sel_pairs):
        A_rgb = to_rgb8_from_meta(A_RAW, sessA, framesA[iA])
        B_rgb = to_rgb8_from_meta(B_RAW, sessB, framesB[iB])
        if A_rgb is None or B_rgb is None:
            print(f"[{k}] brak obrazów")
            continue
        if FLIP_MODE_B is not None:
            B_rgb = cv2.flip(B_rgb, FLIP_MODE_B)

        # Segmentacja A i B, wyznaczenie bboxów
        maskA = infer_mask_once(infer_mod, cv2.cvtColor(A_rgb, cv2.COLOR_RGB2BGR), args.ssseg_cfg, args.ssseg_ckpt)
        maskB = infer_mask_once(infer_mod, cv2.cvtColor(B_rgb, cv2.COLOR_RGB2BGR), args.ssseg_cfg, args.ssseg_ckpt)
        binA = (maskA!=0).astype(np.uint8) if maskA is not None else None
        binB = (maskB!=0).astype(np.uint8) if maskB is not None else None
        bboxA = clamp_roi(bbox_from_mask(binA, pad=args.pad), A_rgb.shape[1], A_rgb.shape[0])
        bboxB = clamp_roi(bbox_from_mask(binB, pad=args.pad), B_rgb.shape[1], B_rgb.shape[0])
        # Fallback na stały ROI A, jeśli maska A nie wyszła
        if bboxA is None:
            xA,yA,wA,hA = A_ROI
            xA = max(0, min(xA, A_rgb.shape[1]-1))
            yA = max(0, min(yA, A_rgb.shape[0]-1))
            wA = max(1, min(wA, A_rgb.shape[1]-xA))
            hA = max(1, min(hA, A_rgb.shape[0]-yA))
            bboxA = (xA,yA,wA,hA)
        if bboxB is None:
            # centralny bbox o rozmiarze bboxA
            Wb, Hb = B_rgb.shape[1], B_rgb.shape[0]
            xB = max(0, (Wb - bboxA[2])//2)
            yB = max(0, (Hb - bboxA[3])//2)
            bboxB = (xB, yB, min(bboxA[2], Wb), min(bboxA[3], Hb))
        xA,yA,wA,hA = bboxA
        xB,yB,wB,hB = bboxB

        # Zgrubne dopasowanie A->B (skala+translacja) z bboxów masek
        M = build_similarity_from_bboxes(bboxA, bboxB)
        if M is not None:
            A_coarse = warp_affine_to_size(A_rgb, M, (B_rgb.shape[1], B_rgb.shape[0]), borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
        else:
            # fallback: tylko resize do dopasowania szerokości ROI
            s = max(1e-6, 0.5*((wB/max(wA,1)) + (hB/max(hA,1))))
            A_coarse = cv2.resize(A_rgb, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
            A_coarse = cv2.copyMakeBorder(A_coarse, 0, max(0, B_rgb.shape[0]-A_coarse.shape[0]), 0, max(0, B_rgb.shape[1]-A_coarse.shape[1]), cv2.BORDER_CONSTANT, value=(0,0,0))

        # Cropy pod flow – wyłącznie w ROI z B (B nieruszony)
        # Optical flow (B->A) na ROI z downscale→flow→upscale
        cropB = B_rgb[yB:yB+hB, xB:xB+wB]
        cropA = A_coarse[yB:yB+hB, xB:xB+wB]
        # 1) zmniejsz ROI do ROI_MAX_WH
        newWR, newHR = compute_resize_shape(hB, wB, ROI_MAX_WH)
        B_small = cv2.resize(cropB, (newWR, newHR), interpolation=cv2.INTER_LINEAR)
        A_small = cv2.resize(cropA, (newWR, newHR), interpolation=cv2.INTER_LINEAR)
        io = IOAdapter(model, (newHR, newWR))
        inputs = io.prepare_inputs([B_small, A_small])
        inputs = {k: (v.to(args.device) if isinstance(v, torch.Tensor) else v) for k,v in inputs.items()}
        with torch.no_grad():
            preds = model(inputs)
        flow_small = preds['flows'][-1][0].permute(1,2,0).detach().cpu().numpy()  # (newHR,newWR,2)
        # 2) przeskaluj flow do pełnego ROI (hB,wB)
        flow_roi = resize_flow(flow_small, (wB, hB))
        # 3) warping ROI w 4K i feather na brzegu ROI
        warped_roi, valid = warp_A_to_B_with_flow(cropA, cropB, flow_roi, sign=+1.0, borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
        if args.feather > 0:
            dt = cv2.distanceTransform((valid>0).astype(np.uint8)*255, cv2.DIST_L2, 3)
            alpha = np.clip(dt/float(args.feather), 0.0, 1.0)[...,None]
            warped_roi = (warped_roi.astype(np.float32)*alpha + cropB.astype(np.float32)*(1.0-alpha)).astype(np.uint8)
        # 4) złóż pełnoklatkowe A_to_B: tylko ROI zastąpione wynikiem, reszta = B (B nieruszony poza ROI)
        out = B_rgb.copy()
        out[yB:yB+hB, xB:xB+wB] = warped_roi

        # zapisy: A_to_B i oryginalny B
        fn = f"{k:04d}.png"
        cv2.imwrite(os.path.join(OUT_WARP, fn), cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
        cv2.imwrite(os.path.join(OUT_A2B, fn), cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
        cv2.imwrite(os.path.join(OUT_BDIR, fn), cv2.cvtColor(B_rgb, cv2.COLOR_RGB2BGR))
        gB = cv2.cvtColor(B_rgb, cv2.COLOR_RGB2GRAY)
        gW = cv2.cvtColor(out,    cv2.COLOR_RGB2GRAY)
        overlay = np.zeros((B_rgb.shape[0], B_rgb.shape[1], 3), np.uint8)
        overlay[...,1] = gW
        overlay[...,2] = gB
        cv2.imwrite(os.path.join(OUT_OVER, fn), overlay)
        print(f"[{k}] zapisano A_to_B: {os.path.join(OUT_A2B, fn)}  oraz B: {os.path.join(OUT_BDIR, fn)}")

if __name__ == '__main__':
    main() 
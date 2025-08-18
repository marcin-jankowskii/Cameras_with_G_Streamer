# run_gma_on_aligned.py
import os, glob, csv, numpy as np, cv2, torch
import argparse

# --- WYMUSZENIE alt_cuda_corr ZANIM PTLFlow ZAŁADUJE GMA/CORR ---
import importlib
try:
    import alt_cuda_corr  # musi być dostępny w sys.modules
    _ALT_OK = True
except Exception as _e:
    _ALT_OK = False
    print("[diag] alt_cuda_corr import FAIL:", _e)

import ptlflow
from ptlflow.utils.io_adapter import IOAdapter

# po załadowaniu alt_cuda_corr przeładuj moduł corr, aby widział kernel
try:
    from ptlflow.models.gma import corr as gma_corr
    importlib.reload(gma_corr)
    HAS_ALT = getattr(gma_corr, "HAS_ALT", None)
    print(f"[diag] gma_corr.HAS_ALT={HAS_ALT}  alt_imported={_ALT_OK}")
except Exception as e:
    print("[diag] reload gma_corr failed:", e)

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test11/aligned_pairs",
                    help="katalog z A_to_B/ i B/")
    ap.add_argument("--ckpt", default="/home/marcin/Documents/Projects/sssegmentation/ssseg/alligment/checkpoints/10000_dental_real_GMA_Step0_Vident_synth_bs_6_02_11.pth",
                    help="ścieżka do checkpointu GMA (.pth)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--clip", type=float, default=80.0,
                    help="wizualizacja: przypięcie magnitudo (px) do bieli/czerni")
    ap.add_argument("--amp", action="store_true",
                    help="użyj autocast FP16 na GPU (mniejsze zużycie VRAM)")
    return ap.parse_args()

def natural_key(p):
    base = os.path.basename(p)
    stem, _ = os.path.splitext(base)
    try: return int(stem)
    except: return stem

def flow_to_white_bg_img(flow, clip=5.0, sat_low_frac=0.02):
    u, v = flow[...,0], flow[...,1]
    mag = np.sqrt(u*u + v*v)
    ang = (np.arctan2(v, u) + np.pi) / (2*np.pi)  # 0..1

    m = np.clip(mag / max(clip, 1e-6), 0, 1)
    val = 1.0 - m                                # <-- klucz: 1 do 0
    sat = np.where(mag < sat_low_frac*clip, 0.0, 0.85)

    hsv = np.stack([ang, sat, val], axis=-1).astype(np.float32)
    hsv8 = (hsv * 255).astype(np.uint8)
    bgr = cv2.cvtColor(hsv8, cv2.COLOR_HSV2BGR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb, mag




def load_state_dict_flex(path, map_location="cpu"):
    """Wczytaj .pth i zwróć możliwy state_dict. Usuwa 'module.'."""
    obj = torch.load(path, map_location=map_location)
    if isinstance(obj, dict) and all(isinstance(k, str) for k in obj.keys()):
        candidate_keys = [
            "state_dict", "model", "model_state_dict",
            "network", "net", "gma", "module", "weights"
        ]
        state_dict = None
        for k in candidate_keys:
            if k in obj and isinstance(obj[k], dict):
                state_dict = obj[k]
                break
        if state_dict is None:
            if all(torch.is_tensor(v) for v in obj.values()):
                state_dict = obj
            else:
                for v in obj.values():
                    if isinstance(v, dict) and all(isinstance(kk, str) for kk in v.keys()):
                        if all(torch.is_tensor(x) for x in v.values()):
                            state_dict = v
                            break
        if state_dict is None:
            raise KeyError(f"Nie znaleziono state_dict w {path}. Klucze: {list(obj.keys())[:10]}")
    else:
        raise TypeError(f"Nieobsługiwany format checkpointu: {type(obj)}")

    new_sd = {}
    for k, v in state_dict.items():
        nk = k[7:] if k.startswith("module.") else k
        new_sd[nk] = v
    return new_sd

def make_colorwheel():
    """
    Generates a color wheel for optical flow visualization as presented in:
        Baker et al. "A Database and Evaluation Methodology for Optical Flow" (ICCV, 2007)
        URL: http://vision.middlebury.edu/flow/flowEval-iccv07.pdf

    Code follows the original C++ source code of Daniel Scharstein.
    Code follows the the Matlab source code of Deqing Sun.

    Returns:
        np.ndarray: Color wheel
    """

    RY = 15
    YG = 6
    GC = 4
    CB = 11
    BM = 13
    MR = 6

    ncols = RY + YG + GC + CB + BM + MR
    colorwheel = np.zeros((ncols, 3))
    col = 0

    # RY
    colorwheel[0:RY, 0] = 255
    colorwheel[0:RY, 1] = np.floor(255*np.arange(0,RY)/RY)
    col = col+RY
    # YG
    colorwheel[col:col+YG, 0] = 255 - np.floor(255*np.arange(0,YG)/YG)
    colorwheel[col:col+YG, 1] = 255
    col = col+YG
    # GC
    colorwheel[col:col+GC, 1] = 255
    colorwheel[col:col+GC, 2] = np.floor(255*np.arange(0,GC)/GC)
    col = col+GC
    # CB
    colorwheel[col:col+CB, 1] = 255 - np.floor(255*np.arange(CB)/CB)
    colorwheel[col:col+CB, 2] = 255
    col = col+CB
    # BM
    colorwheel[col:col+BM, 2] = 255
    colorwheel[col:col+BM, 0] = np.floor(255*np.arange(0,BM)/BM)
    col = col+BM
    # MR
    colorwheel[col:col+MR, 2] = 255 - np.floor(255*np.arange(MR)/MR)
    colorwheel[col:col+MR, 0] = 255
    return colorwheel


def flow_uv_to_colors(u, v, convert_to_bgr=False):
    """
    Applies the flow color wheel to (possibly clipped) flow components u and v.

    According to the C++ source code of Daniel Scharstein
    According to the Matlab source code of Deqing Sun

    Args:
        u (np.ndarray): Input horizontal flow of shape [H,W]
        v (np.ndarray): Input vertical flow of shape [H,W]
        convert_to_bgr (bool, optional): Convert output image to BGR. Defaults to False.

    Returns:
        np.ndarray: Flow visualization image of shape [H,W,3]
    """
    flow_image = np.zeros((u.shape[0], u.shape[1], 3), np.uint8)
    colorwheel = make_colorwheel()  # shape [55x3]
    ncols = colorwheel.shape[0]
    rad = np.sqrt(np.square(u) + np.square(v))
    a = np.arctan2(-v, -u)/np.pi
    fk = (a+1) / 2*(ncols-1)
    k0 = np.floor(fk).astype(np.int32)
    k1 = k0 + 1
    k1[k1 == ncols] = 0
    f = fk - k0
    for i in range(colorwheel.shape[1]):
        tmp = colorwheel[:,i]
        col0 = tmp[k0] / 255.0
        col1 = tmp[k1] / 255.0
        col = (1-f)*col0 + f*col1
        idx = (rad <= 1)
        col[idx]  = 1 - rad[idx] * (1-col[idx])
        col[~idx] = col[~idx] * 0.75   # out of range
        # Note the 2-i => BGR instead of RGB
        ch_idx = 2-i if convert_to_bgr else i
        flow_image[:,:,ch_idx] = np.floor(255 * col)
    return flow_image


def flow_to_image(flow_uv, clip_flow=None, convert_to_bgr=False):
    """
    Expects a two dimensional flow image of shape.

    Args:
        flow_uv (np.ndarray): Flow UV image of shape [H,W,2]
        clip_flow (float, optional): Clip maximum of flow values. Defaults to None.
        convert_to_bgr (bool, optional): Convert output image to BGR. Defaults to False.

    Returns:
        np.ndarray: Flow visualization image of shape [H,W,3]
    """
    assert flow_uv.ndim == 3, 'input flow must have three dimensions'
    assert flow_uv.shape[2] == 2, 'input flow must have shape [H,W,2]'
    if clip_flow is not None:
        flow_uv = np.clip(flow_uv, 0, clip_flow)
    u = flow_uv[:,:,0]
    v = flow_uv[:,:,1]
    rad = np.sqrt(np.square(u) + np.square(v))
    rad_max = np.max(rad)
    epsilon = 1e-5
    u = u / (rad_max + epsilon)
    v = v / (rad_max + epsilon)
    return flow_uv_to_colors(u, v, convert_to_bgr)

def main():
    args = parse_args()
    DIR_B   = os.path.join(args.base, "B")
    DIR_A2B = os.path.join(args.base, "A_to_B") #"A2B_warped_to_B" , "A_to_B"
    OUT_FLOW = os.path.join(args.base, "flows_numpy")
    OUT_VIS  = os.path.join(args.base, "flows_vis")
    OUT_OVERLAY = os.path.join(args.base, "flows_overlay")
    OUT_MAG  = os.path.join(args.base, "flows_mag")
    OUT_QUIVER = os.path.join(args.base, "flows_quiver")
    OUT_SIGNED = os.path.join(args.base, "flows_signed")
    OUT_OVERLAY_STRONG = os.path.join(args.base, "flows_overlay_strong")
    OUT_OVERLAY_EDGES = os.path.join(args.base, "flows_overlay_edges")
    OUT_OVERLAY_CHECKER = os.path.join(args.base, "flows_overlay_checker")
    OUT_OVERLAY_QA = os.path.join(args.base, "flows_overlay_qa")
    os.makedirs(OUT_FLOW, exist_ok=True)
    os.makedirs(OUT_VIS,  exist_ok=True)
    os.makedirs(OUT_OVERLAY, exist_ok=True)
    os.makedirs(OUT_MAG,  exist_ok=True)
    os.makedirs(OUT_QUIVER, exist_ok=True)
    os.makedirs(OUT_SIGNED, exist_ok=True)
    os.makedirs(OUT_OVERLAY_STRONG, exist_ok=True)
    os.makedirs(OUT_OVERLAY_EDGES, exist_ok=True)
    os.makedirs(OUT_OVERLAY_CHECKER, exist_ok=True)
    os.makedirs(OUT_OVERLAY_QA, exist_ok=True)

    imgs_B   = sorted(glob.glob(os.path.join(DIR_B, "*.*")), key=natural_key)
    imgs_A2B = sorted(glob.glob(os.path.join(DIR_A2B, "*.*")), key=natural_key)
    pairs = list(zip(imgs_B, imgs_A2B))
    if not pairs:
        raise SystemExit(f"Brak par w {DIR_B} i {DIR_A2B}")

    # ---- Model GMA + ckpt ----
    print(f"Ładuję GMA (PTLFlow) + ckpt: {args.ckpt}")
    model = ptlflow.get_model('gma')  # bez ckpt
    model = model.to(args.device).eval()

    try:
        sd = load_state_dict_flex(args.ckpt, map_location=args.device)
    except Exception as e:
        print("Błąd przy wczytywaniu ckpt:", e)
        print("Spróbuję jeszcze raz z map_location='cpu' i potem przeniosę na urządzenie.")
        sd = load_state_dict_flex(args.ckpt, map_location="cpu")
    missing, unexpected = model.load_state_dict(sd, strict=False)
    if missing:
        print(f"[INFO] Missing keys (ok, strict=False): {len(missing)}")
    if unexpected:
        print(f"[INFO] Unexpected keys (ok, strict=False): {len(unexpected)}")

    rows = [("idx","file_B","file_A2B","mean_mag","median_mag","p90_mag","p95_mag","max_mag")]

    use_amp = args.amp and args.device.startswith("cuda")
    if use_amp:
        print("[diag] AMP włączony (float16)")

    for idx, (pB, pA2B) in enumerate(pairs):
        imB   = cv2.cvtColor(cv2.imread(pB, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        imA2B = cv2.cvtColor(cv2.imread(pA2B, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        TARGET_SIZE = (1024, 576)  # (szerokość, wysokość)
        imB   = cv2.resize(imB, TARGET_SIZE, interpolation=cv2.INTER_LINEAR)
        imA2B = cv2.resize(imA2B, TARGET_SIZE, interpolation=cv2.INTER_LINEAR)

        if imB is None or imA2B is None:
            print(f"[{idx}] pomijam (brak obrazu)"); continue
        if imB.shape != imA2B.shape:
            print(f"[{idx}] różne rozmiary, pomijam"); continue

        H, W = imB.shape[:2]
        io = IOAdapter(model, (H, W))
        inputs = io.prepare_inputs([imB, imA2B])  # (1,2,3,H,W)
        inputs = {k: (v.to(args.device) if isinstance(v, torch.Tensor) else v)
                  for k, v in inputs.items()}

        with torch.no_grad():
            if use_amp:
                with torch.cuda.amp.autocast(dtype=torch.float16):
                    preds = model(inputs)
            else:
                preds = model(inputs)

        flow = preds['flows'][-1][0].permute(1,2,0).detach().cpu().numpy()  # (H,W,2)

        # metryki na magnitudo flow
        mag = np.sqrt(flow[...,0]*flow[...,0] + flow[...,1]*flow[...,1])
        v_min = float(np.min(mag))
        v_max = float(np.max(mag))
        v_mean = float(np.mean(mag))
        v_med  = float(np.median(mag))
        v_p90  = float(np.percentile(mag, 90))
        v_p95  = float(np.percentile(mag, 95))
        print(f"[{idx:04d}] min={v_min:.3f}  mean={v_mean:.3f}  max={v_max:.3f}  med={v_med:.3f}  p90={v_p90:.3f}  p95={v_p95:.3f}")
        rows.append((idx, os.path.basename(pB), os.path.basename(pA2B), v_mean, v_med, v_p90, v_p95, v_max))

        # zapisz .npy
        np.save(os.path.join(OUT_FLOW, f"{idx:04d}.npy"), flow)

        # wizualizacja (statyczne ≈ białe)
        vis = flow_to_image(flow, clip_flow=args.clip, convert_to_bgr=False)

        cv2.imwrite(os.path.join(OUT_VIS, f"{idx:04d}.png"),
                    cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))

        # Dodatkowe zapisy diagnostyczne
        base = f"{idx:04d}.png"
        # 1) Overlay: B jako niebieski, A2B jako czerwony; zgodność -> szarość
        # Normalizacja do [0,1]
        imB_f   = imB.astype(np.float32) / 255.0
        imA2B_f = imA2B.astype(np.float32) / 255.0
        # luminancja (szarość) do sterowania neutralnością
        grayB   = cv2.cvtColor((imB_f*255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)/255.0
        grayA2B = cv2.cvtColor((imA2B_f*255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)/255.0
        gray = 0.5*(grayB + grayA2B)
        gray3 = np.dstack([gray, gray, gray])
        # kanały: B→niebieski (z luminancji), A2B→żółty (R+G z luminancji)
        overlay = np.zeros_like(imB_f)
        overlay[..., 2] = grayB  # niebieski z luminancji B
        overlay[..., 0] = grayA2B  # czerwony z luminancji A2B
        overlay[..., 1] = grayA2B  # zielony z luminancji A2B (żółty)
        # mieszanie do szarości, gdy obrazy podobne: użyj średniej luminancji
        alpha = 0.5
        overlay = alpha*overlay + (1.0-alpha)*gray3
        overlay_u8 = np.clip(overlay*255.0, 0, 255).astype(np.uint8)
        cv2.imwrite(os.path.join(OUT_OVERLAY, base), cv2.cvtColor(overlay_u8, cv2.COLOR_RGB2BGR))

        # 2) Heatmapa magnitudo
        mag = np.sqrt(flow[...,0]*flow[...,0] + flow[...,1]*flow[...,1])
        mag_norm = mag / (np.percentile(mag, 99.0) + 1e-6)
        mag_norm = np.clip(mag_norm, 0, 1)
        mag_vis = (mag_norm*255).astype(np.uint8)
        mag_vis = cv2.applyColorMap(mag_vis, cv2.COLORMAP_JET)
        cv2.imwrite(os.path.join(OUT_MAG, base), mag_vis)

        # 4) Signed displacement (pseudo 3D): u->R, v->G, magnitudo->B
        u = flow[...,0]; v = flow[...,1]
        um = np.percentile(np.abs(u), 99.0) + 1e-6
        vm = np.percentile(np.abs(v), 99.0) + 1e-6
        u_vis = np.clip((u/um*0.5 + 0.5)*255, 0, 255).astype(np.uint8)
        v_vis = np.clip((v/vm*0.5 + 0.5)*255, 0, 255).astype(np.uint8)
        m_vis = np.clip((mag/(np.percentile(mag,99.0)+1e-6))*255, 0, 255).astype(np.uint8)
        signed_rgb = np.dstack([u_vis, v_vis, m_vis])
        cv2.imwrite(os.path.join(OUT_SIGNED, base), cv2.cvtColor(signed_rgb, cv2.COLOR_RGB2BGR))

        # 5) Quiver (rzadkie strzałki)
        try:
            step = max(min(W, H)//32, 8)
            quiv = np.zeros((H, W, 3), np.uint8)
            quiv[:] = (255, 255, 255)
            for yy in range(step//2, H, step):
                for xx in range(step//2, W, step):
                    du = int(round(u[yy, xx]))
                    dv = int(round(v[yy, xx]))
                    x2 = np.clip(xx + du, 0, W-1)
                    y2 = np.clip(yy + dv, 0, H-1)
                    cv2.arrowedLine(quiv, (xx, yy), (x2, y2), (0,0,255), 1, tipLength=0.3)
            cv2.imwrite(os.path.join(OUT_QUIVER, base), quiv)
        except Exception as _e:
            pass

        # 1a) Overlay STRONG: anaglif czerwony/cyjan (B->cyjan, A2B->czerwony)
        # Silniejszy kontrast przez podbicie i gamma
        def _boost(img):
            x = np.clip(img, 0, 1)
            x = x**0.8
            return np.clip(x*1.2, 0, 1)
        Bb = _boost(imB_f); Ab = _boost(imA2B_f)
        anaglyph = np.zeros_like(Bb)
        # cyjan = G+B z B; żółty = R+G z A2B
        anaglyph[...,0] = 0.0
        anaglyph[...,1] = np.clip(Ab[...,0] + Ab[...,1], 0, 1)
        anaglyph[...,2] = np.clip(Bb[...,1] + Bb[...,2], 0, 1)
        anaglyph_u8 = (anaglyph*255).astype(np.uint8)
        cv2.imwrite(os.path.join(OUT_OVERLAY_STRONG, base), cv2.cvtColor(anaglyph_u8, cv2.COLOR_RGB2BGR))

        # 1b) Overlay EDGES: krawędzie Canny, B na niebiesko, A2B na czerwono
        gB = cv2.cvtColor((imB_f*255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        gA = cv2.cvtColor((imA2B_f*255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        eB = cv2.Canny(gB, 50, 150)
        eA = cv2.Canny(gA, 50, 150)
        edge_overlay = np.zeros_like((imB_f*255).astype(np.uint8))
        edge_overlay[eB>0] = (0,0,255)   # niebieskie krawędzie B
        edge_overlay[eA>0] = (255,0,0)   # czerwone krawędzie A2B
        cv2.imwrite(os.path.join(OUT_OVERLAY_EDGES, base), edge_overlay)

        # 1c) Overlay CHECKER: szachownica (np. kafel 32px)
        tile_sz = 32
        Hc, Wc = imB.shape[:2]
        checker = np.zeros_like(imB)
        for yy in range(0, Hc, tile_sz):
            for xx in range(0, Wc, tile_sz):
                y1 = min(yy+tile_sz, Hc); x1 = min(xx+tile_sz, Wc)
                if ((yy//tile_sz)+(xx//tile_sz)) % 2 == 0:
                    checker[yy:y1, xx:x1] = imB[yy:y1, xx:x1]
                else:
                    checker[yy:y1, xx:x1] = imA2B[yy:y1, xx:x1]
        cv2.imwrite(os.path.join(OUT_OVERLAY_CHECKER, base), cv2.cvtColor(checker, cv2.COLOR_RGB2BGR))

        # overlay QA (jak w align_estimate): G = A2B gray, R = B gray
        qa_overlay = np.zeros((H, W, 3), np.uint8)
        qa_overlay[..., 1] = (grayA2B * 255).astype(np.uint8)  # G
        qa_overlay[..., 2] = (grayB * 255).astype(np.uint8)    # R
        cv2.imwrite(os.path.join(OUT_OVERLAY_QA, base), qa_overlay)

    # # CSV
    # csv_path = os.path.join(args.base, "metrics_gma.csv")
    # with open(csv_path, "w", newline="") as f:
    #     csv.writer(f).writerows(rows)

    print("Gotowe:")
    print(" - flows_numpy:", OUT_FLOW)
    print(" - flows_vis  :", OUT_VIS)
    # print(" - metrics    :", csv_path)

if __name__ == "__main__":
    main()

# run_gma_on_aligned_tiled.py
import os, glob, csv, numpy as np, cv2, torch, argparse, importlib

# --- Spróbuj załadować alt_cuda_corr zanim PTLFlow załaduje GMA ---
try:
    import alt_cuda_corr  # jeśli jest skompilowany, super
    _ALT_OK = True
except Exception as _e:
    _ALT_OK = False
    print("[diag] alt_cuda_corr import FAIL:", _e)

import ptlflow
from ptlflow.utils.io_adapter import IOAdapter

# Po imporcie PTLFlow przeładuj corr, aby widział alt_cuda_corr (jeśli jest)
try:
    from ptlflow.models.gma import corr as gma_corr
    importlib.reload(gma_corr)
    HAS_ALT = getattr(gma_corr, "HAS_ALT", None)
    print(f"[diag] gma_corr.HAS_ALT={HAS_ALT}  alt_imported={_ALT_OK}")
except Exception as e:
    print("[diag] reload gma_corr failed:", e)

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test9/aligned_pairs",
                    help="katalog z A_to_B/ i B/")
    ap.add_argument("--ckpt", default="/home/marcin/Documents/Projects/Cameras_with_G_Streamer/python/checkpoints/10000_dental_real_GMA_Step0_Vident_synth_bs_6_02_11.pth",
                    help="ścieżka do checkpointu GMA (.pth)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--clip", type=float, default=5.0,
                    help="wizualizacja: przypięcie magnitudo (px) do bieli/czerni")
    ap.add_argument("--amp", action="store_true",
                    help="autocast FP16 na GPU (mniejsze zużycie VRAM)")
    # tiling
    ap.add_argument("--tile", type=int, default=1024, help="rozmiar kafelka (np. 1024)")
    ap.add_argument("--overlap", type=int, default=192, help="nakładka między kafelkami (np. 128-256)")
    ap.add_argument("--iters", type=int, default=12, help="liczba iteracji GMA")
    return ap.parse_args()

def natural_key(p):
    base = os.path.basename(p); stem, _ = os.path.splitext(base)
    try: return int(stem)
    except: return stem

def flow_to_white_bg_img(flow, clip=5.0):
    """Statyczne ≈ białe; kolor niesie kierunek (HSV)."""
    u, v = flow[...,0], flow[...,1]
    mag = np.sqrt(u*u + v*v)
    ang = (np.arctan2(v, u) + np.pi) / (2*np.pi)  # 0..1
    m = np.clip(mag / max(clip, 1e-6), 0, 1)
    val = 1.0 - m
    sat = np.where(mag < 0.02*clip, 0.0, 0.85)
    hsv = np.stack([ang, sat, val], axis=-1).astype(np.float32)
    hsv8 = (hsv * 255).astype(np.uint8)
    bgr = cv2.cvtColor(hsv8, cv2.COLOR_HSV2BGR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb, mag

def load_state_dict_flex(path, map_location="cpu"):
    obj = torch.load(path, map_location=map_location)
    if not isinstance(obj, dict):
        raise TypeError(f"Nieobsługiwany format ckpt: {type(obj)}")
    # spróbuj znaleźć faktyczny state_dict
    sd = None
    for k in ["state_dict","model","model_state_dict","network","net","gma","module","weights"]:
        if k in obj and isinstance(obj[k], dict):
            sd = obj[k]; break
    if sd is None:
        if all(torch.is_tensor(v) for v in obj.values()):
            sd = obj
        else:
            for v in obj.values():
                if isinstance(v, dict) and all(torch.is_tensor(x) for x in v.values()):
                    sd = v; break
    if sd is None:
        raise KeyError(f"Nie znaleziono state_dict. Klucze: {list(obj.keys())[:10]}")
    # usuń 'module.' prefix
    return { (k[7:] if k.startswith("module.") else k): v for k,v in sd.items() }

def pad_to_multiple_of_8(img):
    """Pad do wielokrotności 8 (border replicate). Zwraca obraz i tuple padów (t,b,l,r)."""
    h, w = img.shape[:2]
    H = (h + 7)//8*8
    W = (w + 7)//8*8
    if H==h and W==w:
        return img, (0,0,0,0)
    pad_t, pad_l = 0, 0
    pad_b, pad_r = H - h, W - w
    img2 = cv2.copyMakeBorder(img, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)
    return img2, (pad_t, pad_b, pad_l, pad_r)

def unpad(arr, pads):
    t,b,l,r = pads
    if (t|b|l|r)==0: return arr
    return arr[t:arr.shape[0]-b, l:arr.shape[1]-r, :]

def hann2d(h, w):
    # okno Hanninga 2D do blendu
    wy = np.hanning(max(h, 2))
    wx = np.hanning(max(w, 2))
    win = np.outer(wy, wx).astype(np.float32)
    # zabezpieczenie: gdy h<2 lub w<2, hanning daje dziwne wartości → wymuś jedynki
    if h < 2 or w < 2:
        win = np.ones((h,w), dtype=np.float32)
    else:
        win = win[:h, :w]
    # żeby brzegi nie były zerowe (co powoduje „dziury”), lekko podnieś minimum
    win = np.clip(win, 0.05, 1.0)
    return win

def _cosine_flat_1d(length: int, left_margin: int, right_margin: int) -> np.ndarray:
    """Okno 1D: płaski środek (=1), kosinusowe zbocza o zadanych marginesach."""
    left_margin = max(int(left_margin), 0)
    right_margin = max(int(right_margin), 0)
    w = np.ones((length,), dtype=np.float32)
    if left_margin > 0:
        x = np.linspace(0.0, np.pi, left_margin, endpoint=True, dtype=np.float32)
        w[:left_margin] = 0.5 - 0.5 * np.cos(x)  # 0→1
    if right_margin > 0:
        x = np.linspace(np.pi, 2.0*np.pi, right_margin, endpoint=True, dtype=np.float32)
        w[-right_margin:] = 0.5 - 0.5 * np.cos(x)  # 1→0
    return w


def _cosine_flat_2d(h: int, w: int, top: int, bottom: int, left: int, right: int) -> np.ndarray:
    """Okno 2D separowalne z płaskim środkiem i kosinusowymi zboczami per krawędź."""
    wy = _cosine_flat_1d(h, top, bottom)
    wx = _cosine_flat_1d(w, left, right)
    return (np.outer(wy, wx)).astype(np.float32)

def run_gma_on_pair(model, device, img1_rgb, img2_rgb, iters=12, amp=False):
    """Liczy flow na parze (RGB uint8) z pad8 i zwraca (H,W,2) float32."""
    # do tensorów (NCHW, [0,1])
    t1 = torch.from_numpy(img1_rgb).permute(2,0,1).float()[None] / 255.0
    t2 = torch.from_numpy(img2_rgb).permute(2,0,1).float()[None] / 255.0
    t1 = t1.to(device); t2 = t2.to(device)

    # PTLFlow IOAdapter przygotowuje dict dla modelu
    H, W = img1_rgb.shape[:2]
    io = IOAdapter(model, (H, W))
    inputs = io.prepare_inputs([img1_rgb, img2_rgb])
    inputs = {k: (v.to(device) if isinstance(v, torch.Tensor) else v) for k,v in inputs.items()}

    with torch.no_grad():
        if amp and device.startswith("cuda"):
            with torch.amp.autocast('cuda', dtype=torch.float16):
                preds = model(inputs)
        else:
            preds = model(inputs)

    flow = preds['flows'][-1][0].permute(1,2,0).detach().float().cpu().numpy()  # (H,W,2)
    return flow

def run_gma_on_pair_tiled(model, device, img1_rgb, img2_rgb, tile=1024, overlap=192, iters=12, amp=False):
    """Tiling z overlapem i miękkim blendowaniem (okno z płaskim środkiem).

    Zmiany względem poprzedniej wersji:
    - Liczymy flow na powiększonym o margines (overlap//2) kafelku jako kontekst,
      a do akumulatora trafia tylko centralny obszar kafelka.
    - Okno wagowe ma płaski środek i kosinusowe zbocza o szerokości zależnej od
      położenia (na krawędziach obrazu zbocze = 0 aby nie gasić brzegów).
    """
    H, W = img1_rgb.shape[:2]
    stride = max(tile - overlap, 64)
    context = max(overlap // 2, 0)

    flow_acc = np.zeros((H, W, 2), np.float32)
    weight   = np.zeros((H, W),    np.float32)

    y = 0
    while y < H:
        y1 = min(y + tile, H)
        # duży wycinek z kontekstem w pionie
        y0_big = max(0, y - context)
        y2_big = min(H, y1 + context)

        x = 0
        while x < W:
            x1 = min(x + tile, W)
            # duży wycinek z kontekstem w poziomie
            x0_big = max(0, x - context)
            x2_big = min(W, x1 + context)

            crop1_big = img1_rgb[y0_big:y2_big, x0_big:x2_big, :]
            crop2_big = img2_rgb[y0_big:y2_big, x0_big:x2_big, :]

            # policz flow na większym fragmencie (z kontekstem)
            flow_big = run_gma_on_pair(model, device, crop1_big, crop2_big, iters=iters, amp=amp)

            # wytnij centralny kafelek (bez kontekstu) do wklejenia
            cy0 = (y - y0_big)
            cy1 = cy0 + (y1 - y)
            cx0 = (x - x0_big)
            cx1 = cx0 + (x1 - x)
            flow_tile = flow_big[cy0:cy1, cx0:cx1, :]

            th = flow_tile.shape[0]
            tw = flow_tile.shape[1]

            # szerokości zboczy: w środku obrazu = context, przy brzegu = 0
            top_margin    = min(context, y - 0)
            bottom_margin = min(context, H - y1)
            left_margin   = min(context, x - 0)
            right_margin  = min(context, W - x1)

            # dodatkowe bezpieczeństwo: marginesy nie większe niż połowa wymiaru
            top_margin    = int(max(0, min(top_margin,    th // 2)))
            bottom_margin = int(max(0, min(bottom_margin, th // 2)))
            left_margin   = int(max(0, min(left_margin,   tw // 2)))
            right_margin  = int(max(0, min(right_margin,  tw // 2)))

            win = _cosine_flat_2d(th, tw, top_margin, bottom_margin, left_margin, right_margin)

            flow_acc[y:y1, x:x1, :] += flow_tile * win[..., None]
            weight[y:y1, x:x1]      += win

            x += stride
        y += stride

    weight = np.clip(weight, 1e-6, None)
    flow = flow_acc / weight[..., None]
    return flow

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
    DIR_A2B = os.path.join(args.base, "A_to_B")
    OUT_FLOW = os.path.join(args.base, "flows_numpy")
    OUT_VIS  = os.path.join(args.base, "flows_vis")
    os.makedirs(OUT_FLOW, exist_ok=True)
    os.makedirs(OUT_VIS,  exist_ok=True)

    imgs_B   = sorted(glob.glob(os.path.join(DIR_B, "*.*")), key=natural_key)
    imgs_A2B = sorted(glob.glob(os.path.join(DIR_A2B, "*.*")), key=natural_key)
    pairs = list(zip(imgs_B, imgs_A2B))
    if not pairs:
        raise SystemExit(f"Brak par w {DIR_B} i {DIR_A2B}")

    # ---- Model GMA + ckpt ----
    print(f"Ładuję GMA (PTLFlow) + ckpt: {args.ckpt}")
    model = ptlflow.get_model('gma')
    model = model.to(args.device).eval()

    try:
        sd = load_state_dict_flex(args.ckpt, map_location=args.device)
    except Exception as e:
        print("Błąd przy wczytywaniu ckpt:", e)
        print("Spróbuję jeszcze raz z map_location='cpu' i potem przeniosę na urządzenie.")
        sd = load_state_dict_flex(args.ckpt, map_location="cpu")
    missing, unexpected = model.load_state_dict(sd, strict=False)
    if missing:    print(f"[INFO] Missing keys (ok, strict=False): {len(missing)}")
    if unexpected: print(f"[INFO] Unexpected keys (ok, strict=False): {len(unexpected)}")

    use_amp = args.amp and args.device.startswith("cuda")
    if use_amp:
        print("[diag] AMP włączony (float16)")

    rows = [("idx","file_B","file_A2B","mean_mag","median_mag","p90_mag","p95_mag","max_mag")]

    for idx, (pB, pA2B) in enumerate(pairs):
        imB   = cv2.cvtColor(cv2.imread(pB,  cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        imA2B = cv2.cvtColor(cv2.imread(pA2B, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        if imB is None or imA2B is None:
            print(f"[{idx}] pomijam (brak obrazu)"); continue
        if imB.shape != imA2B.shape:
            print(f"[{idx}] różne rozmiary, pomijam"); continue

        # --- TILE INFERENCE ---
        flow = run_gma_on_pair_tiled(model, args.device, imB, imA2B,
                                     tile=args.tile, overlap=args.overlap,
                                     iters=args.iters, amp=use_amp)

        # zapisz .npy
        np.save(os.path.join(OUT_FLOW, f"{idx:04d}.npy"), flow)

        # wizualizacja na białym tle
        vis = flow_to_image(flow, clip_flow=args.clip, convert_to_bgr=False)
        cv2.imwrite(os.path.join(OUT_VIS, f"{idx:04d}.png"),
                    cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))

        # # metryki
        # mean = float(np.mean(mag)); med = float(np.median(mag))
        # p90  = float(np.percentile(mag, 90)); p95 = float(np.percentile(mag, 95))
        # mmax = float(np.max(mag))
        # rows.append((idx, os.path.basename(pB), os.path.basename(pA2B), mean, med, p90, p95, mmax))
        # print(f"[{idx:04d}] mean={mean:.3f}  p95={p95:.3f}")

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

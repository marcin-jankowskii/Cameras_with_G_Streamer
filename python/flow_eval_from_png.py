# flow_eval_from_png.py
import os, cv2, csv, numpy as np
from skimage.metrics import structural_similarity as ssim

# ====== ŚCIEŻKI ======
BASE_PATH = "/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test9/aligned_pairs"
DIR_B     = os.path.join(BASE_PATH, "B")
DIR_A2B   = os.path.join(BASE_PATH, "A_to_B")

OUT_DIR     = os.path.join(BASE_PATH, "flow_from_png")
OUT_FLOWHSV = os.path.join(OUT_DIR, "flow_hsv")
OUT_CONCAT  = os.path.join(OUT_DIR, "concat")
OUT_COLORWHEEL = os.path.join(OUT_DIR, "flow_colorwheel")
os.makedirs(OUT_FLOWHSV, exist_ok=True)
os.makedirs(OUT_CONCAT,  exist_ok=True)
os.makedirs(OUT_COLORWHEEL, exist_ok=True)

# ====== Parametry ======
FLOW_ALGO = "farneback"   # "farneback" albo "tvl1"
DOWNSCALE = 1.0           # np. 0.5 dla szybkości
CSV_PATH  = os.path.join(OUT_DIR, "metrics.csv")

# ---------- Utils ----------
def list_pngs(d):
    files = [f for f in os.listdir(d) if f.lower().endswith((".png",".jpg",".jpeg","tif","tiff"))]
    files.sort()
    return [os.path.join(d,f) for f in files]

def imread_rgb(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None: return None
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    # OpenCV zwraca BGR; konwertujemy do RGB dla spójności
    return img

def to_gray(img_rgb):
    return cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

def compute_flow(g1, g2, algo="farneback"):
    if algo == "tvl1":
        tvl1 = cv2.optflow.DualTVL1OpticalFlow_create()
        flow = tvl1.calc(g1, g2, None)
    else:
        flow = cv2.calcOpticalFlowFarneback(
            g1, g2, None,
            pyr_scale=0.5, levels=5, winsize=21,
            iterations=5, poly_n=7, poly_sigma=1.5, flags=0
        )
    return flow

def flow_to_hsv_rgb(flow):
    fx, fy = flow[...,0], flow[...,1]
    mag, ang = cv2.cartToPolar(fx, fy, angleInDegrees=True)
    m98 = np.percentile(mag, 98) if np.isfinite(mag).any() else 1.0
    m98 = max(m98, 1e-6)
    hsv = np.zeros((*mag.shape, 3), dtype=np.uint8)
    hsv[...,0] = (ang / 2).astype(np.uint8)   # 0..179
    hsv[...,1] = 255
    hsv[...,2] = np.clip((mag / m98)*255, 0, 255).astype(np.uint8)
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return rgb, mag

def psnr_uint8(a, b, mask=None):
    if mask is not None:
        m = mask > 0
        if not np.any(m): return 0.0
        a = a[m]; b = b[m]
    mse = np.mean((a.astype(np.float32)-b.astype(np.float32))**2)
    if mse <= 1e-12: return 99.0
    return 20*np.log10(255.0) - 10*np.log10(mse)

def ssim_uint8(a, b, mask=None):
    if mask is not None:
        m = mask>0
        if not np.any(m): return 0.0
        a = a.copy(); b = b.copy()
        a[~m] = 0; b[~m] = 0
    return ssim(a, b, data_range=255)

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

# ---------- MAIN ----------
paths_B   = list_pngs(DIR_B)
paths_A2B = list_pngs(DIR_A2B)

n = min(len(paths_B), len(paths_A2B))
if n == 0:
    raise SystemExit("Brak plików PNG w B/A_to_B.")

rows = [["index","mean_EPE","median_EPE","p95_EPE","max_EPE","PSNR","SSIM","num_valid","mag_min","mag_mean","mag_max","mag_median","mag_p90","mag_p95"]]

for idx in range(n):
    pB   = paths_B[idx]
    pA2B = paths_A2B[idx]

    imgB   = imread_rgb(pB)
    imgA2B = imread_rgb(pA2B)
    if imgB is None or imgA2B is None:
        print(f"[{idx}] nie mogę wczytać obrazu"); continue

    # ujednolicenie rozmiaru, gdyby się różniły (nie powinny)
    h = min(imgB.shape[0], imgA2B.shape[0])
    w = min(imgB.shape[1], imgA2B.shape[1])
    if (imgB.shape[0], imgB.shape[1]) != (h, w):
        imgB = cv2.resize(imgB, (w, h), interpolation=cv2.INTER_AREA)
    if (imgA2B.shape[0], imgA2B.shape[1]) != (h, w):
        imgA2B = cv2.resize(imgA2B, (w, h), interpolation=cv2.INTER_AREA)

    # maska ważnych pikseli (oba obrazy mają treść)
    valid = (np.sum(imgB, axis=2) > 0) & (np.sum(imgA2B, axis=2) > 0)

    # downscale (opcjonalnie)
    if DOWNSCALE != 1.0:
        newsz = (int(w*DOWNSCALE), int(h*DOWNSCALE))
        imgB_s   = cv2.resize(imgB,   newsz, interpolation=cv2.INTER_AREA)
        imgA2B_s = cv2.resize(imgA2B, newsz, interpolation=cv2.INTER_AREA)
        valid    = cv2.resize(valid.astype(np.uint8)*255, newsz, interpolation=cv2.INTER_NEAREST).astype(bool)
    else:
        imgB_s, imgA2B_s = imgB, imgA2B

    g1 = cv2.cvtColor(imgB_s,   cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(imgA2B_s, cv2.COLOR_RGB2GRAY)

    flow = compute_flow(g1, g2, FLOW_ALGO)
    flow_hsv, mag = flow_to_hsv_rgb(flow)

    # dodatkowa wizualizacja colorwheel
    flow_color = flow_to_image(np.dstack([flow[...,0], flow[...,1]]), clip_flow=None, convert_to_bgr=False)

    # dopasuj maskę, gdy rozmiar się zmienił
    if valid.shape != mag.shape:
        valid = cv2.resize(valid.astype(np.uint8)*255, (mag.shape[1], mag.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)

    mags = mag[valid]
    if mags.size == 0:
        mean_epe = med_epe = p95 = mmax = 0.0
        psnr_v = ssim_v = 0.0
        nvalid = 0
        v_min = v_mean = v_max = v_med = v_p90 = v_p95 = 0.0
    else:
        mean_epe = float(np.mean(mags))
        med_epe  = float(np.median(mags))
        p95      = float(np.percentile(mags, 95))
        mmax     = float(np.max(mags))
        psnr_v   = psnr_uint8(g1, g2, mask=valid)
        ssim_v   = ssim_uint8(g1, g2, mask=valid)
        nvalid   = int(mags.size)
        # metryki dla pełnego magnitudo (bez maski)
        mag_full = np.sqrt(flow[...,0]*flow[...,0] + flow[...,1]*flow[...,1])
        v_min = float(np.min(mag_full))
        v_max = float(np.max(mag_full))
        v_mean = float(np.mean(mag_full))
        v_med  = float(np.median(mag_full))
        v_p90  = float(np.percentile(mag_full, 90))
        v_p95  = float(np.percentile(mag_full, 95))

    print(f"[{idx:04d}] min={v_min:.3f}  mean={v_mean:.3f}  max={v_max:.3f}  med={v_med:.3f}  p90={v_p90:.3f}  p95={v_p95:.3f}")

    rows.append([idx, mean_epe, med_epe, p95, mmax, psnr_v, ssim_v, nvalid,
                 v_min, v_mean, v_max, v_med, v_p90, v_p95])

    # zapisy wizualizacji (RGB)
    base = f"{idx:04d}.png"
    concat = cv2.hconcat([imgB_s, imgA2B_s, flow_hsv])
    cv2.imwrite(os.path.join(OUT_FLOWHSV, base), flow_hsv)
    cv2.imwrite(os.path.join(OUT_CONCAT,  base), concat)
    cv2.imwrite(os.path.join(OUT_COLORWHEEL, base), flow_color)

# CSV + agregaty
with open(CSV_PATH, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerows(rows)
    if len(rows) > 1:
        arr = np.array(rows[1:], dtype=object)
        epe_mean = np.mean(arr[:,1].astype(np.float64))
        epe_med  = np.median(arr[:,2].astype(np.float64))
        epe_p95  = np.median(arr[:,3].astype(np.float64))
        ssim_m   = np.mean(arr[:,6].astype(np.float64))
        psnr_m   = np.mean(arr[:,5].astype(np.float64))
        # agregaty dla magnitudo
        mag_min_mean  = np.mean(arr[:,8].astype(np.float64))
        mag_mean_mean = np.mean(arr[:,9].astype(np.float64))
        mag_max_mean  = np.mean(arr[:,10].astype(np.float64))
        mag_med_mean  = np.mean(arr[:,11].astype(np.float64))
        mag_p90_mean  = np.mean(arr[:,12].astype(np.float64))
        mag_p95_mean  = np.mean(arr[:,13].astype(np.float64))
        writer.writerow([])
        writer.writerow(["AGG_mean_EPE", epe_mean])
        writer.writerow(["AGG_median_EPE", epe_med])
        writer.writerow(["AGG_p95_EPE", epe_p95])
        writer.writerow(["AGG_mean_SSIM", ssim_m])
        writer.writerow(["AGG_mean_PSNR", psnr_m])
        writer.writerow(["AGG_mean_mag_min",  mag_min_mean])
        writer.writerow(["AGG_mean_mag_mean", mag_mean_mean])
        writer.writerow(["AGG_mean_mag_max",  mag_max_mean])
        writer.writerow(["AGG_mean_mag_median", mag_med_mean])
        writer.writerow(["AGG_mean_mag_p90",  mag_p90_mean])
        writer.writerow(["AGG_mean_mag_p95",  mag_p95_mean])

print(f"Gotowe. Wizualizacje: {OUT_DIR}")
print(f"CSV: {CSV_PATH}")

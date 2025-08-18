import os
import glob
import argparse
import numpy as np
import cv2


def natural_key(p):
    base = os.path.basename(p)
    stem, _ = os.path.splitext(base)
    try:
        return int(stem)
    except Exception:
        return stem


def parse_args():
    ap = argparse.ArgumentParser(description="Warp A_to_B to B using precomputed optical flow")
    ap.add_argument("--base", default="/run/user/1003/gvfs/sftp:host=172.20.97.229,user=marceli/home/marceli/Documents/test9/aligned_pairs",
                    help="Base directory containing A_to_B/ and B/")
    ap.add_argument("--dir_b", default=None, help="Override directory for B images")
    ap.add_argument("--dir_a2b", default=None, help="Override directory for A_to_B images")
    ap.add_argument("--flowdir", default=None, help="Directory with flow .npy files (default: base/flows_numpy)")
    ap.add_argument("--outdir", default=None, help="Output directory (default: base/A2B_warped_to_B)")
    ap.add_argument("--sign", type=float, default=+1.0,
                    help="Sampling sign: +1 means sample A2B at (x+u,y+v); -1 means (x-u,y-v)")
    ap.add_argument("--border", default="constant", choices=["constant","replicate","reflect","reflect101"],
                    help="Border mode for remap")
    ap.add_argument("--fill", type=int, default=0, help="Fill value for constant border")
    ap.add_argument("--vis", action="store_true", help="Save overlay and diff diagnostics")
    ap.add_argument("--fillmode", default="base", choices=["none","base"],
                    help="How to fill black borders after warping: none | base (use original A2B)")
    ap.add_argument("--feather", type=int, default=0,
                    help="Feather width (pixels) for blending warped vs base when fillmode=base")
    # direct-from-A mode
    ap.add_argument("--dir_a", default=None, help="Directory with original A images (to sample directly from A)")
    ap.add_argument("--alignnpz", default=None, help="Path to alignment.npz containing H_B2A/H_A2B")
    ap.add_argument("--mode", default="from_a", choices=["a2b","from_a"],
                    help="a2b: remap A_to_B using flow; from_a: sample directly from A using H_B2A and flow")
    # auto sign and improvement gating
    ap.add_argument("--autosign", action="store_true", help="Try both signs (+1/-1) and pick the better wrt B")
    ap.add_argument("--apply_if_better", action="store_true", help="Apply flow only if it improves over base by at least better_delta")
    ap.add_argument("--better_delta", type=float, default=0.0, help="Minimal MAE improvement (gray) to accept flow")
    # flow hygiene
    ap.add_argument("--flow_clip_low", type=float, default=1.0, help="Low percentile for flow clipping (e.g., 1.0)")
    ap.add_argument("--flow_clip_high", type=float, default=99.0, help="High percentile for flow clipping (e.g., 99.0)")
    ap.add_argument("--flow_median_ksize", type=int, default=3, help="Median filter kernel for flow (odd, 0 to disable)")
    return ap.parse_args()


def load_flow(flow_path):
    f = np.load(flow_path)  # HxWx2 float
    assert f.ndim == 3 and f.shape[2] == 2, f"Bad flow shape: {f.shape}"
    return f.astype(np.float32)


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


def sanitize_flow(flow, p_low=1.0, p_high=99.0, median_ksize=3):
    if flow is None:
        return None
    u = flow[...,0]; v = flow[...,1]
    if p_low is not None and p_high is not None and p_low < p_high:
        lo_u, hi_u = np.percentile(u, p_low), np.percentile(u, p_high)
        lo_v, hi_v = np.percentile(v, p_low), np.percentile(v, p_high)
        u = np.clip(u, lo_u, hi_u)
        v = np.clip(v, lo_v, hi_v)
    flow2 = np.dstack([u, v]).astype(np.float32)
    if median_ksize and median_ksize >= 3 and (median_ksize % 2 == 1):
        u_m = cv2.medianBlur(flow2[...,0], median_ksize)
        v_m = cv2.medianBlur(flow2[...,1], median_ksize)
        flow2 = np.dstack([u_m, v_m]).astype(np.float32)
    return flow2


def warp_a2b_to_b(img_a2b, flow_b_to_a2b, sign=+1.0, borderMode=cv2.BORDER_CONSTANT, borderValue=0):
    H, W = img_a2b.shape[:2]
    u = flow_b_to_a2b[...,0] * float(sign)
    v = flow_b_to_a2b[...,1] * float(sign)
    grid_x, grid_y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    map_x = grid_x + u
    map_y = grid_y + v
    warped = cv2.remap(img_a2b, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                       borderMode=borderMode, borderValue=borderValue)
    # maska ważności: gdzie współrzędne w granicach obrazu
    valid = (map_x >= 0) & (map_x <= (W-1)) & (map_y >= 0) & (map_y <= (H-1))
    return warped, valid.astype(np.uint8), map_x, map_y


def blend_with_base(warped, base, valid_mask, feather=0):
    if valid_mask is None:
        return warped
    H, W = valid_mask.shape
    alpha = valid_mask.astype(np.float32)
    if feather and feather > 0:
        # distance-transform feather: im bardziej w środku valid, tym większa alfa
        alpha_dt = cv2.distanceTransform((alpha>0).astype(np.uint8)*255, cv2.DIST_L2, 3)
        alpha = np.clip(alpha_dt / float(feather), 0.0, 1.0)
    alpha3 = alpha[..., None]
    out = (warped.astype(np.float32) * alpha3 + base.astype(np.float32) * (1.0 - alpha3)).astype(np.uint8)
    return out


def mae_gray(a_bgr, b_bgr):
    ga = cv2.cvtColor(a_bgr, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b_bgr, cv2.COLOR_BGR2GRAY)
    return float(np.mean(np.abs(ga.astype(np.int16) - gb.astype(np.int16))))


def bgrid_to_a_coords(map_x_b, map_y_b, H_B2A):
    # map punkty w geometrii B (map_x_b, map_y_b) do geometrii A za pomocą H_B2A
    Hh, Ww = map_x_b.shape
    pts = np.dstack([map_x_b, map_y_b]).reshape(-1,1,2).astype(np.float32)
    ptsA = cv2.perspectiveTransform(pts, H_B2A.astype(np.float32)).reshape(Hh, Ww, 2)
    return ptsA[...,0], ptsA[...,1]


def main():
    args = parse_args()
    DIR_B   = args.dir_b   if args.dir_b   else os.path.join(args.base, "B")
    DIR_A   = args.dir_a   if args.dir_a   else os.path.join(args.base, "A")
    DIR_A2B = args.dir_a2b if args.dir_a2b else os.path.join(args.base, "A_to_B")
    DIR_FLOW = args.flowdir if args.flowdir else os.path.join(args.base, "flows_numpy")
    OUT_DIR  = args.outdir  if args.outdir  else os.path.join(args.base, "A2B_warped_to_B")
    OUT_OVER = os.path.join(OUT_DIR, "overlay")
    OUT_DIFF = os.path.join(OUT_DIR, "diff")
    ALIGN_NPZ = (
    args.alignnpz
    if args.alignnpz
    else os.path.join(args.base, "..", "align_out", "alignment.npz")
    )
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.vis:
        os.makedirs(OUT_OVER, exist_ok=True)
        os.makedirs(OUT_DIFF, exist_ok=True)

    if args.mode == "from_a":
        al = np.load(ALIGN_NPZ, allow_pickle=True)
        H_B2A = al["H_B2A"] if "H_B2A" in al else np.linalg.inv(al["H_A2B"]) 

    imgs_B   = sorted(glob.glob(os.path.join(DIR_B,   "*.*")), key=natural_key)
    imgs_A2B = sorted(glob.glob(os.path.join(DIR_A2B, "*.*")), key=natural_key)
    flows    = sorted(glob.glob(os.path.join(DIR_FLOW, "*.npy")), key=natural_key)
    if args.mode == "from_a":
        imgs_A = sorted(glob.glob(os.path.join(DIR_A, "*.*")), key=natural_key)

    n = min(len(imgs_B), len(imgs_A2B), len(flows))
    if args.mode == "from_a":
        n = min(n, len(imgs_A))
    if n == 0:
        raise SystemExit(f"Brak danych. B: {DIR_B}, A2B: {DIR_A2B}, flows: {DIR_FLOW}{' A: '+args.dir_a if args.mode=='from_a' else ''}")

    border_map = {
        "constant": cv2.BORDER_CONSTANT,
        "replicate": cv2.BORDER_REPLICATE,
        "reflect": cv2.BORDER_REFLECT,
        "reflect101": cv2.BORDER_REFLECT_101,
    }
    borderMode = border_map[args.border]

    for i in range(n):
        pB   = imgs_B[i]
        pA2B = imgs_A2B[i]
        pF   = flows[i]
        base = os.path.splitext(os.path.basename(pB))[0]
        imgB   = cv2.imread(pB, cv2.IMREAD_COLOR)
        imgA2B = cv2.imread(pA2B, cv2.IMREAD_COLOR)
        if args.mode == "from_a":
            pA = imgs_A[i]
            imgA = cv2.imread(pA, cv2.IMREAD_COLOR)
        flow   = load_flow(pF)
        if imgB is None or imgA2B is None or (args.mode=="from_a" and imgA is None):
            print(f"[{i:04d}] pomijam (brak obrazu)")
            continue
        if imgB.shape != imgA2B.shape:
            print(f"[{i:04d}] różne rozmiary obrazów ({imgB.shape} vs {imgA2B.shape}) – warpuję do rozmiaru B")
            imgA2B = cv2.resize(imgA2B, (imgB.shape[1], imgB.shape[0]), interpolation=cv2.INTER_LINEAR)
        flow_r = resize_flow(flow, (imgB.shape[1], imgB.shape[0]))
        flow_r = sanitize_flow(flow_r, p_low=args.flow_clip_low, p_high=args.flow_clip_high, median_ksize=args.flow_median_ksize)

        if args.mode == "a2b":
            # auto-sign selection (optional)
            if args.autosign:
                base_err = mae_gray(imgA2B, imgB)
                w_p, valid_p, _, _ = warp_a2b_to_b(imgA2B, flow_r, sign=+1.0, borderMode=borderMode, borderValue=(args.fill,args.fill,args.fill))
                w_m, valid_m, _, _ = warp_a2b_to_b(imgA2B, flow_r, sign=-1.0, borderMode=borderMode, borderValue=(args.fill,args.fill,args.fill))
                err_p = mae_gray(w_p, imgB)
                err_m = mae_gray(w_m, imgB)
                best = (w_p, valid_p, +1.0, err_p) if err_p <= err_m else (w_m, valid_m, -1.0, err_m)
                improved = (best[3] <= base_err - args.better_delta) if args.apply_if_better else True
                if improved:
                    warped_raw, valid = best[0], best[1]
                    if args.fillmode == "base":
                        warped = blend_with_base(warped_raw, imgA2B, valid, feather=args.feather)
                    else:
                        warped = warped_raw
                    print(f"[{i:04d}] autosign applied sign={best[2]:+.0f} err={best[3]:.2f} base={base_err:.2f}")
                else:
                    warped = imgA2B.copy()
                    print(f"[{i:04d}] autosign skipped (no improvement) base={base_err:.2f} best={min(err_p,err_m):.2f}")
            else:
                warped_raw, valid, _, _ = warp_a2b_to_b(imgA2B, flow_r, sign=args.sign, borderMode=borderMode, borderValue=(args.fill,args.fill,args.fill))
                if args.fillmode == "base":
                    warped = blend_with_base(warped_raw, imgA2B, valid, feather=args.feather)
                else:
                    warped = warped_raw
        else:
            # from_a: zbuduj mapę z B do A przez flow (B->A2B) i H_B2A (A2B->A)
            def build_from_a_with_sign(sgn):
                _, _, map_x, map_y = warp_a2b_to_b(imgA2B, flow_r, sign=sgn, borderMode=borderMode, borderValue=(args.fill,args.fill,args.fill))
                map_x_A, map_y_A = bgrid_to_a_coords(map_x, map_y, H_B2A)
                warpedA = cv2.remap(imgA, map_x_A, map_y_A, interpolation=cv2.INTER_LINEAR, borderMode=borderMode, borderValue=(args.fill,args.fill,args.fill))
                # valid where sampling inside A
                validA = (map_x_A >= 0) & (map_x_A <= (imgA.shape[1]-1)) & (map_y_A >= 0) & (map_y_A <= (imgA.shape[0]-1))
                return warpedA, validA.astype(np.uint8)
            if args.autosign:
                base_err = mae_gray(imgA2B, imgB)
                w_p, v_p = build_from_a_with_sign(+1.0)
                w_m, v_m = build_from_a_with_sign(-1.0)
                err_p = mae_gray(w_p, imgB)
                err_m = mae_gray(w_m, imgB)
                if err_p <= err_m:
                    warped_raw, valid = w_p, v_p
                    chosen_err = err_p; chosen_sign = +1.0
                else:
                    warped_raw, valid = w_m, v_m
                    chosen_err = err_m; chosen_sign = -1.0
                if args.apply_if_better and not (chosen_err <= base_err - args.better_delta):
                    warped = imgA2B.copy()
                    print(f"[{i:04d}] from_a autosign skipped (no improvement) base={base_err:.2f} best={chosen_err:.2f}")
                else:
                    if args.fillmode == "base":
                        warped = blend_with_base(warped_raw, imgA2B, valid, feather=args.feather)
                    else:
                        warped = warped_raw
                    print(f"[{i:04d}] from_a autosign applied sign={chosen_sign:+.0f} err={chosen_err:.2f} base={base_err:.2f}")
            else:
                warped_raw, valid = build_from_a_with_sign(args.sign)
                if args.fillmode == "base":
                    warped = blend_with_base(warped_raw, imgA2B, valid, feather=args.feather)
                else:
                    warped = warped_raw

        out_path = os.path.join(OUT_DIR, f"{i:04d}.png")
        cv2.imwrite(out_path, warped)

        if args.vis:
            gB = cv2.cvtColor(imgB, cv2.COLOR_BGR2GRAY)
            gW = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            overlay = np.zeros_like(imgB)
            overlay[...,1] = gW
            overlay[...,2] = gB
            cv2.imwrite(os.path.join(OUT_OVER, f"{i:04d}.png"), overlay)
            diff = cv2.absdiff(gB, gW)
            cv2.imwrite(os.path.join(OUT_DIFF, f"{i:04d}.png"), diff)

        print(f"[{i:04d}] zapisano: {out_path}")


if __name__ == "__main__":
    main() 
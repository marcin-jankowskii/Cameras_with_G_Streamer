import os
import cv2
import numpy as np

# =========================
# Parametry użytkownika
# =========================
BASE_PATH = "/home/marceli/Documents/test8/"
file1 = os.path.join(BASE_PATH, "camera1/camera.raw")
file2 = os.path.join(BASE_PATH, "camera2/camera.raw")
ts_file1 = os.path.join(BASE_PATH, "camera1/timestamps.txt")
ts_file2 = os.path.join(BASE_PATH, "camera2/timestamps.txt")

# Dane obrazu (BayerRG8)
width = 3840
height = 2160
buffer_size = width * height  # 1 bajt na piksel dla Bayer RG8

# Synchronizacja
max_time_diff_ms = 30  # maks. różnica timestampów do parowania

# Wyjście
output_dir = os.path.join(BASE_PATH, "synced_jpgs2")
os.makedirs(output_dir, exist_ok=True)

# =========================
# Pomocnicze
# =========================
def read_timestamps(path):
    """Wczytuje timestampy niezależnie od EOL/BOM, pomija puste/zepsute linie."""
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip().lstrip("\ufeff")
            if not s:
                continue
            try:
                out.append(int(s))
            except ValueError:
                # Pomijamy linie, których nie da się sparsować
                pass
    return out

def calculate_fps(timestamps):
    if len(timestamps) < 2:
        return 0.0
    dur = timestamps[-1] - timestamps[0]
    if dur <= 0:
        return 0.0
    return round(1000.0 * (len(timestamps) - 1) / dur, 2)

def expected_frames(raw_path, frame_bytes):
    return (os.path.getsize(raw_path) // frame_bytes) if os.path.exists(raw_path) and frame_bytes > 0 else 0

def read_frame_at(raw_path, index, frame_bytes):
    """Czyta pojedyńczą klatkę z RAW z danego indeksu (losowy dostęp)."""
    with open(raw_path, "rb") as f:
        f.seek(index * frame_bytes, os.SEEK_SET)
        data = f.read(frame_bytes)
    if len(data) != frame_bytes:
        return None
    return data

def bayer_rg8_to_bgr(frame_data, w, h):
    bayer = np.frombuffer(frame_data, dtype=np.uint8)
    if bayer.size != w * h:
        return None
    bayer = bayer.reshape((h, w))
    return cv2.cvtColor(bayer, cv2.COLOR_BayerRG2RGB)

# =========================
# Start
# =========================
print(f"Format: {width}x{height} Bayer RG8")
print(f"Buffer size per frame: {buffer_size} bytes")

# 1) Wczytaj timestampy (odpornie)
ts1 = read_timestamps(ts_file1)
ts2 = read_timestamps(ts_file2)
print(f"Loaded timestamps: camera1 = {len(ts1)}, camera2 = {len(ts2)}")

# 2) Sprawdź rozmiary RAW i obetnij timestampy do realnej liczby klatek
exp1 = expected_frames(file1, buffer_size)
exp2 = expected_frames(file2, buffer_size)
print(f"Camera 1 RAW size = {os.path.getsize(file1) if os.path.exists(file1) else 0} bytes -> expected frames: {exp1}")
print(f"Camera 2 RAW size = {os.path.getsize(file2) if os.path.exists(file2) else 0} bytes -> expected frames: {exp2}")

if exp1 < len(ts1):
    print(f"[WARN] Camera 1: timestamps={len(ts1)} > raw_frames={exp1}. Obcinam do {exp1}.")
    ts1 = ts1[:exp1]
if exp2 < len(ts2):
    print(f"[WARN] Camera 2: timestamps={len(ts2)} > raw_frames={exp2}. Obcinam do {exp2}.")
    ts2 = ts2[:exp2]

# 3) FPS (po przycięciu)
fps1 = calculate_fps(ts1)
fps2 = calculate_fps(ts2)
print(f"Camera 1 FPS: {fps1}")
print(f"Camera 2 FPS: {fps2}")

# 4) Parowanie O(n) – dwa wskaźniki
i, j = 0, 0
paired = []
while i < len(ts1) and j < len(ts2):
    diff = ts1[i] - ts2[j]
    ad = abs(diff)
    if ad <= max_time_diff_ms:
        paired.append((i, j, ts1[i], ts2[j], ad))
        i += 1
        j += 1
    elif diff > 0:
        # kamera2 później dogoni kamerę1
        j += 1
    else:
        # kamera1 później dogoni kamerę2
        i += 1

print(f"Found {len(paired)} synchronized pairs (within {max_time_diff_ms} ms)")

if not paired:
    print("Brak sparowanych klatek – zwiększ max_time_diff_ms lub sprawdź timestampy.")
    exit(0)

# 5) Zapis JPG – czytaj tylko potrzebne klatki (losowy dostęp)
saved = 0
for pair_idx, (i1, i2, t1, t2, diff) in enumerate(paired):
    raw1 = read_frame_at(file1, i1, buffer_size)
    raw2 = read_frame_at(file2, i2, buffer_size)
    if raw1 is None or raw2 is None:
        print(f"[WARN] Skipping pair {pair_idx}: read_frame_at failed (i1={i1}, i2={i2})")
        continue

    bgr1 = bayer_rg8_to_bgr(raw1, width, height)
    bgr2 = bayer_rg8_to_bgr(raw2, width, height)
    if bgr1 is None or bgr2 is None:
        print(f"[WARN] Skipping pair {pair_idx}: conversion failed (i1={i1}, i2={i2})")
        continue

    # Odbicie drugiej kamery (jeśli chcesz)
    bgr2 = cv2.flip(bgr2, 0)

    # podglądowe zmniejszenie (960x540)
    # small1 = cv2.resize(bgr1, (960, 540))
    # small2 = cv2.resize(bgr2, (960, 540))
    # combined = cv2.hconcat([small1, small2])

    combined = cv2.hconcat([bgr1,bgr2])

    filename = f"{pair_idx:04d}_t1_{t1}_t2_{t2}_diff_{diff}ms.jpg"
    cv2.imwrite(os.path.join(output_dir, filename), combined)
    saved += 1

print(f"Saved {saved} synchronized JPEGs to {output_dir}")

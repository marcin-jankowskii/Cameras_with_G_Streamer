import cv2
import numpy as np
import os

# Parametry
width, height = 3840, 2160
frame_size = width * height * 3  # RGB24
max_time_diff_ms = 20  # Maksymalna różnica timestampów do parowania

# Ścieżki
file1 = '/home/marcin/Saves/camera1/camera.raw'
file2 = '/home/marcin/Saves/camera2/camera.raw'
ts_file1 = '/home/marcin/Saves/camera1/timestamps.txt'
ts_file2 = '/home/marcin/Saves/camera2/timestamps.txt'

output_dir = '/home/marcin/Saves/synced_jpgs'
os.makedirs(output_dir, exist_ok=True)

# Wczytaj timestampy
with open(ts_file1) as f:
    ts1 = [int(line.strip()) for line in f]
with open(ts_file2) as f:
    ts2 = [int(line.strip()) for line in f]

print(f"Camera 1 frames: {len(ts1)}")
print(f"Camera 2 frames: {len(ts2)}")

# Oblicz FPS dla obu kamer
def calculate_fps(timestamps):
    if len(timestamps) < 2:
        return 0
    duration_ms = timestamps[-1] - timestamps[0]
    if duration_ms <= 0:
        return 0
    return round(1000 * (len(timestamps) - 1) / duration_ms, 2)

fps1 = calculate_fps(ts1)
fps2 = calculate_fps(ts2)

print(f"Camera 1 FPS: {fps1}")
print(f"Camera 2 FPS: {fps2}")

# Wczytaj klatki
def read_frames(file_path, timestamps):
    frames = []
    with open(file_path, 'rb') as f:
        for _ in timestamps:
            data = f.read(frame_size)
            if len(data) < frame_size:
                break
            frames.append(data)
    return frames

frames1 = read_frames(file1, ts1)
frames2 = read_frames(file2, ts2)

# Mapujemy: timestamp → index (dla szybkiego lookupu)
used2 = set()
paired = []

for idx1, t1 in enumerate(ts1):
    closest_idx2 = None
    closest_diff = None

    for idx2, t2 in enumerate(ts2):
        if idx2 in used2:
            continue
        diff = abs(t1 - t2)
        if closest_diff is None or diff < closest_diff:
            closest_diff = diff
            closest_idx2 = idx2

    if closest_diff is not None and closest_diff <= max_time_diff_ms:
        paired.append((idx1, closest_idx2, t1, ts2[closest_idx2], closest_diff))
        used2.add(closest_idx2)

print(f"Found {len(paired)} synchronized pairs (within {max_time_diff_ms} ms)")

# Zapisz pary jako JPG
for pair_idx, (i1, i2, t1, t2, diff) in enumerate(paired):
    rgb1 = np.frombuffer(frames1[i1], dtype=np.uint8).reshape((height, width, 3))
    bgr1 = cv2.cvtColor(rgb1, cv2.COLOR_RGB2BGR)

    rgb2 = np.frombuffer(frames2[i2], dtype=np.uint8).reshape((height, width, 3))
    bgr2 = cv2.cvtColor(rgb2, cv2.COLOR_RGB2BGR)

    small1 = cv2.resize(bgr1, (960, 540))
    small2 = cv2.resize(bgr2, (960, 540))
    combined = cv2.hconcat([small1, small2])

    filename = f"{pair_idx:04d}_t1_{t1}_t2_{t2}_diff_{diff}ms.jpg"
    cv2.imwrite(os.path.join(output_dir, filename), combined)

print(f"Saved {len(paired)} synchronized JPEGs to {output_dir}")

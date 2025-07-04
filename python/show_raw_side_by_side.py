import cv2
import numpy as np

# Parametry
width, height = 3840, 2160
frame_size = width * height * 3 // 2  # I420/YUV420P

# Pliki
raw1 = '/home/marcin/Saves/camera1/camera.raw'
ts1 = '/home/marcin/Saves/camera1/timestamps.txt'

raw2 = '/home/marcin/Saves/camera2/camera.raw'
ts2 = '/home/marcin/Saves/camera2/timestamps.txt'

# Wczytaj timestampy
with open(ts1) as f:
    timestamps1 = [int(line.strip()) for line in f]

with open(ts2) as f:
    timestamps2 = [int(line.strip()) for line in f]

# Otwórz RAWy
f1 = open(raw1, 'rb')
f2 = open(raw2, 'rb')

idx1 = idx2 = 0

while idx1 < len(timestamps1) and idx2 < len(timestamps2):
    t1 = timestamps1[idx1]
    t2 = timestamps2[idx2]

    # Synchronizacja: dobierz pary klatek o najbliższych timestampach
    if t1 < t2:
        data1 = f1.read(frame_size)
        idx1 += 1
        continue  # Kamera 1 dogania
    elif t2 < t1:
        data2 = f2.read(frame_size)
        idx2 += 1
        continue  # Kamera 2 dogania
    else:
        # Mamy parę zsynchronizowaną
        data1 = f1.read(frame_size)
        data2 = f2.read(frame_size)

        if len(data1) < frame_size or len(data2) < frame_size:
            break

        yuv1 = np.frombuffer(data1, dtype=np.uint8).reshape((height * 3) // 2, width)
        yuv2 = np.frombuffer(data2, dtype=np.uint8).reshape((height * 3) // 2, width)

        bgr1 = cv2.cvtColor(yuv1, cv2.COLOR_YUV2BGR_I420)
        bgr2 = cv2.cvtColor(yuv2, cv2.COLOR_YUV2BGR_I420)

        small1 = cv2.resize(bgr1, (960, 540))
        small2 = cv2.resize(bgr2, (960, 540))
        combined = np.hstack((small1, small2))

        cv2.imshow(f"T1: {t1} ms | T2: {t2} ms", combined)

        idx1 += 1
        idx2 += 1

        key = cv2.waitKey(30)
        if key == ord('q'):
            break

f1.close()
f2.close()
cv2.destroyAllWindows()

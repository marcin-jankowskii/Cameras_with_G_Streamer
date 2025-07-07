import cv2
import os
import time

# Folder z wygenerowanymi JPGami
input_dir = '/home/marcin/Saves/synced_jpgs'

# Wczytaj i posortuj pliki JPG
images = sorted([f for f in os.listdir(input_dir) if f.lower().endswith('.jpg')])

if not images:
    print("❗ Brak obrazów JPG w folderze.")
    exit()

fps = 30  # Możesz zmienić jeśli chcesz

paused = False
frame_idx = 0
total_frames = len(images)

while True:
    img_path = os.path.join(input_dir, images[frame_idx])
    img = cv2.imread(img_path)

    if img is None:
        print(f"❗ Nie udało się wczytać: {img_path}")
        break

    cv2.imshow("Synced Video", img)

    key = cv2.waitKey(0 if paused else int(1000 / fps)) & 0xFF

    if key == ord('q') or key == 27:  # Quit (q or ESC)
        break
    elif key == ord(' '):  # Space → pauza/wznów
        paused = not paused
    elif key == ord('d') and frame_idx < total_frames - 1:  # Next frame
        frame_idx += 1
    elif key == ord('a') and frame_idx > 0:  # Previous frame
        frame_idx -= 1
    elif not paused:
        frame_idx += 1
        if frame_idx >= total_frames:
            break

cv2.destroyAllWindows()

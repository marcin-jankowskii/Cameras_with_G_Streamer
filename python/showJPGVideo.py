import cv2
import os
import time

# Folder z wygenerowanymi JPGami
BASE_PATH = "/home/marceli/Documents/test8/"
input_dir =  BASE_PATH + 'synced_jpgs2'

# Wczytaj i posortuj pliki JPG
images = sorted([f for f in os.listdir(input_dir) if f.lower().endswith('.jpg')])

if not images:
    print("❗ Brak obrazów JPG w folderze.")
    exit()

fps = 30  # Możesz zmienić jeśli chcesz

paused = False
frame_idx = 0
total_frames = len(images)

# Parametry dla VideoWriter (rozmiar, FPS, kodek)
first_image_path = os.path.join(input_dir, images[0])
first_img = cv2.imread(first_image_path)
height, width, _ = first_img.shape
fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Używamy kodeka mp4v (możesz użyć także 'XVID', 'MJPG' itp.)
output_video = cv2.VideoWriter(BASE_PATH + 'output_video.mp4', fourcc, fps, (width, height))

while True:
    img_path = os.path.join(input_dir, images[frame_idx])
    img = cv2.imread(img_path)

    if img is None:
        print(f"❗ Nie udało się wczytać: {img_path}")
        break

    # Dodaj obraz do wideo
    output_video.write(img)

    cv2.imshow("Synced Video", img)

    key = cv2.waitKey(0 if paused else int(1000 / fps)) & 0xFF

    if key == ord('q') or key == 27:  # Quit (q lub ESC)
        break
    elif key == ord(' '):  # Spacja → pauza/wznów
        paused = not paused
    elif key == ord('d') and frame_idx < total_frames - 1:  # Następna klatka
        frame_idx += 1
    elif key == ord('a') and frame_idx > 0:  # Poprzednia klatka
        frame_idx -= 1
    elif not paused:
        frame_idx += 1
        if frame_idx >= total_frames:
            break

# Zakończ zapis i zamknij wszystkie okna
output_video.release()
cv2.destroyAllWindows()

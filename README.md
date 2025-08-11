# Aplikacja do obsługi kamer z GStreamer i Basler Pylon

Ta aplikacja umożliwia obsługę kamer V4L2 (przez GStreamer) oraz kamer Basler Pylon.

## Wymagania systemowe

### Ubuntu/Debian
```bash
# Zainstaluj wymagane pakiety
sudo apt-get update
sudo apt-get install build-essential cmake qt6-base-dev libgstreamer1.0-dev \
                     libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
                     gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
                     gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
                     gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x \
                     gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 \
                     gstreamer1.0-qt5 gstreamer1.0-pulseaudio
```

### Basler Pylon SDK
Pobierz i zainstaluj Basler Pylon SDK ze strony: https://www.baslerweb.com/en/sales-support/downloads/software-downloads/pylon-6-3-0-linux/

```bash
# Zainstaluj Pylon SDK (przykład dla wersji 6.3.0)
sudo dpkg -i pylon_6.3.0.0_amd64.deb
sudo apt-get install -f
```

## Kompilacja

```bash
# Utwórz katalog build
mkdir build
cd build

# Skonfiguruj projekt
qmake ../2kamery_gstreameer.pro

# Skompiluj
make -j$(nproc)
```

## Uruchomienie

```bash
./2kamery_gstreameer
```

## Funkcje

### Obsługiwane kamery:
- **V4L2 kamery**: Standardowe kamery USB obsługiwane przez Video4Linux2
- **Basler kamery**: Kamery przemysłowe Basler z interfejsem USB

### Funkcje aplikacji:
- Podgląd na żywo z maksymalnie 2 kamer
- Nagrywanie w formatach RAW, JPG
- Synchronizacja nagrywania między kamerami
- Kontrola parametrów kamer:
  - **V4L2**: jasność, kontrast, nasycenie, wzmocnienie, ostrość, ekspozycja, balans bieli, zoom, focus
  - **Basler**: czas ekspozycji, wzmocnienie, jasność, format pikseli, tryb triggera

## Konfiguracja kamer Basler

### Automatyczna detekcja
Aplikacja automatycznie wykrywa podłączone kamery Basler i dodaje je do listy dostępnych kamer.

### Parametry kamer Basler:
- **Czas ekspozycji**: Kontroluje czas ekspozycji w mikrosekundach
- **Wzmocnienie**: Kontroluje wzmocnienie sygnału
- **Format pikseli**: Mono8, RGB8, BGR8
- **Tryb triggera**: Włącza/wyłącza tryb triggera

## Rozwiązywanie problemów

### Problem z bibliotekami Pylon
Jeśli występują błędy kompilacji związane z Pylon:
```bash
# Sprawdź czy Pylon jest zainstalowany
ls /opt/pylon/

# Dodaj ścieżki do zmiennych środowiskowych
export PYTHONPATH=/opt/pylon/lib/python:$PYTHONPATH
export LD_LIBRARY_PATH=/opt/pylon/lib:$LD_LIBRARY_PATH
```

### Problem z uprawnieniami do kamer
```bash
# Dodaj użytkownika do grupy video
sudo usermod -a -G video $USER

# Uruchom ponownie sesję lub zaloguj się ponownie
```

### Problem z GStreamer
```bash
# Sprawdź czy GStreamer jest poprawnie zainstalowany
gst-launch-1.0 --version

# Sprawdź dostępne elementy
gst-inspect-1.0 v4l2src
```

## Struktura projektu

```
Cameras_with_G_Streamer-main/
├── 2kamery_gstreameer.pro    # Plik projektu Qt
├── main.cpp                   # Główny plik aplikacji
├── mainwindow.h/cpp          # Główne okno aplikacji
├── camerathread.h/cpp        # Obsługa kamer V4L2
├── baslercamerathread.h/cpp  # Obsługa kamer Basler
├── mainwindow.ui             # Interfejs użytkownika
└── python/                   # Skrypty Python
    ├── saveSyncedToJPG.py
    └── showJPGVideo.py
```

## Licencja

Ten projekt jest udostępniony na licencji MIT. 
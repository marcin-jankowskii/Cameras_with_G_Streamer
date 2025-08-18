#include "baslercamerathread.h"
#include "framewriter.h"
#include <QDir>
#include <QDateTime>
#include <QDebug>

// Pylon / GenApi
using namespace Pylon;
using namespace Basler_UniversalCameraParams;
// (GenApi forward deklaracje są dostępne przez Pylon headers; jeśli by krzyczało o include,
// dodaj: #include <GenApi/GenApi.h>)

static inline QStringList splitResolution(const QString& r) {
    const auto parts = r.split('x');
    return parts.size() == 2 ? parts : QStringList{"0","0"};
}

BaslerCameraThread::BaslerCameraThread(const QString& serialNumber,
                                       const QString& resolution,
                                       int fps,
                                       const QString& format,
                                       QWidget* widget,
                                       const QString& saveDir,
                                       bool isSecondCamera,
                                       QObject* parent)
    : QThread(parent),
      serialNumber(serialNumber),
      resolution(resolution),
      format(format),
      requestedFps(fps),
      widget(widget),
      saveDirectory(saveDir),
      isSecondCamera(isSecondCamera),
      camera(nullptr),
      isRecording(false),
      isRunning(false),
      exposureTime(15000),
      gain(0.0),
      brightness(0.0),
      contrast(0.0),
      saturation(1.0),
      pixelFormat("BayerRG12p"),
      triggerMode(false),
      acquisitionFrameRate(45.0)
{
    // Writer pracuje w osobnym wątku
    writer = new FrameWriter(saveDirectory, format, serialNumber);
    writer->moveToThread(&writerThread);

    // NIE otwieramy plików przy starcie wątku — robimy to dopiero przy startRecording()
    // connect(&writerThread, &QThread::started,  writer, &FrameWriter::open);
    connect(&writerThread, &QThread::finished, writer, &FrameWriter::close);

    writerThread.start(QThread::LowestPriority);
}

BaslerCameraThread::~BaslerCameraThread()
{
    stopCamera();

    writerThread.quit();
    writerThread.wait();
    delete writer;
    writer = nullptr;
}

void BaslerCameraThread::run()
{
    try {
        initializeCamera();
        configureCamera();
        startCamera();

        perfTimer.start();
        framesProcessed = 0;
        framesDropped   = 0;

        while (isRunning) {
            if (camera && camera->IsGrabbing()) {
                bool ok = camera->RetrieveResult(500, grabResult, TimeoutHandling_Return);
                if (ok && grabResult && grabResult->GrabSucceeded()) {

                    // Podgląd (bez flipu; flip zrobimy offline w align_batch)
                    QImage image = convertToQImage(grabResult);
                    if (!image.isNull()) {
                        emit newFrameAvailable(image);
                    }

                    // Sprzętowy timestamp z chunków (fallback: czas OS)
                    quint64 hwTs = 0;
                    quint64 frameCounter = 0; // opcjonalnie do diagnostyki

                    try {
                        GenApi::INodeMap& nm = grabResult->GetChunkDataNodeMap();

                        if (GenApi::CIntegerPtr tsNode = nm.GetNode("ChunkTimestamp")) {
                            if (GenApi::IsReadable(tsNode)) {
                                hwTs = static_cast<quint64>(tsNode->GetValue());
                            }
                        }
                        if (GenApi::CIntegerPtr fcNode = nm.GetNode("ChunkFramecounter")) {
                            if (GenApi::IsReadable(fcNode)) {
                                frameCounter = static_cast<quint64>(fcNode->GetValue());
                            }
                        }
                    } catch (const Pylon::GenericException& e) {
                        qWarning() << "Chunk read failed:" << e.GetDescription();
                    }
                    if (hwTs == 0) {
                        hwTs = static_cast<quint64>(QDateTime::currentMSecsSinceEpoch());
                    }

                    // Zapis klatek (writer w osobnym wątku)
                    if (isRecording) {
                        if (format.compare("RAW", Qt::CaseInsensitive) == 0) {
                            pushRawToWriter(grabResult, hwTs, frameCounter);
                        } else { // JPG — opcjonalne przerzedzanie
                            if ((framesProcessed % 3) == 0 && !image.isNull()) {
                                pushJpegToWriter(image, hwTs);
                            }
                        }
                    }

                    ++framesProcessed;
                    if ((framesProcessed % 200) == 0) {
                        monitorPerformance();
                    }
                } else {
                    ++framesDropped;
                }
            } else {
                msleep(2);
            }
        }
    } catch (const Pylon::GenericException& e) {
        qWarning() << "Pylon error:" << e.GetDescription();
    }
}

void BaslerCameraThread::monitorPerformance()
{
    const qint64 elapsed = perfTimer.elapsed();
    if (elapsed <= 0) return;
    const double fps = (framesProcessed * 1000.0) / double(elapsed);
    const double drop = (framesDropped * 100.0) / double(framesProcessed + framesDropped + 1);
    // (opcjonalnie) qDebug() << "FPS:" << fps << "Drop%:" << drop;
}

void BaslerCameraThread::initializeCamera()
{
    // Uwaga: PylonInitialize/Terminate w main.cpp!
    CTlFactory& tlFactory = CTlFactory::GetInstance();
    DeviceInfoList_t devices;
    tlFactory.EnumerateDevices(devices);

    for (const auto& dev : devices) {
        const QString sn = QString::fromStdString(std::string(dev.GetSerialNumber()));
        if (sn == serialNumber) {
            camera = new CBaslerUniversalInstantCamera(tlFactory.CreateDevice(dev));
            break;
        }
    }
    if (!camera) {
        throw GenericException("Basler camera not found", __FILE__, __LINE__);
    }
}

void BaslerCameraThread::configureCamera()
{
    camera->Open();

    // Rozdzielczość
    const auto parts = splitResolution(resolution);
    const int w = parts[0].toInt();
    const int h = parts[1].toInt();
    if (w > 0 && h > 0) {
        if (camera->Width.IsWritable())  camera->Width.SetValue(w);
        if (camera->Height.IsWritable()) camera->Height.SetValue(h);
    }

    // Strategia grabowania + buforowanie
    camera->MaxNumBuffer = 64;
    camera->AcquisitionMode.SetValue(AcquisitionMode_Continuous);

    // Format piksela
    try {
        if (pixelFormat == "BayerRG12p") {
            camera->PixelFormat.SetValue(PixelFormat_BayerRG12p);
        } else if (pixelFormat == "BayerRG12") {
            camera->PixelFormat.SetValue(PixelFormat_BayerRG12);
        } else if (pixelFormat == "BayerRG16") {
            camera->PixelFormat.SetValue(PixelFormat_BayerRG16);
        } else if (pixelFormat == "BayerRG8") {
            camera->PixelFormat.SetValue(PixelFormat_BayerRG8);
        } else if (pixelFormat == "Mono8") {
            camera->PixelFormat.SetValue(PixelFormat_Mono8);
        } else if (pixelFormat == "RGB8") {
            camera->PixelFormat.SetValue(PixelFormat_RGB8Packed);
        } else if (pixelFormat == "BGR8") {
            camera->PixelFormat.SetValue(PixelFormat_BGR8Packed);
        } else {
            camera->PixelFormat.SetValue(PixelFormat_BayerRG12p);
            pixelFormat = "BayerRG12p";
        }
    } catch (...) {
        // jeśli zadany nie wyszedł, spróbuj w kolejności od najlepszych do najprostszych
        try { camera->PixelFormat.SetValue(PixelFormat_BayerRG12p); pixelFormat = "BayerRG12p"; }
        catch (...) {
            try { camera->PixelFormat.SetValue(PixelFormat_BayerRG12); pixelFormat = "BayerRG12"; }
            catch (...) {
                try { camera->PixelFormat.SetValue(PixelFormat_BayerRG16); pixelFormat = "BayerRG16"; }
                catch (...) {
                    try { camera->PixelFormat.SetValue(PixelFormat_BayerRG8);  pixelFormat = "BayerRG8"; }
                    catch (...) {
                        camera->PixelFormat.SetValue(PixelFormat_Mono8); pixelFormat = "Mono8";
                    }
                }
            }
        }
    }

    // Ekspozycja / gain / kolor — wyłącz auto i ustaw stałe wartości
    try {
        if (camera->ExposureAuto.IsWritable()) camera->ExposureAuto.SetValue(ExposureAuto_Off);
        if (camera->GainAuto.IsWritable())     camera->GainAuto.SetValue(GainAuto_Off);
        if (camera->BalanceWhiteAuto.IsWritable()) camera->BalanceWhiteAuto.SetValue(BalanceWhiteAuto_Off);
        if (camera->GammaEnable.IsWritable())  camera->GammaEnable.SetValue(false);
    } catch (...) {}
    if (camera->ExposureTime.IsWritable()) camera->ExposureTime.SetValue(exposureTime);
    if (camera->Gain.IsWritable())         camera->Gain.SetValue(gain);
    if (camera->BslBrightness.IsWritable()) camera->BslBrightness.SetValue(brightness);
    if (camera->BslContrast.IsWritable())   camera->BslContrast.SetValue(contrast);
    if (camera->BslSaturation.IsWritable()) camera->BslSaturation.SetValue(saturation);

    // Tryb: ciągłe grabowanie (bez triggera) — prościej dla „klikam Record i ma działać”
    try {
        camera->TriggerMode.SetValue(TriggerMode_Off);
    } catch (...) {}

    // FPS (jeśli dostępne) — przy trybie ciągłym możesz go włączyć
    if (camera->AcquisitionFrameRateEnable.IsWritable())
        camera->AcquisitionFrameRateEnable.SetValue(true);
    if (camera->AcquisitionFrameRate.IsWritable())
        camera->AcquisitionFrameRate.SetValue(acquisitionFrameRate);

    // --- CHUNK DATA: włącz Timestamp; Framecounter tylko jeśli dostępny ---
    try {
        if (camera->ChunkModeActive.IsWritable())
            camera->ChunkModeActive.SetValue(true);

        if (camera->ChunkSelector.IsWritable()) {
            // Timestamp
            camera->ChunkSelector.SetValue(ChunkSelector_Timestamp);
            if (camera->ChunkEnable.IsWritable())
                camera->ChunkEnable.SetValue(true);

            // Framecounter (opcjonalnie – spróbuj, ale jak się nie da, olej)
            try {
                camera->ChunkSelector.SetValue(ChunkSelector_Framecounter);
                if (camera->ChunkEnable.IsWritable())
                    camera->ChunkEnable.SetValue(true);
            } catch (...) {
                // Ten model nie wspiera Framecounter — to OK
            }
        }
    } catch (const Pylon::GenericException& e) {
        qWarning() << "Chunk enable failed (Timestamp):" << e.GetDescription();
    }
}

void BaslerCameraThread::startCamera()
{
    camera->StartGrabbing(GrabStrategy_OneByOne, GrabLoop_ProvidedByUser);
    isRunning = true;
}

void BaslerCameraThread::stopCamera()
{
    isRunning = false;

    if (camera) {
        if (camera->IsGrabbing()) camera->StopGrabbing();
        if (camera->IsOpen())     camera->Close();
        delete camera;
        camera = nullptr;
    }

    stopRecording(); // domknij pliki, jeśli sesja trwała
}

void BaslerCameraThread::startRecording()
{
    qDebug() << "BaslerCameraThread: Rozpoczynam nagrywanie...";
    qDebug() << "  - Katalog zapisu:" << saveDirectory;
    qDebug() << "  - Format:" << format;
    qDebug() << "  - Serial number:" << serialNumber;

    if (writer) {
        // otwórz pliki dla tej sesji (blokująco – gwarancja gotowości)
        QMetaObject::invokeMethod(writer, "open", Qt::BlockingQueuedConnection);

        // przekaż metadane do nagłówka sesji
        if (camera) {
            int w = camera->Width.IsReadable()  ? static_cast<int>(camera->Width.GetValue())  : 0;
            int h = camera->Height.IsReadable() ? static_cast<int>(camera->Height.GetValue()) : 0;

            // mapowanie na nasz enum nagłówka
            quint16 pix = 1;  // domyślnie BayerRG8
            quint16 bd  = 8;  // bit depth

        try {
            switch (camera->PixelFormat.GetValue()) {
                case PixelFormat_Mono8:        pix = 0;  bd = 8;  break;
                case PixelFormat_BayerRG8:     pix = 1;  bd = 8;  break;
                case PixelFormat_RGB8Packed:   pix = 2;  bd = 8;  break;
                case PixelFormat_BGR8Packed:   pix = 3;  bd = 8;  break;

                case PixelFormat_BayerRG12p:   pix = 11; bd = 12; break; // 12-bit packed
                case PixelFormat_BayerRG12:    pix = 11; bd = 12; break; // 12-bit unpacked
                case PixelFormat_BayerRG16:    pix = 11; bd = 16; break; // 16-bit (często unpacked)

                // (opcjonalnie gdybyś użył Mono12/Mono16)
                // case PixelFormat_Mono12:       pix = 10; bd = 12; break;
                // case PixelFormat_Mono16:       pix = 10; bd = 16; break;

                default:                        pix = 1;  bd = 8;  break;
            }
        } catch (...) {}

            QMetaObject::invokeMethod(
                writer, "setMeta", Qt::BlockingQueuedConnection,
                Q_ARG(int, w), Q_ARG(int, h),
                Q_ARG(quint16, pix), Q_ARG(quint16, bd)
            );
        }
    }

    isRecording = true;
    qDebug() << "BaslerCameraThread: Nagrywanie rozpoczęte pomyślnie";
}


void BaslerCameraThread::stopRecording()
{
    qDebug() << "BaslerCameraThread: Zatrzymuję nagrywanie...";
    qDebug() << "  - Przetworzone klatki:" << framesProcessed;
    qDebug() << "  - Porzucone klatki:" << framesDropped;

    isRecording = false;
    if (writer) {
        QMetaObject::invokeMethod(writer, "close", Qt::BlockingQueuedConnection);
    }

    qDebug() << "BaslerCameraThread: Nagrywanie zatrzymane pomyślnie";
}

QImage BaslerCameraThread::convertToQImage(const Pylon::CGrabResultPtr& r)
{
    if (!r || !r->GrabSucceeded()) return QImage();

    const int width  = r->GetWidth();
    const int height = r->GetHeight();

    const EPixelType pt = r->GetPixelType();
    if (pt == PixelType_Mono8) {
        const uchar* p = static_cast<const uchar*>(r->GetBuffer());
        return QImage(p, width, height, width, QImage::Format_Grayscale8).copy();
    }

    // Bayer i RGB/BGR — użyj konwertera Pylon
    try {
        CImageFormatConverter conv;
        conv.OutputPixelFormat.SetValue(PixelType_RGB8packed);
        conv.OutputBitAlignment.SetValue(OutputBitAlignment_MsbAligned);
        CPylonImage out;
        conv.Convert(out, r);
        const uchar* p = static_cast<const uchar*>(out.GetBuffer());
        return QImage(p, width, height, width * 3, QImage::Format_RGB888).copy();
    } catch (...) {
        return QImage();
    }
}

void BaslerCameraThread::pushRawToWriter(const Pylon::CGrabResultPtr& r, quint64 ts, quint64 frameCounter)
{
    if (!writer) return;
    const char* p = reinterpret_cast<const char*>(r->GetBuffer());
    const int   n = static_cast<int>(r->GetBufferSize());
    QByteArray ba(p, n);
    QMetaObject::invokeMethod(writer, "writeRaw", Qt::QueuedConnection,
                              Q_ARG(QByteArray, ba),
                              Q_ARG(quint64, ts),
                              Q_ARG(quint64, frameCounter));
}

void BaslerCameraThread::pushJpegToWriter(const QImage& img, quint64 ts)
{
    if (!writer || img.isNull()) return;
    QMetaObject::invokeMethod(writer, "writeJpeg", Qt::QueuedConnection,
                              Q_ARG(QImage, img),
                              Q_ARG(quint64, ts));
}

// --- Settery UI ---

void BaslerCameraThread::setExposureTime(double us)
{
    exposureTime = us;
    if (camera && camera->IsOpen() && camera->ExposureTime.IsWritable()) {
        try { camera->ExposureTime.SetValue(us); } catch (...) {}
    }
}

void BaslerCameraThread::setGain(double g)
{
    gain = g;
    if (camera && camera->IsOpen() && camera->Gain.IsWritable()) {
        try { camera->Gain.SetValue(g); } catch (...) {}
    }
}

void BaslerCameraThread::setBrightness(double v)
{
    brightness = v;
    if (camera && camera->IsOpen() && camera->BslBrightness.IsWritable()) {
        try { camera->BslBrightness.SetValue(v); } catch (...) {}
    }
}

void BaslerCameraThread::setContrast(double v)
{
    contrast = v;
    if (camera && camera->IsOpen() && camera->BslContrast.IsWritable()) {
        try { camera->BslContrast.SetValue(v); } catch (...) {}
    }
}

void BaslerCameraThread::setSaturation(double v)
{
    saturation = v;
    if (camera && camera->IsOpen() && camera->BslSaturation.IsWritable()) {
        try { camera->BslSaturation.SetValue(v); } catch (...) {}
    }
}

void BaslerCameraThread::setPixelFormat(const QString& fmt)
{
    pixelFormat = fmt;
    if (!camera || !camera->IsOpen()) return;
    try {
        if (fmt == "BayerRG8") camera->PixelFormat.SetValue(PixelFormat_BayerRG8);
        else if (fmt == "Mono8") camera->PixelFormat.SetValue(PixelFormat_Mono8);
        else if (fmt == "RGB8") camera->PixelFormat.SetValue(PixelFormat_RGB8Packed);
        else if (fmt == "BGR8") camera->PixelFormat.SetValue(PixelFormat_BGR8Packed);
    } catch (...) { /* ignoruj */ }
}

void BaslerCameraThread::setTriggerMode(bool enabled)
{
    triggerMode = enabled;
    if (!camera || !camera->IsOpen()) return;
    try {
        // Zostajemy przy ciągłym grabowaniu; jeśli w UI włączysz, przełączy na Software
        camera->TriggerMode.SetValue(enabled ? TriggerMode_On : TriggerMode_Off);
        if (enabled) camera->TriggerSource.SetValue(TriggerSource_Software);
    } catch (...) {}
}

void BaslerCameraThread::setAcquisitionFrameRate(double fps)
{
    acquisitionFrameRate = fps;
    if (!camera || !camera->IsOpen()) return;
    try {
        if (camera->AcquisitionFrameRateEnable.IsWritable())
            camera->AcquisitionFrameRateEnable.SetValue(true);
        if (camera->AcquisitionFrameRate.IsWritable())
            camera->AcquisitionFrameRate.SetValue(fps);
    } catch (...) {}
}

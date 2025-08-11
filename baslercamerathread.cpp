#include "baslercamerathread.h"
#include "framewriter.h"
#include <QDir>
#include <QDateTime>
#include <QDebug>

using namespace Pylon;
using namespace Basler_UniversalCameraParams;

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
      pixelFormat("BayerRG8"),
      triggerMode(false),
      acquisitionFrameRate(45.0)
{
    // przygotuj writer (osobny wątek)
    writer = new FrameWriter(saveDirectory, format);
    writer->moveToThread(&writerThread);
    connect(&writerThread, &QThread::started, writer, &FrameWriter::open);
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
                    // konwersja do QImage tylko do podglądu
                    QImage image = convertToQImage(grabResult);
                    if (!image.isNull()) {
                        if (isSecondCamera) image = image.mirrored(false, true);
                        emit newFrameAvailable(image);
                    }

                    // zapis w wątku writer (nie blokuje)
                    if (isRecording) {
                        const quint64 ts = QDateTime::currentMSecsSinceEpoch();
                        if (format == "RAW") {
                            pushRawToWriter(grabResult, ts);
                        } else { // JPG
                            // można dodatkowo przerzedzać: np. co 3. klatkę
                            if (framesProcessed % 3 == 0 && !image.isNull())
                                pushJpegToWriter(image, ts);
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
}

void BaslerCameraThread::initializeCamera()
{
    // Uwaga: PylonInitialize/Teriminate w main.cpp!
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
    camera->MaxNumBuffer = 64; // sporo buforów by I/O nie dławiło
    camera->AcquisitionMode.SetValue(AcquisitionMode_Continuous);

    // Format piksela
    try {
        if (pixelFormat == "BayerRG8") {
            camera->PixelFormat.SetValue(PixelFormat_BayerRG8);
        } else if (pixelFormat == "Mono8") {
            camera->PixelFormat.SetValue(PixelFormat_Mono8);
        } else if (pixelFormat == "RGB8") {
            camera->PixelFormat.SetValue(PixelFormat_RGB8Packed);
        } else if (pixelFormat == "BGR8") {
            camera->PixelFormat.SetValue(PixelFormat_BGR8Packed);
        } else {
            camera->PixelFormat.SetValue(PixelFormat_BayerRG8);
        }
    } catch (...) {
        camera->PixelFormat.SetValue(PixelFormat_Mono8);
        pixelFormat = "Mono8";
    }

    // Ekspozycja / gain / kolor
    if (camera->ExposureTime.IsWritable()) camera->ExposureTime.SetValue(exposureTime);
    if (camera->Gain.IsWritable())         camera->Gain.SetValue(gain);
    if (camera->BslBrightness.IsWritable()) camera->BslBrightness.SetValue(brightness);
    if (camera->BslContrast.IsWritable())   camera->BslContrast.SetValue(contrast);
    if (camera->BslSaturation.IsWritable()) camera->BslSaturation.SetValue(saturation);

    // Trigger
    if (triggerMode) {
        camera->TriggerMode.SetValue(TriggerMode_On);
        camera->TriggerSource.SetValue(TriggerSource_Software);
    } else {
        camera->TriggerMode.SetValue(TriggerMode_Off);
    }

    // FPS (jeśli dostępne)
    if (camera->AcquisitionFrameRateEnable.IsWritable())
        camera->AcquisitionFrameRateEnable.SetValue(true);
    if (camera->AcquisitionFrameRate.IsWritable())
        camera->AcquisitionFrameRate.SetValue(acquisitionFrameRate);
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

    stopRecording(); // zamknij writer jeśli trzeba
}

void BaslerCameraThread::startRecording()
{
    qDebug() << "BaslerCameraThread: Rozpoczynam nagrywanie...";
    qDebug() << "  - Katalog zapisu:" << saveDirectory;
    qDebug() << "  - Format:" << format;
    qDebug() << "  - Serial number:" << serialNumber;
    
    isRecording = true;
    // writer już działa, open() wykonał się przy starcie wątku writerThread
    // if (writer) {
    //     // otwórz pliki dla tej sesji (blokująco, żeby mieć pewność)
    //     QMetaObject::invokeMethod(writer, "open", Qt::BlockingQueuedConnection);
    // }
    
    qDebug() << "BaslerCameraThread: Nagrywanie rozpoczęte pomyślnie";
}

void BaslerCameraThread::stopRecording()
{
    qDebug() << "BaslerCameraThread: Zatrzymuję nagrywanie...";
    qDebug() << "  - Przetworzone klatki:" << framesProcessed;
    qDebug() << "  - Porzucone klatki:" << framesDropped;
    
    isRecording = false;
    // if (writer) {
    //     // domknij i wyflushuj wszystko (blokująco)
    //     QMetaObject::invokeMethod(writer, "close", Qt::BlockingQueuedConnection);
    // }
    
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

void BaslerCameraThread::pushRawToWriter(const Pylon::CGrabResultPtr& r, quint64 ts)
{
    if (!writer) return;
    const char* p = reinterpret_cast<const char*>(r->GetBuffer());
    const int   n = static_cast<int>(r->GetBufferSize());
    QByteArray ba(p, n);
    QMetaObject::invokeMethod(writer, "writeRaw", Qt::QueuedConnection,
                              Q_ARG(QByteArray, ba),
                              Q_ARG(quint64, ts));
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

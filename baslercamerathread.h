#pragma once
#include <QThread>
#include <QImage>
#include <QElapsedTimer>
#include <QPointer>
#include <pylon/PylonIncludes.h>
#include <pylon/BaslerUniversalInstantCamera.h>

class FrameWriter; // forward

class BaslerCameraThread : public QThread
{
    Q_OBJECT
public:
    BaslerCameraThread(const QString& serialNumber,
                       const QString& resolution,
                       int fps,
                       const QString& format,
                       QWidget* widget,
                       const QString& saveDir,
                       bool isSecondCamera,
                       QObject* parent = nullptr);
    ~BaslerCameraThread() override;

    // API
    void setExposureTime(double us);
    void setGain(double gain);
    void setBrightness(double v);
    void setContrast(double v);
    void setSaturation(double v);
    void setPixelFormat(const QString& fmt);
    void setTriggerMode(bool enabled);
    void setAcquisitionFrameRate(double fps);

    void startRecording();
    void stopRecording();
    void stopCamera();

signals:
    void newFrameAvailable(const QImage& img);

protected:
    void run() override;

private:
    void initializeCamera();
    void configureCamera();
    void startCamera();
    void monitorPerformance();
    QImage convertToQImage(const Pylon::CGrabResultPtr& grabResult);
    void pushRawToWriter(const Pylon::CGrabResultPtr& grabResult, quint64 ts, quint64 frameCounter = 0);
    void pushJpegToWriter(const QImage& img, quint64 ts);

private:
    // parametry z UI
    QString serialNumber, resolution, format;
    int requestedFps;
    QWidget* widget;
    QString saveDirectory;
    bool isSecondCamera;

    // stan
    Pylon::CBaslerUniversalInstantCamera* camera = nullptr;
    bool isRecording = false;
    bool isRunning = false;

    // ustawienia
    double exposureTime = 15000;
    double gain = 0.0;
    double brightness = 0.0;
    double contrast = 0.0;
    double saturation = 1.0;
    QString pixelFormat = "BayerRG8";
    bool triggerMode = false;
    double acquisitionFrameRate = 45.0;

    // statystyki
    QElapsedTimer perfTimer;
    quint64 framesProcessed = 0, framesDropped = 0;

    // wynik grabowania
    Pylon::CGrabResultPtr grabResult;

    // writer
    QThread writerThread;
    QPointer<FrameWriter> writer;
};

#ifndef CAMERATHREAD_H
#define CAMERATHREAD_H

#include <QThread>
#include <gst/gst.h>
#include <gst/video/videooverlay.h>
#include <QWidget>
#include <gst/app/gstappsink.h>
#include <QFile>

class CameraThread : public QThread
{
    Q_OBJECT

public:
    CameraThread(const QString& device, const QString& resolution, int fps, const QString& format, QWidget* widget, const QString& saveDir, QObject* parent = nullptr);
    ~CameraThread();

    void startRecording();
    void stopRecording();
    void stopPipeline();
    void startPipeline(bool record = false, GstClock* externalClock = nullptr);
    QString getSaveDirectory() const { return saveDirectory; }
    GstClock* getSharedClock() const { return sharedClock; }
    GstElement* getPipeline() const { return pipeline; }
    QString getDevice() const { return device; }
    QString getFormat() const { return format; }
    QFile rawOutputFile;

signals:
    void newFrameAvailable(const QImage& image);  

protected:
    void run() override;

private:
    QString device;
    QString resolution;
    int fps;
    QString format;
    QWidget* widget;
    QString saveDirectory;
    GstElement* pipeline;
    GMainLoop* loop; 
    bool isRecording = false;
    GstClock* sharedClock;

    static gboolean bus_callback(GstBus* bus, GstMessage* message, gpointer data);
};


#endif // CAMERATHREAD_H

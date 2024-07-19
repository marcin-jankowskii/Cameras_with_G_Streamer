#ifndef CAMERATHREAD_H
#define CAMERATHREAD_H

#include <QThread>
#include <gst/gst.h>
#include <gst/video/videooverlay.h>
#include <QWidget>

class CameraThread : public QThread
{
    Q_OBJECT

public:
    CameraThread(const QString& device, const QString& resolution, int fps, const QString& format, QWidget* widget, const QString& saveDir, QObject* parent = nullptr);
    ~CameraThread();

    void startRecording();
    void stopRecording();
    void stopPipeline();

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

    void startPipeline(bool record = false);
};

#endif // CAMERATHREAD_H

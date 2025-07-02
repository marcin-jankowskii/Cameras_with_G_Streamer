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
    GMainLoop* loop;  // Dodane pole dla głównej pętli
    bool isRecording = false; // Flaga nagrywania

    void startPipeline(bool record = false);

    // Deklaracja funkcji zwrotnej dla komunikatów z GstBus
    static gboolean bus_callback(GstBus* bus, GstMessage* message, gpointer data);
};

#endif // CAMERATHREAD_H

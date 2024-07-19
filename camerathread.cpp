#include "camerathread.h"
#include <gst/gst.h>
#include <gst/video/videooverlay.h>
#include <QDebug>
#include <QDir>

CameraThread::CameraThread(const QString& device, const QString& resolution, int fps, const QString& format, QWidget* widget, const QString& saveDir, QObject* parent)
    : QThread(parent), device(device), resolution(resolution), fps(fps), format(format), widget(widget), saveDirectory(saveDir), pipeline(nullptr)
{
}

CameraThread::~CameraThread()
{
    stopPipeline();
}

void CameraThread::run()
{
    gst_init(nullptr, nullptr);
    startPipeline();

    GMainLoop* loop = g_main_loop_new(nullptr, FALSE);
    g_main_loop_run(loop);
    g_main_loop_unref(loop);
}

void CameraThread::startPipeline(bool record)
{
    QString pipeline_desc;

    if (resolution == "3840x2160" || resolution == "4096x2160" || resolution == "2560x1440") {
        // Use MJPG for high resolutions
        pipeline_desc = QString("v4l2src device=%1 ! image/jpeg,width=%2,height=%3,framerate=%4/1 ! jpegdec ! videoconvert ")
                            .arg(device)
                            .arg(resolution.split('x')[0])
                            .arg(resolution.split('x')[1])
                            .arg(fps);
    } else {
        // Use YUYV for lower resolutions
        pipeline_desc = QString("v4l2src device=%1 ! video/x-raw,width=%2,height=%3,framerate=%4/1 ! videoconvert ")
                            .arg(device)
                            .arg(resolution.split('x')[0])
                            .arg(resolution.split('x')[1])
                            .arg(fps);
    }

    if (record) {
        if (format == "RAW") {
            QString rawFilePath = QDir(saveDirectory).filePath("output.raw");
            pipeline_desc += QString("! queue ! filesink location=%1 ").arg(rawFilePath);
            qDebug() << "Saving RAW to:" << rawFilePath;
        } else if (format == "PNG") {
            QString pngFilePath = QDir(saveDirectory).filePath("frame_%05d.png");
            pipeline_desc += QString("! queue ! pngenc ! multifilesink location=%1 ").arg(pngFilePath);
            qDebug() << "Saving PNG to:" << pngFilePath;
        }
    } else {
        pipeline_desc += "! queue ! xvimagesink sync=false";
    }

    qDebug() << "GStreamer pipeline:" << pipeline_desc;

    pipeline = gst_parse_launch(pipeline_desc.toStdString().c_str(), nullptr);

    if (!pipeline) {
        qWarning() << "Failed to create pipeline";
        return;
    }

    GstElement* videosink = gst_bin_get_by_interface(GST_BIN(pipeline), GST_TYPE_VIDEO_OVERLAY);

    if (videosink) {
        gst_video_overlay_set_window_handle(GST_VIDEO_OVERLAY(videosink), widget->winId());
        gst_video_overlay_set_render_rectangle(GST_VIDEO_OVERLAY(videosink), 0, 0, widget->width(), widget->height());
    }

    GstStateChangeReturn ret = gst_element_set_state(pipeline, GST_STATE_PLAYING);
    if (ret == GST_STATE_CHANGE_FAILURE) {
        qWarning() << "Failed to start pipeline";
        gst_object_unref(pipeline);
        pipeline = nullptr;
    } else {
        qDebug() << "Pipeline started successfully";
        GstState state;
        GstState pending;
        gst_element_get_state(pipeline, &state, &pending, GST_CLOCK_TIME_NONE);
        qDebug() << "Pipeline state:" << gst_element_state_get_name(state);
        qDebug() << "Pending state:" << gst_element_state_get_name(pending);
    }
}

void CameraThread::stopPipeline()
{
    if (pipeline) {
        qDebug() << "Stopping pipeline";
        gst_element_set_state(pipeline, GST_STATE_NULL);
        gst_object_unref(pipeline);
        pipeline = nullptr;
        qDebug() << "Pipeline stopped";
    }
}

void CameraThread::startRecording()
{
    stopPipeline(); // Zatrzymaj aktualny pipeline przed rozpoczęciem nagrywania
    startPipeline(true);
}

void CameraThread::stopRecording()
{
    stopPipeline();
    startPipeline(); // Restart pipeline bez nagrywania
}

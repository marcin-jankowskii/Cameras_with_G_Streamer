#include "camerathread.h"
#include <gst/gst.h>
#include <gst/video/videooverlay.h>
#include <gst/app/gstappsink.h>
#include <QDebug>
#include <QDir>
#include <QFile>
#include <QRunnable>
#include <QThreadPool>


CameraThread::CameraThread(const QString& device, const QString& resolution, int fps, const QString& format, QWidget* widget, const QString& saveDir, QObject* parent)
    : QThread(parent), device(device), resolution(resolution), fps(fps), format(format), widget(widget), saveDirectory(saveDir), pipeline(nullptr), sharedClock(nullptr)
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


class SaveFrameTask : public QRunnable {
public:
    SaveFrameTask(const QString& path, const QByteArray& data)
        : path(path), data(data) {}

    void run() override {
        QFile file(path);
        if (file.open(QIODevice::WriteOnly)) {
            file.write(data);
            file.close();
        }
    }

private:
    QString path;
    QByteArray data;
};


static GstFlowReturn on_new_sample(GstAppSink* sink, gpointer user_data)
{
    CameraThread* thread = static_cast<CameraThread*>(user_data);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_ERROR;

    GstBuffer* buffer = gst_sample_get_buffer(sample);
    GstMapInfo map;
   if (gst_buffer_map(buffer, &map, GST_MAP_READ)) {
        GstClock* clock = thread->getSharedClock() ? thread->getSharedClock() : gst_element_get_clock(thread->getPipeline());

        GstClockTime pts = GST_BUFFER_PTS(buffer);

        if (!thread->getSharedClock())  {
            gst_object_unref(clock);  
        }
        quint64 timestamp = pts / GST_MSECOND;

        QString deviceId = QFileInfo(thread->getDevice()).fileName();
        QString filename = QString("frame_%1.jpg").arg(timestamp);
        QString fullPath = QDir(thread->getSaveDirectory()).filePath(filename);

        QByteArray byteData(reinterpret_cast<const char*>(map.data), map.size);
        QThreadPool::globalInstance()->start(new SaveFrameTask(fullPath, byteData));

        gst_buffer_unmap(buffer, &map);
    }

    gst_sample_unref(sample);
    return GST_FLOW_OK;
}


void CameraThread::startPipeline(bool record, GstClock* externalClock)
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

    if (device == "/dev/video4") { // Assuming /dev/video4 is the second camera
        pipeline_desc += " ! videoflip method=horizontal-flip "; // Add mirror flip for the second camera
    }

    // Dodaję element videoscale, aby obraz mógł być skalowany do rozmiaru widgetu
    // Używam aspektarioadjust=1 aby zachować proporcje obrazu
    pipeline_desc += " ! videoscale method=0 add-borders=true ! video/x-raw,pixel-aspect-ratio=1/1 ";

    if (record) {
        if (format == "RAW") {
            QString rawFilePath = QDir(saveDirectory).filePath("frame_%05d.raw");
            pipeline_desc += QString("! tee name=t ! queue ! multifilesink location=%1 t. ! queue ").arg(rawFilePath);
            qDebug() << "Saving RAW to:" << rawFilePath;
        } else if (format == "PNG") {
            QString pngFilePath = QDir(saveDirectory).filePath("frame_%05d.png");
            pipeline_desc += QString("! tee name=t ! queue ! pngenc ! multifilesink location=%1 t. ! queue ").arg(pngFilePath);
            qDebug() << "Saving PNG to:" << pngFilePath;
        }  else if (format == "JPG") {
            pipeline_desc += "! tee name=t ! queue ! jpegenc ! appsink name=mysink emit-signals=true sync=false t. ! queue ";
            qDebug() << "Saving JPG via appsink";
        }
         else if (format == "YUYV") {
            QString yuyvFilePath = QDir(saveDirectory).filePath("frame_%05d.yuv");
            pipeline_desc += QString("! tee name=t ! queue ! multifilesink location=%1 t. ! queue ").arg(yuyvFilePath);
            qDebug() << "Saving YUYV to:" << yuyvFilePath;
        }
        pipeline_desc += "! xvimagesink sync=false force-aspect-ratio=true";
    } else {
        pipeline_desc += "! queue ! xvimagesink sync=false force-aspect-ratio=true";
    }

    qDebug() << "GStreamer pipeline:" << pipeline_desc;

    pipeline = gst_parse_launch(pipeline_desc.toStdString().c_str(), nullptr);

    if (!pipeline) {
        qWarning() << "Failed to create pipeline";
        return;
    }

    // Dodaj appsink tylko jeśli nagrywanie
    if (record) {
        GstElement* appsink = gst_bin_get_by_name(GST_BIN(pipeline), "mysink");
        if (appsink) {
            gst_app_sink_set_emit_signals((GstAppSink*)appsink, TRUE);
            gst_app_sink_set_drop((GstAppSink*)appsink, TRUE);
            gst_app_sink_set_max_buffers((GstAppSink*)appsink, 1);
            g_signal_connect(appsink, "new-sample", G_CALLBACK(on_new_sample), this);
            gst_object_unref(appsink);
        } else {
            qWarning() << "Appsink not found in pipeline!";
        }
    }

    // Dodaj wspólny zegar, jeśli przekazano
    if (externalClock) {
        sharedClock = externalClock;  // ZAPISUJEMY zegar!
        gst_pipeline_use_clock(GST_PIPELINE(pipeline), sharedClock);
        gst_element_set_start_time(pipeline, GST_CLOCK_TIME_NONE);
    }

    GstElement* videosink = gst_bin_get_by_interface(GST_BIN(pipeline), GST_TYPE_VIDEO_OVERLAY);

    if (videosink) {
        gst_video_overlay_set_window_handle(GST_VIDEO_OVERLAY(videosink), widget->winId());
        
        // Ustaw flagę, żeby video sink uwzględniał zmiany rozmiaru widgetu
        gst_video_overlay_handle_events(GST_VIDEO_OVERLAY(videosink), TRUE);
        
        // Ustaw, żeby obraz był skalowany do pełnego rozmiaru widgetu
        gst_video_overlay_set_render_rectangle(GST_VIDEO_OVERLAY(videosink), 0, 0, widget->width(), widget->height());
        
        // Uwolnij referencję do videosink
        gst_object_unref(videosink);
    }

    // Podłącz handler do sygnału "prepare-window-handle" aby przechwycić sygnał zmiany rozmiaru
    GstBus* bus = gst_pipeline_get_bus(GST_PIPELINE(pipeline));
    gst_bus_add_watch(bus, (GstBusFunc)bus_callback, this);
    gst_object_unref(bus);

    qDebug() << "Setting pipeline to PLAYING state";
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

gboolean CameraThread::bus_callback(GstBus* bus, GstMessage* message, gpointer data)
{
    CameraThread* thread = static_cast<CameraThread*>(data);
    
    switch (GST_MESSAGE_TYPE(message)) {
        case GST_MESSAGE_ERROR: {
            GError* err;
            gchar* debug;
            
            gst_message_parse_error(message, &err, &debug);
            qWarning() << "GStreamer error:" << err->message;
            g_error_free(err);
            g_free(debug);
            break;
        }
        case GST_MESSAGE_EOS:
            qDebug() << "End of stream";
            break;
        case GST_MESSAGE_ELEMENT: {
            const GstStructure* s = gst_message_get_structure(message);
            const gchar* name = gst_structure_get_name(s);
            
            if (gst_structure_has_name(s, "prepare-window-handle")) {
                qDebug() << "Received prepare-window-handle";
                GstElement* sink = GST_ELEMENT(GST_MESSAGE_SRC(message));
                
                if (thread && thread->widget) {
                    gst_video_overlay_set_window_handle(GST_VIDEO_OVERLAY(sink), thread->widget->winId());
                    gst_video_overlay_handle_events(GST_VIDEO_OVERLAY(sink), TRUE);
                    gst_video_overlay_set_render_rectangle(GST_VIDEO_OVERLAY(sink), 0, 0, 
                                                           thread->widget->width(), thread->widget->height());
                }
            }
            break;
        }
        default:
            break;
    }
    
    return TRUE;
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




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


static GstFlowReturn on_new_sample_view(GstAppSink* sink, gpointer user_data)
{
    CameraThread* thread = static_cast<CameraThread*>(user_data);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_ERROR;

    GstBuffer* buffer = gst_sample_get_buffer(sample);
    GstCaps* caps = gst_sample_get_caps(sample);
    GstMapInfo map;
    

    if (gst_buffer_map(buffer, &map, GST_MAP_READ)) {
        int width = 0, height = 0;
        gst_structure_get_int(gst_caps_get_structure(caps, 0), "width", &width);
        gst_structure_get_int(gst_caps_get_structure(caps, 0), "height", &height);

        // Uwaga! Zakładamy RGB → dostosuj jeśli masz inny format
        QImage image((uchar*)map.data, width, height, QImage::Format_RGB888);

        emit thread->newFrameAvailable(image.copy());  // emitujemy kopię QImage

        gst_buffer_unmap(buffer, &map);
    }

    gst_sample_unref(sample);
    return GST_FLOW_OK;
}



static GstFlowReturn on_new_sample(GstAppSink* sink, gpointer user_data)
{
    CameraThread* thread = static_cast<CameraThread*>(user_data);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (!sample) return GST_FLOW_ERROR;

    GstBuffer* buffer = gst_sample_get_buffer(sample);
    GstMapInfo map;
    if (gst_buffer_map(buffer, &map, GST_MAP_READ)) {

        GstClockTime pts = GST_BUFFER_PTS(buffer);
        quint64 timestamp_ms = pts / GST_MSECOND;

        if (thread->getFormat() == "RAW") {
            if (thread->rawOutputFile.isOpen()) {
                thread->rawOutputFile.write(reinterpret_cast<const char*>(map.data), map.size);
            }

            // DOPISUJEMY TIMESTAMP DO PLIKU:
            QString timestampFile = QDir(thread->getSaveDirectory()).filePath("timestamps.txt");
            QFile tsFile(timestampFile);
            if (tsFile.open(QIODevice::Append | QIODevice::Text)) {
                QTextStream out(&tsFile);
                out << timestamp_ms << "\n";
                tsFile.close();
            }

        } else if (thread->getFormat() == "JPG") {
            QString filename = QString("frame_%1.jpg").arg(timestamp_ms);
            QString fullPath = QDir(thread->getSaveDirectory()).filePath(filename);
            QByteArray byteData(reinterpret_cast<const char*>(map.data), map.size);
            QThreadPool::globalInstance()->start(new SaveFrameTask(fullPath, byteData));
        }

        gst_buffer_unmap(buffer, &map);
    }

    gst_sample_unref(sample);
    return GST_FLOW_OK;
}



void CameraThread::startPipeline(bool record, GstClock* externalClock)
{
    QString pipeline_desc;

    // 1. Źródło i dekoder
    if (resolution == "3840x2160" || resolution == "4096x2160" || resolution == "2560x1440") {
        pipeline_desc = QString("v4l2src device=%1 ! image/jpeg,width=%2,height=%3,framerate=%4/1 ! jpegdec ! videoconvert ")
                            .arg(device)
                            .arg(resolution.section('x', 0, 0))
                            .arg(resolution.section('x', 1, 1))
                            .arg(fps);
    } else {
        pipeline_desc = QString("v4l2src device=%1 ! video/x-raw,width=%2,height=%3,framerate=%4/1 ! videoconvert ")
                            .arg(device)
                            .arg(resolution.section('x', 0, 0))
                            .arg(resolution.section('x', 1, 1))
                            .arg(fps);
    }

    if (device == "/dev/video4") {
        pipeline_desc += " ! videoflip method=horizontal-flip ";
    }

    pipeline_desc += " ! videoscale ! video/x-raw,pixel-aspect-ratio=1/1 ! tee name=t ";

    // 2. Gałąź nagrywania
    if (record && (format == "RAW" || format == "JPG" || format == "PNG" || format == "YUYV")) {
        if (format == "RAW") {
            QString filePath = QDir(saveDirectory).filePath("camera.raw");
            rawOutputFile.setFileName(filePath);
            if (!rawOutputFile.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                qWarning() << "Failed to open RAW file:" << filePath;
            } else {
                qDebug() << "Opened RAW file:" << filePath;
            }
            pipeline_desc += "t. ! queue ! appsink name=mysink emit-signals=true sync=false ";
        } else if (format == "JPG") {
            pipeline_desc += "t. ! queue ! jpegenc ! appsink name=mysink emit-signals=true sync=false ";
        } else if (format == "PNG") {
            QString path = QDir(saveDirectory).filePath("frame_%05d.png");
            pipeline_desc += QString("t. ! queue ! pngenc ! multifilesink location=%1 ").arg(path);
        } else if (format == "YUYV") {
            QString path = QDir(saveDirectory).filePath("frame_%05d.yuv");
            pipeline_desc += QString("t. ! queue ! multifilesink location=%1 ").arg(path);
        }
    }

    // 3. Gałąź podglądu
    pipeline_desc += "t. ! queue ! videoconvert ! video/x-raw,format=RGB ! appsink name=mysink_view emit-signals=true sync=false";

    qDebug() << "GStreamer pipeline:" << pipeline_desc;

    pipeline = gst_parse_launch(pipeline_desc.toStdString().c_str(), nullptr);
    if (!pipeline) {
        qWarning() << "Failed to create pipeline";
        return;
    }

    // 4. Obsługa nagrywania (jeśli dotyczy)
    if (record && (format == "RAW" || format == "JPG")) {
        GstElement* appsink = gst_bin_get_by_name(GST_BIN(pipeline), "mysink");
        if (appsink) {
            gst_app_sink_set_emit_signals(GST_APP_SINK(appsink), TRUE);
            gst_app_sink_set_drop(GST_APP_SINK(appsink), TRUE);
            gst_app_sink_set_max_buffers(GST_APP_SINK(appsink), 1);
            g_signal_connect(appsink, "new-sample", G_CALLBACK(on_new_sample), this);
            gst_object_unref(appsink);
        } else {
            qWarning() << "Appsink mysink not found";
        }
    }

    // 5. Obsługa podglądu (ZAWSZE)
    GstElement* appsink_view = gst_bin_get_by_name(GST_BIN(pipeline), "mysink_view");
    if (appsink_view) {
        gst_app_sink_set_emit_signals(GST_APP_SINK(appsink_view), TRUE);
        gst_app_sink_set_drop(GST_APP_SINK(appsink_view), TRUE);
        gst_app_sink_set_max_buffers(GST_APP_SINK(appsink_view), 1);
        g_signal_connect(appsink_view, "new-sample", G_CALLBACK(on_new_sample_view), this);
        gst_object_unref(appsink_view);
    } else {
        qWarning() << "Appsink mysink_view not found";
    }

    // 6. Zegar (jeśli trzeba)
    if (externalClock) {
        sharedClock = externalClock;
        gst_pipeline_use_clock(GST_PIPELINE(pipeline), sharedClock);
        gst_element_set_start_time(pipeline, GST_CLOCK_TIME_NONE);
    }

    // 7. Bus
    GstBus* bus = gst_pipeline_get_bus(GST_PIPELINE(pipeline));
    gst_bus_add_watch(bus, (GstBusFunc)bus_callback, this);
    gst_object_unref(bus);

    qDebug() << "Starting pipeline...";
    gst_element_set_state(pipeline, GST_STATE_PLAYING);
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

        // Zatrzymaj pipeline
        gst_element_set_state(pipeline, GST_STATE_NULL);
        gst_object_unref(pipeline);
        pipeline = nullptr;

        // Zamknij plik RAW jeśli był otwarty
        if (rawOutputFile.isOpen()) {
            rawOutputFile.flush();
            rawOutputFile.close();
            qDebug() << "Raw output file closed.";
        }

        isRecording = false;

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




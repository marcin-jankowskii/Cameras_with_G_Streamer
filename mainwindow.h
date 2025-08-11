#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QProcess>
#include <QDir>
#include <QFileDialog>
#include "camerathread.h"
#include "baslercamerathread.h"
#include "concatenatedwindow.h"

QT_BEGIN_NAMESPACE
namespace Ui { class MainWindow; }
QT_END_NAMESPACE

class CameraThread; // Forward declaration
class BaslerCameraThread; // Forward declaration

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void on_startButton_clicked();
    void on_recordButton_clicked();
    void on_stopRecordingButton_clicked();
    void on_stopButton_clicked();
    void on_selectDirectoryButton_clicked();

    void setBrightness(int value);
    void setContrast(int value);
    void setSaturation(int value);
    void setGain(int value);

    void setBrightness2(int value);
    void setContrast2(int value);
    void setSaturation2(int value);
    void setGain2(int value);

    void setExposure(int value);     // For camera 1
    void setExposure2(int value);    // For camera 2

    // Basler camera functions
    void setBaslerExposureTime(int value);
    void setBaslerExposureTime2(int value);
    void setBaslerGain(int value);
    void setBaslerGain2(int value);
    void setBaslerBrightness(int value);
    void setBaslerBrightness2(int value);
    void setBaslerContrast(int value);
    void setBaslerContrast2(int value);
    void setBaslerSaturation(int value);
    void setBaslerSaturation2(int value);
    void setBaslerPixelFormat(const QString& format);
    void setBaslerPixelFormat2(const QString& format);
    void setBaslerTriggerMode(bool enabled);
    void setBaslerTriggerMode2(bool enabled);


    
    void on_brightnessEdit_textChanged(const QString &value);
    void on_contrastEdit_textChanged(const QString &value);
    void on_saturationEdit_textChanged(const QString &value);
    void on_gainEdit_textChanged(const QString &value);

    void on_brightnessEdit2_textChanged(const QString &value);
    void on_contrastEdit2_textChanged(const QString &value);
    void on_saturationEdit2_textChanged(const QString &value);
    void on_gainEdit2_textChanged(const QString &value);

    void on_exposureEdit_textChanged(const QString &value);   // For camera 1
    void on_exposureEdit2_textChanged(const QString &value);  // For camera 2

    void updateCamera1Image(const QImage& img);
    void updateCamera2Image(const QImage& img);
    void onDisplayModeChanged(int index);

private:
    Ui::MainWindow *ui;
    QString saveDirectory;
    QList<CameraThread*> cameraThreads;
    QList<BaslerCameraThread*> baslerCameraThreads;
    ConcatenatedWindow *concatenatedWindow;
    int currentDisplayMode;
    void populateCameraList();
    QStringList getCameraDevices();
    QStringList getBaslerCameras();
    void populateBaslerCameraList();
    void setupBaslerSliderDefaults();
};

#endif // MAINWINDOW_H

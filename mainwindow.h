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

    // Camera 3/4 controls
    void setBrightness3(int value);
    void setContrast3(int value);
    void setSaturation3(int value);
    void setGain3(int value);

    void setBrightness4(int value);
    void setContrast4(int value);
    void setSaturation4(int value);
    void setGain4(int value);

    void setExposure(int value);     // For camera 1
    void setExposure2(int value);    // For camera 2
    void setExposure3(int value);    // For camera 3
    void setExposure4(int value);    // For camera 4

    // Basler camera functions
    void setBaslerExposureTime(int value);
    void setBaslerExposureTime2(int value);
    void setBaslerExposureTime3(int value);
    void setBaslerExposureTime4(int value);
    void setBaslerGain(int value);
    void setBaslerGain2(int value);
    void setBaslerGain3(int value);
    void setBaslerGain4(int value);
    void setBaslerBrightness(int value);
    void setBaslerBrightness2(int value);
    void setBaslerBrightness3(int value);
    void setBaslerBrightness4(int value);
    void setBaslerContrast(int value);
    void setBaslerContrast2(int value);
    void setBaslerContrast3(int value);
    void setBaslerContrast4(int value);
    void setBaslerSaturation(int value);
    void setBaslerSaturation2(int value);
    void setBaslerSaturation3(int value);
    void setBaslerSaturation4(int value);
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

    // text edits for camera 3/4
    void on_brightnessEdit3_textChanged(const QString &value);
    void on_contrastEdit3_textChanged(const QString &value);
    void on_saturationEdit3_textChanged(const QString &value);
    void on_gainEdit3_textChanged(const QString &value);
    void on_brightnessEdit4_textChanged(const QString &value);
    void on_contrastEdit4_textChanged(const QString &value);
    void on_saturationEdit4_textChanged(const QString &value);
    void on_gainEdit4_textChanged(const QString &value);

    void on_exposureEdit_textChanged(const QString &value);   // For camera 1
    void on_exposureEdit2_textChanged(const QString &value);  // For camera 2
    void on_exposureEdit3_textChanged(const QString &value);  // For camera 3
    void on_exposureEdit4_textChanged(const QString &value);  // For camera 4

    void updateCamera1Image(const QImage& img);
    void updateCamera2Image(const QImage& img);
    // new for 3rd and 4th cameras
    void updateCamera3Image(const QImage& img);
    void updateCamera4Image(const QImage& img);
    void onDisplayModeChanged(int index);

    // zależność widoczności od liczby kamer
    void onCameraCountChanged(int index);

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
    void applyCameraCountVisibility();
};

#endif // MAINWINDOW_H

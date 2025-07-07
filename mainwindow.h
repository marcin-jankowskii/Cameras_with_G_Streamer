#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QProcess>
#include <QDir>
#include <QFileDialog>
#include "camerathread.h"

QT_BEGIN_NAMESPACE
namespace Ui { class MainWindow; }
QT_END_NAMESPACE

class CameraThread; // Forward declaration

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

    void setFocusMin(int value);
    void setZoom(int value);

    void setFocusMin2(int value); // For camera 2
    void setZoom2(int value);     // For camera 2

    void setBrightness(int value);
    void setContrast(int value);
    void setSaturation(int value);
    void setGain(int value);
    void setSharpness(int value);

    void setBrightness2(int value);
    void setContrast2(int value);
    void setSaturation2(int value);
    void setGain2(int value);
    void setSharpness2(int value);

    void setExposure(int value);     // For camera 1
    void setExposure2(int value);    // For camera 2

    void setWhiteBalanceTemperature(int value);     // For camera 1
    void setWhiteBalanceTemperature2(int value);    // For camera 2

    void setPowerLineFrequency(int value);          // For camera 1
    void setPowerLineFrequency2(int value);         // For camera 2

    void setBacklightCompensation(int value);       // For camera 1
    void setBacklightCompensation2(int value);      // For camera 2

    void updateFocusMinLabel(int value);
    void updateZoomLabel(int value);

    void updateFocusMinLabel2(int value); // For camera 2
    void updateZoomLabel2(int value);     // For camera 2

    void updateWhiteBalanceLabel(int value);     // For camera 1
    void updateWhiteBalanceLabel2(int value);    // For camera 2
    
    void on_brightnessEdit_textChanged(const QString &value);
    void on_contrastEdit_textChanged(const QString &value);
    void on_saturationEdit_textChanged(const QString &value);
    void on_gainEdit_textChanged(const QString &value);
    void on_sharpnessEdit_textChanged(const QString &value);

    void on_brightnessEdit2_textChanged(const QString &value);
    void on_contrastEdit2_textChanged(const QString &value);
    void on_saturationEdit2_textChanged(const QString &value);
    void on_gainEdit2_textChanged(const QString &value);
    void on_sharpnessEdit2_textChanged(const QString &value);

    void on_exposureEdit_textChanged(const QString &value);   // For camera 1
    void on_exposureEdit2_textChanged(const QString &value);  // For camera 2

    void on_whiteBalanceEdit_textChanged(const QString &value);   // For camera 1
    void on_whiteBalanceEdit2_textChanged(const QString &value);  // For camera 2

    void on_powerLineFrequencyEdit_textChanged(const QString &value);   // For camera 1
    void on_powerLineFrequencyEdit2_textChanged(const QString &value);  // For camera 2
    
    void on_backlightCompensationEdit_textChanged(const QString &value);   // For camera 1
    void on_backlightCompensationEdit2_textChanged(const QString &value);  // For camera 2

    void updateCamera1Image(const QImage& img);
    void updateCamera2Image(const QImage& img);

private:
    Ui::MainWindow *ui;
    QString saveDirectory;
    QList<CameraThread*> cameraThreads;
    void populateCameraList();
    QStringList getCameraDevices();
};

#endif // MAINWINDOW_H

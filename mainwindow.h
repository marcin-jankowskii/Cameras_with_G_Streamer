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
    void populateCameraList();

private:
    Ui::MainWindow *ui;
    QList<CameraThread*> cameraThreads;
    QList<QWidget*> cameraWindows; // Lista okien podglądu kamer
    QStringList getCameraDevices();
    QString saveDirectory;
};

#endif // MAINWINDOW_H

#include "mainwindow.h"
#include "ui_mainwindow.h"
#include <QProcess>
#include <QRegularExpression>
#include <QDebug>
#include <QTextStream>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::MainWindow)
    , saveDirectory(QDir::homePath())
{
    ui->setupUi(this);

    // Configure UI elements
    ui->cameraCountComboBox->addItems({"1", "2"});
    ui->resolutionComboBox->addItems({
        "640x480", "160x120", "176x144", "320x180", "320x240", "352x288", "424x240",
        "480x270", "640x360", "800x448", "800x600", "848x480", "960x540",
        "1024x576", "1280x720", "1600x896", "1920x1080", "2560x1440",
        "3840x2160", "4096x2160"
    });
    ui->formatComboBox->addItems({"RAW", "PNG"});

    // Set default values
    ui->cameraCountComboBox->setCurrentIndex(1); // Default to 2 cameras
    ui->resolutionComboBox->setCurrentText("1920x1080"); // Default to Full HD
    ui->formatComboBox->setCurrentText("PNG"); // Default to PNG

    populateCameraList();
}

MainWindow::~MainWindow()
{
    for (CameraThread* thread : cameraThreads) {
        thread->quit();
        thread->wait();
        delete thread;
    }
    for (QWidget* window : cameraWindows) {
        delete window;
    }

    delete ui;
}

void MainWindow::populateCameraList()
{
    QStringList cameras = getCameraDevices();
    qDebug() << "Detected cameras:" << cameras;

    if (cameras.isEmpty()) {
        qDebug() << "No cameras detected.";
    }

    ui->camera1ComboBox->clear();
    ui->camera2ComboBox->clear();
    ui->camera1ComboBox->addItems(cameras);
    ui->camera2ComboBox->addItems(cameras);
}

QStringList MainWindow::getCameraDevices()
{
    QStringList cameraDevices;
    QProcess process;
    process.start("v4l2-ctl", QStringList() << "--list-devices");
    process.waitForFinished();

    QString output = process.readAllStandardOutput();
    qDebug() << "v4l2-ctl output:" << output;

    QRegularExpression re("(/dev/video\\d+)");
    QRegularExpressionMatchIterator i = re.globalMatch(output);

    while (i.hasNext()) {
        QRegularExpressionMatch match = i.next();
        cameraDevices << match.captured(1);
    }

    return cameraDevices;
}

void MainWindow::on_startButton_clicked()
{
    int cameraCount = ui->cameraCountComboBox->currentText().toInt();
    QString resolution = ui->resolutionComboBox->currentText();
    int fps = ui->fpsSpinBox->value();
    QString format = ui->formatComboBox->currentText();

    for (CameraThread* thread : cameraThreads) {
        thread->quit();
        thread->wait();
        delete thread;
    }
    cameraThreads.clear();

    for (QWidget* window : cameraWindows) {
        window->close();
        delete window;
    }
    cameraWindows.clear();

    QStringList selectedCameras;
    if (cameraCount >= 1) {
        selectedCameras << ui->camera1ComboBox->currentText();
    }
    if (cameraCount >= 2) {
        selectedCameras << ui->camera2ComboBox->currentText();
    }

    for (int i = 0; i < cameraCount; ++i) {
        QString device = selectedCameras[i];
        QString cameraDir = saveDirectory + QString("/camera%1").arg(i+1);
        QDir().mkpath(cameraDir);
        qDebug() << "Camera" << i+1 << "save directory:" << cameraDir;

        QWidget* window = new QWidget();
        window->setWindowTitle(QString("Camera %1").arg(i+1));
        window->resize(640, 480);
        window->show();
        cameraWindows.append(window);

        CameraThread* thread = new CameraThread(device, resolution, fps, format, window, cameraDir, this);
        cameraThreads.append(thread);
        thread->start();
    }
}

void MainWindow::on_recordButton_clicked()
{
    for (CameraThread* thread : cameraThreads) {
        thread->startRecording();
    }
}

void MainWindow::on_stopRecordingButton_clicked()
{
    for (CameraThread* thread : cameraThreads) {
        thread->stopRecording();
    }
}

void MainWindow::on_stopButton_clicked()
{
    for (CameraThread* thread : cameraThreads) {
        thread->stopPipeline();
        thread->quit();
        thread->wait();
        delete thread;
    }
    cameraThreads.clear();

    for (QWidget* window : cameraWindows) {
        window->close();
        delete window;
    }
    cameraWindows.clear();
}

void MainWindow::on_selectDirectoryButton_clicked()
{
    QString dir = QFileDialog::getExistingDirectory(this, tr("Select Save Directory"), QDir::homePath());
    if (!dir.isEmpty()) {
        saveDirectory = dir;
        qDebug() << "Selected save directory:" << saveDirectory;
    }
}

#include "mainwindow.h"
#include "ui_mainwindow.h"

#include <QProcess>
#include <QRegularExpression>
#include <QDebug>
#include <QTextStream>
#include <QThread>
#include <QFileDialog>
#include <QDir>

#include <pylon/PylonIncludes.h>
#include <pylon/usb/BaslerUsbInstantCamera.h>

#include "baslercamerathread.h"   // używamy wersji z osobnym writerem

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::MainWindow)
    , saveDirectory(QDir::homePath())
{
    ui->setupUi(this);

    // UI
    ui->cameraCountComboBox->addItems({"1", "2", "3", "4"});
    ui->resolutionComboBox->addItems({
        "640x480", "160x120", "176x144", "320x180", "320x240", "352x288", "424x240",
        "480x270", "640x360", "800x448", "800x600", "848x480", "960x540",
        "1024x576", "1280x720", "1600x896", "1920x1080", "2560x1440",
        "3840x2160", "4096x2160"
    });
    ui->formatComboBox->addItems({"JPG", "RAW"});

    ui->cameraCountComboBox->setCurrentIndex(0);
    ui->resolutionComboBox->setCurrentText("3840x2160");
    ui->formatComboBox->setCurrentText("JPG");

    ui->displayModeComboBox->addItems({"Separate Windows", "Concatenated Window"});
    ui->displayModeComboBox->setCurrentIndex(0);
    currentDisplayMode = 0;
    concatenatedWindow = nullptr;

    populateCameraList();
    populateBaslerCameraList();

    // reaguj na zmianę liczby kamer
    connect(ui->cameraCountComboBox, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &MainWindow::onCameraCountChanged);

    // Suwaki i pola edycyjne
    connect(ui->brightnessSlider,  &QSlider::valueChanged, this, &MainWindow::setBrightness);
    connect(ui->contrastSlider,    &QSlider::valueChanged, this, &MainWindow::setContrast);
    connect(ui->saturationSlider,  &QSlider::valueChanged, this, &MainWindow::setSaturation);
    connect(ui->gainSlider,        &QSlider::valueChanged, this, &MainWindow::setGain);

    connect(ui->brightnessSlider2, &QSlider::valueChanged, this, &MainWindow::setBrightness2);
    connect(ui->contrastSlider2,   &QSlider::valueChanged, this, &MainWindow::setContrast2);
    connect(ui->saturationSlider2, &QSlider::valueChanged, this, &MainWindow::setSaturation2);
    connect(ui->gainSlider2,       &QSlider::valueChanged, this, &MainWindow::setGain2);

    // Nowe połączenia dla kamer 3 i 4 (jeśli istnieją w UI)
    if (ui->brightnessSlider3) connect(ui->brightnessSlider3, &QSlider::valueChanged, this, &MainWindow::setBrightness3);
    if (ui->contrastSlider3)   connect(ui->contrastSlider3,   &QSlider::valueChanged, this, &MainWindow::setContrast3);
    if (ui->saturationSlider3) connect(ui->saturationSlider3, &QSlider::valueChanged, this, &MainWindow::setSaturation3);
    if (ui->gainSlider3)       connect(ui->gainSlider3,       &QSlider::valueChanged, this, &MainWindow::setGain3);

    if (ui->brightnessSlider4) connect(ui->brightnessSlider4, &QSlider::valueChanged, this, &MainWindow::setBrightness4);
    if (ui->contrastSlider4)   connect(ui->contrastSlider4,   &QSlider::valueChanged, this, &MainWindow::setContrast4);
    if (ui->saturationSlider4) connect(ui->saturationSlider4, &QSlider::valueChanged, this, &MainWindow::setSaturation4);
    if (ui->gainSlider4)       connect(ui->gainSlider4,       &QSlider::valueChanged, this, &MainWindow::setGain4);

    connect(ui->exposureSlider,    &QSlider::valueChanged, this, &MainWindow::setExposure);
    connect(ui->exposureSlider2,   &QSlider::valueChanged, this, &MainWindow::setExposure2);
    if (ui->exposureSlider3) connect(ui->exposureSlider3, &QSlider::valueChanged, this, &MainWindow::setExposure3);
    if (ui->exposureSlider4) connect(ui->exposureSlider4, &QSlider::valueChanged, this, &MainWindow::setExposure4);

    connect(ui->brightnessEdit,    &QLineEdit::textChanged, this, &MainWindow::on_brightnessEdit_textChanged);
    connect(ui->contrastEdit,      &QLineEdit::textChanged, this, &MainWindow::on_contrastEdit_textChanged);
    connect(ui->saturationEdit,    &QLineEdit::textChanged, this, &MainWindow::on_saturationEdit_textChanged);
    connect(ui->gainEdit,          &QLineEdit::textChanged, this, &MainWindow::on_gainEdit_textChanged);

    connect(ui->brightnessEdit2,   &QLineEdit::textChanged, this, &MainWindow::on_brightnessEdit2_textChanged);
    connect(ui->contrastEdit2,     &QLineEdit::textChanged, this, &MainWindow::on_contrastEdit2_textChanged);
    connect(ui->saturationEdit2,   &QLineEdit::textChanged, this, &MainWindow::on_saturationEdit2_textChanged);
    connect(ui->gainEdit2,         &QLineEdit::textChanged, this, &MainWindow::on_gainEdit2_textChanged);

    if (ui->brightnessEdit3) connect(ui->brightnessEdit3, &QLineEdit::textChanged, this, &MainWindow::on_brightnessEdit3_textChanged);
    if (ui->contrastEdit3)   connect(ui->contrastEdit3,   &QLineEdit::textChanged, this, &MainWindow::on_contrastEdit3_textChanged);
    if (ui->saturationEdit3) connect(ui->saturationEdit3, &QLineEdit::textChanged, this, &MainWindow::on_saturationEdit3_textChanged);
    if (ui->gainEdit3)       connect(ui->gainEdit3,       &QLineEdit::textChanged, this, &MainWindow::on_gainEdit3_textChanged);

    if (ui->brightnessEdit4) connect(ui->brightnessEdit4, &QLineEdit::textChanged, this, &MainWindow::on_brightnessEdit4_textChanged);
    if (ui->contrastEdit4)   connect(ui->contrastEdit4,   &QLineEdit::textChanged, this, &MainWindow::on_contrastEdit4_textChanged);
    if (ui->saturationEdit4) connect(ui->saturationEdit4, &QLineEdit::textChanged, this, &MainWindow::on_saturationEdit4_textChanged);
    if (ui->gainEdit4)       connect(ui->gainEdit4,       &QLineEdit::textChanged, this, &MainWindow::on_gainEdit4_textChanged);

    connect(ui->exposureEdit,      &QLineEdit::textChanged, this, &MainWindow::on_exposureEdit_textChanged);
    connect(ui->exposureEdit2,     &QLineEdit::textChanged, this, &MainWindow::on_exposureEdit2_textChanged);
    if (ui->exposureEdit3) connect(ui->exposureEdit3, &QLineEdit::textChanged, this, &MainWindow::on_exposureEdit3_textChanged);
    if (ui->exposureEdit4) connect(ui->exposureEdit4, &QLineEdit::textChanged, this, &MainWindow::on_exposureEdit4_textChanged);

    connect(ui->displayModeComboBox, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &MainWindow::onDisplayModeChanged);

    setupBaslerSliderDefaults();
    applyCameraCountVisibility();
}

MainWindow::~MainWindow()
{
    for (CameraThread* thread : cameraThreads) {
        thread->quit();
        thread->wait();
        delete thread;
    }
    for (BaslerCameraThread* thread : baslerCameraThreads) {
        thread->stopCamera();
        thread->quit();
        thread->wait();
        delete thread;
    }
    delete ui;
}

void MainWindow::populateCameraList()
{
    const QStringList cameras       = getCameraDevices();
    const QStringList baslerCameras = getBaslerCameras();
    const QStringList allCameras    = cameras + baslerCameras;

    ui->camera1ComboBox->clear();
    ui->camera2ComboBox->clear();
    if (ui->camera3ComboBox) ui->camera3ComboBox->clear();
    if (ui->camera4ComboBox) ui->camera4ComboBox->clear();
    ui->camera1ComboBox->addItems(allCameras);
    ui->camera2ComboBox->addItems(allCameras);
    if (ui->camera3ComboBox) ui->camera3ComboBox->addItems(allCameras);
    if (ui->camera4ComboBox) ui->camera4ComboBox->addItems(allCameras);
}

QStringList MainWindow::getCameraDevices()
{
    QStringList cameraDevices;
    QProcess process;
    process.start("v4l2-ctl", QStringList() << "--list-devices");
    process.waitForFinished();
    const QString output = process.readAllStandardOutput();

    QRegularExpression re("(/dev/video\\d+)");
    QRegularExpressionMatchIterator it = re.globalMatch(output);
    while (it.hasNext()) {
        const QRegularExpressionMatch m = it.next();
        cameraDevices << m.captured(1);
    }
    return cameraDevices;
}

void MainWindow::on_startButton_clicked()
{
    const int cameraCount = ui->cameraCountComboBox->currentText().toInt();
    const QString resolution = ui->resolutionComboBox->currentText();
    const int fps = ui->fpsSpinBox->value();
    const QString format = ui->formatComboBox->currentText();

    // wyczyść wcześniejsze wątki
    for (CameraThread* thread : cameraThreads) {
        thread->quit();
        thread->wait();
        delete thread;
    }
    cameraThreads.clear();
    for (BaslerCameraThread* thread : baslerCameraThreads) {
        thread->stopCamera();
        thread->quit();
        thread->wait();
        delete thread;
    }
    baslerCameraThreads.clear();

    QStringList selectedCameras;
    if (cameraCount >= 1) selectedCameras << ui->camera1ComboBox->currentText();
    if (cameraCount >= 2) selectedCameras << ui->camera2ComboBox->currentText();
    if (cameraCount >= 3 && ui->camera3ComboBox) selectedCameras << ui->camera3ComboBox->currentText();
    if (cameraCount >= 4 && ui->camera4ComboBox) selectedCameras << ui->camera4ComboBox->currentText();

    for (int i = 0; i < cameraCount; ++i) {
        const QString device = selectedCameras[i];
        const QString cameraDir = saveDirectory + QString("/camera%1").arg(i+1);
        QDir().mkpath(cameraDir);

        const bool isBaslerCamera = device.contains("Basler") || device.contains("(");

        if (isBaslerCamera) {
            // wyciągnij SN z "Model (SERIAL)"
            QString serialNumber;
            int l = device.lastIndexOf("(");
            int r = device.lastIndexOf(")");
            if (l >= 0 && r > l) serialNumber = device.mid(l+1, r-l-1);
            else serialNumber = device;

            auto* thread = new BaslerCameraThread(serialNumber, resolution, fps, format, nullptr, cameraDir, (i == 1), this);
            baslerCameraThreads.append(thread);

            if (i == 0)      connect(thread, &BaslerCameraThread::newFrameAvailable, this, &MainWindow::updateCamera1Image);
            else if (i == 1) connect(thread, &BaslerCameraThread::newFrameAvailable, this, &MainWindow::updateCamera2Image);
            else if (i == 2) connect(thread, &BaslerCameraThread::newFrameAvailable, this, &MainWindow::updateCamera3Image);
            else if (i == 3) connect(thread, &BaslerCameraThread::newFrameAvailable, this, &MainWindow::updateCamera4Image);

            thread->start();
        } else {
            // V4L2 kamera — Twoja istniejąca obsługa
            // (opcjonalne: wyłączenia auto trybów)
            {
                QStringList args1 = {"-d", device, "--set-ctrl=focus_automatic_continuous=0"};
                QProcess p1; p1.start("v4l2-ctl", args1); p1.waitForFinished();
                QStringList args2 = {"-d", device, "--set-ctrl=auto_exposure=1"};
                QProcess p2; p2.start("v4l2-ctl", args2); p2.waitForFinished();
                QStringList args3 = {"-d", device, "--set-ctrl=white_balance_automatic=0"};
                QProcess p3; p3.start("v4l2-ctl", args3); p3.waitForFinished();
            }

            CameraThread* thread = new CameraThread(device, resolution, fps, format, nullptr, cameraDir, this);
            cameraThreads.append(thread);

            if (i == 0)      connect(thread, &CameraThread::newFrameAvailable, this, &MainWindow::updateCamera1Image);
            else if (i == 1) connect(thread, &CameraThread::newFrameAvailable, this, &MainWindow::updateCamera2Image);
            else if (i == 2) connect(thread, &CameraThread::newFrameAvailable, this, &MainWindow::updateCamera3Image);
            else if (i == 3) connect(thread, &CameraThread::newFrameAvailable, this, &MainWindow::updateCamera4Image);

            thread->start();
        }
    }
}

void MainWindow::on_recordButton_clicked()
{
    qDebug() << "MainWindow: Rozpoczynam nagrywanie wszystkich kamer...";
    qDebug() << "  - Liczba kamer V4L2:" << cameraThreads.size();
    qDebug() << "  - Liczba kamer Basler:" << baslerCameraThreads.size();
    qDebug() << "  - Katalog zapisu:" << saveDirectory;
    
    // V4L2 (GStreamer)
    GstClock* sharedClock = gst_system_clock_obtain();
    for (CameraThread* thread : cameraThreads) {
        thread->stopPipeline();
        thread->startPipeline(true, sharedClock);
    }
    for (CameraThread* thread : cameraThreads) {
        if (auto* pipeline = thread->getPipeline()) {
            gst_element_set_state(pipeline, GST_STATE_PLAYING);
        }
    }
    // Basler — start zapisu w writerze
    for (BaslerCameraThread* thread : baslerCameraThreads) {
        thread->startRecording();
    }
    
    qDebug() << "MainWindow: Nagrywanie rozpoczęte pomyślnie";
}

void MainWindow::updateCamera1Image(const QImage& img)
{
    if (currentDisplayMode == 0) {
        if (ui->camera1Label) {
            ui->camera1Label->setPixmap(QPixmap::fromImage(img).scaled(ui->camera1Label->size(),
                                                                       Qt::KeepAspectRatio, Qt::SmoothTransformation));
        }
    } else if (currentDisplayMode == 1 && concatenatedWindow) {
        concatenatedWindow->updateCamera1Image(img);
    }
}

void MainWindow::updateCamera2Image(const QImage& img)
{
    // Uwaga: BaslerCameraThread już odbija obraz dla drugiej kamery (isSecondCamera=true),
    // więc tutaj NIE robimy dodatkowego odbicia. Jeśli chcesz odbijać obraz z V4L2,
    // zrób to w swojej klasie CameraThread.
    const QImage toShow = img.mirrored(false,true);

    if (currentDisplayMode == 0) {
        if (ui->camera2Label) {
            ui->camera2Label->setPixmap(QPixmap::fromImage(toShow).scaled(ui->camera2Label->size(),
                                                                          Qt::KeepAspectRatio, Qt::SmoothTransformation));
        }
    } else if (currentDisplayMode == 1 && concatenatedWindow) {
        concatenatedWindow->updateCamera2Image(toShow);
    }
}

void MainWindow::updateCamera3Image(const QImage& img)
{
    const QImage toShow = img;

    if (currentDisplayMode == 0) {
        if (ui->camera3Label) {
            ui->camera3Label->setPixmap(QPixmap::fromImage(toShow).scaled(ui->camera3Label->size(),
                                                                          Qt::KeepAspectRatio, Qt::SmoothTransformation));
        }
    } else if (currentDisplayMode == 1 && concatenatedWindow) {
        concatenatedWindow->updateCamera3Image(toShow);
    }
}

void MainWindow::updateCamera4Image(const QImage& img)
{
    const QImage toShow = img;

    if (currentDisplayMode == 0) {
        if (ui->camera4Label) {
            ui->camera4Label->setPixmap(QPixmap::fromImage(toShow).scaled(ui->camera4Label->size(),
                                                                          Qt::KeepAspectRatio, Qt::SmoothTransformation));
        }
    } else if (currentDisplayMode == 1 && concatenatedWindow) {
        concatenatedWindow->updateCamera4Image(toShow);
    }
}

void MainWindow::on_stopRecordingButton_clicked()
{
    qDebug() << "MainWindow: Zatrzymuję nagrywanie wszystkich kamer...";
    qDebug() << "  - Liczba kamer V4L2:" << cameraThreads.size();
    qDebug() << "  - Liczba kamer Basler:" << baslerCameraThreads.size();
    
    for (CameraThread* thread : cameraThreads) {
        thread->stopRecording();
    }
    for (BaslerCameraThread* thread : baslerCameraThreads) {
        thread->stopRecording();
    }
    
    qDebug() << "MainWindow: Nagrywanie zatrzymane pomyślnie";
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

    for (BaslerCameraThread* thread : baslerCameraThreads) {
        thread->stopCamera();
        thread->quit();
        thread->wait();
        delete thread;
    }
    baslerCameraThreads.clear();
}

void MainWindow::on_selectDirectoryButton_clicked()
{
    const QString dir = QFileDialog::getExistingDirectory(this, tr("Select Save Directory"), QDir::homePath());
    if (!dir.isEmpty()) {
        saveDirectory = dir;
    }
}

// ---- Sterowanie parametrami (Basler lub V4L2) ----

void MainWindow::setBrightness(int value)
{
    const QString device = ui->camera1ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerBrightness(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=brightness=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}
void MainWindow::setContrast(int value)
{
    const QString device = ui->camera1ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerContrast(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=contrast=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}
void MainWindow::setSaturation(int value)
{
    const QString device = ui->camera1ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerSaturation(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=saturation=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}
void MainWindow::setGain(int value)
{
    const QString device = ui->camera1ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerGain(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=gain=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}

void MainWindow::setBrightness2(int value)
{
    const QString device = ui->camera2ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerBrightness2(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=brightness=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}
void MainWindow::setContrast2(int value)
{
    const QString device = ui->camera2ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerContrast2(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=contrast=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}
void MainWindow::setSaturation2(int value)
{
    const QString device = ui->camera2ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerSaturation2(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=saturation=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}
void MainWindow::setGain2(int value)
{
    const QString device = ui->camera2ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerGain2(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=gain=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}

void MainWindow::setBrightness3(int value)
{
    if (!ui->camera3ComboBox) return;
    const QString device = ui->camera3ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerBrightness3(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=brightness=%1").arg(value)}); p.waitForFinished(); }
}
void MainWindow::setContrast3(int value)
{
    if (!ui->camera3ComboBox) return;
    const QString device = ui->camera3ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerContrast3(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=contrast=%1").arg(value)}); p.waitForFinished(); }
}
void MainWindow::setSaturation3(int value)
{
    if (!ui->camera3ComboBox) return;
    const QString device = ui->camera3ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerSaturation3(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=saturation=%1").arg(value)}); p.waitForFinished(); }
}
void MainWindow::setGain3(int value)
{
    if (!ui->camera3ComboBox) return;
    const QString device = ui->camera3ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerGain3(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=gain=%1").arg(value)}); p.waitForFinished(); }
}

void MainWindow::setBrightness4(int value)
{
    if (!ui->camera4ComboBox) return;
    const QString device = ui->camera4ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerBrightness4(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=brightness=%1").arg(value)}); p.waitForFinished(); }
}
void MainWindow::setContrast4(int value)
{
    if (!ui->camera4ComboBox) return;
    const QString device = ui->camera4ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerContrast4(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=contrast=%1").arg(value)}); p.waitForFinished(); }
}
void MainWindow::setSaturation4(int value)
{
    if (!ui->camera4ComboBox) return;
    const QString device = ui->camera4ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerSaturation4(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=saturation=%1").arg(value)}); p.waitForFinished(); }
}
void MainWindow::setGain4(int value)
{
    if (!ui->camera4ComboBox) return;
    const QString device = ui->camera4ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerGain4(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=gain=%1").arg(value)}); p.waitForFinished(); }
}

void MainWindow::setExposure(int value)
{
    const QString device = ui->camera1ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerExposureTime(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=exposure_time_absolute=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}
void MainWindow::setExposure2(int value)
{
    const QString device = ui->camera2ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerExposureTime2(value);
    else {
        QStringList args = {"-d", device, QString("--set-ctrl=exposure_time_absolute=%1").arg(value)};
        QProcess p; p.start("v4l2-ctl", args); p.waitForFinished();
    }
}

void MainWindow::setExposure3(int value)
{
    if (!ui->camera3ComboBox) return;
    const QString device = ui->camera3ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerExposureTime3(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=exposure_time_absolute=%1").arg(value)}); p.waitForFinished(); }
}
void MainWindow::setExposure4(int value)
{
    if (!ui->camera4ComboBox) return;
    const QString device = ui->camera4ComboBox->currentText();
    const bool isBaslerCamera = device.contains("Basler") || device.contains("(");
    if (isBaslerCamera) setBaslerExposureTime4(value);
    else { QProcess p; p.start("v4l2-ctl", {"-d", device, QString("--set-ctrl=exposure_time_absolute=%1").arg(value)}); p.waitForFinished(); }
}

// ---- Edycja pól tekstowych -> suwaki ----
void MainWindow::on_brightnessEdit_textChanged(const QString &v) { ui->brightnessSlider->setValue(v.toInt()); }
void MainWindow::on_contrastEdit_textChanged(const QString &v)   { ui->contrastSlider->setValue(v.toInt()); }
void MainWindow::on_saturationEdit_textChanged(const QString &v) { ui->saturationSlider->setValue(v.toInt()); }
void MainWindow::on_gainEdit_textChanged(const QString &v)       { ui->gainSlider->setValue(v.toInt()); }

void MainWindow::on_brightnessEdit2_textChanged(const QString &v){ ui->brightnessSlider2->setValue(v.toInt()); }
void MainWindow::on_contrastEdit2_textChanged(const QString &v)  { ui->contrastSlider2->setValue(v.toInt()); }
void MainWindow::on_saturationEdit2_textChanged(const QString &v){ ui->saturationSlider2->setValue(v.toInt()); }
void MainWindow::on_gainEdit2_textChanged(const QString &v)      { ui->gainSlider2->setValue(v.toInt()); }

void MainWindow::on_brightnessEdit3_textChanged(const QString &v){ if (ui->brightnessSlider3) ui->brightnessSlider3->setValue(v.toInt()); }
void MainWindow::on_contrastEdit3_textChanged(const QString &v)  { if (ui->contrastSlider3) ui->contrastSlider3->setValue(v.toInt()); }
void MainWindow::on_saturationEdit3_textChanged(const QString &v){ if (ui->saturationSlider3) ui->saturationSlider3->setValue(v.toInt()); }
void MainWindow::on_gainEdit3_textChanged(const QString &v)      { if (ui->gainSlider3) ui->gainSlider3->setValue(v.toInt()); }
void MainWindow::on_brightnessEdit4_textChanged(const QString &v){ if (ui->brightnessSlider4) ui->brightnessSlider4->setValue(v.toInt()); }
void MainWindow::on_contrastEdit4_textChanged(const QString &v)  { if (ui->contrastSlider4) ui->contrastSlider4->setValue(v.toInt()); }
void MainWindow::on_saturationEdit4_textChanged(const QString &v){ if (ui->saturationSlider4) ui->saturationSlider4->setValue(v.toInt()); }
void MainWindow::on_gainEdit4_textChanged(const QString &v)      { if (ui->gainSlider4) ui->gainSlider4->setValue(v.toInt()); }

void MainWindow::on_exposureEdit_textChanged(const QString &v)   { ui->exposureSlider->setValue(v.toInt()); }
void MainWindow::on_exposureEdit2_textChanged(const QString &v)  { ui->exposureSlider2->setValue(v.toInt()); }

void MainWindow::on_exposureEdit3_textChanged(const QString &v)  { if (ui->exposureSlider3) ui->exposureSlider3->setValue(v.toInt()); }
void MainWindow::on_exposureEdit4_textChanged(const QString &v)  { if (ui->exposureSlider4) ui->exposureSlider4->setValue(v.toInt()); }

// ---- Basler: enumeracja urządzeń (bez PylonInitialize/Terterminate tutaj!) ----
QStringList MainWindow::getBaslerCameras()
{
    QStringList baslerCameras;
    try {
        Pylon::CTlFactory& tlFactory = Pylon::CTlFactory::GetInstance();
        Pylon::DeviceInfoList_t devices;
        tlFactory.EnumerateDevices(devices);

        for (const auto& device : devices) {
            const QString serialNumber = QString::fromStdString(std::string(device.GetSerialNumber()));
            const QString modelName   = QString::fromStdString(std::string(device.GetModelName()));
            baslerCameras << QString("%1 (%2)").arg(modelName).arg(serialNumber);
        }
    } catch (const Pylon::GenericException& e) {
        qWarning() << "Failed to enumerate Basler cameras:" << e.GetDescription();
    }
    return baslerCameras;
}

void MainWindow::populateBaslerCameraList()
{
    const QStringList baslerCameras = getBaslerCameras();
    Q_UNUSED(baslerCameras);
    // Jeśli chcesz, możesz dodać te pozycje do osobnych comboboxów.
}

// ---- Basler: settery mapowane na suwaki ----
void MainWindow::setBaslerExposureTime(int value)
{
    if (!baslerCameraThreads.isEmpty()) baslerCameraThreads[0]->setExposureTime(double(value));
}
void MainWindow::setBaslerExposureTime2(int value)
{
    if (baslerCameraThreads.size() > 1) baslerCameraThreads[1]->setExposureTime(double(value));
}
void MainWindow::setBaslerExposureTime3(int value)
{
    if (baslerCameraThreads.size() > 2) baslerCameraThreads[2]->setExposureTime(double(value));
}
void MainWindow::setBaslerExposureTime4(int value)
{
    if (baslerCameraThreads.size() > 3) baslerCameraThreads[3]->setExposureTime(double(value));
}
void MainWindow::setBaslerGain(int value)
{
    if (!baslerCameraThreads.isEmpty()) baslerCameraThreads[0]->setGain(value * 0.001);
}
void MainWindow::setBaslerGain2(int value)
{
    if (baslerCameraThreads.size() > 1) baslerCameraThreads[1]->setGain(value * 0.001);
}
void MainWindow::setBaslerGain3(int value)
{
    if (baslerCameraThreads.size() > 2) baslerCameraThreads[2]->setGain(value * 0.001);
}
void MainWindow::setBaslerGain4(int value)
{
    if (baslerCameraThreads.size() > 3) baslerCameraThreads[3]->setGain(value * 0.001);
}
void MainWindow::setBaslerPixelFormat(const QString& format)
{
    for (BaslerCameraThread* t : baslerCameraThreads) t->setPixelFormat(format);
}
void MainWindow::setBaslerPixelFormat2(const QString& format)
{
    if (baslerCameraThreads.size() > 1) baslerCameraThreads[1]->setPixelFormat(format);
}
void MainWindow::setBaslerTriggerMode(bool enabled)
{
    for (BaslerCameraThread* t : baslerCameraThreads) t->setTriggerMode(enabled);
}
void MainWindow::setBaslerTriggerMode2(bool enabled)
{
    if (baslerCameraThreads.size() > 1) baslerCameraThreads[1]->setTriggerMode(enabled);
}
void MainWindow::setBaslerBrightness(int value)
{
    if (!baslerCameraThreads.isEmpty()) baslerCameraThreads[0]->setBrightness(value * 0.004);
}
void MainWindow::setBaslerContrast(int value)
{
    if (!baslerCameraThreads.isEmpty()) baslerCameraThreads[0]->setContrast(value * 0.004);
}
void MainWindow::setBaslerSaturation(int value)
{
    if (!baslerCameraThreads.isEmpty()) baslerCameraThreads[0]->setSaturation(value * 0.004);
}
void MainWindow::setBaslerBrightness2(int value)
{
    if (baslerCameraThreads.size() > 1) baslerCameraThreads[1]->setBrightness(value * 0.004);
}
void MainWindow::setBaslerContrast2(int value)
{
    if (baslerCameraThreads.size() > 1) baslerCameraThreads[1]->setContrast(value * 0.004);
}
void MainWindow::setBaslerSaturation2(int value)
{
    if (baslerCameraThreads.size() > 1) baslerCameraThreads[1]->setSaturation(value * 0.004);
}
void MainWindow::setBaslerBrightness3(int value)
{
    if (baslerCameraThreads.size() > 2) baslerCameraThreads[2]->setBrightness(value * 0.004);
}
void MainWindow::setBaslerContrast3(int value)
{
    if (baslerCameraThreads.size() > 2) baslerCameraThreads[2]->setContrast(value * 0.004);
}
void MainWindow::setBaslerSaturation3(int value)
{
    if (baslerCameraThreads.size() > 2) baslerCameraThreads[2]->setSaturation(value * 0.004);
}
void MainWindow::setBaslerBrightness4(int value)
{
    if (baslerCameraThreads.size() > 3) baslerCameraThreads[3]->setBrightness(value * 0.004);
}
void MainWindow::setBaslerContrast4(int value)
{
    if (baslerCameraThreads.size() > 3) baslerCameraThreads[3]->setContrast(value * 0.004);
}
void MainWindow::setBaslerSaturation4(int value)
{
    if (baslerCameraThreads.size() > 3) baslerCameraThreads[3]->setSaturation(value * 0.004);
}

void MainWindow::setupBaslerSliderDefaults()
{
    ui->exposureSlider->setRange(27, 1000000);
    ui->exposureSlider->setValue(15000);
    ui->exposureSlider2->setRange(27, 1000000);
    ui->exposureSlider2->setValue(15000);
    if (ui->exposureSlider3) ui->exposureSlider3->setRange(27, 1000000);
    if (ui->exposureSlider3) ui->exposureSlider3->setValue(15000);
    if (ui->exposureSlider4) ui->exposureSlider4->setRange(27, 1000000);
    if (ui->exposureSlider4) ui->exposureSlider4->setValue(15000);

    ui->gainSlider->setRange(0, 48000);
    ui->gainSlider->setValue(0);
    ui->gainSlider2->setRange(0, 48000);
    ui->gainSlider2->setValue(0);
    if (ui->gainSlider3) ui->gainSlider3->setRange(0, 48000);
    if (ui->gainSlider3) ui->gainSlider3->setValue(0);
    if (ui->gainSlider4) ui->gainSlider4->setRange(0, 48000);
    if (ui->gainSlider4) ui->gainSlider4->setValue(0);

    ui->saturationSlider->setRange(0, 500);
    ui->saturationSlider->setValue(250);
    ui->saturationSlider2->setRange(0, 500);
    ui->saturationSlider2->setValue(250);
    if (ui->saturationSlider3) ui->saturationSlider3->setRange(0, 500);
    if (ui->saturationSlider3) ui->saturationSlider3->setValue(250);
    if (ui->saturationSlider4) ui->saturationSlider4->setRange(0, 500);
    if (ui->saturationSlider4) ui->saturationSlider4->setValue(250);

    ui->contrastSlider->setRange(-250, 250);
    ui->contrastSlider->setValue(0);
    ui->contrastSlider2->setRange(-250, 250);
    ui->contrastSlider2->setValue(0);
    if (ui->contrastSlider3) ui->contrastSlider3->setRange(-250, 250);
    if (ui->contrastSlider3) ui->contrastSlider3->setValue(0);
    if (ui->contrastSlider4) ui->contrastSlider4->setRange(-250, 250);
    if (ui->contrastSlider4) ui->contrastSlider4->setValue(0);

    ui->brightnessSlider->setRange(-250, 250);
    ui->brightnessSlider->setValue(0);
    ui->brightnessSlider2->setRange(-250, 250);
    ui->brightnessSlider2->setValue(0);
    if (ui->brightnessSlider3) ui->brightnessSlider3->setRange(-250, 250);
    if (ui->brightnessSlider3) ui->brightnessSlider3->setValue(0);
    if (ui->brightnessSlider4) ui->brightnessSlider4->setRange(-250, 250);
    if (ui->brightnessSlider4) ui->brightnessSlider4->setValue(0);

    ui->brightnessSlider->setSingleStep(1);
    ui->contrastSlider->setSingleStep(1);
    ui->saturationSlider->setSingleStep(1);
    ui->gainSlider->setSingleStep(1);
    ui->exposureSlider->setSingleStep(1);

    ui->brightnessSlider2->setSingleStep(1);
    ui->contrastSlider2->setSingleStep(1);
    ui->saturationSlider2->setSingleStep(1);
    ui->gainSlider2->setSingleStep(1);
    ui->exposureSlider2->setSingleStep(1);

    ui->brightnessEdit->setText("0");
    ui->contrastEdit->setText("0");
    ui->saturationEdit->setText("250");
    ui->gainEdit->setText("0");
    ui->exposureEdit->setText("15000");

    ui->brightnessEdit2->setText("0");
    ui->contrastEdit2->setText("0");
    ui->saturationEdit2->setText("250");
    ui->gainEdit2->setText("0");
    ui->exposureEdit2->setText("15000");

    if (ui->brightnessEdit3) ui->brightnessEdit3->setText("0");
    if (ui->contrastEdit3)   ui->contrastEdit3->setText("0");
    if (ui->saturationEdit3) ui->saturationEdit3->setText("250");
    if (ui->gainEdit3)       ui->gainEdit3->setText("0");
    if (ui->exposureEdit3)   ui->exposureEdit3->setText("15000");

    if (ui->brightnessEdit4) ui->brightnessEdit4->setText("0");
    if (ui->contrastEdit4)   ui->contrastEdit4->setText("0");
    if (ui->saturationEdit4) ui->saturationEdit4->setText("250");
    if (ui->gainEdit4)       ui->gainEdit4->setText("0");
    if (ui->exposureEdit4)   ui->exposureEdit4->setText("15000");
}

void MainWindow::onDisplayModeChanged(int index)
{
    currentDisplayMode = index;
    if (index == 1) {
        if (!concatenatedWindow) concatenatedWindow = new ConcatenatedWindow(this);
        // ustaw aktywną liczbę kamer dla okna konkatenacji
        if (concatenatedWindow) {
            int camCount = ui->cameraCountComboBox->currentText().toInt();
            concatenatedWindow->setActiveCameraCount(camCount);
        }
        concatenatedWindow->show();
        ui->camera1Label->hide();
        ui->camera2Label->hide();
        if (ui->camera3Label) ui->camera3Label->hide();
        if (ui->camera4Label) ui->camera4Label->hide();
    } else {
        if (concatenatedWindow) concatenatedWindow->hide();
        applyCameraCountVisibility();
    }
}

void MainWindow::onCameraCountChanged(int index)
{
    Q_UNUSED(index);
    applyCameraCountVisibility();
    if (concatenatedWindow && currentDisplayMode == 1) {
        int camCount = ui->cameraCountComboBox->currentText().toInt();
        concatenatedWindow->setActiveCameraCount(camCount);
    }
}

void MainWindow::applyCameraCountVisibility()
{
    int camCount = ui->cameraCountComboBox->currentText().toInt();

    // Pokaż/ukryj labele podglądu
    if (ui->camera1Label) ui->camera1Label->setVisible(camCount >= 1);
    if (ui->camera2Label) ui->camera2Label->setVisible(camCount >= 2);
    if (ui->camera3Label) ui->camera3Label->setVisible(camCount >= 3);
    if (ui->camera4Label) ui->camera4Label->setVisible(camCount >= 4);
}

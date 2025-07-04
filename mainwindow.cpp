#include "mainwindow.h"
#include "ui_mainwindow.h"
#include <QProcess>
#include <QRegularExpression>
#include <QDebug>
#include <QTextStream>
#include <QThread>

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
    ui->formatComboBox->addItems({"JPG", "RAW"});

    // Set default values
    ui->cameraCountComboBox->setCurrentIndex(0); // Default to 2 cameras
    ui->resolutionComboBox->setCurrentText("3840x2160"); // Default to Full HD
    ui->formatComboBox->setCurrentText("JPG"); // Default to PNG

    populateCameraList();

    // Connect sliders to slots
    connect(ui->focusMinSlider, &QSlider::valueChanged, this, &MainWindow::setFocusMin);
    connect(ui->zoomSlider, &QSlider::valueChanged, this, &MainWindow::setZoom);

    connect(ui->focusMinSlider2, &QSlider::valueChanged, this, &MainWindow::setFocusMin2);
    connect(ui->zoomSlider2, &QSlider::valueChanged, this, &MainWindow::setZoom2);

    connect(ui->brightnessSlider, &QSlider::valueChanged, this, &MainWindow::setBrightness);
    connect(ui->contrastSlider, &QSlider::valueChanged, this, &MainWindow::setContrast);
    connect(ui->saturationSlider, &QSlider::valueChanged, this, &MainWindow::setSaturation);
    connect(ui->gainSlider, &QSlider::valueChanged, this, &MainWindow::setGain);
    connect(ui->sharpnessSlider, &QSlider::valueChanged, this, &MainWindow::setSharpness);

    connect(ui->brightnessSlider2, &QSlider::valueChanged, this, &MainWindow::setBrightness2);
    connect(ui->contrastSlider2, &QSlider::valueChanged, this, &MainWindow::setContrast2);
    connect(ui->saturationSlider2, &QSlider::valueChanged, this, &MainWindow::setSaturation2);
    connect(ui->gainSlider2, &QSlider::valueChanged, this, &MainWindow::setGain2);
    connect(ui->sharpnessSlider2, &QSlider::valueChanged, this, &MainWindow::setSharpness2);

    connect(ui->exposureSlider, &QSlider::valueChanged, this, &MainWindow::setExposure);
    connect(ui->exposureSlider2, &QSlider::valueChanged, this, &MainWindow::setExposure2);

    // Dodajemy połączenia dla nowych parametrów
    connect(ui->powerLineFrequencySlider, &QSlider::valueChanged, this, &MainWindow::setPowerLineFrequency);
    connect(ui->powerLineFrequencySlider2, &QSlider::valueChanged, this, &MainWindow::setPowerLineFrequency2);
    
    connect(ui->backlightCompensationSlider, &QSlider::valueChanged, this, &MainWindow::setBacklightCompensation);
    connect(ui->backlightCompensationSlider2, &QSlider::valueChanged, this, &MainWindow::setBacklightCompensation2);

    // Connect text edits to slots
    connect(ui->brightnessEdit, &QLineEdit::textChanged, this, &MainWindow::on_brightnessEdit_textChanged);
    connect(ui->contrastEdit, &QLineEdit::textChanged, this, &MainWindow::on_contrastEdit_textChanged);
    connect(ui->saturationEdit, &QLineEdit::textChanged, this, &MainWindow::on_saturationEdit_textChanged);
    connect(ui->gainEdit, &QLineEdit::textChanged, this, &MainWindow::on_gainEdit_textChanged);
    connect(ui->sharpnessEdit, &QLineEdit::textChanged, this, &MainWindow::on_sharpnessEdit_textChanged);

    connect(ui->brightnessEdit2, &QLineEdit::textChanged, this, &MainWindow::on_brightnessEdit2_textChanged);
    connect(ui->contrastEdit2, &QLineEdit::textChanged, this, &MainWindow::on_contrastEdit2_textChanged);
    connect(ui->saturationEdit2, &QLineEdit::textChanged, this, &MainWindow::on_saturationEdit2_textChanged);
    connect(ui->gainEdit2, &QLineEdit::textChanged, this, &MainWindow::on_gainEdit2_textChanged);
    connect(ui->sharpnessEdit2, &QLineEdit::textChanged, this, &MainWindow::on_sharpnessEdit2_textChanged);

    connect(ui->exposureEdit, &QLineEdit::textChanged, this, &MainWindow::on_exposureEdit_textChanged);
    connect(ui->exposureEdit2, &QLineEdit::textChanged, this, &MainWindow::on_exposureEdit2_textChanged);

    connect(ui->whiteBalanceEdit, &QLineEdit::textChanged, this, &MainWindow::on_whiteBalanceEdit_textChanged);
    connect(ui->whiteBalanceEdit2, &QLineEdit::textChanged, this, &MainWindow::on_whiteBalanceEdit2_textChanged);

    // Dodajemy połączenia dla pól tekstowych nowych parametrów
    connect(ui->powerLineFrequencyEdit, &QLineEdit::textChanged, this, &MainWindow::on_powerLineFrequencyEdit_textChanged);
    connect(ui->powerLineFrequencyEdit2, &QLineEdit::textChanged, this, &MainWindow::on_powerLineFrequencyEdit2_textChanged);
    
    connect(ui->backlightCompensationEdit, &QLineEdit::textChanged, this, &MainWindow::on_backlightCompensationEdit_textChanged);
    connect(ui->backlightCompensationEdit2, &QLineEdit::textChanged, this, &MainWindow::on_backlightCompensationEdit2_textChanged);

    // Connect sliders to labels
    connect(ui->focusMinSlider, &QSlider::valueChanged, this, &MainWindow::updateFocusMinLabel);
    connect(ui->zoomSlider, &QSlider::valueChanged, this, &MainWindow::updateZoomLabel);

    connect(ui->focusMinSlider2, &QSlider::valueChanged, this, &MainWindow::updateFocusMinLabel2);
    connect(ui->zoomSlider2, &QSlider::valueChanged, this, &MainWindow::updateZoomLabel2);


    connect(ui->whiteBalanceSlider, &QSlider::valueChanged, this, &MainWindow::setWhiteBalanceTemperature);
    connect(ui->whiteBalanceEdit, &QLineEdit::textChanged, this, &MainWindow::on_whiteBalanceEdit_textChanged);

    connect(ui->whiteBalanceSlider2, &QSlider::valueChanged, this, &MainWindow::setWhiteBalanceTemperature2);
    connect(ui->whiteBalanceEdit2, &QLineEdit::textChanged, this, &MainWindow::on_whiteBalanceEdit2_textChanged);

    // Dodajemy połączenia do aktualizacji etykiet dla white balance
    connect(ui->whiteBalanceSlider, &QSlider::valueChanged, this, &MainWindow::updateWhiteBalanceLabel);
    connect(ui->whiteBalanceSlider2, &QSlider::valueChanged, this, &MainWindow::updateWhiteBalanceLabel2);

    // Set initial label values
    updateFocusMinLabel(ui->focusMinSlider->value());
    updateZoomLabel(ui->zoomSlider->value());

    updateFocusMinLabel2(ui->focusMinSlider2->value());
    updateZoomLabel2(ui->zoomSlider2->value());
    

}

MainWindow::~MainWindow()
{
    for (CameraThread* thread : cameraThreads) {
        thread->quit();
        thread->wait();
        delete thread;
    }
    
    if (cameraDisplayWindow) {
        cameraDisplayWindow->close();
        delete cameraDisplayWindow;
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

    if (cameraDisplayWindow) {
        cameraDisplayWindow->close();
        delete cameraDisplayWindow;
        cameraDisplayWindow = nullptr;
    }

    QStringList selectedCameras;
    if (cameraCount >= 1) {
        selectedCameras << ui->camera1ComboBox->currentText();
    }
    if (cameraCount >= 2) {
        selectedCameras << ui->camera2ComboBox->currentText();
    }

    // Tworzę nowe okno wyświetlania kamer
    cameraDisplayWindow = new CameraDisplayWindow();
    cameraDisplayWindow->show();

    // Dodaję opóźnienie przed uruchomieniem kamer
    QThread::msleep(100);

    for (int i = 0; i < cameraCount; ++i) {
        QString device = selectedCameras[i];
        QString cameraDir = saveDirectory + QString("/camera%1").arg(i+1);
        QDir().mkpath(cameraDir);
        qDebug() << "Camera" << i+1 << "save directory:" << cameraDir;

        // Wyłączenie autofocusu, autoeksponowania i ustawienie zoomu
        QStringList disableAutofocusArgs = {"-d", device, "--set-ctrl=focus_automatic_continuous=0"};
        QStringList disableAutoExposureArgs = {"-d", device, "--set-ctrl=auto_exposure=1"}; // Manual exposure
        QStringList disableAutoWhiteBalanceArgs = {"-d", device, "--set-ctrl=white_balance_automatic=0"};
        QStringList setZoomArgs;
        
        // Ustawienie dodatkowych parametrów wpływających na kolory
        QStringList setPowerLineFrequencyArgs;
        QStringList setBacklightCompensationArgs;
        
        if (i == 0) {
            setZoomArgs = {"-d", device, QString("--set-ctrl=zoom_absolute=%1").arg(ui->zoomSlider->value())};
            setPowerLineFrequencyArgs = {"-d", device, QString("--set-ctrl=power_line_frequency=%1").arg(ui->powerLineFrequencySlider->value())};
            setBacklightCompensationArgs = {"-d", device, QString("--set-ctrl=backlight_compensation=%1").arg(ui->backlightCompensationSlider->value())};
        } else {
            setZoomArgs = {"-d", device, QString("--set-ctrl=zoom_absolute=%1").arg(ui->zoomSlider2->value())};
            setPowerLineFrequencyArgs = {"-d", device, QString("--set-ctrl=power_line_frequency=%1").arg(ui->powerLineFrequencySlider2->value())};
            setBacklightCompensationArgs = {"-d", device, QString("--set-ctrl=backlight_compensation=%1").arg(ui->backlightCompensationSlider2->value())};
        }

        qDebug() << "Executing command:" << "v4l2-ctl" << disableAutofocusArgs;
        QProcess process1;
        process1.start("v4l2-ctl", disableAutofocusArgs);
        process1.waitForFinished();

        qDebug() << "Executing command:" << "v4l2-ctl" << disableAutoExposureArgs;
        QProcess process2;
        process2.start("v4l2-ctl", disableAutoExposureArgs);
        process2.waitForFinished();
        
        qDebug() << "Executing command:" << "v4l2-ctl" << disableAutoWhiteBalanceArgs;
        QProcess process2a;
        process2a.start("v4l2-ctl", disableAutoWhiteBalanceArgs);
        process2a.waitForFinished();

        qDebug() << "Executing command:" << "v4l2-ctl" << setZoomArgs;
        QProcess process3;
        process3.start("v4l2-ctl", setZoomArgs);
        process3.waitForFinished();
        
        // Ustawiamy dodatkowe parametry
        qDebug() << "Executing command:" << "v4l2-ctl" << setPowerLineFrequencyArgs;
        QProcess process4;
        process4.start("v4l2-ctl", setPowerLineFrequencyArgs);
        process4.waitForFinished();
        
        qDebug() << "Executing command:" << "v4l2-ctl" << setBacklightCompensationArgs;
        QProcess process5;
        process5.start("v4l2-ctl", setBacklightCompensationArgs);
        process5.waitForFinished();

        // Wybieram odpowiedni widget dla kamery
        QWidget* cameraWidget = (i == 0) ? cameraDisplayWindow->getCamera1Widget() : cameraDisplayWindow->getCamera2Widget();

        // // Dodaję opóźnienie przed uruchomieniem drugiej kamery
        // if (i > 0) {
        //     QThread::msleep(300); // Opóźnienie 300ms przed uruchomieniem drugiej kamery
        // }

        CameraThread* thread = new CameraThread(device, resolution, fps, format, cameraWidget, cameraDir, this);
        cameraThreads.append(thread);
        thread->start();
    }
}

void MainWindow::on_recordButton_clicked()
{
    // Wspólny zegar
    GstClock* sharedClock = gst_system_clock_obtain();

    // Restartuj pipeline'y w trybie nagrywania z tym samym zegarem
    for (CameraThread* thread : cameraThreads) {
        thread->stopPipeline();
        thread->startPipeline(true, sharedClock);
    }

    // Wymuś ręcznie przełączenie wszystkich pipeline'ów na PLAYING równocześnie
    for (CameraThread* thread : cameraThreads) {
        GstElement* pipeline = thread->getPipeline();
        if (pipeline) {
            gst_element_set_state(pipeline, GST_STATE_PLAYING);
        }
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
    // Najpierw zatrzymujemy wątki kamer
    for (CameraThread* thread : cameraThreads) {
        thread->stopPipeline();
        thread->quit();
        thread->wait();
        delete thread;
    }
    cameraThreads.clear();

    // Dopiero po zatrzymaniu wątków zamykamy okno wyświetlania
    if (cameraDisplayWindow) {
        cameraDisplayWindow->close();
        delete cameraDisplayWindow;
        cameraDisplayWindow = nullptr;
    }
}

void MainWindow::on_selectDirectoryButton_clicked()
{
    QString dir = QFileDialog::getExistingDirectory(this, tr("Select Save Directory"), QDir::homePath());
    if (!dir.isEmpty()) {
        saveDirectory = dir;
        qDebug() << "Selected save directory:" << saveDirectory;
    }
}

void MainWindow::setFocusMin(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList disableAutofocusArgs = {"-d", device, "--set-ctrl=focus_automatic_continuous=0"};
    QStringList setFocusArgs = {"-d", device, QString("--set-ctrl=focus_absolute=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << disableAutofocusArgs;
    QProcess process1;
    process1.start("v4l2-ctl", disableAutofocusArgs);
    process1.waitForFinished();

    qDebug() << "Executing command:" << "v4l2-ctl" << setFocusArgs;
    QProcess process2;
    process2.start("v4l2-ctl", setFocusArgs);
    process2.waitForFinished();
}

void MainWindow::setFocusMin2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList disableAutofocusArgs = {"-d", device, "--set-ctrl=focus_automatic_continuous=0"};
    QStringList setFocusArgs = {"-d", device, QString("--set-ctrl=focus_absolute=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << disableAutofocusArgs;
    QProcess process1;
    process1.start("v4l2-ctl", disableAutofocusArgs);
    process1.waitForFinished();

    qDebug() << "Executing command:" << "v4l2-ctl" << setFocusArgs;
    QProcess process2;
    process2.start("v4l2-ctl", setFocusArgs);
    process2.waitForFinished();
}

void MainWindow::setZoom(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setZoomArgs = {"-d", device, QString("--set-ctrl=zoom_absolute=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setZoomArgs;
    QProcess process;
    process.start("v4l2-ctl", setZoomArgs);
    process.waitForFinished();
}

void MainWindow::setZoom2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setZoomArgs = {"-d", device, QString("--set-ctrl=zoom_absolute=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setZoomArgs;
    QProcess process;
    process.start("v4l2-ctl", setZoomArgs);
    process.waitForFinished();
}

void MainWindow::setBrightness(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setBrightnessArgs = {"-d", device, QString("--set-ctrl=brightness=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setBrightnessArgs;
    QProcess process;
    process.start("v4l2-ctl", setBrightnessArgs);
    process.waitForFinished();
}

void MainWindow::setContrast(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setContrastArgs = {"-d", device, QString("--set-ctrl=contrast=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setContrastArgs;
    QProcess process;
    process.start("v4l2-ctl", setContrastArgs);
    process.waitForFinished();
}

void MainWindow::setSaturation(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setSaturationArgs = {"-d", device, QString("--set-ctrl=saturation=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setSaturationArgs;
    QProcess process;
    process.start("v4l2-ctl", setSaturationArgs);
    process.waitForFinished();
}

void MainWindow::setGain(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setGainArgs = {"-d", device, QString("--set-ctrl=gain=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setGainArgs;
    QProcess process;
    process.start("v4l2-ctl", setGainArgs);
    process.waitForFinished();
}

void MainWindow::setSharpness(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setSharpnessArgs = {"-d", device, QString("--set-ctrl=sharpness=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setSharpnessArgs;
    QProcess process;
    process.start("v4l2-ctl", setSharpnessArgs);
    process.waitForFinished();
}

void MainWindow::setBrightness2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setBrightnessArgs = {"-d", device, QString("--set-ctrl=brightness=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setBrightnessArgs;
    QProcess process;
    process.start("v4l2-ctl", setBrightnessArgs);
    process.waitForFinished();
}

void MainWindow::setContrast2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setContrastArgs = {"-d", device, QString("--set-ctrl=contrast=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setContrastArgs;
    QProcess process;
    process.start("v4l2-ctl", setContrastArgs);
    process.waitForFinished();
}

void MainWindow::setSaturation2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setSaturationArgs = {"-d", device, QString("--set-ctrl=saturation=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setSaturationArgs;
    QProcess process;
    process.start("v4l2-ctl", setSaturationArgs);
    process.waitForFinished();
}

void MainWindow::setGain2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setGainArgs = {"-d", device, QString("--set-ctrl=gain=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setGainArgs;
    QProcess process;
    process.start("v4l2-ctl", setGainArgs);
    process.waitForFinished();
}

void MainWindow::setSharpness2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setSharpnessArgs = {"-d", device, QString("--set-ctrl=sharpness=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setSharpnessArgs;
    QProcess process;
    process.start("v4l2-ctl", setSharpnessArgs);
    process.waitForFinished();
}

void MainWindow::setExposure(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setExposureArgs = {"-d", device, QString("--set-ctrl=exposure_time_absolute=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setExposureArgs;
    QProcess process;
    process.start("v4l2-ctl", setExposureArgs);
    process.waitForFinished();
}

void MainWindow::setExposure2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setExposureArgs = {"-d", device, QString("--set-ctrl=exposure_time_absolute=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setExposureArgs;
    QProcess process;
    process.start("v4l2-ctl", setExposureArgs);
    process.waitForFinished();
}

void MainWindow::setWhiteBalanceTemperature(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    
    // Najpierw wyłączamy automatyczny balans bieli
    QStringList disableAutoWhiteBalanceArgs = {"-d", device, "--set-ctrl=white_balance_automatic=0"};
    QProcess processDisableAuto;
    processDisableAuto.start("v4l2-ctl", disableAutoWhiteBalanceArgs);
    processDisableAuto.waitForFinished();
    
    // Teraz ustawiamy temperaturę balansu bieli
    QStringList setWhiteBalanceArgs = {"-d", device, QString("--set-ctrl=white_balance_temperature=%1").arg(value)};
    QProcess process;
    process.start("v4l2-ctl", setWhiteBalanceArgs);
    process.waitForFinished();
    
    // Aktualizujemy pole tekstowe
    ui->whiteBalanceEdit->setText(QString::number(value));
    
    qDebug() << "Setting white balance temperature for camera 1:" << value;
}

void MainWindow::setWhiteBalanceTemperature2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    
    // Najpierw wyłączamy automatyczny balans bieli
    QStringList disableAutoWhiteBalanceArgs = {"-d", device, "--set-ctrl=white_balance_automatic=0"};
    QProcess processDisableAuto;
    processDisableAuto.start("v4l2-ctl", disableAutoWhiteBalanceArgs);
    processDisableAuto.waitForFinished();
    
    // Teraz ustawiamy temperaturę balansu bieli
    QStringList setWhiteBalanceArgs = {"-d", device, QString("--set-ctrl=white_balance_temperature=%1").arg(value)};
    QProcess process;
    process.start("v4l2-ctl", setWhiteBalanceArgs);
    process.waitForFinished();
    
    // Aktualizujemy pole tekstowe
    ui->whiteBalanceEdit2->setText(QString::number(value));
    
    qDebug() << "Setting white balance temperature for camera 2:" << value;
}

void MainWindow::updateZoomLabel(int value)
{
    ui->zoomLabel->setText(QString("Zoom: %1").arg(value));
}

void MainWindow::updateFocusMinLabel(int value)
{
    ui->focusMinLabel->setText(QString("Focus Min: %1").arg(value));
}

void MainWindow::updateZoomLabel2(int value)
{
    ui->zoomLabel2->setText(QString("Zoom: %1").arg(value));
}

void MainWindow::updateFocusMinLabel2(int value)
{
    ui->focusMinLabel2->setText(QString("Focus Min: %1").arg(value));
}

void MainWindow::on_brightnessEdit_textChanged(const QString &value)
{
    ui->brightnessSlider->setValue(value.toInt());
}

void MainWindow::on_contrastEdit_textChanged(const QString &value)
{
    ui->contrastSlider->setValue(value.toInt());
}

void MainWindow::on_saturationEdit_textChanged(const QString &value)
{
    ui->saturationSlider->setValue(value.toInt());
}

void MainWindow::on_gainEdit_textChanged(const QString &value)
{
    ui->gainSlider->setValue(value.toInt());
}

void MainWindow::on_sharpnessEdit_textChanged(const QString &value)
{
    ui->sharpnessSlider->setValue(value.toInt());
}

void MainWindow::on_brightnessEdit2_textChanged(const QString &value)
{
    ui->brightnessSlider2->setValue(value.toInt());
}

void MainWindow::on_contrastEdit2_textChanged(const QString &value)
{
    ui->contrastSlider2->setValue(value.toInt());
}

void MainWindow::on_saturationEdit2_textChanged(const QString &value)
{
    ui->saturationSlider2->setValue(value.toInt());
}

void MainWindow::on_gainEdit2_textChanged(const QString &value)
{
    ui->gainSlider2->setValue(value.toInt());
}

void MainWindow::on_sharpnessEdit2_textChanged(const QString &value)
{
    ui->sharpnessSlider2->setValue(value.toInt());
}

void MainWindow::on_exposureEdit_textChanged(const QString &value)
{
    ui->exposureSlider->setValue(value.toInt());
}

void MainWindow::on_exposureEdit2_textChanged(const QString &value)
{
    ui->exposureSlider2->setValue(value.toInt());
}

void MainWindow::on_whiteBalanceEdit_textChanged(const QString &value)
{
    ui->whiteBalanceSlider->setValue(value.toInt());
}

void MainWindow::on_whiteBalanceEdit2_textChanged(const QString &value)
{
    ui->whiteBalanceSlider2->setValue(value.toInt());
}

void MainWindow::updateWhiteBalanceLabel(int value)
{
    // Aktualizacja etykiety dla white balance kamery 1
    ui->label_19->setText(QString("White temp: %1").arg(value));
}

void MainWindow::updateWhiteBalanceLabel2(int value)
{
    // Aktualizacja etykiety dla white balance kamery 2
    ui->label_20->setText(QString("White temp: %1").arg(value));
}

void MainWindow::setPowerLineFrequency(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setPowerLineFrequencyArgs = {"-d", device, QString("--set-ctrl=power_line_frequency=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setPowerLineFrequencyArgs;
    QProcess process;
    process.start("v4l2-ctl", setPowerLineFrequencyArgs);
    process.waitForFinished();
    
    // Aktualizujemy pole tekstowe
    ui->powerLineFrequencyEdit->setText(QString::number(value));
}

void MainWindow::setPowerLineFrequency2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setPowerLineFrequencyArgs = {"-d", device, QString("--set-ctrl=power_line_frequency=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setPowerLineFrequencyArgs;
    QProcess process;
    process.start("v4l2-ctl", setPowerLineFrequencyArgs);
    process.waitForFinished();
    
    // Aktualizujemy pole tekstowe
    ui->powerLineFrequencyEdit2->setText(QString::number(value));
}

void MainWindow::setBacklightCompensation(int value)
{
    QString device = ui->camera1ComboBox->currentText();
    QStringList setBacklightCompensationArgs = {"-d", device, QString("--set-ctrl=backlight_compensation=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setBacklightCompensationArgs;
    QProcess process;
    process.start("v4l2-ctl", setBacklightCompensationArgs);
    process.waitForFinished();
    
    // Aktualizujemy pole tekstowe
    ui->backlightCompensationEdit->setText(QString::number(value));
}

void MainWindow::setBacklightCompensation2(int value)
{
    QString device = ui->camera2ComboBox->currentText();
    QStringList setBacklightCompensationArgs = {"-d", device, QString("--set-ctrl=backlight_compensation=%1").arg(value)};

    qDebug() << "Executing command:" << "v4l2-ctl" << setBacklightCompensationArgs;
    QProcess process;
    process.start("v4l2-ctl", setBacklightCompensationArgs);
    process.waitForFinished();
    
    // Aktualizujemy pole tekstowe
    ui->backlightCompensationEdit2->setText(QString::number(value));
}

void MainWindow::on_powerLineFrequencyEdit_textChanged(const QString &value)
{
    ui->powerLineFrequencySlider->setValue(value.toInt());
}

void MainWindow::on_powerLineFrequencyEdit2_textChanged(const QString &value)
{
    ui->powerLineFrequencySlider2->setValue(value.toInt());
}

void MainWindow::on_backlightCompensationEdit_textChanged(const QString &value)
{
    ui->backlightCompensationSlider->setValue(value.toInt());
}

void MainWindow::on_backlightCompensationEdit2_textChanged(const QString &value)
{
    ui->backlightCompensationSlider2->setValue(value.toInt());
}




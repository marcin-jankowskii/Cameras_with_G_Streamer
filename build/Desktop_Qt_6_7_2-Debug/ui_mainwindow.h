/********************************************************************************
** Form generated from reading UI file 'mainwindow.ui'
**
** Created by: Qt User Interface Compiler version 6.7.2
**
** WARNING! All changes made in this file will be lost when recompiling UI file!
********************************************************************************/

#ifndef UI_MAINWINDOW_H
#define UI_MAINWINDOW_H

#include <QtCore/QVariant>
#include <QtWidgets/QApplication>
#include <QtWidgets/QComboBox>
#include <QtWidgets/QMainWindow>
#include <QtWidgets/QMenuBar>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QSpinBox>
#include <QtWidgets/QStatusBar>
#include <QtWidgets/QWidget>

QT_BEGIN_NAMESPACE

class Ui_MainWindow
{
public:
    QWidget *centralwidget;
    QComboBox *cameraCountComboBox;
    QComboBox *resolutionComboBox;
    QComboBox *formatComboBox;
    QSpinBox *fpsSpinBox;
    QPushButton *startButton;
    QWidget *cameraView1;
    QWidget *cameraView2;
    QComboBox *camera1ComboBox;
    QComboBox *camera2ComboBox;
    QPushButton *recordButton;
    QPushButton *stopButton;
    QPushButton *stopRecordingButton;
    QPushButton *selectDirectoryButton;
    QMenuBar *menubar;
    QStatusBar *statusbar;

    void setupUi(QMainWindow *MainWindow)
    {
        if (MainWindow->objectName().isEmpty())
            MainWindow->setObjectName("MainWindow");
        MainWindow->resize(1459, 893);
        centralwidget = new QWidget(MainWindow);
        centralwidget->setObjectName("centralwidget");
        cameraCountComboBox = new QComboBox(centralwidget);
        cameraCountComboBox->setObjectName("cameraCountComboBox");
        cameraCountComboBox->setGeometry(QRect(150, 40, 86, 25));
        resolutionComboBox = new QComboBox(centralwidget);
        resolutionComboBox->setObjectName("resolutionComboBox");
        resolutionComboBox->setGeometry(QRect(260, 30, 86, 25));
        formatComboBox = new QComboBox(centralwidget);
        formatComboBox->setObjectName("formatComboBox");
        formatComboBox->setGeometry(QRect(390, 30, 86, 25));
        fpsSpinBox = new QSpinBox(centralwidget);
        fpsSpinBox->setObjectName("fpsSpinBox");
        fpsSpinBox->setGeometry(QRect(550, 30, 44, 26));
        fpsSpinBox->setMinimum(30);
        fpsSpinBox->setMaximum(30);
        startButton = new QPushButton(centralwidget);
        startButton->setObjectName("startButton");
        startButton->setGeometry(QRect(660, 20, 89, 25));
        cameraView1 = new QWidget(centralwidget);
        cameraView1->setObjectName("cameraView1");
        cameraView1->setGeometry(QRect(10, 180, 661, 491));
        cameraView2 = new QWidget(centralwidget);
        cameraView2->setObjectName("cameraView2");
        cameraView2->setGeometry(QRect(770, 180, 641, 481));
        camera1ComboBox = new QComboBox(centralwidget);
        camera1ComboBox->setObjectName("camera1ComboBox");
        camera1ComboBox->setGeometry(QRect(310, 130, 86, 25));
        camera2ComboBox = new QComboBox(centralwidget);
        camera2ComboBox->setObjectName("camera2ComboBox");
        camera2ComboBox->setGeometry(QRect(1070, 130, 86, 25));
        recordButton = new QPushButton(centralwidget);
        recordButton->setObjectName("recordButton");
        recordButton->setGeometry(QRect(790, 20, 89, 25));
        stopButton = new QPushButton(centralwidget);
        stopButton->setObjectName("stopButton");
        stopButton->setGeometry(QRect(660, 80, 89, 25));
        stopRecordingButton = new QPushButton(centralwidget);
        stopRecordingButton->setObjectName("stopRecordingButton");
        stopRecordingButton->setGeometry(QRect(790, 80, 89, 25));
        selectDirectoryButton = new QPushButton(centralwidget);
        selectDirectoryButton->setObjectName("selectDirectoryButton");
        selectDirectoryButton->setGeometry(QRect(930, 80, 89, 25));
        MainWindow->setCentralWidget(centralwidget);
        menubar = new QMenuBar(MainWindow);
        menubar->setObjectName("menubar");
        menubar->setGeometry(QRect(0, 0, 1459, 22));
        MainWindow->setMenuBar(menubar);
        statusbar = new QStatusBar(MainWindow);
        statusbar->setObjectName("statusbar");
        MainWindow->setStatusBar(statusbar);

        retranslateUi(MainWindow);

        QMetaObject::connectSlotsByName(MainWindow);
    } // setupUi

    void retranslateUi(QMainWindow *MainWindow)
    {
        MainWindow->setWindowTitle(QCoreApplication::translate("MainWindow", "MainWindow", nullptr));
        startButton->setText(QCoreApplication::translate("MainWindow", "Start", nullptr));
        recordButton->setText(QCoreApplication::translate("MainWindow", "Record", nullptr));
        stopButton->setText(QCoreApplication::translate("MainWindow", "Stop", nullptr));
        stopRecordingButton->setText(QCoreApplication::translate("MainWindow", "Stop Record", nullptr));
        selectDirectoryButton->setText(QCoreApplication::translate("MainWindow", "Select Dir", nullptr));
    } // retranslateUi

};

namespace Ui {
    class MainWindow: public Ui_MainWindow {};
} // namespace Ui

QT_END_NAMESPACE

#endif // UI_MAINWINDOW_H

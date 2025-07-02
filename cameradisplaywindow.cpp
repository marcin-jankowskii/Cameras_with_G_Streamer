#include "cameradisplaywindow.h"
#include <QDebug>
#include <QApplication>
#include <QScreen>
#include <QVBoxLayout>

CameraDisplayWindow::CameraDisplayWindow(QWidget *parent)
    : QWidget(parent)
{
    // Ustawiam tytuł okna
    setWindowTitle("Podgląd kamer");
    
    // Ustawiam rozmiar okna względem dostępnego ekranu
    QScreen *screen = QApplication::primaryScreen();
    QSize screenSize = screen->availableSize();
    resize(screenSize.width() , screenSize.height());
    
    // Tworzę układ horyzontalny
    mainLayout = new QHBoxLayout(this);
    mainLayout->setSpacing(10); // Większy odstęp między kamerami
    mainLayout->setContentsMargins(10, 10, 10, 10); // Większe marginesy
    
    // Tworzę ramki dla kamer
    camera1Frame = new QFrame(this);
    camera2Frame = new QFrame(this);
    
    // Ustawiam styl ramek
    camera1Frame->setFrameStyle(QFrame::Panel | QFrame::Sunken);
    camera1Frame->setLineWidth(2);
    camera2Frame->setFrameStyle(QFrame::Panel | QFrame::Sunken);
    camera2Frame->setLineWidth(2);
    
    // Ustawiam politykę rozmiaru ramek
    camera1Frame->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    camera2Frame->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    
    // Tworzę układy wewnątrz ramek
    QVBoxLayout* camera1Layout = new QVBoxLayout(camera1Frame);
    QVBoxLayout* camera2Layout = new QVBoxLayout(camera2Frame);
    camera1Layout->setContentsMargins(0, 0, 0, 0);
    camera2Layout->setContentsMargins(0, 0, 0, 0);
    
    // Tworzę widgety dla obu kamer
    camera1Widget = new QWidget(camera1Frame);
    camera2Widget = new QWidget(camera2Frame);
    
    // Ustawiam tło widgetów na czarne (lepiej widać gdy nie ma obrazu)
    camera1Widget->setStyleSheet("background-color: black;");
    camera2Widget->setStyleSheet("background-color: black;");
    
    // Ustawiam politykę rozmiaru widgetów kamer
    camera1Widget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    camera2Widget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    
    // Dodaję widgety do układów ramek
    camera1Layout->addWidget(camera1Widget);
    camera2Layout->addWidget(camera2Widget);
    
    // Dodaję ramki do głównego układu
    mainLayout->addWidget(camera1Frame, 1);
    mainLayout->addWidget(camera2Frame, 1);
    
    // Ustawiam układ dla całego okna
    setLayout(mainLayout);
    
    // Ustawiam minimalny rozmiar okna
    setMinimumSize(800, 480);
    
    qDebug() << "CameraDisplayWindow utworzone z widgetami" << camera1Widget << "i" << camera2Widget;
}

CameraDisplayWindow::~CameraDisplayWindow()
{
    qDebug() << "CameraDisplayWindow zniszczone";
}

void CameraDisplayWindow::resizeEvent(QResizeEvent* event)
{
    QWidget::resizeEvent(event);
    
    // Obliczam nowe rozmiary widgetów kamer
    QSize newSize = event->size();
    
    // Wypisujemy informacje o nowym rozmiarze okna
    qDebug() << "Okno CameraDisplayWindow zmienilo rozmiar na:" << newSize;
    qDebug() << "Rozmiar widgetu camera1Widget:" << camera1Widget->size();
    qDebug() << "Rozmiar widgetu camera2Widget:" << camera2Widget->size();
    
    // Aktualizujemy układ
    mainLayout->update();
} 
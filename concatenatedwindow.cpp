#include "concatenatedwindow.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QWidget>
#include <QPainter>

ConcatenatedWindow::ConcatenatedWindow(QWidget *parent)
    : QMainWindow(parent)
    , camera1Updated(false)
    , camera2Updated(false)
    , camera3Updated(false)
    , camera4Updated(false)
{
    setWindowTitle("Concatenated Cameras");
    setGeometry(100, 100, 1200, 800);
    
    QWidget *centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);
    
    QVBoxLayout *layout = new QVBoxLayout(centralWidget);
    
    concatenatedLabel = new QLabel(this);
    concatenatedLabel->setStyleSheet("border: 1px solid black; background-color: #f0f0f0;");
    concatenatedLabel->setText("Waiting for camera images...");
    concatenatedLabel->setAlignment(Qt::AlignCenter);
    concatenatedLabel->setMinimumSize(1200, 800);
    
    layout->addWidget(concatenatedLabel);
}

ConcatenatedWindow::~ConcatenatedWindow()
{
}

void ConcatenatedWindow::updateCamera1Image(const QImage& img)
{
    camera1Image = img;
    camera1Updated = true;
    updateConcatenatedImage();
}

void ConcatenatedWindow::updateCamera2Image(const QImage& img)
{
    camera2Image = img;
    camera2Updated = true;
    updateConcatenatedImage();
}

void ConcatenatedWindow::updateCamera3Image(const QImage& img)
{
    camera3Image = img;
    camera3Updated = true;
    updateConcatenatedImage();
}

void ConcatenatedWindow::updateCamera4Image(const QImage& img)
{
    camera4Image = img;
    camera4Updated = true;
    updateConcatenatedImage();
}

void ConcatenatedWindow::setActiveCameraCount(int count)
{
    activeCameraCount = qBound(1, count, 4);
}

void ConcatenatedWindow::updateConcatenatedImage()
{
    // Gromadź obrazy zgodnie z activeCameraCount
    QList<QImage> images;
    if (activeCameraCount >= 1 && camera1Updated) images << camera1Image; else images << QImage();
    if (activeCameraCount >= 2 && camera2Updated) images << camera2Image; else if (activeCameraCount >= 2) images << QImage();
    if (activeCameraCount >= 3 && camera3Updated) images << camera3Image; else if (activeCameraCount >= 3) images << QImage();
    if (activeCameraCount >= 4 && camera4Updated) images << camera4Image; else if (activeCameraCount >= 4) images << QImage();

    int available = 0; for (const QImage& im : images) if (!im.isNull()) ++available;
    if (available == 0) return;

    // Układ zależny od liczby kamer: 1 -> 1x1, 2 -> 1x2, 3 -> 2x2 (ostatni czarny), 4 -> 2x2
    int rows = (activeCameraCount <= 2) ? 1 : 2;
    int cols = (activeCameraCount == 1) ? 1 : ((activeCameraCount == 2) ? 2 : 2);

    // Wyznacz wysokości wierszy
    if (rows == 1) {
        int h = 0; for (int i = 0; i < cols; ++i) h = qMax(h, images.value(i).height()); if (h <= 0) h = 480;
        QImage i0 = images.value(0).isNull() ? QImage(640, h, QImage::Format_RGB32) : images.value(0).scaledToHeight(h, Qt::SmoothTransformation);
        if (images.value(0).isNull()) i0.fill(Qt::black);
        QImage canvas(i0.width(), h, QImage::Format_RGB32);
        canvas.fill(Qt::black);
        if (cols == 1) {
            QPainter p(&canvas); p.drawImage(0, 0, i0); p.end();
            concatenatedLabel->setPixmap(QPixmap::fromImage(canvas).scaled(concatenatedLabel->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
            return;
        } else {
            QImage i1 = images.value(1).isNull() ? QImage(640, h, QImage::Format_RGB32) : images.value(1).scaledToHeight(h, Qt::SmoothTransformation);
            if (images.value(1).isNull()) i1.fill(Qt::black);
            QImage out(i0.width() + i1.width(), h, QImage::Format_RGB32); out.fill(Qt::black);
            QPainter p(&out); p.drawImage(0,0,i0); p.drawImage(i0.width(),0,i1); p.end();
            concatenatedLabel->setPixmap(QPixmap::fromImage(out).scaled(concatenatedLabel->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
            return;
        }
    }

    // rows == 2 (3 lub 4 kamery)
    int row1h = qMax(images.value(0).height(), images.value(1).height()); if (row1h <= 0) row1h = 480;
    int row2h = qMax(images.value(2).height(), images.value(3).height()); if (row2h <= 0) row2h = row1h;

    QImage i0 = images.value(0).isNull() ? QImage(640, row1h, QImage::Format_RGB32) : images.value(0).scaledToHeight(row1h, Qt::SmoothTransformation);
    QImage i1 = images.value(1).isNull() ? QImage(640, row1h, QImage::Format_RGB32) : images.value(1).scaledToHeight(row1h, Qt::SmoothTransformation);
    QImage i2 = images.value(2).isNull() ? QImage(640, row2h, QImage::Format_RGB32) : images.value(2).scaledToHeight(row2h, Qt::SmoothTransformation);
    QImage i3 = images.value(3).isNull() ? QImage(640, row2h, QImage::Format_RGB32) : images.value(3).scaledToHeight(row2h, Qt::SmoothTransformation);

    if (images.value(0).isNull()) i0.fill(Qt::black);
    if (images.value(1).isNull()) i1.fill(Qt::black);
    if (images.value(2).isNull()) i2.fill(Qt::black);
    if (images.value(3).isNull()) i3.fill(Qt::black);

    int widthTop = i0.width() + i1.width();
    int widthBottom = i2.width() + i3.width();
    int finalWidth = qMax(widthTop, widthBottom);
    int finalHeight = row1h + row2h;

    QImage concatenatedImage(finalWidth, finalHeight, QImage::Format_RGB32);
    concatenatedImage.fill(Qt::black);

    QPainter painter(&concatenatedImage);
    painter.drawImage(0, 0, i0);
    painter.drawImage(i0.width(), 0, i1);
    painter.drawImage(0, row1h, i2);
    painter.drawImage(i2.width(), row1h, i3);
    painter.end();

    concatenatedLabel->setPixmap(QPixmap::fromImage(concatenatedImage).scaled(
        concatenatedLabel->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
} 
#include "concatenatedwindow.h"
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QWidget>
#include <QPainter>

ConcatenatedWindow::ConcatenatedWindow(QWidget *parent)
    : QMainWindow(parent)
    , camera1Updated(false)
    , camera2Updated(false)
{
    setWindowTitle("Concatenated Cameras");
    setGeometry(100, 100, 800, 450);
    
    // Create central widget
    QWidget *centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);
    
    // Create layout
    QVBoxLayout *layout = new QVBoxLayout(centralWidget);
    
    // Create label for concatenated image
    concatenatedLabel = new QLabel(this);
    concatenatedLabel->setStyleSheet("border: 1px solid black; background-color: #f0f0f0;");
    concatenatedLabel->setText("Waiting for camera images...");
    concatenatedLabel->setAlignment(Qt::AlignCenter);
    concatenatedLabel->setMinimumSize(800, 450);
    
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

void ConcatenatedWindow::updateConcatenatedImage()
{
    if (!camera1Updated || !camera2Updated) {
        return;
    }
    
    // Create concatenated image
    int height1 = camera1Image.height();
    int height2 = camera2Image.height();
    
    // Use the larger height for both images
    int targetHeight = qMax(height1, height2);
    
    // Scale images to same height
    QImage scaledImage1 = camera1Image.scaledToHeight(targetHeight, Qt::SmoothTransformation);
    QImage scaledImage2 = camera2Image.scaledToHeight(targetHeight, Qt::SmoothTransformation);
    
    // Create concatenated image
    QImage concatenatedImage(scaledImage1.width() + scaledImage2.width(), targetHeight, QImage::Format_RGB32);
    
    // Copy images side by side
    QPainter painter(&concatenatedImage);
    painter.drawImage(0, 0, scaledImage1);
    painter.drawImage(scaledImage1.width(), 0, scaledImage2);
    painter.end();
    
    // Display concatenated image
    concatenatedLabel->setPixmap(QPixmap::fromImage(concatenatedImage).scaled(
        concatenatedLabel->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
} 
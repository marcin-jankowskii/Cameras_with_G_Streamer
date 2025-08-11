#ifndef CONCATENATEDWINDOW_H
#define CONCATENATEDWINDOW_H

#include <QMainWindow>
#include <QLabel>
#include <QImage>

class ConcatenatedWindow : public QMainWindow
{
    Q_OBJECT

public:
    ConcatenatedWindow(QWidget *parent = nullptr);
    ~ConcatenatedWindow();

public slots:
    void updateCamera1Image(const QImage& img);
    void updateCamera2Image(const QImage& img);

private:
    QLabel* concatenatedLabel;
    QImage camera1Image;
    QImage camera2Image;
    bool camera1Updated;
    bool camera2Updated;
    
    void updateConcatenatedImage();
};

#endif // CONCATENATEDWINDOW_H 
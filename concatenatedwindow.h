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
    void updateCamera3Image(const QImage& img);
    void updateCamera4Image(const QImage& img);
    void setActiveCameraCount(int count);

private:
    QLabel* concatenatedLabel;
    QImage camera1Image;
    QImage camera2Image;
    QImage camera3Image;
    QImage camera4Image;
    bool camera1Updated;
    bool camera2Updated;
    bool camera3Updated;
    bool camera4Updated;
    int activeCameraCount = 2;
    
    void updateConcatenatedImage();
};

#endif // CONCATENATEDWINDOW_H 
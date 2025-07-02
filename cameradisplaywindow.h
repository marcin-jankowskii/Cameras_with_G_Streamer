#ifndef CAMERADISPLAYWINDOW_H
#define CAMERADISPLAYWINDOW_H

#include <QWidget>
#include <QHBoxLayout>
#include <QResizeEvent>
#include <QFrame>
#include "camerathread.h"

class CameraDisplayWindow : public QWidget
{
    Q_OBJECT

public:
    explicit CameraDisplayWindow(QWidget *parent = nullptr);
    ~CameraDisplayWindow();

    // Zwraca wskaźnik do widżetu dla pierwszej kamery
    QWidget* getCamera1Widget() const { return camera1Widget; }
    
    // Zwraca wskaźnik do widżetu dla drugiej kamery
    QWidget* getCamera2Widget() const { return camera2Widget; }

protected:
    // Przeładowana funkcja obsługi zdarzenia zmiany rozmiaru okna
    void resizeEvent(QResizeEvent* event) override;

private:
    QWidget* camera1Widget;  // Widżet dla pierwszej kamery
    QWidget* camera2Widget;  // Widżet dla drugiej kamery
    QHBoxLayout* mainLayout; // Układ horyzontalny
    QFrame* camera1Frame;    // Ramka dla pierwszej kamery
    QFrame* camera2Frame;    // Ramka dla drugiej kamery
};

#endif // CAMERADISPLAYWINDOW_H 
#include <QApplication>
#include "mainwindow.h"
#include <pylon/PylonIncludes.h>

int main(int argc, char *argv[])
{
    Pylon::PylonInitialize();
    QApplication a(argc, argv);
    MainWindow w; w.show();
    int rc = a.exec();
    Pylon::PylonTerminate();
    return rc;
}

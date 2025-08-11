#pragma once
#include <QObject>
#include <QFile>
#include <QImage>
#include <QMutex>

class FrameWriter : public QObject
{
    Q_OBJECT
public:
    explicit FrameWriter(const QString& saveDir, const QString& format, QObject* parent = nullptr);
    ~FrameWriter();

public slots:
    void open();
    void close();

    // RAW — surowe dane z kamery (pojedyncza klatka)
    void writeRaw(const QByteArray& raw, quint64 timestamp);

    // JPG — QImage do zakodowania i zapisu
    void writeJpeg(const QImage& image, quint64 timestamp);

private:
    QString saveDir;
    QString format;

    // RAW
    QFile rawFile;
    QFile tsFile;
    QByteArray tsBuffer;
    qint64 tsLines = 0;

    // ochrona przed równoległym zamknięciem
    QMutex mtx;
};

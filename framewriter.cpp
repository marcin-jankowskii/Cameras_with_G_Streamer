#include "framewriter.h"
#include <QDir>
#include <QTextStream>

FrameWriter::FrameWriter(const QString& saveDir, const QString& format, QObject* parent)
    : QObject(parent), saveDir(saveDir), format(format)
{
}

FrameWriter::~FrameWriter()
{
    close();
}

void FrameWriter::open()
{
    QMutexLocker lock(&mtx);
    QDir().mkpath(saveDir);

    if (format == "RAW") {
        rawFile.setFileName(QDir(saveDir).filePath("camera.raw"));
        if (!rawFile.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            qWarning() << "FrameWriter: nie można otworzyć" << rawFile.fileName();
        }
        tsFile.setFileName(QDir(saveDir).filePath("timestamps.txt"));
        if (!tsFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
            qWarning() << "FrameWriter: nie można otworzyć" << tsFile.fileName();
        }
        tsBuffer.reserve(16 * 1024);
        tsLines = 0;
    }
}

void FrameWriter::close()
{
    QMutexLocker lock(&mtx);

    if (format == "RAW") {
        if (!tsBuffer.isEmpty() && tsFile.isOpen()) {
            tsFile.write(tsBuffer);
            tsBuffer.clear();
        }
        if (tsFile.isOpen()) {
            tsFile.flush();
            tsFile.close();
        }
        if (rawFile.isOpen()) {
            rawFile.flush();
            rawFile.close();
        }
    }
}

void FrameWriter::writeRaw(const QByteArray& raw, quint64 timestamp)
{
    QMutexLocker lock(&mtx);
    if (!rawFile.isOpen()) return;

    // zapis surowego bufora
    qint64 w = rawFile.write(raw);
    if (w != raw.size()) {
        qWarning() << "FrameWriter: niepełny zapis RAW";
    }

    // buforuj timestampy i co ~1000 linii flush
    tsBuffer.append(QByteArray::number(timestamp));
    tsBuffer.append('\n');
    if (++tsLines >= 100) {
        if (tsFile.isOpen()) {
            tsFile.write(tsBuffer);
            tsFile.flush();
        }
        tsBuffer.clear();
        tsLines = 0;
    }
}

void FrameWriter::writeJpeg(const QImage& image, quint64 timestamp)
{
    // zapis JPG pojedynczo — slot działa w wątku writer’a
    const QString filename = QDir(saveDir).filePath(QString("frame_%1.jpg").arg(timestamp));
    image.save(filename, "JPG", 85); // brak logów przy sukcesie
}

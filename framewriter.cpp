#include "framewriter.h"
#include <QDir>
#include <QDateTime>
#include <QDebug>
#include <cstring>

static inline quint64 nowNs()
{
    // ns z czasu systemowego (na potrzeby sessionStartNs)
    return static_cast<quint64>(QDateTime::currentMSecsSinceEpoch()) * 1000000ull;
}

FrameWriter::FrameWriter(const QString& saveDir,
                         const QString& format,
                         const QString& serialNumber,
                         QObject* parent)
    : QObject(parent),
      saveDir(saveDir),
      format(format),
      serialNumber(serialNumber)
{
}

FrameWriter::~FrameWriter()
{
    close();
}

void FrameWriter::open()
{
    QMutexLocker lock(&mtx);

    // domknij starą sesję jeśli była
    if (rawFile.isOpen()) {
        rawFile.flush();
        rawFile.close();
    }

    QDir().mkpath(saveDir);

    // Prefiks sesji: cam_<SN>_<YYYYmmdd_HHmmsszzz>
    const QString ts = QDateTime::currentDateTime().toString("yyyyMMdd_HHmmsszzz");
    sessionPrefix = QString("cam_%1_%2").arg(serialNumber, ts);

    sessionHeaderWritten = false;

    if (format.compare("RAW", Qt::CaseInsensitive) == 0) {
        const QString rawPath = QDir(saveDir).filePath(sessionPrefix + ".raw");
        rawFile.setFileName(rawPath);
        if (!rawFile.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            qWarning() << "FrameWriter: nie można otworzyć" << rawFile.fileName();
        } else {
            qDebug() << "FrameWriter: session started ->" << rawFile.fileName();
        }
    } else {
        qDebug() << "FrameWriter: session started (JPG prefix)" << sessionPrefix;
    }
}

void FrameWriter::close()
{
    QMutexLocker lock(&mtx);
    if (rawFile.isOpen()) {
        rawFile.flush();
        rawFile.close();
    }
    qDebug() << "FrameWriter: session closed";
}

void FrameWriter::setMeta(int width, int height, quint16 pixelType, quint16 bitDepth)
{
    QMutexLocker lock(&mtx);
    metaW = width;
    metaH = height;
    metaPixelType = pixelType;
    metaBitDepth  = bitDepth;
}

void FrameWriter::writeSessionHeaderIfNeeded_unlocked()
{
    if (sessionHeaderWritten) return;
    if (!rawFile.isOpen())    return;

    SessionHeader sh{};
    sh.magic       = 0x52415753u; // 'RAWS'
    sh.version     = 1;
    sh.headerBytes = static_cast<quint16>(sizeof(SessionHeader));
    sh.width       = static_cast<quint16>(qMax(0, metaW));
    sh.height      = static_cast<quint16>(qMax(0, metaH));
    sh.pixelType   = metaPixelType;
    sh.bitDepth    = metaBitDepth;

    std::memset(sh.serial, 0, sizeof(sh.serial));
    QByteArray snBA = serialNumber.toUtf8();
    std::memcpy(sh.serial, snBA.constData(), qMin<int>(snBA.size(), sizeof(sh.serial)-1));

    sh.sessionStartNs = nowNs();

    const qint64 w = rawFile.write(reinterpret_cast<const char*>(&sh), sizeof(sh));
    if (w != sizeof(sh)) {
        qWarning() << "FrameWriter: niepełny zapis nagłówka sesji";
    } else {
        sessionHeaderWritten = true;
    }
}

void FrameWriter::writeRaw(const QByteArray& raw, quint64 timestampNs, quint64 frameCounter)
{
    QMutexLocker lock(&mtx);
    if (!rawFile.isOpen()) return;

    // Upewnij się, że nagłówek sesji jest zapisany (wymaga wcześniejszego setMeta)
    writeSessionHeaderIfNeeded_unlocked();

    // Nagłówek klatki
    FrameHeader fh{};
    fh.magic        = 0x4652414Du; // 'FRAM'
    fh.timestampNs  = timestampNs;
    fh.frameCounter = frameCounter;    // 0 jeśli nieużywany
    fh.dataBytes    = static_cast<quint32>(raw.size());

    qint64 w = rawFile.write(reinterpret_cast<const char*>(&fh), sizeof(fh));
    if (w != sizeof(fh)) {
        qWarning() << "FrameWriter: niepełny zapis nagłówka klatki";
        return;
    }
    w = rawFile.write(raw);
    if (w != raw.size()) {
        qWarning() << "FrameWriter: niepełny zapis danych klatki";
    }
}

void FrameWriter::writeJpeg(const QImage& image, quint64 timestampNs)
{
    // cam_<SN>_<sessTS>_frame_<hwTS>.jpg
    const QString filename = QDir(saveDir).filePath(
        QString("%1_frame_%2.jpg").arg(sessionPrefix).arg(timestampNs)
    );
    image.save(filename, "JPG", 85);
}

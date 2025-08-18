#pragma once
#include <QObject>
#include <QFile>
#include <QImage>
#include <QMutex>
#include <QtGlobal>

#pragma pack(push,1)
// 'RAWS'
struct SessionHeader {
    quint32 magic;         // 0x52415753
    quint16 version;       // 1
    quint16 headerBytes;   // sizeof(SessionHeader)
    quint16 width;
    quint16 height;
    quint16 pixelType;     // 0=Mono8, 1=BayerRG8, 2=RGB8, 3=BGR8, 10=Mono12, 11=BayerRG12...
    quint16 bitDepth;      // 8, 12, 16
    char    serial[16];    // zero-terminated/padded
    quint64 sessionStartNs;// QDateTime::currentMSecsSinceEpoch()*1e6 (ns)
};
static_assert(sizeof(SessionHeader) == 40, "SessionHeader size unexpected");

// 'FRAM'
struct FrameHeader {
    quint32 magic;         // 0x4652414D
    quint64 timestampNs;   // HW timestamp (ns/ticki)
    quint64 frameCounter;  // opcjonalnie (0 jeśli nieużywany)
    quint32 dataBytes;     // rozmiar danych obrazu w bajtach
};
static_assert(sizeof(FrameHeader) == 24, "FrameHeader size unexpected");
#pragma pack(pop)

class FrameWriter : public QObject
{
    Q_OBJECT
public:
    // serialNumber: np. "40123456" — idzie do nagłówka sesji i prefiksu nazw JPG
    explicit FrameWriter(const QString& saveDir,
                         const QString& format,
                         const QString& serialNumber,
                         QObject* parent = nullptr);
    ~FrameWriter();

public slots:
    // Otwiera NOWĄ sesję zapisu (prefiks plików, przygotowanie .raw)
    void open();
    // Domyka bieżącą sesję
    void close();

    // Ustaw meta danych obrazu (wymagane przed pierwszym writeRaw)
    // pixelType: 0=Mono8,1=BayerRG8,2=RGB8,3=BGR8,10=Mono12,11=BayerRG12...
    void setMeta(int width, int height, quint16 pixelType, quint16 bitDepth);

    // RAW — surowe dane z kamery (pojedyncza klatka); timestampNs = HW timestamp z kamery
    void writeRaw(const QByteArray& raw, quint64 timestampNs, quint64 frameCounter = 0);

    // JPG — zapis pojedynczego obrazu do osobnego pliku (prefiks sesji w nazwie)
    void writeJpeg(const QImage& image, quint64 timestampNs);

private:
    // konfiguracja
    QString saveDir;
    QString format;
    QString serialNumber;

    // identyfikator sesji: cam_<SN>_<YYYYmmdd_HHmmsszzz>
    QString sessionPrefix;

    // meta obrazu
    int     metaW = 0;
    int     metaH = 0;
    quint16 metaPixelType = 0;
    quint16 metaBitDepth  = 8;

    // plik RAW
    QFile   rawFile;
    bool    sessionHeaderWritten = false;

    // ochrona
    QMutex  mtx;

    // pomocnicze
    void writeSessionHeaderIfNeeded_unlocked();
};

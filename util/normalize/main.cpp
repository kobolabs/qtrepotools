/****************************************************************************
**
** Copyright (C) 2013 Digia Plc and/or its subsidiary(-ies).
** Contact: http://www.qt-project.org/legal
**
** This file is part of the utils of the Qt Toolkit.
**
** $QT_BEGIN_LICENSE:LGPL$
** Commercial License Usage
** Licensees holding valid commercial Qt licenses may use this file in
** accordance with the commercial license agreement provided with the
** Software or, alternatively, in accordance with the terms contained in
** a written agreement between you and Digia.  For licensing terms and
** conditions see http://qt.digia.com/licensing.  For further information
** use the contact form at http://qt.digia.com/contact-us.
**
** GNU Lesser General Public License Usage
** Alternatively, this file may be used under the terms of the GNU Lesser
** General Public License version 2.1 as published by the Free Software
** Foundation and appearing in the file LICENSE.LGPL included in the
** packaging of this file.  Please review the following information to
** ensure the GNU Lesser General Public License version 2.1 requirements
** will be met: http://www.gnu.org/licenses/old-licenses/lgpl-2.1.html.
**
** In addition, as a special exception, Digia gives you certain additional
** rights.  These rights are described in the Digia Qt LGPL Exception
** version 1.1, included in the file LGPL_EXCEPTION.txt in this package.
**
** GNU General Public License Usage
** Alternatively, this file may be used under the terms of the GNU
** General Public License version 3.0 as published by the Free Software
** Foundation and appearing in the file LICENSE.GPL included in the
** packaging of this file.  Please review the following information to
** ensure the GNU General Public License version 3.0 requirements will be
** met: http://www.gnu.org/copyleft/gpl.html.
**
**
** $QT_END_LICENSE$
**
****************************************************************************/

#include <qcoreapplication.h>
#include <qdiriterator.h>
#include <qfile.h>
#include <qmetaobject.h>
#include <qstring.h>
#include <qtextstream.h>
#include <qcommandlineparser.h>

#include <qdebug.h>

#include <limits.h>
#include <stdio.h>

static bool printFilename = true;
static bool modify = false;

QString signature(const QString &line, int pos)
{
    int start = pos;
    // find first open parentheses
    while (start < line.length() && line.at(start) != QLatin1Char('('))
        ++start;
    int i = ++start;
    int par = 1;
    // find matching closing parentheses
    while (i < line.length() && par > 0) {
        if (line.at(i) == QLatin1Char('('))
            ++par;
        else if (line.at(i) == QLatin1Char(')'))
            --par;
        ++i;
    }
    if (par == 0)
        return line.mid(start, i - start - 1);
    return QString();
}

bool checkSignature(const QString &fileName, QString &line, const char *sig)
{
    static QStringList fileList;

    int idx = -1;
    bool found = false;
    while ((idx = line.indexOf(sig, ++idx)) != -1) {
        const QByteArray sl(signature(line, idx).toLocal8Bit());
        QByteArray nsl(QMetaObject::normalizedSignature(sl.constData()));
        if (sl != nsl) {
            found = true;
            if (printFilename && !fileList.contains(fileName)) {
                fileList.prepend(fileName);
                printf("%s\n", fileName.toLocal8Bit().constData());
            }
            if (modify)
                line.replace(sl, nsl);
            //qDebug("expected '%s', got '%s'", nsl.data(), sl.data());
        }
    }
    return found;
}

void writeChanges(const QString &fileName, const QStringList &lines)
{
    QFile file(fileName);
    if (!file.open(QIODevice::WriteOnly)) {
        qDebug("unable to open file '%s' for writing (%s)", fileName.toLocal8Bit().constData(), file.errorString().toLocal8Bit().constData());
        return;
    }
    QTextStream stream(&file);
    for (int i = 0; i < lines.count(); ++i)
        stream << lines.at(i);
    file.close();
}

void check(const QString &fileName)
{
    QFile file(fileName);
    if (!file.open(QIODevice::ReadOnly)) {
        qDebug("unable to open file: '%s' (%s)", fileName.toLocal8Bit().constData(), file.errorString().toLocal8Bit().constData());
        return;
    }
    QStringList lines;
    bool found = false;
    while (true) {
        QByteArray bline = file.readLine(16384);
        if (bline.isEmpty())
            break;
        QString line = QString::fromLocal8Bit(bline);
        found |= checkSignature(fileName, line, "SLOT");
        found |= checkSignature(fileName, line, "SIGNAL");
        if (modify)
            lines << line;
    }
    file.close();

    if (found && modify) {
        printf("Modifying file: '%s'\n", fileName.toLocal8Bit().constData());
        writeChanges(fileName, lines);
    }
}

void traverse(const QString &path)
{
    QDirIterator dirIterator(path, QDir::NoDotAndDotDot | QDir::Dirs | QDir::Files | QDir::NoSymLinks);

    while (dirIterator.hasNext()) {
        QString filePath = dirIterator.next();
        if (filePath.endsWith(".cpp"))
            check(filePath);
        else if (QFileInfo(filePath).isDir())
            traverse(filePath); // recurse
    }
}

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);

    QCommandLineParser parser;
    parser.setApplicationDescription(
            QStringLiteral("Qt Normalize tool (Qt %1)\nOutputs all filenames that contain non-normalized SIGNALs and SLOTs")
            .arg(QString::fromLatin1(QT_VERSION_STR)));
    parser.addHelpOption();
    parser.addVersionOption();

    QCommandLineOption modifyOption(QStringLiteral("modify"),
                                    QStringLiteral("Fix all occurrences of non-normalized SIGNALs and SLOTs."));
    parser.addOption(modifyOption);

    parser.addPositionalArgument(QStringLiteral("path"),
                                 QStringLiteral("can be a single file or a directory (in which case, look for *.cpp recursively)"));

    parser.process(app);

    if (parser.positionalArguments().count() != 1)
        parser.showHelp(1);
    QString path = parser.positionalArguments().first();
    if (path == "-")
        parser.showHelp(1);

    if (parser.isSet(modifyOption)) {
        printFilename = false;
        modify = true;
    }

    QFileInfo fi(path);
    if (fi.isFile()) {
        check(path);
    } else if (fi.isDir()) {
        if (!path.endsWith("/"))
            path.append("/");
        traverse(path);
    } else {
        qWarning("Don't know what to do with '%s'", path.toLocal8Bit().constData());
        return 1;
    }

    return 0;
}

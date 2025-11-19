import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QPainter, QPainterPath


class ClickableVersionWidget(QWidget):
    doubleClicked = pyqtSignal(dict, str)

    def __init__(self, file, image_path=None, parent=None):
        super().__init__(parent)
        self.file_path = file["path"]
        self.version_name = os.path.basename(self.file_path)
        self.image_path = None
        self.file = file

        self.setFixedSize(160, 90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Thumbnail placeholder
        self.image_label = QLabel("Loading...")
        self.image_label.setFixedSize(160, 90)
        self.image_label.setScaledContents(True)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #000; color: white; border-radius: 10px;")

        if image_path:
            pixmap = QPixmap(image_path)
            self.image_label.setPixmap(self.get_rounded_pixmap(pixmap, 200))
            self.image_path = image_path

        # Info text
        label_name = f'{self.version_name}'
        self.text_label = QLabel(label_name)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("background-color: rgba(0,0,0,128); color: white; padding: 5px; border-radius: 200px;")
        self.text_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout.addWidget(self.image_label)
        layout.addWidget(self.text_label, alignment=Qt.AlignTop)

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit(self.file, self.image_path)

    def get_rounded_pixmap(self, pixmap, target_size, radius=None):
        """
        Return a pixmap scaled to `target_size` with rounded corners.
        target_size can be:
        - QSize
        - (width, height) tuple
        - int (width, height will match pixmap aspect ratio)
        """
        if pixmap.isNull():
            return pixmap

        # Convert int or tuple to QSize
        if isinstance(target_size, int):
            w = target_size
            h = int(w * pixmap.height() / pixmap.width())
            target_size = QSize(w, h)
        elif isinstance(target_size, tuple):
            target_size = QSize(*target_size)

        if radius is None:
            radius = min(target_size.width(), target_size.height()) // 10

        scaled_pixmap = pixmap.scaled(
            target_size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )

        rounded = QPixmap(target_size)
        rounded.fill(Qt.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, target_size.width(), target_size.height(), radius, radius)
        painter.setClipPath(path)

        x_offset = (target_size.width() - scaled_pixmap.width()) // 2
        y_offset = (target_size.height() - scaled_pixmap.height()) // 2
        painter.drawPixmap(x_offset, y_offset, scaled_pixmap)
        painter.end()

        return rounded

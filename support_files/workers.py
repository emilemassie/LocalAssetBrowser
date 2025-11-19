from PyQt5.QtCore import QThread, pyqtSignal, QObject, Qt, QSize, QRect
from datetime import datetime
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtGui import QPixmap, QColor, QPainter, QFont
from functools import lru_cache
import os


# Simple pixmap cache with LRU eviction
class PixmapCache:
    def __init__(self, max_size=100):
        self.cache = {}
        self.max_size = max_size
        self.access_order = []
    
    def get(self, path):
        if path in self.cache:
            # Move to end (most recently used)
            self.access_order.remove(path)
            self.access_order.append(path)
            return self.cache[path]
        return None
    
    def put(self, path, pixmap):
        if path in self.cache:
            self.access_order.remove(path)
        elif len(self.cache) >= self.max_size:
            # Remove least recently used
            oldest = self.access_order.pop(0)
            del self.cache[oldest]
        
        self.cache[path] = pixmap
        self.access_order.append(path)
    
    def clear(self):
        self.cache.clear()
        self.access_order.clear()


# Global pixmap cache
pixmap_cache = PixmapCache(max_size=150)


class OptimizedTableDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate that renders table items without creating individual widgets"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumbnail_width = 100
        self.thumbnail_height = 100
        self.row_height = 110
    
    def paint(self, painter, option, index):
        """Paint table cell content"""
        if index.column() == 0:  # Thumbnail column
            self.paint_thumbnail(painter, option, index)
        else:
            # Use default painting for other columns
            super().paint(painter, option, index)
    
    def paint_thumbnail(self, painter, option, index):
        """Paint a thumbnail with fallback to text"""
        painter.save()
        
        # Fill background
        if option.state & QtWidgets.QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())
        
        thumbnail_path = index.data(Qt.DisplayRole)
        
        if thumbnail_path and os.path.exists(thumbnail_path):
            # Try to get from cache first
            pixmap = pixmap_cache.get(thumbnail_path)
            
            if pixmap is None:
                # Load and cache
                pixmap = QPixmap(thumbnail_path)
                if not pixmap.isNull():
                    # Scale to fill cell while preserving aspect ratio
                    # Use cell dimensions for max size, then scale down if needed
                    cell_w = option.rect.width() - 4  # small padding
                    cell_h = option.rect.height() - 4
                    pixmap = pixmap.scaledToWidth(cell_w, Qt.FastTransformation)
                    # If height exceeds cell height, scale by height instead
                    if pixmap.height() > cell_h:
                        pixmap = pixmap.scaledToHeight(cell_h, Qt.FastTransformation)
                    pixmap_cache.put(thumbnail_path, pixmap)
            
            # Draw pixmap centered
            if pixmap and not pixmap.isNull():
                x = option.rect.x() + (option.rect.width() - pixmap.width()) // 2
                y = option.rect.y() + (option.rect.height() - pixmap.height()) // 2
                painter.drawPixmap(x, y, pixmap)
            else:
                self.paint_text(painter, option, "No Image")
        else:
            self.paint_text(painter, option, "No Image")
        
        painter.restore()
    
    def paint_text(self, painter, option, text):
        """Paint fallback text"""
        painter.drawText(option.rect, Qt.AlignCenter, text)
    
    def sizeHint(self, option, index):
        """Return size hint for items"""
        if index.column() == 0:
            return QSize(self.thumbnail_width, self.row_height)
        return super().sizeHint(option, index)


class TableBuilderWorker(QObject):
    finished = pyqtSignal()
    update_status = pyqtSignal(str, int)
    # Signal to send batch of rows from worker thread to main thread
    add_rows_batch = pyqtSignal(list)

    def __init__(self, parent=None, database=None):
        super().__init__(parent)
        self.database = database
        self.is_running = True
        

    def run(self):
        if self.database:
            print("Building table widget...")
            
            batch = []
            batch_size = 250  # Even larger batches since we're not creating widgets
            total = len(self.database)
            count = 0
            
            for file_id, info in self.database.items():
                if not self.is_running:
                    break
                    
                count += 1
                
                # Fast attribute access
                thumbnail = info.get("thumbnail", "")
                name = info.get("name", "")
                type_ = info.get("type", "")
                path = info.get("path", "")

                # ---- Convert ctime to readable date (only if present) ----
                date_str = ""
                if "ctime" in info:
                    try:
                        date_str = datetime.fromtimestamp(info["ctime"]).strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        pass

                # ---- Build the "extra info" section (without path) ----
                extra_lines = []
                if date_str:
                    extra_lines.append(f"Date: {date_str}")

                # Only include extra fields (exclude standard ones)
                excluded = {"name", "type", "path", "ctime", "thumbnail"}
                for k, v in info.items():
                    if k not in excluded:
                        extra_lines.append(f"{k}: {v}")

                extra_info_text = "\n".join(extra_lines)

                # Add to batch with minimal data
                row_data = {
                    'thumbnail': thumbnail,
                    'name': name,
                    'type': type_,
                    'extra_info': extra_info_text,
                    'path': path,
                    'file_id': file_id
                }
                batch.append(row_data)
                
                # Emit batch when it reaches batch_size or at the end
                if len(batch) >= batch_size or count == total:
                    self.add_rows_batch.emit(batch)
                    # Update status less frequently
                    if count % (batch_size * 2) == 0 or count == total:
                        progress = int((count / total) * 100)
                        self.update_status.emit(f"Building table: {count}/{total}", progress)
                    batch = []
            
            print(f"Finished building table widget. Total: {total} items.")
        self.finished.emit()
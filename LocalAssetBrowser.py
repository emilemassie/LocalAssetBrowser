import sys, os
import struct
import json
from datetime import datetime

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtWidgets import QMessageBox, QSplashScreen, QApplication
from PyQt5.QtCore import QThread, Qt, QTimer, QEvent, QUrl, QMimeData, QByteArray
from PyQt5.QtGui import QIcon, QPixmap, QDrag
from PyQt5 import uic



from appdirs import user_config_dir

from support_files.settings import LocalAssetBrowserSettings
from support_files.search import SearchWorker
from support_files.flow_layout import FlowLayout
from support_files.asset_widget import ClickableVersionWidget
from support_files.ffmpeg_worker import FFMPEGWorker, BackGroundWorker
from support_files.workers import TableBuilderWorker, OptimizedTableDelegate



class SplashScreen(QSplashScreen):
    def __init__(self, window):
        image = os.path.join(os.path.dirname(__file__), 'icons', 'splash.jpg')
        super().__init__(QPixmap(image))
        
        self.ui = uic.loadUi(os.path.join(os.path.dirname(__file__), 'ui', 'splash.ui'), self)
        self.window = window
        self.ui.status_text.setText(self.window.status)
        self.ui.progressBar.setValue(0)
        self.setFixedSize(1050, 600)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.CustomizeWindowHint)
        self.show()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(10)

    def refresh_status(self):
        if self.window.loaded:
            self.timer.stop()
            self.close()
            self.window.show()
        else:
            if not self.window.database or len(self.window.database) == 0:
                self.ui.status_text.setText(self.window.status)
                self.ui.progressBar.setValue(int(self.window.percent/3.33))
            else:
                self.ui.status_text.setText(self.window.status)
                self.ui.progressBar.setValue(int(self.window.percent/3.33*2 +33))

            
        
 
class LocalAssetBrowser(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Local Asset Browser")
        self.settings = LocalAssetBrowserSettings()
        self.status = 'Initializing...'
        self.percent = 0
        self.file_list = {}
        self.database = {}
        
        # Track active threads for proper cleanup
        self.table_builder_thread = None
        self.table_builder_worker = None

        self.search_worker = SearchWorker()
        self.search_worker.search_completed.connect(self.on_search_completed)
        self.search_worker.search_status.connect(self.on_search_status)
        self.search_worker.create_widget.connect(self.create_asset_widget)
        
        # queue for batching widget creation to keep UI responsive
        self._widget_queue = []
        self._processing_queue = False

        self.setup_ui()
        self.settings.load_settings()
        self.set_library_root()
        self.search_worker.set_search_parameters(self.library_root)
        self.refresh_versions_threaded()
        self.loaded = False
        


        
    def refresh_versions_threaded(self):
        # If a worker thread is already running, stop it first
        self.ui.version_grid.clear()
        self.file_list = {}
        try:
            if hasattr(self, "worker_thread") and self.worker_thread.isRunning():
                print("⏹ Stopping previous worker...")
                self.worker.is_stopped = True
                self.worker_thread.requestInterruption()
                self.worker_thread.quit()
                self.worker_thread.wait()  # Block until fully stopped
                self.ui.refresh_button.setText("Refresh")
                return
        except Exception as e:
            print("Error stopping previous worker:", e)

        self.ui.refresh_button.setText("Cancel")

        print("🔄 Starting new refresh...")
        
        self.worker_thread = QThread()
        self.worker = SearchWorker()
        self.worker.set_search_parameters(self.set_library_root())
        self.worker.moveToThread(self.worker_thread)

        # Connect signals
        self.worker_thread.started.connect(self.worker.run)
        self.worker.create_widget.connect(self.create_asset_widget)
        self.worker.search_status.connect(self.on_search_status)
        #self.worker.finished.connect(self.on_search_completed)
        self.worker.search_completed.connect(self.on_search_completed)

        # Cleanup
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()
        return
    
    def save_database(self):
        db_folder = os.path.join(self.library_root, ".db")
        if not os.path.exists(db_folder):
            os.makedirs(db_folder)
        db_file = os.path.join(db_folder, "database.json")
        with open(db_file, "w") as f:
            json.dump(self.database, f, indent=4)
    
    def generate_thumbnails_in_bg(self, thumbnails_folder, file_list):
        if not os.path.exists(thumbnails_folder):
            os.makedirs(thumbnails_folder)
        self.background_worker = BackGroundWorker(thumbnails_folder,file_list)
        self.background_worker.set_tumbnail.connect(self.set_thumbnail)
        self.background_worker.set_status.connect(self.on_search_status)
        self.background_worker.finished.connect(self.build_table_widget)
        self.background_worker.finished.connect(self.save_database)
        self.background_worker.moveToThread(self.worker_thread)
        self.background_worker.start()

    def set_thumbnail(self, id ,thumbnail_path):
        self.database[id]['thumbnail'] = thumbnail_path
  
    def set_file_list(self, file_list):
        self.file_list = file_list
        self.ui.statusbar.showMessage(f"Search completed: {len(file_list)} items found.")
        db_folder = os.path.join(self.library_root, ".db")
        db_file = os.path.join(db_folder, "database.json")



        if not os.path.exists(db_file):
            with open(db_file, "w") as f:
                json.dump({}, f, indent=4)


        thumbnails_folder = os.path.join(db_folder, "thumbnails")
        if not os.path.exists(thumbnails_folder):
            os.makedirs(thumbnails_folder)

        #update the current json file and add keys that are missing
        with open(db_file, "r") as f:
            data = json.load(f)
            for file in file_list:
                if file not in data:
                    data[file] = file_list[file]
            with open(db_file, "w") as f:
                json.dump(data, f, indent=4)

        

        #self.generate_thumbnails_in_bg(thumbnails_folder,file_list)

    def finished_search(self):
        self.ui.statusbar.showMessage(f"Search completed: {len(self.database)} items found.")
        #self.update()
        self.ui.setUpdatesEnabled(True)
        self.ui.table_widget.viewport().update()
        self.loaded = True
        
    def create_asset_widget(self, file, preview_file):
        # Prefer a generated thumbnail if available in file metadata
        thumb = None
        if isinstance(file, dict) and file.get('thumbnail'):
            thumb = file.get('thumbnail')
        else:
            # if preview_file is inside .db/thumbnails, treat it as thumbnail
            try:
                if preview_file and '.db' + os.sep + 'thumbnails' in preview_file:
                    thumb = preview_file
            except Exception:
                thumb = None

        # enqueue widget creation to avoid blocking the GUI when many widgets arrive
        self._widget_queue.append((file, thumb))
        if not self._processing_queue:
            self._process_widget_queue()

    def _process_widget_queue(self, batch_size=20):
        """Process queued widget creations in small batches to keep UI responsive."""
        self._processing_queue = True
        count = 0
        while self._widget_queue and count < batch_size:
            file, thumb = self._widget_queue.pop(0)
            widget = ClickableVersionWidget(file, thumb)
            widget.doubleClicked.connect(self.load_file)
            self.ui.version_grid.addWidget(widget)
            count += 1

        if self._widget_queue:
            # schedule next batch after a short delay to let the UI breathe
            QTimer.singleShot(50, lambda: self._process_widget_queue(batch_size))
        else:
            self._processing_queue = False
        #self.update()

    def load_file(self, id):
        # find all child of the Qwidget and delete them
        for child in self.ui.info_widget.findChildren(QtWidgets.QWidget):
            child.deleteLater()

        file = self.database.get(id)
        preview_file = file.get('thumbnail', None)

        order = ["name", "type", 'first_frame', 'last_frame', 'duration', 'fps', 'size', 'path']
        sorted_dict = {k: file[k] for k in order if k in file}

        # Add remaining keys not in 'order'
        for k in file:
            if k not in sorted_dict:
                sorted_dict[k] = file[k]

        for key in sorted_dict:
            print(key, file[key])
            if key == 'thumbnail':
                self.ui.current_frame_label.setPixmap(QPixmap(preview_file))
            else:
                if key == 'ctime':
                    value = QtWidgets.QLabel(str(datetime.fromtimestamp(file[key]).strftime('%Y-%m-%d %H:%M:%S')))
                    title = QtWidgets.QLabel('Creation Date'.upper())
                else:
                    value = QtWidgets.QLabel(str(file[key]))
                    title = QtWidgets.QLabel(str(key).replace("_", " ").upper())
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                value.setWordWrap(True)
                value.setStyleSheet("font-weight: italic;")
                title.setStyleSheet("font-weight: bold;")
                self.ui.info_widget.layout().addRow(title, value)
        print(f"Loading file: {file}")


    def merge_dicts(self, dict1, dict2):
        """
        Merge dict2 into dict1.
        - For overlapping keys:
            * If both values are dicts, merge recursively.
            * Otherwise, keep dict1's value.
        - Add keys missing in dict1 from dict2.
        """

        result = dict1.copy()

        for key, value in dict2.items():
            if key not in result:
                # Add missing key from dict2
                result[key] = value
            else:
                # If both values are dicts → merge recursively
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self.merge_dicts(result[key], value)
                # Else keep dict1’s value (result[key]) and ignore dict2’s

        return result

    def on_search_completed(self, results):
        self.ui.version_grid.clear()
        self.ui.table_widget.clear()

        db_file = os.path.join(self.library_root, ".db", "database.json")

        if os.path.exists(db_file):
            with open(db_file, "r") as f:
                self.database = json.load(f)

        new_db = self.merge_dicts(self.database, results)
        self.database = new_db

        with open(db_file, "w") as f:
            json.dump(new_db, f, indent=4)
        
        self.on_search_status('Saving database...', 0)
        
        self.generate_thumbnails_in_bg(os.path.join(self.library_root, ".db", "thumbnails"), new_db)


    def build_table_widget(self):
        # Stop any existing table builder thread before creating a new one
        self._stop_table_builder_thread()
        
        # Clear and setup table widget on main thread
        self.ui.table_widget.setRowCount(0)
        self.ui.table_widget.setColumnCount(5)
        self.ui.table_widget.setHorizontalHeaderLabels(["Thumbnail", "Name", "Type", "Info", "Path"])
        
        # Make table non-editable
        self.ui.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.ui.table_widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        
        # Set column widths
        self.ui.table_widget.setColumnWidth(0, 120)
        self.ui.table_widget.setColumnWidth(1, 150)
        self.ui.table_widget.setColumnWidth(2, 100)
        self.ui.table_widget.setColumnWidth(3, 200)
        self.ui.table_widget.setColumnWidth(4, 300)
        
        # Set custom delegate for thumbnail column to handle rendering efficiently
        # keep a reference on self so we can update delegate sizes later
        self.table_delegate = OptimizedTableDelegate()
        self.ui.table_widget.setItemDelegateForColumn(0, self.table_delegate)
        # Connect header resize signals so thumbnails update to fill cell on resize
        try:
            self.ui.table_widget.horizontalHeader().sectionResized.connect(self.on_table_section_resized)
            self.ui.table_widget.verticalHeader().sectionResized.connect(self.on_table_section_resized)
        except Exception:
            # If UI isn't fully constructed yet, ignore - connections can be made later
            pass
        # Enable dragging rows (we handle the drag start in an event filter)
        try:
            self.ui.table_widget.setDragEnabled(True)
            self.ui.table_widget.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
            # Install event filter to start drag with custom mime data
            self.ui.table_widget.installEventFilter(self)
            # track drag start
            self._drag_start_pos = None
            self._drag_pressed_row = None
        except Exception:
            pass
        
        # Connect double-click signal
        self.ui.table_widget.doubleClicked.connect(self.on_table_row_double_clicked)
        
        # Create a new thread for the table builder
        self.table_builder_thread = QThread()
        self.table_builder_worker = TableBuilderWorker(database=self.database)
        
        # Move worker to thread
        self.table_builder_worker.moveToThread(self.table_builder_thread)
        
        # Connect signals
        self.table_builder_thread.started.connect(self.table_builder_worker.run)
        self.table_builder_worker.update_status.connect(self.on_search_status)
        # Connect worker signals to add rows in batches on main thread
        self.table_builder_worker.add_rows_batch.connect(self.add_table_rows_batch)
        
        # Cleanup connections
        self.table_builder_worker.finished.connect(self.table_builder_thread.quit)
        self.table_builder_worker.finished.connect(self.table_builder_worker.deleteLater)
        self.table_builder_thread.finished.connect(self.finished_search)
        
        # Start the thread
        self.table_builder_thread.start()
    
    def on_table_row_double_clicked(self, index):
        """Handle table row double-click"""
        row = index.row()
        
        # Get the file ID from the Name column (column 1)
        name_item = self.ui.table_widget.item(row, 1)
        if name_item is None:
            return
        
        file_id = name_item.data(Qt.UserRole)
        self.load_file(file_id)
    
    def add_table_rows_batch(self, rows_batch):
        """Add a batch of rows to the table widget (runs on main thread)"""
        # Disable updates while adding rows to prevent repainting
        self.ui.table_widget.setUpdatesEnabled(False)
        
        try:
            for row_data in rows_batch:
                thumbnail = row_data['thumbnail']
                name = row_data['name']
                type_ = row_data['type']
                extra_info_text = row_data['extra_info']
                path = row_data['path']
                file_id = row_data['file_id']
                
                # ---- Insert row ----
                row = self.ui.table_widget.rowCount()
                self.ui.table_widget.insertRow(row)

                # ---- COLUMN 0: THUMBNAIL (using delegate, just store path) ----
                thumb_item = QtWidgets.QTableWidgetItem(thumbnail)
                thumb_item.setData(Qt.DisplayRole, thumbnail)
                self.ui.table_widget.setItem(row, 0, thumb_item)

                # ---- COLUMN 1: NAME ----
                name_item = QtWidgets.QTableWidgetItem(str(name))
                # Store file_id in the name item for easy access
                name_item.setData(Qt.UserRole, file_id)
                self.ui.table_widget.setItem(row, 1, name_item)

                # ---- COLUMN 2: TYPE ----
                self.ui.table_widget.setItem(row, 2, QtWidgets.QTableWidgetItem(str(type_)))

                # ---- COLUMN 3: INFO (QLabel for multiline) ----
                info_label = QtWidgets.QLabel(extra_info_text)
                info_label.setWordWrap(True)
                info_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
                info_label.setStyleSheet("padding: 5px;")
                self.ui.table_widget.setCellWidget(row, 3, info_label)

                # ---- COLUMN 4: PATH ----
                path_item = QtWidgets.QTableWidgetItem(str(path))
                self.ui.table_widget.setItem(row, 4, path_item)

                # Set row height
                self.ui.table_widget.setRowHeight(row, 110)
        
        finally:
            # Re-enable updates and refresh once
            self.ui.table_widget.setUpdatesEnabled(True)
            self.ui.table_widget.viewport().update()

    def set_table_row_height(self, height):
        """Set a fixed height for all table rows and update the thumbnail delegate.

        height: integer pixels for each row (will be clamped to >=1)
        """
        try:
            h = int(max(1, height))
        except Exception:
            return

        # Update default size and delegate expectations
        #print(self.ui.table_widget.verticalHeader().defaultSectionSize())
        self.ui.table_widget.verticalHeader().setDefaultSectionSize(h)
        self.ui.table_widget.setColumnWidth(0, int(h*16/9))
        
        #self.ui.table_widget.horizontalHeader().setDefaultSectionSize(h)
        if hasattr(self, 'table_delegate') and self.table_delegate:
            # Keep thumbnail height slightly smaller than row
            self.table_delegate.row_height = h
            self.table_delegate.thumbnail_height = max(16, h - 10)

        # Apply to each existing row quickly with updates disabled
        self.ui.table_widget.setUpdatesEnabled(False)
        try:
            for r in range(self.ui.table_widget.rowCount()):
                self.ui.table_widget.setRowHeight(r, h)
        finally:
            self.ui.table_widget.setUpdatesEnabled(True)
            self.ui.table_widget.viewport().update()

    def reset_thumbnail_sizes(self):
        """Recalculate and apply thumbnail sizes based on current column/row sizes.

        This updates the delegate's expected thumbnail width/height and clears
        the pixmap cache so images are reloaded and scaled to the new size.
        """
        try:
            # Column 0 width (thumbnail column)
            col_w = max(16, self.ui.table_widget.columnWidth(0))
            # Use default section size as representative row height
            row_h = max(16, self.ui.table_widget.verticalHeader().defaultSectionSize())

            if hasattr(self, 'table_delegate') and self.table_delegate:
                # Keep small paddings so images don't touch cell borders
                self.table_delegate.thumbnail_width = max(16, col_w - 8)
                self.table_delegate.thumbnail_height = max(16, row_h - 8)
                self.table_delegate.row_height = row_h

            # Clear the pixmap cache so images are reloaded at the new size
            try:
                from support_files.workers import pixmap_cache
                pixmap_cache.clear()
            except Exception:
                pass

            # Trigger a repaint
            self.ui.table_widget.viewport().update()
        except Exception:
            # Non-fatal; ignore errors during resize handling
            pass

    def on_table_section_resized(self, *args):
        """Slot for header sectionResized — refresh thumbnail sizes."""
        # Delegate actual work to reset_thumbnail_sizes for clarity/testing
        self.reset_thumbnail_sizes()

    def _get_drag_path_for_row(self, row):
        """Return the appropriate path to drag for a given row.

        If the type column indicates a sequence (case-insensitive contains 'sequence'),
        return the containing folder of the file path. Otherwise return the file path.
        Returns None if path can't be determined.
        """
        try:
            type_item = self.ui.table_widget.item(row, 2)
            path_item = self.ui.table_widget.item(row, 4)
            if path_item is None:
                return None
            path = path_item.text()
            type_text = '' if type_item is None else type_item.text() or ''
            if 'sequence' in type_text.lower():
                # return folder containing the path
                return os.path.dirname(path)
            return path
        except Exception:
            return None

    def eventFilter(self, obj, event):
        """Handle mouse events on the table to start a drag with file/folder path."""
        try:
            if obj is self.ui.table_widget:
                # Mouse press: record start pos and row
                if event.type() == QEvent.MouseButtonPress:
                    if event.buttons() & Qt.LeftButton:
                        self._drag_start_pos = event.pos()
                        idx = self.ui.table_widget.indexAt(self._drag_start_pos)
                        self._drag_pressed_row = idx.row() if idx.isValid() else None
                # Mouse move: check threshold and start drag
                elif event.type() == QEvent.MouseMove:
                    if self._drag_start_pos is None:
                        return super().eventFilter(obj, event)
                    if not (event.buttons() & Qt.LeftButton):
                        return super().eventFilter(obj, event)
                    dist = (event.pos() - self._drag_start_pos).manhattanLength()
                    if dist >= QApplication.startDragDistance() and self._drag_pressed_row is not None:
                        pressed_row = self._drag_pressed_row
                        # Decide which rows to drag: if multiple selected and the pressed row is in selection,
                        # drag all selected rows; otherwise drag only the pressed row.
                        sel_rows = [idx.row() for idx in self.ui.table_widget.selectionModel().selectedRows()]
                        if sel_rows and pressed_row in sel_rows:
                            rows_to_drag = sel_rows
                        else:
                            rows_to_drag = [pressed_row]

                        # Collect unique paths (preserve order)
                        paths = []
                        seen = set()
                        for r in rows_to_drag:
                            p = self._get_drag_path_for_row(r)
                            if p and p not in seen:
                                seen.add(p)
                                paths.append(p)

                        if not paths:
                            # nothing to drag
                            self._drag_start_pos = None
                            self._drag_pressed_row = None
                            return super().eventFilter(obj, event)

                        mime = QMimeData()
                        urls = [QUrl.fromLocalFile(p) for p in paths]
                        mime.setUrls(urls)
                        mime.setText(';'.join(paths))

                        # Also provide several additional formats to increase compatibility with Windows apps
                        try:
                            # 1) text/uri-list (UTF-8) — common URI list format
                            uri_list = '\r\n'.join([u.toString() for u in urls])
                            mime.setData('text/uri-list', QByteArray(uri_list.encode('utf-8')))

                            # 2) plain text with local paths (newline separated)
                            mime.setData('text/plain', QByteArray('\r\n'.join(paths).encode('utf-8')))

                            # 3) FileNameW (UTF-16LE Windows native)
                            fnw = b''.join([p.encode('utf-16le') + b'\x00\x00' for p in paths]) + b'\x00\x00'
                            mime.setData('application/x-qt-windows-mime;value="FileNameW"', QByteArray(fnw))

                            # 4) FileName (ANSI) — some older apps expect ANSI null-terminated strings
                            try:
                                ansi = b''.join([p.encode('mbcs', errors='replace') + b'\x00' for p in paths]) + b'\x00'
                                mime.setData('application/x-qt-windows-mime;value="FileName"', QByteArray(ansi))
                            except Exception:
                                pass

                            # 5) CF_HDROP (DROPFILES wide) — construct DROPFILES struct + UTF-16LE filenames
                            try:
                                # DROPFILES struct: DWORD pFiles; LONG pt.x; LONG pt.y; BOOL fNC; BOOL fWide;
                                # We set pFiles to size of header (20) and fWide=1
                                pFiles = 20
                                drop_header = struct.pack('<IiiII', pFiles, 0, 0, 0, 1)
                                drop_buf = drop_header + fnw
                                mime.setData('application/x-qt-windows-mime;value="CF_HDROP"', QByteArray(drop_buf))
                            except Exception:
                                pass
                        except Exception:
                            pass

                        drag = QDrag(self.ui.table_widget)
                        drag.setMimeData(mime)

                        # Try to use the first thumbnail as drag pixmap for nicer UX
                        try:
                            thumb_item = self.ui.table_widget.item(rows_to_drag[0], 0)
                            thumb_path = thumb_item.data(Qt.DisplayRole) if thumb_item is not None else None
                            if thumb_path and os.path.exists(thumb_path):
                                pm = QPixmap(thumb_path)
                                if not pm.isNull():
                                    pm = pm.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                    drag.setPixmap(pm)
                        except Exception:
                            pass

                        drag.exec_(Qt.CopyAction)
                        # reset drag trackers
                        self._drag_start_pos = None
                        self._drag_pressed_row = None
                        return True
                # Mouse release: clear trackers
                elif event.type() == QEvent.MouseButtonRelease:
                    self._drag_start_pos = None
                    self._drag_pressed_row = None
        except Exception:
            # swallow exceptions in filter to avoid breaking UI
            pass
        return super().eventFilter(obj, event)

    def auto_adjust_table_row_heights(self, min_height=50, max_height=400):
        """Adjust row heights to fit content.

        This inspects the info widget (column 3) and the delegate thumbnail
        height and sets each row to the larger of those values clamped by
        min_height/max_height. Runs on the main thread and disables updates
        while resizing to reduce flicker.
        """
        # Read thumbnail preferred height from delegate if available

        print(min_height, max_height)
        thumb_h = 100
        if hasattr(self, 'table_delegate') and self.table_delegate:
            try:
                thumb_h = int(getattr(self.table_delegate, 'thumbnail_height', thumb_h))
            except Exception:
                pass

        self.ui.table_widget.setUpdatesEnabled(False)
        try:
            rows = self.ui.table_widget.rowCount()
            for r in range(rows):
                # Prefer the info widget sizeHint if present
                info_widget = self.ui.table_widget.cellWidget(r, 3)
                info_h = 0
                if info_widget is not None:
                    info_h = info_widget.sizeHint().height()

                required = max(min_height, min(max_height, max(info_h, thumb_h)))
                self.ui.table_widget.setRowHeight(r, required)
        finally:
            self.ui.table_widget.setUpdatesEnabled(True)
            self.ui.table_widget.viewport().update()



    def on_search_status(self, status, percent=None):
        self.status = status
        self.percent = percent
        self.ui.statusbar.showMessage(status)
        self.ui.statusbar.update()
        self.update()

    def refresh_library(self):
        root_dir = self.set_library_root()
        self.ui.table_widget.clearContents()
        self.ui.table_widget.setRowCount(0)
        self.ui.version_grid.clear()
        if not root_dir or not os.path.exists(root_dir):
            QMessageBox.warning(self, "Invalid Directory", "The specified root directory does not exist.")
            return

        db_folder = os.path.join(root_dir, ".db")
        if not os.path.exists(db_folder):
            os.makedirs(db_folder)

        thumbnails_folder = os.path.join(db_folder, "thumbnails")
        if not os.path.exists(thumbnails_folder):
            os.makedirs(thumbnails_folder)

        print(f"Refreshing library from: {root_dir}")
        self.search_worker.set_search_parameters(root_dir)
        self.search_worker.start()

    def set_library_root(self):
        self.library_root = self.settings.ui.root_dir.text()
        self.ui.library_path.setText(self.library_root)
        return self.library_root
    
    def _stop_table_builder_thread(self):
        """Helper method to safely stop the table builder thread"""
        try:
            if self.table_builder_thread is not None:
                # Check if thread still exists and is running
                if self.table_builder_thread.isRunning():
                    print("⏹ Stopping table builder...")
                    if self.table_builder_worker:
                        self.table_builder_worker.is_running = False
                    self.table_builder_thread.quit()
                    self.table_builder_thread.wait(5000)  # Wait up to 5 seconds
        except RuntimeError:
            # Thread was already deleted
            pass
    
    def closeEvent(self, event):
        """Ensure all threads are properly stopped before closing"""
        # Stop table builder thread
        self._stop_table_builder_thread()
        
        # Stop search worker thread
        try:
            if hasattr(self, "worker_thread") and self.worker_thread is not None:
                if self.worker_thread.isRunning():
                    if hasattr(self, "worker"):
                        self.worker.is_stopped = True
                    self.worker_thread.quit()
                    self.worker_thread.wait(5000)
        except RuntimeError:
            # Thread was already deleted
            pass
        
        event.accept()
    
    def setup_ui(self):
        uic_path = os.path.join(os.path.dirname(__file__), 'ui', 'LocalAssetBrowser.ui')
        self.ui = uic.loadUi(uic_path, self)

        self.ui.scroll_content = QtWidgets.QWidget()
        self.ui.version_grid = FlowLayout(self.ui.scroll_content)
        self.ui.scroll_content.setLayout(self.ui.version_grid)
        self.ui.scrollArea.setWidget(self.ui.scroll_content)

        self.ui.search_button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'search.svg')))
        self.ui.refresh_button.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'refresh.svg')))
        self.ui.list_view.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'list.svg')))
        self.ui.grid_view.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icons', 'grid.svg')))
        #make the window have no close or min mac butotn
       

        self.ui.actionPreferences.triggered.connect(self.settings.show)
        self.ui.refresh_button.clicked.connect(self.refresh_library)
        self.ui.tumb_slider.valueChanged.connect(self.set_table_row_height)
        #self.ui.search_button.clicked.connect(self.search)
        self.ui.list_view.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(1))
        self.ui.grid_view.clicked.connect(lambda: self.ui.stackedWidget.setCurrentIndex(0))

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = LocalAssetBrowser()
    splash = SplashScreen(window)
    sys.exit(app.exec_())

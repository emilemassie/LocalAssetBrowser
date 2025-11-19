import os
import subprocess
import concurrent.futures
import multiprocessing
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication
import hashlib
import time

class BackGroundWorker(QThread):
    # Emits a status message and percent complete
    set_status = pyqtSignal(str, int)
    set_tumbnail = pyqtSignal(str,str)
    finished = pyqtSignal()

    def __init__(self, thumbnail_path, file_list, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.file_list = file_list
        self.thumbnail_path = thumbnail_path

    def run(self):
        # Use a ThreadPoolExecutor to run conversions in parallel up to CPU cores
        self.set_status.emit('Generating thumbnails', 0)
        try:
            max_workers = multiprocessing.cpu_count() or 1
        except Exception:
            max_workers = 1

        # Don't create more workers than files
        total_files = len(self.file_list)
        workers = min(max_workers, total_files) if total_files > 0 else 1

        completed = 0
        percent = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_key = {executor.submit(self._convert_one, key, file): key for key, file in self.file_list.items()}

            for future in concurrent.futures.as_completed(future_to_key):
                
                key = future_to_key[future]
                file = self.file_list.get(key)
                try:
                    thumbnail_path = future.result()
                except Exception as e:
                    thumbnail_path = None
                    self.set_status.emit(f'Error generating thumbnail for {key}: {e}', 0)

                # attach thumbnail to file metadata if available
                if file is not None and thumbnail_path:
                    self.set_tumbnail.emit(key, thumbnail_path)
                    file['thumbnail'] = thumbnail_path
                 

                completed += 1

                # find key index in filelist as a number
                index = list(self.file_list.keys()).index(key)+1

                
                percent = int(index / total_files * 100) if total_files else 100


                name = file.get('name') if isinstance(file, dict) and 'name' in file else str(key)
                self.set_status.emit(f'Done generating thumbnail for {name} [{completed}/{total_files}]', percent)



        # All done
        self.set_status.emit('All thumbnails generated', 100)
        self.finished.emit()

    def _convert_one(self, key, file):
        """Helper that runs a single conversion and returns the thumbnail path."""
        file_path = file.get('path') if isinstance(file, dict) else file
        worker = FFMPEGWorker(self.thumbnail_path, file_path)
        thumbnail_path = worker.convert_tumbnail()
        return thumbnail_path

        

class FFMPEGWorker():
    def __init__(self, thumbnail_path, file_path, parent=None):
        self.parent = parent
        self.file_path = file_path
        self.root_path = thumbnail_path
        self.ffmpeg_executable = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg', 'ffmpeg.exe')
        self.oiiotool_executable = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'OpenImageIO', 'oiiotool.exe')
        self.thumbnail_name = None

    def convert_tumbnail(self):
        """Generate thumbnail using FFMPEG"""

        #generate unique key for filename
        hash_object = hashlib.sha1(self.file_path.encode('utf-8'))
        self.thumbnail_name = hash_object.hexdigest()
        tumbnail_path = os.path.join(self.root_path, self.thumbnail_name + '.jpeg')

        if os.path.exists(tumbnail_path):
            return tumbnail_path


        # convert video to image
        IMAGE_EXTENSIONS = {'.exr', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp'}
        VIDEO_EXTENSIONS = {'.mov','.mp4', '.mkv', '.avi', '.flv', '.wmv', '.webm', '.m4v', '.mts', '.m2ts'}
        if self.file_path.lower().endswith('.exr'):
            subprocess.run([self.oiiotool_executable, self.file_path, '--ch', 'R,G,B', '--flatten', '-o', tumbnail_path])
        
        else:
            subprocess.run([self.ffmpeg_executable, '-y', '-i', self.file_path, '-frames:v', '1', '-vf', 'format=rgb24,scale=-1:1080:force_original_aspect_ratio=decrease','-loglevel', 'error', tumbnail_path])

        return tumbnail_path

        

 
        
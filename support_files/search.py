import os
import re
from PyQt5.QtCore import QThread, pyqtSignal
import hashlib





class SearchWorker(QThread):
    search_completed = pyqtSignal(dict)
    search_status = pyqtSignal(str, int)
    create_widget = pyqtSignal(str, str)  # path, preview file

    def __init__(self, ):
        super().__init__()
        self.is_stopped = False
        self.root_path = None
        self.total_folders = 0

    def set_search_parameters(self, root_dir):
        self.root_path = root_dir
        self.db_folder = os.path.join(root_dir, ".db")

    def run(self):
        result = self.collect_version_folders()
        self.search_completed.emit(result or {})

    def collect_version_folders(self):
        """
        Scan for individual files. Emit each file as a separate entry.
        For image sequences, group by directory and emit as one entry with range format.
        Videos are always emitted as individual files (never grouped).
        """
        all_files = {}  # Maps display name -> file info
        
        # broad list of media extensions (images, image sequences, video)
        image_exts = {'.exr', '.dpx', '.tif', '.tiff', '.tga', '.png', '.jpg', '.jpeg', '.bmp', '.webp'}
        video_exts = {'.mov', '.mp4', '.mkv', '.avi', '.flv', '.wmv', '.webm', '.m4v', '.mts', '.m2ts'}
        all_exts = image_exts | video_exts

        # sequence detection pattern: name.0001.ext or name_0001.ext (3-6 digits)
        seq_pattern = re.compile(r'^(.+?)[\._](\d{3,6})(\.[^\.]+)$', re.IGNORECASE)

        # Gather all directories for progress
        all_dirs = [d for d, _, _ in os.walk(self.root_path)]
        self.total_folders = len(all_dirs) or 1
        self.search_status.emit(f"Processing 0/{self.total_folders}", 0)

        processed_sequences = set()  # Track which files are part of sequences

        for counter, full_path in enumerate(all_dirs, 1):

            if getattr(self, "is_stopped", False):
                print("⏹ Worker interrupted")
                return

            # Skip .db folder and anything under it
            if '.db' in full_path.split(os.sep):
                continue

            try:
                filenames = os.listdir(full_path)
            except PermissionError:
                continue  # skip restricted folders

            # Separate videos and potential image sequences
            video_files = [f for f in filenames if f.lower().endswith(tuple(video_exts))]
            image_files = [f for f in filenames if f.lower().endswith(tuple(image_exts))]

            # Emit video files as individual entries (never sequences)
            for video_file in video_files:
                file_path = os.path.join(full_path, video_file)
                id = hashlib.sha1(file_path.encode('utf-8')).hexdigest()
                display_name = video_file
                all_files[id] = {
                    'id': id,
                    "ctime": os.path.getctime(file_path),
                    "path": file_path,
                    "name": display_name,
                    "type": "video",
                }

            # Process image files: detect sequences and emit
            for img_file in image_files:
                # Skip if already processed as part of a sequence
                if os.path.join(full_path, img_file) in processed_sequences:
                    continue

                match = seq_pattern.match(img_file)
                if match:
                    # This is a sequence frame; find all frames in the sequence
                    base_name = match.group(1)
                    ext = match.group(3)
                    
                    frame_list = []
                    for other_file in image_files:
                        m = seq_pattern.match(other_file)
                        if m and m.group(1) == base_name and m.group(3) == ext:
                            frame_path = os.path.join(full_path, other_file)
                            frame_list.append((int(m.group(2)), other_file, frame_path))
                            processed_sequences.add(frame_path)
                    
                    if frame_list:
                        frame_list.sort()
                        first_frame = frame_list[0][0]
                        last_frame = frame_list[-1][0]
                        first_frame_file = frame_list[0][2]
                        
                        # Format: basename[firstframe-lastframe].ext
                        display_name = f"{base_name}[{first_frame:04d}-{last_frame:04d}]{ext}"
                        id = hashlib.sha1(first_frame_file.encode('utf-8')).hexdigest()
                        all_files[id] = {
                            "id": id,
                            "ctime": os.path.getctime(first_frame_file),
                            "path": first_frame_file,
                            "name": display_name,
                            "type": "sequence",
                            "frame_count": len(frame_list),
                            "first_frame": first_frame,
                            "last_frame": last_frame
                        }
                       
                else:
                    # Standalone image file
                    file_path = os.path.join(full_path, img_file)
                    display_name = img_file
                    id = hashlib.sha1(file_path.encode('utf-8')).hexdigest()
                    all_files[id] = {
                        "ctime": os.path.getctime(file_path),
                        "path": file_path,
                        "name": display_name,
                        "type": "image",
                    }
                    

            self.search_status.emit(f"Scanning {counter}/{self.total_folders} Folders", int(counter / self.total_folders * 100))

        # Sort by creation time (descending)
        complete_dict = dict(sorted(all_files.items(), key=lambda item: item[1]["ctime"], reverse=True))
        self.search_completed.emit(complete_dict)
        return complete_dict
    

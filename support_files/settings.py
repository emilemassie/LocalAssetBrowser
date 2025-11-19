import os

from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5 import uic
import getpass
from appdirs import user_config_dir
import json

class LocalAssetBrowserSettings(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setup_ui()
        self.setWindowTitle("Settings")
        self.load_settings()

    def set_root(self):
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Root Directory")
        if directory:
            self.ui.root_dir.setText(directory)

    def set_external_player(self):
        file_dialog = QtWidgets.QFileDialog(self)
        file_dialog.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        if file_dialog.exec_():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.ui.external_player.setText(selected_files[0])
        
    def load_settings(self):
        config_file = self.get_config_file()
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    settings = json.load(f)
                    self.ui.root_dir.setText(settings.get("root_directory", ""))
                    self.ui.external_player.setText(settings.get("external_player", ""))
            except json.JSONDecodeError:
                # create an empty one if corrupted
                with open(config_file, 'w') as f:
                    json.dump({}, f)

    def save_settings(self):
        config_file = self.get_config_file()
        with open(config_file, 'w') as f:
            root_dir = self.ui.root_dir.text()
            external_player = self.ui.external_player.text()
            settings = {
                "root_directory": root_dir,
                "external_player": external_player
            }
            f.write(json.dumps(settings, indent=4))

    def get_config_file(self):
        # Get the current username
        username = getpass.getuser()

        # Define your application name and author/company name
        app_name = "Local Asset Browser"
        app_author = "Local Asset Browser"  # Optional, not needed for Linux

        # Get the user-specific configuration directory
        config_dir = user_config_dir(app_name, app_author)

        # Create the configuration directory if it doesn't exist
        os.makedirs(config_dir, exist_ok=True)

        # Define the path for your configuration file
        config_file = os.path.join(config_dir, f"{username}_settings.conf")
        return config_file  
        
    def setup_ui(self):
        uic_path = os.path.join(os.path.dirname(__file__), '..', 'ui', 'settings.ui')
        self.ui = uic.loadUi(uic_path, self)
        self.ui.save_button.clicked.connect(self.save_settings)
        self.ui.cancel_button.clicked.connect(self.close)
        self.ui.set_player_button.clicked.connect(self.set_external_player)
        self.ui.set_root_button.clicked.connect(self.set_root)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)



if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    window = LocalAssetBrowserSettings()
    window.show()
    sys.exit(app.exec_())
import os
import sys
import json
import time
import shutil
import logging
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- LOGGING SETUP ---
# This creates a log file in your main user folder (e.g., C:\Users\kodur\FileOrganizer.log)
LOG_FILE = os.path.join(os.path.expanduser('~'), 'FileOrganizer.log')
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    force=True
)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller. """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- CONFIGURATION AND SETUP ---
DOWNLOADS_PATH = os.path.join(os.path.expanduser('~'), 'Downloads')
CONFIG_FILE = resource_path('config.json')
HISTORY_FILE = os.path.join(os.path.expanduser('~'), 'FileOrganizer_history.json')
PROCESSED_FILES = set()

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'w') as f: json.dump([], f)
    with open(HISTORY_FILE, 'r') as f:
        return json.load(f)

def save_history(record):
    history = load_history()
    history.append(record)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def get_file_type(filename, config):
    file_ext = os.path.splitext(filename)[1].lower()
    for f_type, extensions in config['file_types'].items():
        if file_ext in extensions:
            return f_type
    return 'Others'

def is_file_stable(filepath, wait_seconds=2):
    try:
        initial_size = os.path.getsize(filepath)
        time.sleep(wait_seconds)
        final_size = os.path.getsize(filepath)
        return initial_size == final_size and final_size > 0
    except (OSError, FileNotFoundError):
        return False

class DownloadHandler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config

    def on_created(self, event):
        if not event.is_directory: self._process_file(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            PROCESSED_FILES.add(event.src_path)
            self._process_file(event.dest_path)

    def _process_file(self, filepath):
        try:
            if filepath in PROCESSED_FILES: return
            filename = os.path.basename(filepath)
            if filename.startswith('.') or filename.endswith(('.tmp', '.crdownload')): return
            if not os.path.exists(filepath): return
            
            logging.info(f"File event detected for: {filename}")
            PROCESSED_FILES.add(filepath)

            while not is_file_stable(filepath):
                logging.info(f"Waiting for {filename} to be fully downloaded...")
                time.sleep(2)
            logging.info(f"{filename} is now stable.")

            file_type = get_file_type(filename, self.config)
            type_folder_name = self.config['folder_paths'].get(file_type, 'Others')
            destination_folder = os.path.join(DOWNLOADS_PATH, type_folder_name)
            os.makedirs(destination_folder, exist_ok=True)
            destination_path = os.path.join(destination_folder, filename)

            counter = 1
            base, ext = os.path.splitext(filename)
            while os.path.exists(destination_path):
                destination_path = os.path.join(destination_folder, f"{base}_{counter}{ext}")
                counter += 1
            
            shutil.move(filepath, destination_path)
            PROCESSED_FILES.add(destination_path)
            logging.info(f"Moved '{filename}' to '{os.path.relpath(destination_path, DOWNLOADS_PATH)}'")
            
            history_record = {
                "file": filename, "type": file_type, "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "destination": os.path.relpath(destination_path, DOWNLOADS_PATH)
            }
            save_history(history_record)
        except Exception as e:
            logging.error(f"Error processing {filename}: {e}", exc_info=True)

def main_logic():
    """Contains the main application logic."""
    logging.info("--- Program Start ---")
    
    config = load_config()
    logging.info("Configuration loaded.")

    logging.info("Scanning for existing files...")
    temp_handler = DownloadHandler(config)
    for filename in os.listdir(DOWNLOADS_PATH):
        filepath = os.path.join(DOWNLOADS_PATH, filename)
        if os.path.isfile(filepath):
            temp_handler._process_file(filepath)
    logging.info("Finished scanning.")
    
    event_handler = DownloadHandler(config)
    observer = Observer()
    observer.schedule(event_handler, DOWNLOADS_PATH, recursive=False)
    observer.start()
    logging.info(f"--- Monitoring folder: {DOWNLOADS_PATH} ---")

    try:
        while True:
            time.sleep(3600) # Sleep for a long time
    except KeyboardInterrupt:
        observer.stop()
        logging.info("Observer stopped by user.")
    observer.join()

if __name__ == "__main__":
    # This top-level try-except will catch ANY crash during startup and log it.
    try:
        main_logic()
    except Exception as e:
        logging.critical(f"A FATAL error occurred during startup: {e}", exc_info=True)
        sys.exit(1)
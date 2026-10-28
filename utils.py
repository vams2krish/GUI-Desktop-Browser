import logging
import re
import os
import platform
import subprocess

def setup_logging():
    """Setup logging to console and file."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('browser.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def clean_filename(title):
    """Clean title for safe filename (Windows-compatible)."""
    # Replace invalid chars
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
    # Strip spaces/dots
    cleaned = cleaned.strip(' .')
    # Ensure non-empty
    if not cleaned:
        cleaned = "Unknown_Video"
    # Limit length
    if len(cleaned) > 200:
        cleaned = cleaned[:200].rstrip()
    return cleaned

def open_folder(path):
    """Open folder in system file manager."""
    try:
        if platform.system() == "Windows":
            subprocess.run(["explorer", path], check=True)
        elif platform.system() == "Darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
    except subprocess.CalledProcessError:
        logging.warning(f"Could not open folder: {path}")


import sys
import json
import os
import re
import time
from datetime import datetime
import ffmpeg
import shutil
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QTabWidget, QCheckBox, QListWidget, QListWidgetItem,
    QLabel, QSplitter, QGroupBox, QProgressBar, QMessageBox,
    QStatusBar, QToolBar, QMenuBar, QMenu, QInputDialog, QFileDialog,
    QSlider, QComboBox, QSpinBox, QDockWidget, QTextEdit, QScrollArea,
    QFrame, QSizePolicy, QGridLayout, QToolButton,
    QStyleFactory, QColorDialog, QFontDialog, QKeySequenceEdit
)
from PyQt6.QtCore import (
    QUrl, QTimer, Qt, QThread, pyqtSignal, QSettings, QSize, QPoint,
    QRect, pyqtSlot, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
)
from PyQt6.QtGui import (
    QFont, QIcon, QAction, QKeySequence, QPalette, QColor, QPainter,
    QPixmap, QShortcut, QMouseEvent, QWheelEvent
)
from browser_tab import BrowserTab
import utils
from utils import setup_logging, clean_filename, open_folder
utils.setup_logging()


class DownloadThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, str)  # filename, status
    error = pyqtSignal(str)
    
    def __init__(self, video_url, title):
        super().__init__()
        self.video_url = video_url
        self.title = title
        self.filename = None
    
    def run(self):
        try:
            import os
            import requests
            import re
            import yt_dlp
            import streamlink
            from urllib.parse import urlparse
            
            # Create downloads directory
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "BrowserDownloads")
            os.makedirs(downloads_dir, exist_ok=True)
            
            # Clean filename using the same method as main window
            safe_title = self.clean_filename(self.title)
            
            # Configure yt-dlp options with enhanced support for adult sites
            ydl_opts = {
                'outtmpl': os.path.join(downloads_dir, f'{safe_title}.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'noplaylist': True,
                'no_warnings': True,
                'progress_hooks': [self._yt_dlp_progress_hook],
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'extractor_args': {
                    'generic': {
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                        }
                    }
                }
            }
            
            # Try Streamlink first for live streams and supported sites
            try:
                streams = streamlink.streams(self.video_url)
                if streams:
                    # Get the best quality stream
                    stream_name = sorted(streams.keys(), reverse=True)[0]  # Get highest quality
                    stream = streams[stream_name]
                    
                    # Determine file extension
                    if stream_name.endswith('mp4'):
                        ext = 'mp4'
                    elif stream_name.endswith('webm'):
                        ext = 'webm'
                    elif stream_name.endswith('flv'):
                        ext = 'flv'
                    else:
                        ext = 'mp4'  # Default
                    
                    self.filename = os.path.join(downloads_dir, f"{safe_title}.{ext}")
                    
                    # Download with progress tracking
                    with open(self.filename, 'wb') as f:
                        total_size = 0
                        downloaded = 0
                        
                        # Stream the content
                        with stream.open() as stream_fd:
                            while True:
                                chunk = stream_fd.read(8192)
                                if not chunk:
                                    break
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # Emit progress (approximate since we don't know total size)
                                progress = min(95, int((downloaded / (1024 * 1024)) % 100))  # Rough estimate
                                self.progress.emit(progress)
                    
                    self.progress.emit(100)
                    self.finished.emit(self.filename, "Completed (Streamlink)")
                    return
            except Exception:
                # Streamlink failed, continue to yt-dlp
                pass
            
            # Try yt-dlp second
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.video_url, download=True)
                    self.filename = ydl.prepare_filename(info)
                self.finished.emit(self.filename, "Completed (yt-dlp)")
                return
            except yt_dlp.DownloadError:
                # Fall back to direct download
                pass
            
            # Direct download fallback
            if not safe_title.lower().endswith(('.mp4', '.webm', '.avi', '.mov', '.mkv')):
                safe_title += '.mp4'
            
            self.filename = os.path.join(downloads_dir, safe_title)
            
            # Download with progress
            response = requests.get(self.video_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(self.filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.progress.emit(progress)
            
            self.finished.emit(self.filename, "Completed")
            
        except Exception as e:
            self.error.emit(f"Download failed: {str(e)}")
    
    def _yt_dlp_progress_hook(self, d):
        """Progress hook for yt-dlp downloads"""
        if d['status'] == 'downloading':
            if 'total_bytes' in d and d['total_bytes'] > 0:
                progress = int((d['downloaded_bytes'] / d['total_bytes']) * 100)
                self.progress.emit(progress)
        elif d['status'] == 'finished':
            self.progress.emit(100)

    def clean_filename(self, title):
        """Clean title for filename while preserving as much as possible"""
        import re
        import os
        
        # Remove or replace characters that are invalid in filenames
        # Windows invalid characters: < > : " / \ | ? *
        # Also remove control characters
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
        
        # Remove leading/trailing spaces and dots
        cleaned = cleaned.strip(' .')
        
        # Ensure filename is not empty
        if not cleaned:
            cleaned = "Unknown_Video"
        
        # Limit length to avoid filesystem issues (255 chars for most systems)
        if len(cleaned) > 200:
            cleaned = cleaned[:200].rstrip()
        
        return cleaned

class SimpleBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Private Browser")
        self.resize(1400, 900)
        
        # Video and download management
        self.detected_videos = []
        self.download_threads = {}
        self.download_items = {}

        # Create main splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Create left panel for browser
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Create tab container with custom layout
        self.tab_container = QWidget()
        self.tab_layout = QHBoxLayout(self.tab_container)
        self.tab_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.sync_url_bar)

        # Add + button right after tabs (like Chrome)
        self.new_tab_btn = QPushButton("+")
        self.new_tab_btn.setFixedSize(30, 25)
        self.new_tab_btn.clicked.connect(self.add_new_tab)
        self.new_tab_btn.setToolTip("New Tab")
        self.new_tab_btn.setStyleSheet("""
            QPushButton {
                border: 1px solid #ccc;
                border-radius: 3px;
                background: #f0f0f0;
                margin: 2px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)

        self.tab_layout.addWidget(self.tabs)
        self.tab_layout.addWidget(self.new_tab_btn)

        # Navigation controls
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("https://www.google.com")
        self.url_bar.returnPressed.connect(self.navigate)

        back_btn = QPushButton("←")
        back_btn.clicked.connect(lambda: self.current_tab().back() if self.current_tab() else None)

        fwd_btn = QPushButton("→")
        fwd_btn.clicked.connect(lambda: self.current_tab().forward() if self.current_tab() else None)

        reload_btn = QPushButton("↻")
        reload_btn.clicked.connect(lambda: self.current_tab().reload() if self.current_tab() else None)

        go_btn = QPushButton("Go")
        go_btn.clicked.connect(self.navigate)

        self.video_reorder_cb = QCheckBox("Auto-move playing video tabs to front")
        self.video_reorder_cb.setChecked(True)  # Enable by default
        self.video_reorder_cb.toggled.connect(self.on_video_reorder_toggled)

        self.reorder_timer = QTimer(self)
        self.reorder_timer.setInterval(5000)
        self.reorder_timer.timeout.connect(self.check_video_activity)

        top_layout = QHBoxLayout()
        top_layout.addWidget(back_btn)
        top_layout.addWidget(fwd_btn)
        top_layout.addWidget(reload_btn)
        top_layout.addWidget(self.url_bar, stretch=1)
        top_layout.addWidget(go_btn)
        top_layout.addSpacing(16)
        top_layout.addWidget(self.video_reorder_cb)

        left_layout.addLayout(top_layout)
        left_layout.addWidget(self.tab_container)
        
        # Create right panel for downloads
        right_panel = self.create_download_panel()
        
        # Add panels to splitter
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([1000, 400])  # Set initial sizes
        
        # Set as central widget
        self.setCentralWidget(main_splitter)

        # Add initial tab
        self.add_new_tab("https://www.google.com", "Google")

        # Start the reorder timer since it's enabled by default
        self.reorder_timer.start()

    def create_download_panel(self):
        """Create the download panel with video detection and download management"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Video detection section
        video_group = QGroupBox("Video Downloads")
        video_layout = QVBoxLayout(video_group)
        
        # Manual URL input section
        manual_url_layout = QHBoxLayout()
        self.manual_url_input = QLineEdit()
        self.manual_url_input.setPlaceholderText("Enter video URL (YouTube, direct link, etc.)")
        manual_download_btn = QPushButton("Download")
        manual_download_btn.clicked.connect(self.download_manual_url)
        manual_url_layout.addWidget(self.manual_url_input)
        manual_url_layout.addWidget(manual_download_btn)
        video_layout.addLayout(manual_url_layout)
        
        # Detected videos list
        detected_label = QLabel("Detected Videos:")
        video_layout.addWidget(detected_label)
        
        self.video_list = QListWidget()
        self.video_list.setMaximumHeight(150)
        video_layout.addWidget(self.video_list)
        
        # Download buttons for detected videos
        buttons_layout = QHBoxLayout()
        download_btn = QPushButton("Download Selected Video")
        download_btn.clicked.connect(self.download_selected_video)
        clear_videos_btn = QPushButton("Clear Videos")
        clear_videos_btn.clicked.connect(self.clear_detected_videos)
        buttons_layout.addWidget(download_btn)
        buttons_layout.addWidget(clear_videos_btn)
        video_layout.addLayout(buttons_layout)
        
        auto_download_cb = QCheckBox("Auto-download detected videos")
        auto_download_cb.toggled.connect(self.toggle_auto_download)
        video_layout.addWidget(auto_download_cb)
        
        # Active downloads section
        downloads_group = QGroupBox("Active Downloads")
        downloads_layout = QVBoxLayout(downloads_group)
        
        self.downloads_list = QListWidget()
        downloads_layout.addWidget(self.downloads_list)
        
        clear_btn = QPushButton("Clear Completed")
        clear_btn.clicked.connect(self.clear_completed_downloads)
        downloads_layout.addWidget(clear_btn)
        
        layout.addWidget(video_group)
        layout.addWidget(downloads_group)
        
        return panel

    def current_tab(self) -> BrowserTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, BrowserTab) else None

    def add_new_tab(self, url="about:blank", title="New Tab"):
        tab = BrowserTab()
        tab.titleChanged.connect(lambda t: self.tabs.setTabText(self.tabs.indexOf(tab), t[:40] or "Untitled"))
        tab.urlChanged.connect(self.sync_url_bar)
        tab.loadFinished.connect(lambda ok: self.sync_url_bar())
        tab.video_detected.connect(self.on_video_detected)

        idx = self.tabs.addTab(tab, title)
        self.tabs.setCurrentIndex(idx)

        if url and url != "about:blank":
            if isinstance(url, QUrl):
                tab.load(url)
            else:
                tab.load_url(url)

        return tab

    def on_video_detected(self, video_url, title):
        """Handle video detection from tabs"""
        video_info = f"{title[:30]}..." if len(title) > 30 else title
        item = QListWidgetItem(f"🎥 {video_info}")
        item.setData(Qt.ItemDataRole.UserRole, {"url": video_url, "title": title})
        self.video_list.addItem(item)

    def download_selected_video(self):
        """Download selected video from the list"""
        current_item = self.video_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a video to download.")
            return
        
        video_data = current_item.data(Qt.ItemDataRole.UserRole)
        # Get the real video title before downloading
        self.get_video_title_and_download(video_data["url"])

    def download_manual_url(self):
        """Download video from manually entered URL"""
        url = self.manual_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a video URL.")
            return
        
        # Validate URL format
        if not (url.startswith(("http://", "https://"))):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid URL starting with http:// or https://")
            return
        
        # Clear the input field
        self.manual_url_input.clear()
        
        # Get the real video title before downloading
        self.get_video_title_and_download(url)

    def get_video_title_and_download(self, url):
        """Get real video title using yt-dlp before downloading"""
        try:
            import yt_dlp
            
            # Configure yt-dlp with enhanced options for adult sites
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'extractor_args': {
                    'generic': {
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                            'Accept-Language': 'en-US,en;q=0.5',
                            'Accept-Encoding': 'gzip, deflate',
                            'Connection': 'keep-alive',
                            'Upgrade-Insecure-Requests': '1',
                        }
                    }
                }
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    # Extract video info to get real title
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Unknown Video')
                    
                    # If title is still generic, try alternative methods
                    if not title or title in ['Unknown Video', 'Video', 'Untitled']:
                        title = self.extract_title_from_url(url)
                    
                    # Clean title for filename - preserve as much as possible
                    title = self.clean_filename(title)
                    
                    # Start download with real title
                    self.start_download(url, title)
                    
                except Exception as e:
                    # If we can't get the title, try alternative methods
                    print(f"Could not get video title with yt-dlp: {e}")
                    title = self.extract_title_from_url(url)
                    title = self.clean_filename(title)
                    self.start_download(url, title)
                    
        except ImportError:
            # If yt-dlp is not available, try alternative methods
            title = self.extract_title_from_url(url)
            title = self.clean_filename(title)
            self.start_download(url, title)
        except Exception as e:
            # If anything else goes wrong, try alternative methods
            print(f"Error getting video title: {e}")
            title = self.extract_title_from_url(url)
            title = self.clean_filename(title)
            self.start_download(url, title)

    def extract_title_from_url(self, url):
        """Extract title from URL or generate a descriptive one"""
        import re
        from urllib.parse import urlparse, unquote
        
        try:
            # Try to get title from URL path
            parsed = urlparse(url)
            path = unquote(parsed.path)
            
            # Extract filename from path
            if path:
                filename = path.split('/')[-1]
                if filename and '.' in filename:
                    # Remove extension
                    title = filename.rsplit('.', 1)[0]
                    # Replace common separators with spaces
                    title = re.sub(r'[-_]', ' ', title)
                    # Clean up multiple spaces
                    title = re.sub(r'\s+', ' ', title).strip()
                    if title and len(title) > 2:
                        return title.title()
            
            # Try to extract from domain and path
            domain = parsed.netloc.replace('www.', '')
            if domain:
                # Create a descriptive title based on domain
                if 'xnxx' in domain:
                    return f"XNXX_Video_{path.split('/')[-1].split('.')[0] if path.split('/')[-1] else 'Video'}"
                elif 'xvideos' in domain:
                    return f"XVideos_Video_{path.split('/')[-1].split('.')[0] if path.split('/')[-1] else 'Video'}"
                elif 'pornhub' in domain:
                    return f"PornHub_Video_{path.split('/')[-1].split('.')[0] if path.split('/')[-1] else 'Video'}"
                elif 'youporn' in domain:
                    return f"YouPorn_Video_{path.split('/')[-1].split('.')[0] if path.split('/')[-1] else 'Video'}"
                elif 'redtube' in domain:
                    return f"RedTube_Video_{path.split('/')[-1].split('.')[0] if path.split('/')[-1] else 'Video'}"
                else:
                    # Generic title based on domain
                    site_name = domain.split('.')[0].title()
                    video_id = path.split('/')[-1].split('.')[0] if path.split('/')[-1] else 'Video'
                    return f"{site_name}_Video_{video_id}"
            
            return "Adult_Video"
            
        except Exception:
            return "Adult_Video"

    def clean_filename(self, title):
        """Clean title for filename while preserving as much as possible"""
        import re
        import os
        
        # Remove or replace characters that are invalid in filenames
        # Windows invalid characters: < > : " / \ | ? *
        # Also remove control characters
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
        
        # Remove leading/trailing spaces and dots
        cleaned = cleaned.strip(' .')
        
        # Ensure filename is not empty
        if not cleaned:
            cleaned = "Unknown_Video"
        
        # Limit length to avoid filesystem issues (255 chars for most systems)
        if len(cleaned) > 200:
            cleaned = cleaned[:200].rstrip()
        
        return cleaned

    def start_download(self, video_url, title):
        """Start downloading a video"""
        # Create download thread
        download_thread = DownloadThread(video_url, title)
        download_id = f"{video_url}_{title}"
        
        self.download_threads[download_id] = download_thread
        
        # Create download item in list
        item = QListWidgetItem(f"⬇️ {title[:30]}...")
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        
        # Store items
        self.download_items[download_id] = {
            "item": item,
            "progress_bar": progress_bar,
            "thread": download_thread
        }
        
        self.downloads_list.addItem(item)
        
        # Connect signals
        download_thread.progress.connect(progress_bar.setValue)
        download_thread.finished.connect(lambda filename, status: self.on_download_finished(download_id, filename, status))
        download_thread.error.connect(lambda error: self.on_download_error(download_id, error))
        
        # Start download
        download_thread.start()

    def on_download_finished(self, download_id, filename, status):
        """Handle download completion"""
        if download_id in self.download_items:
            items = self.download_items[download_id]
            items["item"].setText(f"✅ {items['item'].text()[2:]} {status}")
            
            # Open downloads folder when download is complete
            self.open_downloads_folder(filename)
            
            # Clean up
            if download_id in self.download_threads:
                del self.download_threads[download_id]

    def on_download_error(self, download_id, error):
        """Handle download error"""
        if download_id in self.download_items:
            items = self.download_items[download_id]
            items["item"].setText(f"❌ {items['item'].text()[2:]} Error")
            
            QMessageBox.warning(self, "Download Error", error)
            
            # Clean up
            if download_id in self.download_threads:
                del self.download_threads[download_id]

    def open_downloads_folder(self, filename):
        """Open the downloads folder in the system file manager"""
        try:
            import os
            import subprocess
            import platform
            
            # Get the directory containing the downloaded file
            downloads_dir = os.path.dirname(filename)
            
            # Platform-specific command to open folder
            if platform.system() == "Windows":
                # On Windows, use explorer
                subprocess.run(["explorer", downloads_dir])
            elif platform.system() == "Darwin":  # macOS
                # On macOS, use open
                subprocess.run(["open", downloads_dir])
            else:  # Linux and other Unix-like systems
                # On Linux, use xdg-open
                subprocess.run(["xdg-open", downloads_dir])
                
        except Exception as e:
            # If opening folder fails, show error but don't crash
            print(f"Could not open downloads folder: {str(e)}")

    def toggle_auto_download(self, checked):
        """Toggle automatic video downloading"""
        if checked:
            QMessageBox.information(self, "Auto Download", "Automatic downloading enabled. Videos will be downloaded as they are detected.")

    def clear_detected_videos(self):
        """Clear all detected videos from the list"""
        self.video_list.clear()

    def clear_completed_downloads(self):
        """Clear completed downloads from list"""
        items_to_remove = []
        for i in range(self.downloads_list.count()):
            item = self.downloads_list.item(i)
            if item.text().startswith("✅") or item.text().startswith("❌"):
                items_to_remove.append(item)
        
        for item in items_to_remove:
            row = self.downloads_list.row(item)
            self.downloads_list.takeItem(row)

    def close_tab(self, index: int):
        if self.tabs.count() > 1:
            widget = self.tabs.widget(index)
            widget.deleteLater()
            self.tabs.removeTab(index)

    def navigate(self):
        text = self.url_bar.text().strip()
        if not text:
            return
        if " " in text or "." not in text:
            query = text.replace(" ", "+")
            url = f"https://www.google.com/search?q={query}"
        else:
            url = text
        self.current_tab().load_url(url) if self.current_tab() else None

    def sync_url_bar(self):
        tab = self.current_tab()
        if tab:
            self.url_bar.setText(tab.url().toString())
            self.url_bar.selectAll()

    def check_video_activity(self):
        """Check for video activity in tabs and reorder if necessary"""
        if not self.video_reorder_cb.isChecked():
            return
            
        active_indices = []
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, BrowserTab):
                # Check if tab has playing video by running JavaScript
                tab.page().runJavaScript("""
                    var videos = document.querySelectorAll('video');
                    var hasPlayingVideo = false;
                    videos.forEach(function(video) {
                        if (!video.paused && !video.ended && video.readyState > 2) {
                            hasPlayingVideo = true;
                        }
                    });
                    hasPlayingVideo;
                """, lambda result, idx=i: self._handle_video_check_result(idx, result, active_indices))
    
    def _handle_video_check_result(self, tab_index: int, has_video: bool, active_indices: list):
        """Handle the result of video check for a specific tab"""
        if has_video:
            active_indices.append(tab_index)
        
        # Check if this was the last tab to check
        if len(active_indices) > 0 and tab_index == self.tabs.count() - 1:
            self.reorder_tabs(active_indices)
    
    def on_video_reorder_toggled(self, checked: bool):
        """Toggle the video reordering timer"""
        if checked:
            self.reorder_timer.start()
        else:
            self.reorder_timer.stop()

    def reorder_tabs(self, active_indices: list[int]):
        """Reorder tabs to move video-playing tabs to the front"""
        if not active_indices:
            return
            
        # Move active tabs to the front in order
        for i, idx in enumerate(sorted(active_indices)):
            if idx != i:  # Only move if not already in position
                tab = self.tabs.widget(idx)
                title = self.tabs.tabText(idx)
                icon = self.tabs.tabIcon(idx)
                tooltip = self.tabs.tabToolTip(idx)
                
                self.tabs.removeTab(idx)
                self.tabs.insertTab(i, tab, icon, title)
                self.tabs.setTabToolTip(i, tooltip)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SimpleBrowser()
    window.show()
    sys.exit(app.exec())

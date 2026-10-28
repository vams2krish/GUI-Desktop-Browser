# browser_tab.py
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtCore import QUrl, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QMenu, QApplication, QMessageBox, QPushButton, QHBoxLayout, QWidget
from PyQt6.QtGui import QAction
import os
import requests
import re
import yt_dlp
import streamlink
import ffmpeg
import subprocess
import tempfile
from urllib.parse import urlparse


class BrowserPage(QWebEnginePage):
    """Custom page to help handle navigation & context menu"""
    def __init__(self, profile=None, parent=None):
        super().__init__(profile, parent)

    def createWindow(self, window_type):
        # Called when Qt wants to open new window/tab (target=_blank, middle-click, etc.)
        if window_type in (QWebEnginePage.WebWindowType.WebBrowserTab,
                           QWebEnginePage.WebWindowType.WebBrowserWindow,
                           QWebEnginePage.WebWindowType.WebBrowserBackgroundTab):
            # Create a new page for the new tab
            new_page = BrowserPage(self.profile(), self.parent())
            return new_page
        return super().createWindow(window_type)


class BrowserTab(QWebEngineView):
    video_detected = pyqtSignal(str, str)  # url, title
    
    def __init__(self, parent=None):
        super().__init__(parent)
        settings = self.settings()
        
        # Enable all necessary features for video playback
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(settings.WebAttribute.PdfViewerEnabled, True)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(settings.WebAttribute.DnsPrefetchEnabled, True)
        settings.setAttribute(settings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
        
        # Enable autoplay and media playback
        settings.setAttribute(settings.WebAttribute.PlaybackRequiresUserGesture, False)
        
        # Set user agent through profile (more reliable method)
        profile = self.page().profile()
        profile.setHttpUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Enable hardware acceleration
        settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
        
        # Allow mixed content (HTTP/HTTPS)
        settings.setAttribute(settings.WebAttribute.AllowRunningInsecureContent, True)
        
        # Enable WebRTC for video streaming
        settings.setAttribute(settings.WebAttribute.WebRTCPublicInterfacesOnly, False)

        # Use our custom page
        self.setPage(BrowserPage(self.page().profile(), self))
        
        # Video detection timer
        self.video_detection_timer = QTimer()
        self.video_detection_timer.setInterval(3000)  # Check every 3 seconds
        self.video_detection_timer.timeout.connect(self.detect_videos)
        self.video_detection_timer.start()
        
        # Store detected videos
        self.detected_videos = []

    def load_url(self, url_str: str):
        if not url_str.strip():
            return
        if not url_str.startswith(("http://", "https://")):
            url_str = "https://" + url_str
        self.load(QUrl(url_str))

    def createWindow(self, window_type):
        # This is called from the page → tell the main window to create new tab
        if window_type in (QWebEnginePage.WebWindowType.WebBrowserTab,
                           QWebEnginePage.WebWindowType.WebBrowserBackgroundTab):
            # Signal or direct call - here we return self so navigation happens in new tab
            # But to create *new* tab, we need access to main window → so we override minimally
            main_window = self.window()
            if hasattr(main_window, 'add_new_tab'):
                # We'll let main window create the tab, but for simplicity return None
                # and handle via context / middle click separately
                pass
        return None  # Let default behavior for other types

    def contextMenuEvent(self, event):
        # Use the built-in contextMenuEvent method which provides the context menu data
        super().contextMenuEvent(event)

    def open_link_in_new_tab(self, url: QUrl, background=False):
        main_window = self.window()
        if hasattr(main_window, 'add_new_tab'):
            tab = main_window.add_new_tab(url.toString(), "Loading...")
            if not background:
                main_window.tabs.setCurrentWidget(tab)
    
    def detect_videos(self):
        """Detect videos on the current page"""
        js_code = """
        (function() {
            var videos = [];
            var videoElements = document.querySelectorAll('video');
            var sources = document.querySelectorAll('source[type^="video/"]');
            
            // Check video elements
            videoElements.forEach(function(video, index) {
                if (video.src && !video.src.startsWith('blob:')) {
                    videos.push({
                        url: video.src,
                        title: document.title || 'Video ' + (index + 1),
                        playing: !video.paused && !video.ended
                    });
                }
                // Check source elements within video
                var videoSources = video.querySelectorAll('source');
                videoSources.forEach(function(source) {
                    if (source.src && !source.src.startsWith('blob:')) {
                        videos.push({
                            url: source.src,
                            title: document.title || 'Video ' + (index + 1),
                            playing: !video.paused && !video.ended
                        });
                    }
                });
                
                // Try to get current time and duration for context
                if (video.duration && !isNaN(video.duration)) {
                    var timeInfo = ' (' + Math.floor(video.currentTime) + 's/' + Math.floor(video.duration) + 's)';
                    if (videos.length > 0) {
                        videos[videos.length - 1].title += timeInfo;
                    }
                }
            });
            
            // Check standalone source elements
            sources.forEach(function(source, index) {
                if (source.src && !source.src.startsWith('blob:')) {
                    videos.push({
                        url: source.src,
                        title: document.title || 'Media ' + (index + 1),
                        playing: false
                    });
                }
            });
            
            // Also check for YouTube iframes
            var iframes = document.querySelectorAll('iframe[src*="youtube.com"], iframe[src*="youtu.be"]');
            iframes.forEach(function(iframe, index) {
                var videoId = null;
                var src = iframe.src;
                
                // Extract YouTube video ID
                var match = src.match(/(?:youtube\\.com\\/watch\\?v=|youtu\\.be\\/|youtube\\.com\\/embed\\/)([^&\\n?#]+)/);
                if (match && match[1]) {
                    videoId = match[1];
                    videos.push({
                        url: 'https://www.youtube.com/watch?v=' + videoId,
                        title: document.title || 'YouTube Video ' + (index + 1),
                        playing: false,
                        type: 'youtube'
                    });
                }
            });
            
            // Check for streaming platforms by looking at current URL
            var currentUrl = window.location.href;
            var streamingSites = ['twitch.tv', 'vimeo.com', 'dailymotion.com', 'facebook.com/watch', 'instagram.com', 'tiktok.com', 'twitter.com', 'youtube.com', 'youtu.be', 'kick.com', 'rumble.com'];
            var isStreamingSite = streamingSites.some(function(site) { return currentUrl.includes(site); });
            
            // Also check for live stream indicators on page
            var hasLiveIndicator = document.querySelector('.live, [data-live="true"], .is-live, .streaming, .broadcasting') !== null;
            
            if ((isStreamingSite || hasLiveIndicator) && videos.length === 0) {
                videos.push({
                    url: currentUrl,
                    title: document.title || 'Live Stream',
                    playing: true,
                    type: 'stream'
                });
            }
            
            // Check for embedded video players and iframes
            var embeds = document.querySelectorAll('iframe[src*="player"], iframe[src*="embed"], iframe[src*="stream"]');
            embeds.forEach(function(embed, index) {
                if (embed.src && !embed.src.startsWith('blob:') && !embed.src.includes('google.com')) {
                    videos.push({
                        url: embed.src,
                        title: document.title || 'Embedded Video ' + (index + 1),
                        playing: false,
                        type: 'embed'
                    });
                }
            });
            
            return videos;
        })();
        """
        
        self.page().runJavaScript(js_code, self._handle_video_detection)
    
    def _handle_video_detection(self, videos):
        """Handle detected videos"""
        if videos and len(videos) > 0:
            for video in videos:
                if video['url'] not in [v['url'] for v in self.detected_videos]:
                    self.detected_videos.append(video)
                    self.video_detected.emit(video['url'], video['title'])
    
    def download_video(self, video_url, title="video"):
        """Download video from URL using yt-dlp for better streaming support"""
        try:
            # Create downloads directory if it doesn't exist
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "BrowserDownloads")
            os.makedirs(downloads_dir, exist_ok=True)
            
            # Clean filename
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
            
            # Configure yt-dlp options
            ydl_opts = {
                'outtmpl': os.path.join(downloads_dir, f'{safe_title}.%(ext)s'),
                'format': 'best[ext=mp4]/best',  # Prefer MP4, fallback to best quality
                'noplaylist': True,  # Download single video only
                'quiet': True,
                'no_warnings': True,
            }
            
            # Try to download with yt-dlp first
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    filename = ydl.prepare_filename(info)
                return filename
            except yt_dlp.DownloadError:
                # If yt-dlp fails, fall back to direct download
                if not safe_title.lower().endswith(('.mp4', '.webm', '.avi', '.mov', '.mkv')):
                    safe_title += '.mp4'
                
                filename = os.path.join(downloads_dir, safe_title)
                
                # Get video content
                response = requests.get(video_url, stream=True)
                response.raise_for_status()
                
                # Save file
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                return filename
                
        except Exception as e:
            raise Exception(f"Download failed: {str(e)}")
    
    def get_detected_videos(self):
        """Get list of detected videos"""
        return self.detected_videos.copy()
    
    def enhance_video_with_ffmpeg(self, input_file, output_file=None):
        """Enhance video using FFmpeg for better codec support"""
        try:
            if output_file is None:
                base_name = os.path.splitext(input_file)[0]
                output_file = f"{base_name}_enhanced.mp4"
            
            # Use FFmpeg to convert to standard format with better codecs
            (
                ffmpeg
                .input(input_file)
                .output(
                    output_file,
                    vcodec='libx264',      # H.264 video codec
                    acodec='aac',           # AAC audio codec
                    video_bitrate='2000k',    # Good quality video
                    audio_bitrate='192k',     # Good quality audio
                    preset='medium',          # Balance between speed and quality
                    movflags='faststart',     # Optimize for web playback
                    pix_fmt='yuv420p'       # Ensure compatibility
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            return output_file
            
        except Exception as e:
            print(f"FFmpeg enhancement failed: {e}")
            return input_file  # Return original if enhancement fails
    
    def extract_audio_with_ffmpeg(self, video_file, output_file=None):
        """Extract audio from video using FFmpeg"""
        try:
            if output_file is None:
                base_name = os.path.splitext(video_file)[0]
                output_file = f"{base_name}.mp3"
            
            # Extract audio using FFmpeg
            (
                ffmpeg
                .input(video_file)
                .output(
                    output_file,
                    acodec='mp3',           # MP3 audio codec
                    audio_bitrate='192k',      # Good quality audio
                    vn=None                    # No video output
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            return output_file
            
        except Exception as e:
            print(f"Audio extraction failed: {e}")
            return None
    
    def get_video_info_ffmpeg(self, video_file):
        """Get detailed video information using FFprobe"""
        try:
            # Use FFprobe to get video information
            probe = ffmpeg.probe(video_file)
            
            video_info = {}
            
            # Get video stream info
            for stream in probe['streams']:
                if stream['codec_type'] == 'video':
                    video_info.update({
                        'duration': float(stream.get('duration', 0)),
                        'width': stream.get('width'),
                        'height': stream.get('height'),
                        'fps': eval(stream.get('r_frame_rate', '0/1')),
                        'video_codec': stream.get('codec_name'),
                        'bitrate': stream.get('bit_rate')
                    })
                elif stream['codec_type'] == 'audio':
                    video_info.update({
                        'audio_codec': stream.get('codec_name'),
                        'sample_rate': stream.get('sample_rate'),
                        'channels': stream.get('channels'),
                        'audio_bitrate': stream.get('bit_rate')
                    })
            
            return video_info
            
        except Exception as e:
            print(f"Failed to get video info: {e}")
            return {}
    
    def check_ffmpeg_available(self):
        """Check if FFmpeg is available in the system"""
        try:
            # Try to run ffmpeg command
            result = subprocess.run(['ffmpeg', '-version'], 
                                capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

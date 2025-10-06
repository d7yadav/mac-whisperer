"""
Settings manager for Mac Whisperer
Handles configuration persistence and app context detection
"""
import json
import os
from pathlib import Path

try:
    from AppKit import NSWorkspace
    APP_DETECTION_AVAILABLE = True
except ImportError:
    APP_DETECTION_AVAILABLE = False


class SettingsManager:
    def __init__(self):
        self.config_dir = Path.home() / '.whisperer'
        self.config_file = self.config_dir / 'config.json'
        self.settings = self.load_settings()

    def load_settings(self):
        """Load settings from JSON file or return defaults"""
        defaults = {
            'use_llm': True,
            'use_clipboard': False,
            'model_name': 'small.en',
            'tone_preference': 'auto',  # 'auto', 'casual', 'professional', 'technical'
            'max_recording_time': 600,
            'ollama_api_url': 'http://localhost:11434/api/generate',  # Ollama API endpoint
            # Overlay settings
            'overlay_enabled': True,  # Enable visual overlay
            'overlay_position': 'bottom-right',  # 'top-left', 'top-right', 'bottom-left', 'bottom-right', 'center'
            'overlay_opacity': 0.95,  # 0.7 - 1.0
            'overlay_show_timer': True,
            'overlay_show_text_preview': True,
            'overlay_auto_hide_delay': 3.0,  # seconds, 0 = never auto-hide
            'overlay_font_size': 14,  # 10-20
            'overlay_stay_on_click': True,  # Keep overlay when clicked
            'overlay_show_copy_button': True,  # Show copy button on completion
            'overlay_show_stats': True,  # Show word/char count
            # Notification feedback (works on macOS)
            'use_audio_feedback': True,  # Play sounds for start/stop
            'use_menu_bar_feedback': True  # Update menu bar icon with status
        }

        if not self.config_file.exists():
            return defaults

        try:
            with open(self.config_file, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults to handle new settings
                return {**defaults, **loaded}
        except Exception as e:
            print(f"Error loading settings: {e}")
            return defaults

    def save_settings(self):
        """Save current settings to JSON file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get(self, key, default=None):
        """Get a setting value"""
        return self.settings.get(key, default)

    def set(self, key, value):
        """Set a setting value and save"""
        self.settings[key] = value
        self.save_settings()


def get_active_app_name():
    """Get the name of the currently active application"""
    if not APP_DETECTION_AVAILABLE:
        return None

    try:
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.activeApplication()
        return active_app.get('NSApplicationName', None)
    except Exception as e:
        print(f"Error detecting active app: {e}")
        return None


def get_tone_for_app(app_name, tone_preference='auto'):
    """
    Determine the appropriate tone based on the active application

    Args:
        app_name: Name of the active application
        tone_preference: User's tone preference ('auto', 'casual', 'professional', 'technical')

    Returns:
        str: Tone description for the LLM
    """
    if tone_preference != 'auto':
        tone_map = {
            'casual': 'casual and conversational with contractions',
            'professional': 'professional and formal',
            'technical': 'technical and precise'
        }
        return tone_map.get(tone_preference, 'neutral and professional')

    if not app_name:
        return 'neutral and professional'

    # Casual apps
    casual_apps = ['Slack', 'Messages', 'Discord', 'WhatsApp', 'Telegram', 'Signal', 'iMessage']
    if app_name in casual_apps:
        return 'casual and conversational with contractions'

    # Professional/Email apps
    professional_apps = ['Mail', 'Outlook', 'Gmail', 'Spark', 'Airmail']
    if app_name in professional_apps:
        return 'professional and formal with proper email etiquette'

    # Technical/Code apps
    technical_apps = ['Terminal', 'iTerm', 'iTerm2', 'Visual Studio Code', 'Code',
                      'Xcode', 'PyCharm', 'IntelliJ IDEA', 'Sublime Text', 'Atom',
                      'WebStorm', 'Android Studio']
    if app_name in technical_apps:
        return 'technical and precise, preserving code syntax and technical terms'

    # Document/Writing apps
    document_apps = ['Notion', 'Pages', 'Word', 'Google Docs', 'Bear', 'Obsidian',
                     'Ulysses', 'Scrivener', 'Evernote']
    if app_name in document_apps:
        return 'clear and structured for documentation'

    # Default
    return 'neutral and professional'


def get_app_context():
    """Get full context about the active app and recommended tone"""
    app_name = get_active_app_name()
    tone = get_tone_for_app(app_name)
    return {
        'app_name': app_name,
        'tone': tone
    }

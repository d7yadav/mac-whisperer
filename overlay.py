"""
Modern Visual Overlay for Mac Whisperer
Provides real-time feedback during recording, transcription, and processing
Inspired by Wispr Flow's clean, unobtrusive design
"""
import tkinter as tk
from tkinter import font
import threading
import time
from enum import Enum


class OverlayState(Enum):
    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class ModernOverlay:
    """
    A modern, semi-transparent overlay that provides visual feedback
    during speech-to-text operations.
    Runs in a separate thread to avoid conflicts with rumps event loop.
    """

    def __init__(self, settings=None):
        self.settings = settings
        self.window = None
        self.state = OverlayState.HIDDEN
        self.start_time = None
        self.timer_thread = None
        self.stop_timer = False
        self.tk_thread = None
        self.ready = False

        # Load settings
        self._load_settings()

        # Start Tkinter in a separate thread
        if self.enabled:
            self.tk_thread = threading.Thread(target=self._run_tk_loop, daemon=True)
            self.tk_thread.start()

            # Wait for window to be ready
            max_wait = 50  # 5 seconds max
            wait_count = 0
            while not self.ready and wait_count < max_wait:
                time.sleep(0.1)
                wait_count += 1

    def _load_settings(self):
        """Load overlay settings from settings manager"""
        if self.settings:
            self.enabled = self.settings.get('overlay_enabled', True)
            self.position = self.settings.get('overlay_position', 'bottom-right')
            self.opacity = self.settings.get('overlay_opacity', 0.95)
            self.show_timer = self.settings.get('overlay_show_timer', True)
            self.show_text_preview = self.settings.get('overlay_show_text_preview', True)
            self.auto_hide_delay = self.settings.get('overlay_auto_hide_delay', 3.0)
            self.font_size = self.settings.get('overlay_font_size', 14)
        else:
            # Defaults
            self.enabled = True
            self.position = 'bottom-right'
            self.opacity = 0.95
            self.show_timer = True
            self.show_text_preview = True
            self.auto_hide_delay = 3.0
            self.font_size = 14

    def _run_tk_loop(self):
        """Run Tkinter mainloop in separate thread"""
        self._init_window()
        if self.window:
            self.ready = True
            self.window.mainloop()

    def _init_window(self):
        """Initialize the overlay window (runs in Tk thread)"""
        if not self.enabled:
            return

        self.window = tk.Tk()
        self.window.withdraw()  # Start hidden

        # Window configuration
        self.window.overrideredirect(True)  # Remove window decorations
        self.window.attributes('-topmost', True)  # Always on top
        self.window.attributes('-alpha', self.opacity)  # Transparency

        # Try to make it appear above all windows (macOS specific)
        try:
            self.window.attributes('-transparentcolor', 'systemTransparent')
        except:
            pass

        # Main container with modern styling
        self.container = tk.Frame(
            self.window,
            bg='#1a1a1a',
            padx=20,
            pady=15,
            relief='flat',
            bd=0
        )
        self.container.pack(fill='both', expand=True)

        # Icon label (emoji/symbol)
        self.icon_font = font.Font(family='San Francisco', size=24, weight='bold')
        self.icon_label = tk.Label(
            self.container,
            text='',
            font=self.icon_font,
            bg='#1a1a1a',
            fg='white'
        )
        self.icon_label.pack(side='left', padx=(0, 12))

        # Text container
        text_container = tk.Frame(self.container, bg='#1a1a1a')
        text_container.pack(side='left', fill='both', expand=True)

        # Status label
        self.status_font = font.Font(family='San Francisco', size=self.font_size, weight='bold')
        self.status_label = tk.Label(
            text_container,
            text='',
            font=self.status_font,
            bg='#1a1a1a',
            fg='white',
            anchor='w'
        )
        self.status_label.pack(anchor='w')

        # Timer/detail label
        self.detail_font = font.Font(family='San Francisco', size=self.font_size - 2)
        self.detail_label = tk.Label(
            text_container,
            text='',
            font=self.detail_font,
            bg='#1a1a1a',
            fg='#999999',
            anchor='w'
        )
        self.detail_label.pack(anchor='w')

        # Text preview label (shown for COMPLETE state)
        self.preview_font = font.Font(family='San Francisco', size=self.font_size - 3)
        self.preview_label = tk.Label(
            self.container,
            text='',
            font=self.preview_font,
            bg='#1a1a1a',
            fg='#cccccc',
            anchor='w',
            justify='left',
            wraplength=400
        )

        # Position window
        self._position_window()

        # Add rounded corners effect (if supported)
        try:
            self.window.configure(bg='#1a1a1a')
        except:
            pass

    def _position_window(self):
        """Position the window based on settings"""
        if not self.window:
            return

        # Update window to get proper size
        self.window.update_idletasks()

        # Get window size
        width = self.window.winfo_reqwidth()
        height = self.window.winfo_reqheight()

        # Get screen size
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()

        # Calculate position based on preference
        margin = 40
        positions = {
            'top-left': (margin, margin),
            'top-right': (screen_width - width - margin, margin),
            'bottom-left': (margin, screen_height - height - margin - 100),
            'bottom-right': (screen_width - width - margin, screen_height - height - margin - 100),
            'center': ((screen_width - width) // 2, (screen_height - height) // 2)
        }

        x, y = positions.get(self.position, positions['bottom-right'])
        self.window.geometry(f'+{x}+{y}')

    def show_recording(self):
        """Show recording state (thread-safe)"""
        if not self.enabled or not self.window or not self.ready:
            return

        def _update_ui():
            self.state = OverlayState.RECORDING
            self.start_time = time.time()

            self.icon_label.config(text='🔴', fg='#ff3b30')
            self.status_label.config(text='Recording', fg='#ff3b30')
            self.detail_label.config(text='00:00')
            self.preview_label.pack_forget()

            self.window.deiconify()
            self._position_window()

            # Start timer thread
            if self.show_timer:
                self.stop_timer = False
                self.timer_thread = threading.Thread(target=self._update_timer, daemon=True)
                self.timer_thread.start()

        self.window.after(0, _update_ui)

    def _update_timer(self):
        """Update the timer display during recording (runs in background thread)"""
        while not self.stop_timer and self.state == OverlayState.RECORDING:
            elapsed = time.time() - self.start_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            time_text = f'{minutes:02d}:{seconds:02d}'

            try:
                # Schedule UI update on Tkinter thread
                self.window.after(0, lambda txt=time_text: self.detail_label.config(text=txt))
            except:
                break

            time.sleep(0.1)

    def show_transcribing(self):
        """Show transcribing state (thread-safe)"""
        if not self.enabled or not self.window or not self.ready:
            return

        def _update_ui():
            self.state = OverlayState.TRANSCRIBING
            self.stop_timer = True

            self.icon_label.config(text='⏳', fg='#ffcc00')
            self.status_label.config(text='Transcribing', fg='#ffcc00')

            if self.start_time:
                elapsed = time.time() - self.start_time
                self.detail_label.config(text=f'Recorded {elapsed:.1f}s')
            else:
                self.detail_label.config(text='Processing audio...')

            self._position_window()

        self.window.after(0, _update_ui)

    def show_processing(self):
        """Show processing state - LLM formatting (thread-safe)"""
        if not self.enabled or not self.window or not self.ready:
            return

        def _update_ui():
            self.state = OverlayState.PROCESSING

            self.icon_label.config(text='✨', fg='#5856d6')
            self.status_label.config(text='Processing', fg='#5856d6')
            self.detail_label.config(text='Improving grammar...')

            self._position_window()

        self.window.after(0, _update_ui)

    def show_complete(self, text=None):
        """Show completion state with optional text preview (thread-safe)"""
        if not self.enabled or not self.window or not self.ready:
            return

        def _update_ui():
            self.state = OverlayState.COMPLETE

            self.icon_label.config(text='✓', fg='#34c759')
            self.status_label.config(text='Complete', fg='#34c759')
            self.detail_label.config(text='Text ready!')

            # Show text preview if enabled and text provided
            if self.show_text_preview and text:
                preview = text[:150] + '...' if len(text) > 150 else text
                self.preview_label.config(text=preview)
                self.preview_label.pack(pady=(10, 0))

            self._position_window()

            # Auto-hide after delay
            threading.Thread(
                target=self._auto_hide,
                args=(self.auto_hide_delay,),
                daemon=True
            ).start()

        self.window.after(0, _update_ui)

    def show_error(self, message='Error occurred'):
        """Show error state (thread-safe)"""
        if not self.enabled or not self.window or not self.ready:
            return

        def _update_ui():
            self.state = OverlayState.ERROR
            self.stop_timer = True

            self.icon_label.config(text='⚠️', fg='#ff3b30')
            self.status_label.config(text='Error', fg='#ff3b30')
            self.detail_label.config(text=message)
            self.preview_label.pack_forget()

            self._position_window()

            # Auto-hide after delay
            threading.Thread(
                target=self._auto_hide,
                args=(self.auto_hide_delay,),
                daemon=True
            ).start()

        self.window.after(0, _update_ui)

    def _auto_hide(self, delay):
        """Auto-hide the overlay after a delay"""
        time.sleep(delay)
        self.hide()

    def hide(self):
        """Hide the overlay (thread-safe)"""
        if not self.window or not self.ready:
            return

        def _update_ui():
            self.state = OverlayState.HIDDEN
            self.stop_timer = True

            try:
                self.window.withdraw()
            except:
                pass

        self.window.after(0, _update_ui)

    def destroy(self):
        """Clean up the overlay"""
        self.stop_timer = True
        if self.window:
            try:
                self.window.destroy()
            except:
                pass


# Global overlay instance
_overlay_instance = None


def get_overlay(settings=None):
    """Get or create the global overlay instance"""
    global _overlay_instance
    if _overlay_instance is None:
        _overlay_instance = ModernOverlay(settings)
    return _overlay_instance


def show_recording():
    """Convenience function: Show recording state"""
    overlay = get_overlay()
    overlay.show_recording()


def show_transcribing():
    """Convenience function: Show transcribing state"""
    overlay = get_overlay()
    overlay.show_transcribing()


def show_processing():
    """Convenience function: Show processing state"""
    overlay = get_overlay()
    overlay.show_processing()


def show_complete(text=None):
    """Convenience function: Show completion state"""
    overlay = get_overlay()
    overlay.show_complete(text)


def show_error(message='Error occurred'):
    """Convenience function: Show error state"""
    overlay = get_overlay()
    overlay.show_error(message)


def hide_overlay():
    """Convenience function: Hide the overlay"""
    overlay = get_overlay()
    overlay.hide()

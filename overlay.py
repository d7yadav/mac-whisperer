"""
Native macOS Overlay for Mac Whisperer
Uses PyObjC with NSPanel for non-intrusive, HUD-style feedback
Compatible with rumps - no threading conflicts
"""
import time
import threading
from enum import Enum
import objc
from Foundation import NSObject, NSTimer, NSRunLoop, NSDefaultRunLoopMode
from AppKit import (
    NSPanel, NSView, NSTextField, NSColor, NSFont, NSScreen,
    NSBorderlessWindowMask, NSNonactivatingPanelMask,
    NSFloatingWindowLevel, NSBackingStoreBuffered,
    NSMakeRect, NSMakePoint, NSMakeSize,
    NSApplication, NSCenterTextAlignment
)


class OverlayState(Enum):
    HIDDEN = "hidden"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class NativeOverlay(NSObject):
    """
    Native macOS overlay using NSPanel
    - Non-activating (doesn't steal focus)
    - Always on top (NSFloatingWindowLevel)
    - HUD-style design
    - Thread-safe updates
    """

    def init(self):
        self = objc.super(NativeOverlay, self).init()
        if self is None:
            return None

        self.panel = None
        self.icon_label = None
        self.status_label = None
        self.detail_label = None
        self.preview_label = None
        self.state = OverlayState.HIDDEN
        self.start_time = None
        self.timer = None
        self.settings = {}
        self.ready = False

        return self

    def initWithSettings_(self, settings):
        self = self.init()
        if self is None:
            return None

        self.settings = settings if settings else {}
        self.load_settings()

        # Don't create panel yet - delay until first use to avoid conflicts with rumps
        # Panel will be created lazily when first show method is called

        return self

    def load_settings(self):
        """Load settings from settings manager"""
        if hasattr(self.settings, 'get'):
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

    def create_panel(self):
        """Create the NSPanel overlay window"""
        # Panel dimensions
        width = 300
        height = 100

        # Create borderless, non-activating panel
        style_mask = NSBorderlessWindowMask | NSNonactivatingPanelMask

        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, width, height),
            style_mask,
            NSBackingStoreBuffered,
            False
        )

        # Panel configuration
        self.panel.setLevel_(NSFloatingWindowLevel)  # Always on top
        self.panel.setOpaque_(False)  # Transparent
        self.panel.setBackgroundColor_(NSColor.clearColor())  # Clear background
        self.panel.setHasShadow_(True)  # Nice shadow
        self.panel.setFloatingPanel_(True)  # Float above other windows
        self.panel.setWorksWhenModal_(True)  # Work in modal contexts
        self.panel.setAlphaValue_(self.opacity)  # Set opacity

        # Create content view with dark background
        content_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        content_view.setWantsLayer_(True)
        content_view.layer().setBackgroundColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.1, 0.1, 0.95).CGColor()
        )
        content_view.layer().setCornerRadius_(12.0)  # Rounded corners

        # Icon label (emoji)
        self.icon_label = NSTextField.alloc().initWithFrame_(NSMakeRect(15, height - 45, 40, 30))
        self.icon_label.setStringValue_("")
        self.icon_label.setFont_(NSFont.systemFontOfSize_(24.0))
        self.icon_label.setBezeled_(False)
        self.icon_label.setDrawsBackground_(False)
        self.icon_label.setEditable_(False)
        self.icon_label.setSelectable_(False)
        content_view.addSubview_(self.icon_label)

        # Status label
        self.status_label = NSTextField.alloc().initWithFrame_(NSMakeRect(60, height - 40, 220, 20))
        self.status_label.setStringValue_("")
        self.status_label.setFont_(NSFont.boldSystemFontOfSize_(float(self.font_size)))
        self.status_label.setTextColor_(NSColor.whiteColor())
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setEditable_(False)
        self.status_label.setSelectable_(False)
        content_view.addSubview_(self.status_label)

        # Detail label (timer/info)
        self.detail_label = NSTextField.alloc().initWithFrame_(NSMakeRect(60, height - 60, 220, 16))
        self.detail_label.setStringValue_("")
        self.detail_label.setFont_(NSFont.systemFontOfSize_(float(self.font_size - 2)))
        self.detail_label.setTextColor_(NSColor.grayColor())
        self.detail_label.setBezeled_(False)
        self.detail_label.setDrawsBackground_(False)
        self.detail_label.setEditable_(False)
        self.detail_label.setSelectable_(False)
        content_view.addSubview_(self.detail_label)

        # Preview label (shown for COMPLETE state)
        self.preview_label = NSTextField.alloc().initWithFrame_(NSMakeRect(15, 10, width - 30, 35))
        self.preview_label.setStringValue_("")
        self.preview_label.setFont_(NSFont.systemFontOfSize_(float(self.font_size - 3)))
        self.preview_label.setTextColor_(NSColor.colorWithWhite_alpha_(0.8, 1.0))
        self.preview_label.setBezeled_(False)
        self.preview_label.setDrawsBackground_(False)
        self.preview_label.setEditable_(False)
        self.preview_label.setSelectable_(False)
        self.preview_label.setHidden_(True)
        content_view.addSubview_(self.preview_label)

        self.panel.setContentView_(content_view)
        self.position_panel()

        self.ready = True

    def _ensure_panel_created(self):
        """Lazy panel creation - only create when first needed"""
        if not self.enabled:
            return False

        if self.panel is not None and self.ready:
            return True

        # Create panel on first use
        self.create_panel()
        return self.ready

    def position_panel(self):
        """Position the panel based on settings"""
        if not self.panel:
            return

        screen = NSScreen.mainScreen()
        screen_frame = screen.visibleFrame()
        panel_frame = self.panel.frame()

        margin = 40
        positions = {
            'top-left': (
                screen_frame.origin.x + margin,
                screen_frame.origin.y + screen_frame.size.height - panel_frame.size.height - margin
            ),
            'top-right': (
                screen_frame.origin.x + screen_frame.size.width - panel_frame.size.width - margin,
                screen_frame.origin.y + screen_frame.size.height - panel_frame.size.height - margin
            ),
            'bottom-left': (
                screen_frame.origin.x + margin,
                screen_frame.origin.y + margin + 100
            ),
            'bottom-right': (
                screen_frame.origin.x + screen_frame.size.width - panel_frame.size.width - margin,
                screen_frame.origin.y + margin + 100
            ),
            'center': (
                screen_frame.origin.x + (screen_frame.size.width - panel_frame.size.width) / 2,
                screen_frame.origin.y + (screen_frame.size.height - panel_frame.size.height) / 2
            )
        }

        x, y = positions.get(self.position, positions['bottom-right'])
        self.panel.setFrameOrigin_(NSMakePoint(x, y))

    def show_recording(self):
        """Show recording state"""
        if not self._ensure_panel_created():
            return

        def update():
            self.state = OverlayState.RECORDING
            self.start_time = time.time()

            self.icon_label.setStringValue_("🔴")
            self.icon_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.23, 0.19, 1.0))
            self.status_label.setStringValue_("Recording")
            self.status_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.23, 0.19, 1.0))
            self.detail_label.setStringValue_("00:00")
            self.detail_label.setHidden_(False)
            self.preview_label.setHidden_(True)

            self.panel.orderFrontRegardless()
            self.position_panel()

            # Start timer updates
            if self.show_timer:
                self.start_timer()

        self.performSelectorOnMainThread_withObject_waitUntilDone_("_update_recording", None, False)
        update()

    def _update_recording(self, _):
        """Called on main thread for recording update"""
        pass

    def start_timer(self):
        """Start timer for recording duration"""
        if self.timer:
            self.timer.invalidate()

        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.1, self, "updateTimer:", None, True
        )

    def updateTimer_(self, timer):
        """Update timer display (called every 100ms)"""
        if self.state != OverlayState.RECORDING or not self.start_time:
            if self.timer:
                self.timer.invalidate()
                self.timer = None
            return

        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        self.detail_label.setStringValue_(f"{minutes:02d}:{seconds:02d}")

    def show_transcribing(self):
        """Show transcribing state"""
        if not self._ensure_panel_created():
            return

        if self.timer:
            self.timer.invalidate()
            self.timer = None

        self.state = OverlayState.TRANSCRIBING

        self.icon_label.setStringValue_("⏳")
        self.icon_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.8, 0.0, 1.0))
        self.status_label.setStringValue_("Transcribing")
        self.status_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.8, 0.0, 1.0))

        if self.start_time:
            elapsed = time.time() - self.start_time
            self.detail_label.setStringValue_(f"Recorded {elapsed:.1f}s")
        else:
            self.detail_label.setStringValue_("Processing audio...")

        self.panel.orderFrontRegardless()
        self.position_panel()

    def show_processing(self):
        """Show processing state (LLM formatting)"""
        if not self._ensure_panel_created():
            return

        self.state = OverlayState.PROCESSING

        self.icon_label.setStringValue_("✨")
        self.icon_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.35, 0.34, 0.84, 1.0))
        self.status_label.setStringValue_("Processing")
        self.status_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.35, 0.34, 0.84, 1.0))
        self.detail_label.setStringValue_("Improving grammar...")

        self.panel.orderFrontRegardless()
        self.position_panel()

    def show_complete(self, text=None):
        """Show completion state with optional text preview"""
        if not self._ensure_panel_created():
            return

        self.state = OverlayState.COMPLETE

        self.icon_label.setStringValue_("✓")
        self.icon_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.78, 0.35, 1.0))
        self.status_label.setStringValue_("Complete")
        self.status_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.78, 0.35, 1.0))
        self.detail_label.setStringValue_("Text ready!")

        # Show text preview if enabled
        if self.show_text_preview and text:
            preview = text[:150] + '...' if len(text) > 150 else text
            self.preview_label.setStringValue_(preview)
            self.preview_label.setHidden_(False)

        self.panel.orderFrontRegardless()
        self.position_panel()

        # Auto-hide after delay
        threading.Thread(target=self._auto_hide, args=(self.auto_hide_delay,), daemon=True).start()

    def show_error(self, message='Error occurred'):
        """Show error state"""
        if not self._ensure_panel_created():
            return

        if self.timer:
            self.timer.invalidate()
            self.timer = None

        self.state = OverlayState.ERROR

        self.icon_label.setStringValue_("⚠️")
        self.icon_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.23, 0.19, 1.0))
        self.status_label.setStringValue_("Error")
        self.status_label.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.23, 0.19, 1.0))
        self.detail_label.setStringValue_(message[:50])
        self.preview_label.setHidden_(True)

        self.panel.orderFrontRegardless()
        self.position_panel()

        # Auto-hide after delay
        threading.Thread(target=self._auto_hide, args=(self.auto_hide_delay,), daemon=True).start()

    def _auto_hide(self, delay):
        """Auto-hide the overlay after a delay"""
        time.sleep(delay)
        self.hide()

    def hide(self):
        """Hide the overlay"""
        if not self.panel:
            return

        self.state = OverlayState.HIDDEN

        if self.timer:
            self.timer.invalidate()
            self.timer = None

        self.panel.orderOut_(None)

    def destroy(self):
        """Clean up the overlay"""
        if self.timer:
            self.timer.invalidate()
            self.timer = None

        if self.panel:
            self.panel.close()
            self.panel = None


# Global overlay instance
_overlay_instance = None


def get_overlay(settings=None):
    """Get or create the global overlay instance"""
    global _overlay_instance
    if _overlay_instance is None:
        _overlay_instance = NativeOverlay.alloc().initWithSettings_(settings)
    return _overlay_instance


# Convenience functions
def show_recording():
    """Show recording state"""
    overlay = get_overlay()
    if overlay:
        overlay.show_recording()


def show_transcribing():
    """Show transcribing state"""
    overlay = get_overlay()
    if overlay:
        overlay.show_transcribing()


def show_processing():
    """Show processing state"""
    overlay = get_overlay()
    if overlay:
        overlay.show_processing()


def show_complete(text=None):
    """Show completion state"""
    overlay = get_overlay()
    if overlay:
        overlay.show_complete(text)


def show_error(message='Error occurred'):
    """Show error state"""
    overlay = get_overlay()
    if overlay:
        overlay.show_error(message)


def hide_overlay():
    """Hide the overlay"""
    overlay = get_overlay()
    if overlay:
        overlay.hide()

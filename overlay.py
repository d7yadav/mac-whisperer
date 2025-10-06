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
    NSApplication, NSCenterTextAlignment,
    NSVisualEffectView, NSAnimationContext, NSAnimation,
    NSViewWidthSizable, NSViewHeightSizable, NSBezierPath
)
import random


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
        self.stats_label = None
        self.visual_effect_view = None
        self.waveform_container = None
        self.waveform_bars = []
        self.waveform_timer = None
        self.state = OverlayState.HIDDEN
        self.start_time = None
        self.timer = None
        self.pulse_timer = None
        self.pulse_scale = 1.0
        self.pulse_direction = 1
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
            self.show_stats = self.settings.get('overlay_show_stats', True)
            self.stay_on_click = self.settings.get('overlay_stay_on_click', True)
        else:
            # Defaults
            self.enabled = True
            self.position = 'bottom-right'
            self.opacity = 0.95
            self.show_timer = True
            self.show_text_preview = True
            self.auto_hide_delay = 3.0
            self.font_size = 14
            self.show_stats = True
            self.stay_on_click = True

        # Store last transcript for re-showing
        self.last_transcript = None
        self.last_transcript_stats = None

    def create_panel(self):
        """Create the NSPanel overlay window with modern macOS blur effects"""
        # Panel dimensions (increased for stats)
        width = 320
        height = 130

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
        self.panel.setAlphaValue_(0.0)  # Start invisible for fade-in

        # Create visual effect view for modern blur (macOS 10.10+)
        try:
            self.visual_effect_view = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
            self.visual_effect_view.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            self.visual_effect_view.setWantsLayer_(True)
            self.visual_effect_view.layer().setCornerRadius_(16.0)  # More rounded
            # Material: 2 = Dark, 8 = HUD (try both)
            try:
                self.visual_effect_view.setMaterial_(2)  # Dark material
            except:
                pass
            content_view = self.visual_effect_view
        except:
            # Fallback to standard view if NSVisualEffectView unavailable
            content_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
            content_view.setWantsLayer_(True)
            content_view.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(0.08, 0.08, 0.08, 0.96).CGColor()
            )
            content_view.layer().setCornerRadius_(16.0)  # More rounded

        # Icon label (larger, more prominent)
        self.icon_label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, height - 50, 45, 35))
        self.icon_label.setStringValue_("")
        self.icon_label.setFont_(NSFont.systemFontOfSize_(28.0))  # Larger icon
        self.icon_label.setBezeled_(False)
        self.icon_label.setDrawsBackground_(False)
        self.icon_label.setEditable_(False)
        self.icon_label.setSelectable_(False)
        self.icon_label.setWantsLayer_(True)  # For animations
        content_view.addSubview_(self.icon_label)

        # Status label (better positioning)
        self.status_label = NSTextField.alloc().initWithFrame_(NSMakeRect(70, height - 42, 230, 22))
        self.status_label.setStringValue_("")
        self.status_label.setFont_(NSFont.boldSystemFontOfSize_(float(self.font_size + 1)))  # Slightly larger
        self.status_label.setTextColor_(NSColor.whiteColor())
        self.status_label.setBezeled_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setEditable_(False)
        self.status_label.setSelectable_(False)
        content_view.addSubview_(self.status_label)

        # Detail label (timer/info) with better spacing
        self.detail_label = NSTextField.alloc().initWithFrame_(NSMakeRect(70, height - 62, 230, 16))
        self.detail_label.setStringValue_("")
        self.detail_label.setFont_(NSFont.systemFontOfSize_(float(self.font_size - 1)))
        self.detail_label.setTextColor_(NSColor.colorWithWhite_alpha_(0.7, 1.0))  # Softer gray
        self.detail_label.setBezeled_(False)
        self.detail_label.setDrawsBackground_(False)
        self.detail_label.setEditable_(False)
        self.detail_label.setSelectable_(False)
        content_view.addSubview_(self.detail_label)

        # Preview label (shown for COMPLETE state)
        self.preview_label = NSTextField.alloc().initWithFrame_(NSMakeRect(15, 25, width - 30, 35))
        self.preview_label.setStringValue_("")
        self.preview_label.setFont_(NSFont.systemFontOfSize_(float(self.font_size - 3)))
        self.preview_label.setTextColor_(NSColor.colorWithWhite_alpha_(0.8, 1.0))
        self.preview_label.setBezeled_(False)
        self.preview_label.setDrawsBackground_(False)
        self.preview_label.setEditable_(False)
        self.preview_label.setSelectable_(False)
        self.preview_label.setHidden_(True)
        content_view.addSubview_(self.preview_label)

        # Stats label (word/char count)
        self.stats_label = NSTextField.alloc().initWithFrame_(NSMakeRect(15, 8, width - 30, 14))
        self.stats_label.setStringValue_("")
        self.stats_label.setFont_(NSFont.systemFontOfSize_(float(self.font_size - 4)))
        self.stats_label.setTextColor_(NSColor.colorWithWhite_alpha_(0.6, 1.0))
        self.stats_label.setBezeled_(False)
        self.stats_label.setDrawsBackground_(False)
        self.stats_label.setEditable_(False)
        self.stats_label.setSelectable_(False)
        self.stats_label.setHidden_(True)
        content_view.addSubview_(self.stats_label)

        # Waveform visualization container (for recording state)
        waveform_height = 40
        waveform_y = 25
        self.waveform_container = NSView.alloc().initWithFrame_(NSMakeRect(20, waveform_y, width - 40, waveform_height))
        self.waveform_container.setHidden_(True)
        self.waveform_container.setWantsLayer_(True)
        content_view.addSubview_(self.waveform_container)

        # Create waveform bars (modern animated visualization)
        num_bars = 25
        bar_width = 3
        bar_spacing = ((width - 40) - (num_bars * bar_width)) / (num_bars - 1)

        self.waveform_bars = []
        for i in range(num_bars):
            x = i * (bar_width + bar_spacing)
            bar = NSView.alloc().initWithFrame_(NSMakeRect(x, waveform_height / 2, bar_width, 2))
            bar.setWantsLayer_(True)
            bar.layer().setBackgroundColor_(
                NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.27, 0.23, 0.8).CGColor()
            )
            bar.layer().setCornerRadius_(1.5)  # Rounded bars
            self.waveform_container.addSubview_(bar)
            self.waveform_bars.append(bar)

        self.panel.setContentView_(content_view)
        self.position_panel()

        self.ready = True

    def _ensure_panel_created(self):
        """Lazy panel creation - only create when first needed"""
        if not self.enabled:
            return False

        if self.panel is not None and self.ready:
            return True

        # Create panel on main thread (required by macOS)
        # Use performSelectorOnMainThread to ensure thread safety
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "createPanelOnMainThread:", None, True
        )
        return self.ready

    def createPanelOnMainThread_(self, _):
        """Called on main thread to create the panel"""
        if self.panel is None:
            self.create_panel()

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

    def fade_in(self):
        """Smooth fade-in animation"""
        if not self.panel:
            return

        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.3)  # 0.3s fade
        self.panel.animator().setAlphaValue_(self.opacity)
        NSAnimationContext.endGrouping()

    def fade_out(self):
        """Smooth fade-out animation"""
        if not self.panel:
            return

        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(0.3)  # 0.3s fade
        self.panel.animator().setAlphaValue_(0.0)
        NSAnimationContext.endGrouping()

    def start_pulse_animation(self):
        """Start pulsing animation for recording state"""
        if self.pulse_timer:
            return  # Already pulsing

        self.pulse_scale = 1.0
        self.pulse_direction = 1
        self.pulse_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.05, self, "updatePulse:", None, True
        )

    def updatePulse_(self, timer):
        """Update pulsing animation (called every 50ms)"""
        if self.state != OverlayState.RECORDING or not self.icon_label:
            self.stop_pulse_animation()
            return

        # Pulse between 0.9 and 1.1 scale
        self.pulse_scale += self.pulse_direction * 0.02
        if self.pulse_scale >= 1.15:
            self.pulse_direction = -1
        elif self.pulse_scale <= 0.90:
            self.pulse_direction = 1

        # Apply transform
        try:
            from Quartz import CGAffineTransformMakeScale
            transform = CGAffineTransformMakeScale(self.pulse_scale, self.pulse_scale)
            self.icon_label.layer().setAffineTransform_(transform)
        except:
            pass  # Fallback if Quartz not available

    def stop_pulse_animation(self):
        """Stop pulsing animation"""
        if self.pulse_timer:
            self.pulse_timer.invalidate()
            self.pulse_timer = None

        # Reset scale
        if self.icon_label:
            try:
                from Quartz import CGAffineTransformMakeScale
                transform = CGAffineTransformMakeScale(1.0, 1.0)
                self.icon_label.layer().setAffineTransform_(transform)
            except:
                pass

    def start_waveform_animation(self):
        """Start animated waveform visualization"""
        if self.waveform_timer:
            return  # Already animating

        self.waveform_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.08, self, "updateWaveform:", None, True
        )

    def updateWaveform_(self, timer):
        """Update waveform bars (called every 80ms)"""
        if self.state != OverlayState.RECORDING or not self.waveform_bars:
            self.stop_waveform_animation()
            return

        # Simulate audio levels with random heights
        waveform_container_height = 40
        for bar in self.waveform_bars:
            # Random height between 2 and 35 pixels (simulating audio levels)
            height = random.uniform(4, 35)
            frame = bar.frame()

            # Center the bar vertically
            y = (waveform_container_height - height) / 2

            # Animate height change
            NSAnimationContext.beginGrouping()
            NSAnimationContext.currentContext().setDuration_(0.08)
            bar.animator().setFrame_(NSMakeRect(frame.origin.x, y, frame.size.width, height))
            NSAnimationContext.endGrouping()

    def stop_waveform_animation(self):
        """Stop waveform animation"""
        if self.waveform_timer:
            self.waveform_timer.invalidate()
            self.waveform_timer = None

        # Reset all bars to minimum height
        if self.waveform_bars:
            for bar in self.waveform_bars:
                frame = bar.frame()
                bar.setFrame_(NSMakeRect(frame.origin.x, 19, frame.size.width, 2))

    def show_recording(self):
        """Show recording state"""
        if not self._ensure_panel_created():
            return

        # Schedule UI updates on main thread
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateRecordingUI:", None, False
        )

    def updateRecordingUI_(self, _):
        """Called on main thread for recording update"""
        self.state = OverlayState.RECORDING
        self.start_time = time.time()

        # Modern red color (more vibrant)
        red_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.27, 0.23, 1.0)

        self.icon_label.setStringValue_("🎙")  # Microphone icon instead of red dot
        self.icon_label.setTextColor_(red_color)
        self.status_label.setStringValue_("Recording...")
        self.status_label.setTextColor_(red_color)
        self.detail_label.setStringValue_("00:00")
        self.detail_label.setHidden_(False)
        self.preview_label.setHidden_(True)
        self.stats_label.setHidden_(True)

        # Show animated waveform
        if self.waveform_container:
            self.waveform_container.setHidden_(False)
            self.start_waveform_animation()

        self.panel.orderFrontRegardless()
        self.position_panel()

        # Smooth fade-in
        self.fade_in()

        # Start pulsing animation on icon
        self.start_pulse_animation()

        # Start timer updates
        if self.show_timer:
            self.start_timer()

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

        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateTranscribingUI:", None, False
        )

    def updateTranscribingUI_(self, _):
        """Called on main thread for transcribing update"""
        # Stop pulse animation from recording
        self.stop_pulse_animation()
        self.stop_waveform_animation()

        # Hide waveform
        if self.waveform_container:
            self.waveform_container.setHidden_(True)

        if self.timer:
            self.timer.invalidate()
            self.timer = None

        self.state = OverlayState.TRANSCRIBING

        # Modern blue color for processing
        blue_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.25, 0.63, 1.0, 1.0)

        self.icon_label.setStringValue_("✍️")  # Writing icon
        self.icon_label.setTextColor_(blue_color)
        self.status_label.setStringValue_("Transcribing...")
        self.status_label.setTextColor_(blue_color)

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

        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateProcessingUI:", None, False
        )

    def updateProcessingUI_(self, _):
        """Called on main thread for processing update"""
        self.state = OverlayState.PROCESSING

        # Modern purple color for AI processing
        purple_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.69, 0.44, 1.0, 1.0)

        self.icon_label.setStringValue_("✨")  # Sparkles for AI magic
        self.icon_label.setTextColor_(purple_color)
        self.status_label.setStringValue_("AI Processing...")
        self.status_label.setTextColor_(purple_color)
        self.detail_label.setStringValue_("Improving grammar...")

        self.panel.orderFrontRegardless()
        self.position_panel()

    def show_complete(self, text=None, word_count=None, char_count=None):
        """Show completion state with optional text preview and stats"""
        if not self._ensure_panel_created():
            return

        # Store text and stats for main thread update
        self._temp_text = text
        self._temp_word_count = word_count if word_count is not None else (len(text.split()) if text else 0)
        self._temp_char_count = char_count if char_count is not None else (len(text) if text else 0)

        # Store last transcript for re-showing
        self.last_transcript = text
        self.last_transcript_stats = {
            'word_count': self._temp_word_count,
            'char_count': self._temp_char_count
        }

        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateCompleteUI:", None, False
        )

    def updateCompleteUI_(self, _):
        """Called on main thread for complete update"""
        self.state = OverlayState.COMPLETE

        # Modern green color for success
        green_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.84, 0.29, 1.0)

        self.icon_label.setStringValue_("✓")  # Checkmark
        self.icon_label.setTextColor_(green_color)
        self.status_label.setStringValue_("Complete!")
        self.status_label.setTextColor_(green_color)
        self.detail_label.setStringValue_("Text ready to paste")

        # Show text preview if enabled
        text = getattr(self, '_temp_text', None)
        if self.show_text_preview and text:
            preview = text[:140] + '...' if len(text) > 140 else text
            self.preview_label.setStringValue_(preview)
            self.preview_label.setHidden_(False)

        # Show stats if enabled
        if self.show_stats:
            word_count = getattr(self, '_temp_word_count', 0)
            char_count = getattr(self, '_temp_char_count', 0)
            self.stats_label.setStringValue_(f"{word_count} words • {char_count} chars")
            self.stats_label.setHidden_(False)
        else:
            self.stats_label.setHidden_(True)

        self.panel.orderFrontRegardless()
        self.position_panel()

        # Auto-hide after delay (if delay > 0)
        if self.auto_hide_delay > 0:
            threading.Thread(target=self._auto_hide, args=(self.auto_hide_delay,), daemon=True).start()

    def show_error(self, message='Error occurred'):
        """Show error state"""
        if not self._ensure_panel_created():
            return

        # Store message for main thread update
        self._temp_error_message = message
        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateErrorUI:", None, False
        )

    def updateErrorUI_(self, _):
        """Called on main thread for error update"""
        # Stop animations
        self.stop_pulse_animation()

        if self.timer:
            self.timer.invalidate()
            self.timer = None

        self.state = OverlayState.ERROR

        # Bright red for errors
        error_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.27, 0.23, 1.0)

        message = getattr(self, '_temp_error_message', 'Error occurred')
        self.icon_label.setStringValue_("⚠️")  # Warning sign
        self.icon_label.setTextColor_(error_color)
        self.status_label.setStringValue_("Error")
        self.status_label.setTextColor_(error_color)
        self.detail_label.setStringValue_(message[:50])
        self.preview_label.setHidden_(True)
        self.stats_label.setHidden_(True)

        self.panel.orderFrontRegardless()
        self.position_panel()

        # Auto-hide after delay
        if self.auto_hide_delay > 0:
            threading.Thread(target=self._auto_hide, args=(self.auto_hide_delay,), daemon=True).start()

    def _auto_hide(self, delay):
        """Auto-hide the overlay after a delay"""
        time.sleep(delay)
        self.hide()

    def hide(self):
        """Hide the overlay"""
        if not self.panel:
            return

        self.performSelectorOnMainThread_withObject_waitUntilDone_(
            "updateHideUI:", None, False
        )

    def updateHideUI_(self, _):
        """Called on main thread for hide update"""
        self.state = OverlayState.HIDDEN

        # Stop all animations
        self.stop_pulse_animation()
        self.stop_waveform_animation()

        # Hide waveform
        if self.waveform_container:
            self.waveform_container.setHidden_(True)

        if self.timer:
            self.timer.invalidate()
            self.timer = None

        if self.panel:
            # Fade out before hiding
            self.fade_out()
            # Order out after fade completes
            threading.Thread(target=self._delayed_order_out, args=(0.4,), daemon=True).start()

    def _delayed_order_out(self, delay):
        """Hide panel after fade-out completes"""
        time.sleep(delay)
        if self.panel:
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "orderOutPanel:", None, False
            )

    def orderOutPanel_(self, _):
        """Called on main thread to hide panel"""
        if self.panel:
            self.panel.orderOut_(None)

    def show_last_transcript(self):
        """Re-show the last transcript"""
        if self.last_transcript:
            word_count = self.last_transcript_stats.get('word_count', 0) if self.last_transcript_stats else 0
            char_count = self.last_transcript_stats.get('char_count', 0) if self.last_transcript_stats else 0
            self.show_complete(self.last_transcript, word_count, char_count)
            return True
        return False

    def destroy(self):
        """Clean up the overlay"""
        # Stop all animations and timers
        self.stop_pulse_animation()
        self.stop_waveform_animation()

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


def show_complete(text=None, word_count=None, char_count=None):
    """Show completion state"""
    overlay = get_overlay()
    if overlay:
        overlay.show_complete(text, word_count, char_count)


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


def show_last_transcript():
    """Re-show the last transcript"""
    overlay = get_overlay()
    if overlay:
        return overlay.show_last_transcript()
    return False

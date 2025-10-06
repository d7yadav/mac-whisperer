"""
Visual feedback for Mac Whisperer - Using native macOS notifications
"""
import subprocess
import threading
import time


def show_recording_overlay():
    """Show recording started notification"""
    script = '''
    display notification "Speak now... Press Cmd+Opt to stop" with title "🔴 Recording" sound name "Tink"
    '''
    subprocess.run(['osascript', '-e', script])


def show_transcribing_overlay():
    """Show transcribing notification"""
    script = '''
    display notification "Processing your speech..." with title "⏳ Transcribing"
    '''
    subprocess.run(['osascript', '-e', script])


def show_result_overlay(text):
    """Show completion notification with text preview"""
    preview = text[:100] + "..." if len(text) > 100 else text
    # Escape quotes for AppleScript
    preview = preview.replace('"', '\\"').replace("'", "\\'")

    script = f'''
    display notification "{preview}" with title "✅ Transcription Complete" sound name "Glass"
    '''
    subprocess.run(['osascript', '-e', script])


def hide_overlay():
    """Hide overlay (not needed for notifications)"""
    pass

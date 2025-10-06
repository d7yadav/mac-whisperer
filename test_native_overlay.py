#!/usr/bin/env python3
"""
Test native PyObjC overlay
"""
import time
from settings_manager import SettingsManager
import overlay

print("Testing native macOS overlay (PyObjC NSPanel)...")
print("=" * 60)

# Initialize settings
settings = SettingsManager()
settings.set('overlay_enabled', True)
print(f"✓ Overlay enabled: {settings.get('overlay_enabled')}")
print(f"✓ Position: {settings.get('overlay_position', 'bottom-right')}")
print()

# Get overlay instance
print("Creating native overlay...")
overlay_instance = overlay.get_overlay(settings)
print(f"✓ Overlay created: {overlay_instance is not None}")
print(f"✓ Panel ready: {overlay_instance.ready if overlay_instance else False}")
print()

if not overlay_instance or not overlay_instance.ready:
    print("❌ Overlay failed to initialize!")
    exit(1)

# Test states
print("Testing overlay states (check bottom-right corner of screen)...")
print()

print("1. 🔴 RECORDING state (with timer)...")
overlay_instance.show_recording()
time.sleep(4)

print("2. ⏳ TRANSCRIBING state...")
overlay_instance.show_transcribing()
time.sleep(2)

print("3. ✨ PROCESSING state...")
overlay_instance.show_processing()
time.sleep(2)

print("4. ✓ COMPLETE state (with text preview)...")
overlay_instance.show_complete("This is a test of the native macOS overlay using PyObjC with NSPanel. The overlay should not steal keyboard focus!")
time.sleep(5)

print("5. Hiding overlay...")
overlay_instance.hide()
time.sleep(1)

print()
print("=" * 60)
print("✅ Test complete!")
print()
print("Did you see the overlay in the bottom-right corner?")
print("- Dark rounded box with colored icons?")
print("- Timer counting up during recording?")
print("- Smooth transitions between states?")
print("- Did it NOT steal your keyboard focus?")
print()
print("If yes, the native overlay is working! 🎉")

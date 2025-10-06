import argparse
import time
import threading
import pyaudio
import numpy as np
import rumps
from pynput import keyboard
import platform
import subprocess

from whispercpp import Whisper
from text_processor import process_text
from settings_manager import SettingsManager, get_app_context
import overlay

class SpeechTranscriber:
    def __init__(self, whisper: Whisper, use_clipboard=False, settings=None):
        self.whisper = whisper
        self.pykeyboard = keyboard.Controller()
        self.use_clipboard = use_clipboard
        self.settings = settings if settings else SettingsManager()

    def set_clipboard_mode(self, use_clipboard):
        """Toggle between typing and clipboard mode"""
        self.use_clipboard = use_clipboard

    def transcribe(self, audio_data, language=None, app_context=None):
        try:
            # Show transcribing overlay
            overlay.show_transcribing()

            # Get raw transcription from Whisper
            raw_result = self.whisper.transcribe(audio_data)

            # Read use_llm setting from settings manager
            use_llm = self.settings.get('use_llm', True)

            # Show processing overlay if using LLM
            if use_llm:
                overlay.show_processing()

            # Process text with LLM for better formatting (with app context)
            formatted_result = process_text(raw_result, use_llm=use_llm, context=app_context)

            # ALWAYS copy to clipboard first as a safety net (prevents text loss)
            try:
                self._copy_to_clipboard(formatted_result)
            except Exception as e:
                print(f"Warning: Failed to copy to clipboard: {e}")
                overlay.show_error(f"Clipboard error: {str(e)[:50]}")
                return formatted_result

            # If not in clipboard-only mode, also try to auto-type
            if not self.use_clipboard:
                try:
                    self.pykeyboard.type(formatted_result)
                    time.sleep(0.0025)
                    print("✓ Text typed and saved to clipboard")
                except Exception as type_error:
                    print(f"✗ Typing failed: {type_error}")
                    print("✓ Text saved to clipboard - paste with Cmd+V")
            else:
                print("✓ Text copied to clipboard (clipboard mode)")

            # Show completion overlay with text preview
            overlay.show_complete(formatted_result)

            return formatted_result

        except Exception as e:
            print(f"Error during transcription: {e}")
            overlay.show_error(f"Transcription error: {str(e)[:50]}")
            return ""

    def _copy_to_clipboard(self, text):
        """Helper method to copy text to clipboard"""
        process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-8'))

class Recorder:
    def __init__(self, transcriber):
        self.recording = False
        self.transcriber = transcriber
        self.app_context = None

    def start(self, language=None, app_context=None):
        self.app_context = app_context
        thread = threading.Thread(target=self._record_impl, args=(language,))
        thread.start()

    def stop(self):
        self.recording = False


    def _record_impl(self, language):
        self.recording = True
        frames_per_buffer = 1024
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        frames_per_buffer=frames_per_buffer,
                        input=True)
        frames = []

        while self.recording:
            data = stream.read(frames_per_buffer)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
        audio_data_fp32 = audio_data.astype(np.float32) / 32768.0
        self.transcriber.transcribe(audio_data_fp32, language, self.app_context)


class GlobalKeyListener:
    def __init__(self, app, key_combination):
        self.app = app
        self.key1, self.key2 = self.parse_key_combination(key_combination)
        self.key1_pressed = False
        self.key2_pressed = False
        self.recording_triggered = False

    def parse_key_combination(self, key_combination):
        key1_name, key2_name = key_combination.split('+')
        key1 = getattr(keyboard.Key, key1_name)
        key2 = getattr(keyboard.Key, key2_name)
        return key1, key2

    def on_key_press(self, key):
        if key == self.key1:
            self.key1_pressed = True
        elif key == self.key2:
            self.key2_pressed = True

        # Push-to-talk: Start recording when both keys are pressed
        if self.key1_pressed and self.key2_pressed and not self.recording_triggered:
            self.recording_triggered = True
            if not self.app.started:
                self.app.start_app(None)

    def on_key_release(self, key):
        if key == self.key1:
            self.key1_pressed = False
        elif key == self.key2:
            self.key2_pressed = False

        # Push-to-talk: Stop recording when either key is released
        if self.recording_triggered and (not self.key1_pressed or not self.key2_pressed):
            self.recording_triggered = False
            if self.app.started:
                self.app.stop_app(None)


class StatusBarApp(rumps.App):
    def __init__(self, recorder, languages=None, max_time=None, settings=None):
        super().__init__("whisper", "⏯")
        self.languages = languages
        self.current_language = languages[0] if languages is not None else None
        self.use_clipboard = False
        self.settings = settings if settings else SettingsManager()

        # Build settings submenu
        tone_menu = [
            rumps.MenuItem('Auto (Context-Aware)', callback=self.set_tone_auto),
            rumps.MenuItem('Always Casual', callback=self.set_tone_casual),
            rumps.MenuItem('Always Professional', callback=self.set_tone_professional),
            rumps.MenuItem('Always Technical', callback=self.set_tone_technical),
        ]
        # Set initial checkmark
        current_tone = self.settings.get('tone_preference', 'auto')
        for item in tone_menu:
            if (current_tone == 'auto' and 'Auto' in item.title) or \
               (current_tone == 'casual' and 'Casual' in item.title) or \
               (current_tone == 'professional' and 'Professional' in item.title) or \
               (current_tone == 'technical' and 'Technical' in item.title):
                item.state = True

        # Build overlay settings submenu
        overlay_position_menu = [
            rumps.MenuItem('Top Left', callback=lambda s: self.set_overlay_position('top-left', s)),
            rumps.MenuItem('Top Right', callback=lambda s: self.set_overlay_position('top-right', s)),
            rumps.MenuItem('Bottom Left', callback=lambda s: self.set_overlay_position('bottom-left', s)),
            rumps.MenuItem('Bottom Right', callback=lambda s: self.set_overlay_position('bottom-right', s)),
            rumps.MenuItem('Center', callback=lambda s: self.set_overlay_position('center', s)),
        ]
        current_position = self.settings.get('overlay_position', 'bottom-right')
        for item in overlay_position_menu:
            if current_position == 'top-left' and 'Top Left' in item.title:
                item.state = True
            elif current_position == 'top-right' and 'Top Right' in item.title:
                item.state = True
            elif current_position == 'bottom-left' and 'Bottom Left' in item.title:
                item.state = True
            elif current_position == 'bottom-right' and 'Bottom Right' in item.title:
                item.state = True
            elif current_position == 'center' and 'Center' in item.title:
                item.state = True

        overlay_menu = [
            rumps.MenuItem('Enable Overlay', callback=self.toggle_overlay),
            None,
            ('Position', overlay_position_menu),
            rumps.MenuItem('Show Timer', callback=self.toggle_overlay_timer),
            rumps.MenuItem('Show Text Preview', callback=self.toggle_overlay_text_preview),
        ]

        menu = [
            'Start Recording',
            'Stop Recording',
            None,
            rumps.MenuItem('Use Clipboard Mode', callback=self.toggle_clipboard_mode),
            None,
            ('Tone Preference', tone_menu),
            rumps.MenuItem('Toggle LLM Processing', callback=self.toggle_llm),
            None,
            ('Overlay Settings', overlay_menu),
            None,
        ]

        if languages is not None:
            for lang in languages:
                callback = self.change_language if lang != self.current_language else None
                menu.append(rumps.MenuItem(lang, callback=callback))
            menu.append(None)

        self.menu = menu
        self.menu['Stop Recording'].set_callback(None)

        # Set initial LLM toggle state
        use_llm = self.settings.get('use_llm', True)
        self.menu['Toggle LLM Processing'].state = use_llm

        # Set initial overlay states
        overlay_enabled = self.settings.get('overlay_enabled', True)
        self.menu['Overlay Settings']['Enable Overlay'].state = overlay_enabled

        show_timer = self.settings.get('overlay_show_timer', True)
        self.menu['Overlay Settings']['Show Timer'].state = show_timer

        show_text_preview = self.settings.get('overlay_show_text_preview', True)
        self.menu['Overlay Settings']['Show Text Preview'].state = show_text_preview

        self.started = False
        self.recorder = recorder
        self.max_time = max_time
        self.timer = None
        self.elapsed_time = 0

    def toggle_clipboard_mode(self, sender):
        """Toggle between typing and clipboard mode"""
        self.use_clipboard = not self.use_clipboard
        sender.state = self.use_clipboard
        self.recorder.transcriber.set_clipboard_mode(self.use_clipboard)
        self.settings.set('use_clipboard', self.use_clipboard)
        mode = "Clipboard" if self.use_clipboard else "Typing"
        print(f"Output mode: {mode}")

    def toggle_llm(self, sender):
        """Toggle LLM processing on/off"""
        current = self.settings.get('use_llm', True)
        new_value = not current
        self.settings.set('use_llm', new_value)
        sender.state = new_value
        print(f"LLM Processing: {'ON' if new_value else 'OFF'}")

    def set_tone_auto(self, sender):
        """Set tone to auto (context-aware)"""
        self._set_tone('auto', sender)

    def set_tone_casual(self, sender):
        """Set tone to always casual"""
        self._set_tone('casual', sender)

    def set_tone_professional(self, sender):
        """Set tone to always professional"""
        self._set_tone('professional', sender)

    def set_tone_technical(self, sender):
        """Set tone to always technical"""
        self._set_tone('technical', sender)

    def _set_tone(self, tone, sender):
        """Helper to set tone preference"""
        self.settings.set('tone_preference', tone)
        # Update checkmarks in menu
        for item in self.menu['Tone Preference'].values():
            item.state = False
        sender.state = True
        print(f"Tone preference: {tone}")

    def toggle_overlay(self, sender):
        """Toggle overlay on/off"""
        current = self.settings.get('overlay_enabled', True)
        new_value = not current
        self.settings.set('overlay_enabled', new_value)
        sender.state = new_value
        # Reinitialize overlay
        overlay_instance = overlay.get_overlay(self.settings)
        overlay_instance.enabled = new_value
        print(f"Overlay: {'Enabled' if new_value else 'Disabled'}")

    def toggle_overlay_timer(self, sender):
        """Toggle overlay timer display"""
        current = self.settings.get('overlay_show_timer', True)
        new_value = not current
        self.settings.set('overlay_show_timer', new_value)
        sender.state = new_value
        # Update overlay settings
        overlay_instance = overlay.get_overlay(self.settings)
        overlay_instance.show_timer = new_value
        print(f"Overlay timer: {'Shown' if new_value else 'Hidden'}")

    def toggle_overlay_text_preview(self, sender):
        """Toggle overlay text preview"""
        current = self.settings.get('overlay_show_text_preview', True)
        new_value = not current
        self.settings.set('overlay_show_text_preview', new_value)
        sender.state = new_value
        # Update overlay settings
        overlay_instance = overlay.get_overlay(self.settings)
        overlay_instance.show_text_preview = new_value
        print(f"Overlay text preview: {'Shown' if new_value else 'Hidden'}")

    def set_overlay_position(self, position, sender):
        """Set overlay position"""
        self.settings.set('overlay_position', position)
        # Update checkmarks in menu
        for item in self.menu['Overlay Settings']['Position'].values():
            item.state = False
        sender.state = True
        # Update overlay settings
        overlay_instance = overlay.get_overlay(self.settings)
        overlay_instance.position = position
        overlay_instance._position_window()
        print(f"Overlay position: {position}")

    def change_language(self, sender):
        self.current_language = sender.title
        for lang in self.languages:
            self.menu[lang].set_callback(self.change_language if lang != self.current_language else None)

    @rumps.clicked('Start Recording')
    def start_app(self, _):
        print('Listening...')

        # Get app context for context-aware formatting
        app_context = get_app_context()
        tone_pref = self.settings.get('tone_preference', 'auto')
        if tone_pref != 'auto':
            # Override with user preference
            from settings_manager import get_tone_for_app
            app_context['tone'] = get_tone_for_app(None, tone_pref)

        print(f"Active app: {app_context.get('app_name', 'Unknown')}")
        print(f"Using tone: {app_context.get('tone', 'neutral')}")

        # Play start recording sound
        try:
            subprocess.Popen(['afplay', '/System/Library/Sounds/Tink.aiff'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

        self.started = True
        self.menu['Start Recording'].set_callback(None)
        self.menu['Stop Recording'].set_callback(self.stop_app)

        # Show recording overlay
        overlay.show_recording()

        self.recorder.start(self.current_language, app_context)

        if self.max_time is not None:
            self.timer = threading.Timer(self.max_time, lambda: self.stop_app(None))
            self.timer.start()

        self.start_time = time.time()
        self.update_title()

    @rumps.clicked('Stop Recording')
    def stop_app(self, _):
        if not self.started:
            return

        if self.timer is not None:
            self.timer.cancel()

        # Play stop recording sound (same as start for consistency)
        try:
            subprocess.Popen(['afplay', '/System/Library/Sounds/Tink.aiff'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

        print('Transcribing...')

        # Show transcribing icon
        self.title = "⏳"
        self.started = False
        self.menu['Stop Recording'].set_callback(None)
        self.menu['Start Recording'].set_callback(self.start_app)

        # Stop recording and transcribe (this is blocking)
        self.recorder.stop()

        # Reset to idle icon after transcription completes
        self.title = "⏯"
        print('Done.\n')

    def update_title(self):
        if self.started:
            self.elapsed_time = int(time.time() - self.start_time)
            minutes, seconds = divmod(self.elapsed_time, 60)
            self.title = f"({minutes:02d}:{seconds:02d}) 🔴"
            threading.Timer(1, self.update_title).start()

    def toggle(self):
        if self.started:
            self.stop_app(None)
        else:
            self.start_app(None)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Dictation app using the OpenAI whisper ASR model. By default the keyboard shortcut cmd+option '
        'starts and stops dictation')
    parser.add_argument('-m', '--model_name', type=str,
                        choices=['tiny', 'tiny.en', 'base', 'base.en', 'small', 'small.en', 'medium', 'medium.en', 'large'],
                        default='base',
                        help='Specify the whisper ASR model to use. Options: tiny, base, small, medium, or large. '
                        'To see the  most up to date list of models along with model size, memory footprint, and estimated '
                        'transcription speed check out this [link](https://github.com/openai/whisper#available-models-and-languages). '
                        'Note that the models ending in .en are trained only on English speech and will perform better on English '
                        'language. Note that the small, medium, and large models may be slow to transcribe and are only recommended '
                        'if you find the base model to be insufficient. Default: base.')
    parser.add_argument('-k', '--key_combination', type=str, default='cmd_l+alt' if platform.system() == 'Darwin' else 'ctrl+alt',
                        help='Specify the key combination to toggle the app. Example: cmd_l+alt for macOS '
                        'ctrl+alt for other platforms. Default: cmd_r+alt (macOS) or ctrl+alt (others).')
    parser.add_argument('-l', '--language', type=str, default=None,
                        help='Specify the two-letter language code (e.g., "en" for English) to improve recognition accuracy. '
                        'This can be especially helpful for smaller model sizes.  To see the full list of supported languages, '
                        'check out the official list [here](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py).')
    parser.add_argument('-t', '--max_time', type=float, default=30,
                        help='Specify the maximum recording time in seconds. The app will automatically stop recording after this duration. '
                        'Default: 30 seconds.')

    args = parser.parse_args()

    if args.language is not None:
        args.language = args.language.split(',')

    if args.model_name.endswith('.en') and args.language is not None and any(lang != 'en' for lang in args.language):
        raise ValueError('If using a model ending in .en, you cannot specify a language other than English.')

    return args


if __name__ == "__main__":
    args = parse_args()

    # Initialize settings manager (shared across components)
    settings = SettingsManager()

    # Initialize overlay with settings
    overlay_instance = overlay.get_overlay(settings)

    w = Whisper.from_pretrained(args.model_name)
    transcriber = SpeechTranscriber(w, settings=settings)
    recorder = Recorder(transcriber)

    app = StatusBarApp(recorder, args.language, args.max_time, settings=settings)
    key_listener = GlobalKeyListener(app, args.key_combination)
    listener = keyboard.Listener(on_press=key_listener.on_key_press, on_release=key_listener.on_key_release)
    listener.start()

    print("Running... ")
    print(f"Overlay: {'Enabled' if settings.get('overlay_enabled', True) else 'Disabled'}")
    print(f"Position: {settings.get('overlay_position', 'bottom-right')}")
    app.run()

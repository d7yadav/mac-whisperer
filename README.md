# Mac Whisperer
High performance local Mac speech-to-keyboard app that uses the highly performance Whisper models from OpenAI. 15 seconds of audio in 1 second! Just press cmd+opt to start/stop recording.

## How to use
```bash
brew install portaudio
git clone https://github.com/jeffzwang/mac-whisperer
cd mac-whisper
pip install -r requirements.txt
python whisper-dictation.py
```

On Mac, press cmd+opt to start/stop recording.

## What is it?
Fork of [foges/whisper-dictation](https://github.com/foges/whisper-dictation) that 1) uses whispercpp for better performance on M1 Macs (about 2x) 2) has more ergonomic start/stop abilities. Right now, it's using the `base.en` model by default. File an issue if you have trouble setting it up - I broke my wrist recently so this has been clutch for me.

## Prerequisites
The PortAudio library is required for this app to work.

```bash
brew install portaudio
```

## Permissions
The app requires accessibility permissions to register global hotkeys and permission to access your microphone for speech recognition.

## Arguments
Can specify model and shortcut like below:
```bash
python whisper-dictation.py -m large -k cmd_r+shift -l en
```

The models are multilingual, and you can specify a two-letter language code (e.g., "no" for Norwegian) with the `-l` or `--language` option. Specifying the language can improve recognition accuracy, especially for smaller model sizes.

## Setting the App as a Startup Item
To have the app run automatically when your computer starts, follow these steps:

 1. Open System Preferences.
 2. Go to Users & Groups.
 3. Click on your username, then select the Login Items tab.
 4. Click the + button and add the `run.sh` script from the whisper-dictation folder.

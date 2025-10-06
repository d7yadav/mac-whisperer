#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting Mac Whisperer..."
echo "Press Cmd+Opt to start/stop recording"
echo "Transcribed text will automatically type into your active app"
echo "Model: small.en (higher accuracy)"
echo "No time limit - record as long as you need!"
echo ""
python whisper-dictation.py -m small.en -t 600

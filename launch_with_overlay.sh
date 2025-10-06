#!/bin/bash
#
# Mac Whisperer - Launch Script with Overlay
# ==========================================
# This script launches Mac Whisperer with visual overlay feedback
#

cd "$(dirname "$0")"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "======================================="
echo "  🎙️  Mac Whisperer with Overlay  🎙️"
echo "======================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment not found. Creating one...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source venv/bin/activate

# Install/upgrade dependencies
if [ ! -f "venv/.deps_installed" ]; then
    echo -e "${BLUE}Installing dependencies...${NC}"
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    touch venv/.deps_installed
fi

echo ""
echo -e "${GREEN}Starting Mac Whisperer...${NC}"
echo ""
echo "📍 Overlay Features:"
echo "   • Real-time recording timer"
echo "   • Transcription status"
echo "   • Processing indicator"
echo "   • Text preview on completion"
echo ""
echo "🎯 Controls:"
echo "   • Hold Cmd+Option to start/stop recording"
echo "   • Configure overlay in menu bar"
echo "   • LLM-powered grammar correction enabled"
echo ""
echo "⚙️  Settings:"
echo "   • Overlay position: $(python3 -c 'from settings_manager import SettingsManager; s=SettingsManager(); print(s.get(\"overlay_position\", \"bottom-right\"))')"
echo "   • Text preview: $(python3 -c 'from settings_manager import SettingsManager; s=SettingsManager(); print(\"ON\" if s.get(\"overlay_show_text_preview\", True) else \"OFF\")')"
echo ""
echo "Press Ctrl+C to stop the app"
echo "======================================="
echo ""

# Run the app
python whisper-dictation.py -m base.en -t 600

# Deactivate virtual environment on exit
deactivate

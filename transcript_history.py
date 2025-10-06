"""
Transcript History Manager for Mac Whisperer
Stores and manages transcription history with timestamps
"""
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class TranscriptHistory:
    """
    Manages transcript history storage and retrieval
    - Stores last 50 transcripts
    - Persists to ~/.whisperer/history.json
    - Provides methods for adding, retrieving, and managing history
    """

    def __init__(self, max_entries: int = 50):
        self.config_dir = Path.home() / '.whisperer'
        self.history_file = self.config_dir / 'history.json'
        self.max_entries = max_entries
        self.history = self.load_history()

    def load_history(self) -> List[Dict]:
        """Load transcript history from JSON file"""
        if not self.history_file.exists():
            return []

        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                # Ensure it's a list
                if isinstance(history, list):
                    return history
                return []
        except Exception as e:
            print(f"Error loading history: {e}")
            return []

    def save_history(self):
        """Save transcript history to JSON file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving history: {e}")
            return False

    def add(self, text: str, app_name: Optional[str] = None) -> bool:
        """
        Add a new transcript to history

        Args:
            text: The transcribed text
            app_name: The application where transcript was used (optional)

        Returns:
            bool: True if added successfully
        """
        if not text or not text.strip():
            return False

        # Calculate stats
        word_count = len(text.split())
        char_count = len(text)

        entry = {
            'timestamp': time.time(),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'text': text,
            'app_name': app_name,
            'word_count': word_count,
            'char_count': char_count
        }

        # Add to beginning of list (most recent first)
        self.history.insert(0, entry)

        # Trim to max entries
        if len(self.history) > self.max_entries:
            self.history = self.history[:self.max_entries]

        # Save to disk
        return self.save_history()

    def get_recent(self, count: int = 10) -> List[Dict]:
        """
        Get the most recent N transcripts

        Args:
            count: Number of recent transcripts to retrieve

        Returns:
            List of transcript dictionaries
        """
        return self.history[:min(count, len(self.history))]

    def get_last(self) -> Optional[Dict]:
        """Get the most recent transcript"""
        if self.history:
            return self.history[0]
        return None

    def clear(self) -> bool:
        """Clear all transcript history"""
        self.history = []
        return self.save_history()

    def export_to_text(self, filepath: str) -> bool:
        """
        Export history to a text file

        Args:
            filepath: Path where to save the export

        Returns:
            bool: True if exported successfully
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("Mac Whisperer Transcript History\n")
                f.write("=" * 60 + "\n\n")

                for i, entry in enumerate(self.history, 1):
                    f.write(f"[{i}] {entry['datetime']}\n")
                    if entry.get('app_name'):
                        f.write(f"App: {entry['app_name']}\n")
                    f.write(f"Stats: {entry['word_count']} words, {entry['char_count']} characters\n")
                    f.write(f"Text: {entry['text']}\n")
                    f.write("-" * 60 + "\n\n")

            return True
        except Exception as e:
            print(f"Error exporting history: {e}")
            return False

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search through transcript history

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching transcript dictionaries
        """
        if not query:
            return self.get_recent(limit)

        query_lower = query.lower()
        results = []

        for entry in self.history:
            if query_lower in entry['text'].lower():
                results.append(entry)
                if len(results) >= limit:
                    break

        return results

    def get_stats(self) -> Dict:
        """
        Get statistics about transcript history

        Returns:
            Dictionary with statistics
        """
        if not self.history:
            return {
                'total_transcripts': 0,
                'total_words': 0,
                'total_characters': 0,
                'average_words': 0,
                'average_characters': 0
            }

        total_words = sum(entry['word_count'] for entry in self.history)
        total_chars = sum(entry['char_count'] for entry in self.history)
        count = len(self.history)

        return {
            'total_transcripts': count,
            'total_words': total_words,
            'total_characters': total_chars,
            'average_words': total_words // count if count > 0 else 0,
            'average_characters': total_chars // count if count > 0 else 0
        }

    def format_preview(self, entry: Dict, max_length: int = 50) -> str:
        """
        Format a transcript entry for display in menu

        Args:
            entry: Transcript dictionary
            max_length: Maximum length of preview text

        Returns:
            Formatted preview string
        """
        text = entry['text']
        if len(text) > max_length:
            text = text[:max_length] + '...'

        # Get time ago
        now = time.time()
        diff = now - entry['timestamp']

        if diff < 60:
            time_ago = "just now"
        elif diff < 3600:
            mins = int(diff / 60)
            time_ago = f"{mins}m ago"
        elif diff < 86400:
            hours = int(diff / 3600)
            time_ago = f"{hours}h ago"
        else:
            days = int(diff / 86400)
            time_ago = f"{days}d ago"

        return f"{time_ago}: {text}"


# Global history instance
_history_instance = None


def get_history() -> TranscriptHistory:
    """Get or create the global history instance"""
    global _history_instance
    if _history_instance is None:
        _history_instance = TranscriptHistory()
    return _history_instance

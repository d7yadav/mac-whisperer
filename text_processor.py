"""
AI-powered text post-processing using Ollama
Adds smart punctuation, capitalization, and removes filler words
"""
import requests
import json
import re
from settings_manager import SettingsManager


def process_with_llm(text, context=None):
    """
    Process transcribed text with local LLM for better formatting

    Args:
        text: Raw transcribed text
        context: Optional dict with 'app_name' and 'tone' for context-aware formatting
    """
    if not text or len(text.strip()) == 0:
        return text

    # Get tone from context or use default
    tone = context.get('tone', 'neutral and professional') if context else 'neutral and professional'
    app_name = context.get('app_name', 'Unknown') if context else 'Unknown'

    # Enhanced prompt focusing on grammar correction and rephrasing (inspired by modern STT services)
    prompt = f"""You are an expert text editing assistant that transforms speech-to-text output into grammatically correct, naturally flowing text.

Context: User is dictating in {app_name}. Use a tone that is {tone}.

Your task: REPHRASE and CORRECT the transcribed speech to create polished, grammatically correct text by:

1. **Grammar Correction**: Fix all grammatical errors including:
   - Subject-verb agreement (e.g., "he go" → "he goes")
   - Tense consistency (maintain proper past/present/future)
   - Pronoun agreement
   - Article usage (add missing "a", "an", "the")
   - Preposition correction

2. **Sentence Rephrasing**: Restructure awkward or unclear sentences for better readability and natural flow

3. **Punctuation & Capitalization**: Add proper punctuation marks and capitalize correctly (sentences, proper nouns, I)

4. **Homophone Correction**: Fix commonly confused words based on context:
   - their/there/they're, to/too/two, your/you're, its/it's, affect/effect, than/then

5. **Filler Word Removal**: Delete verbal fillers (um, uh, like, you know, basically, actually, literally)

6. **Self-Correction Handling**: When speaker corrects themselves, keep only the final version
   - Look for: "no wait", "actually", "I mean", "scratch that", "or rather", "let me rephrase"

7. **Number & Format Consistency**: Handle numbers, times, and emails appropriately

CRITICAL RULES:
- Output ONLY the corrected text with NO explanations, notes, or commentary
- REPHRASE for clarity and correctness, don't just clean up
- Preserve the original meaning and intent
- Don't add information that wasn't spoken
- Make it sound natural, as if written by a fluent speaker

Examples demonstrating grammar correction and rephrasing:

Input: "um so i was thinking like we should probably schedule the meeting for um thursday at 2 pm you know"
Output: "I was thinking we should schedule the meeting for Thursday at 2 PM."

Input: "him and me was going to the store but then we decide to go tomorrow instead"
Output: "He and I were going to the store, but then we decided to go tomorrow instead."

Input: "their going to there house to get they're stuff"
Output: "They're going to their house to get their stuff."

Input: "the team are working on it and its almost done"
Output: "The team is working on it, and it's almost done."

Input: "i need you to send me informations about the new project your working on"
Output: "I need you to send me information about the new project you're working on."

Input: "lets meet at 2 pm no wait make it 4 pm"
Output: "Let's meet at 4 PM."

Input: "he don't know what he doing and i think we should helps him"
Output: "He doesn't know what he's doing, and I think we should help him."

Input: "between you and i this is more better then the last one"
Output: "Between you and me, this is better than the last one."

Input: "can you effect the changes by tomorrow i need it real quick"
Output: "Can you make the changes by tomorrow? I need them quickly."

Now correct and rephrase this text:

Input: "{text}"
Output:"""

    try:
        # Get Ollama API URL from settings
        settings = SettingsManager()
        api_url = settings.get('ollama_api_url', 'http://localhost:11434/api/generate')

        # Call Ollama API with better model
        response = requests.post(
            api_url,
            json={
                'model': 'qwen2.5:3b',  # Upgraded from llama3.2:1b for better quality
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.2,  # Even lower for more consistent formatting
                    'top_p': 0.85,
                    'top_k': 40,
                    'repeat_penalty': 1.1,
                }
            },
            timeout=30  # 30 second timeout
        )

        if response.status_code == 200:
            result = response.json()
            formatted_text = result.get('response', '').strip()

            # Remove common LLM artifacts
            formatted_text = re.sub(r'^Output:\s*', '', formatted_text, flags=re.IGNORECASE)
            formatted_text = re.sub(r'^Formatted text:\s*', '', formatted_text, flags=re.IGNORECASE)
            formatted_text = re.sub(r'^Here.*?:\s*', '', formatted_text, flags=re.IGNORECASE)

            # Remove quotes if the entire text is wrapped in them
            if formatted_text.startswith('"') and formatted_text.endswith('"'):
                formatted_text = formatted_text[1:-1]
            elif formatted_text.startswith("'") and formatted_text.endswith("'"):
                formatted_text = formatted_text[1:-1]

            # Clean up any potential formatting issues
            formatted_text = re.sub(r'\n+', ' ', formatted_text)  # Remove extra newlines
            formatted_text = re.sub(r'\s+', ' ', formatted_text)  # Remove extra spaces
            formatted_text = formatted_text.strip()

            # Validate output - if LLM added explanation, fall back to basic
            if len(formatted_text) > len(text) * 2:  # Output suspiciously longer
                print("LLM output too long, using basic cleanup")
                return basic_cleanup(text)

            return formatted_text if formatted_text else text
        else:
            print(f"LLM processing failed: {response.status_code}")
            return basic_cleanup(text)

    except requests.exceptions.RequestException as e:
        print(f"LLM not available: {e}")
        return basic_cleanup(text)
    except Exception as e:
        print(f"Error in LLM processing: {e}")
        return basic_cleanup(text)


def basic_cleanup(text):
    """
    Basic rule-based text cleanup (fallback when LLM is unavailable)
    """
    if not text:
        return text

    # Remove common filler words
    filler_words = [
        r'\bum+\b', r'\buh+\b', r'\blike\b', r'\byou know\b',
        r'\bbasically\b', r'\bactually\b', r'\bliterally\b',
        r'\byeah\b', r'\bokay\b', r'\bso\b', r'\bwell\b'
    ]

    cleaned = text
    for filler in filler_words:
        cleaned = re.sub(filler, '', cleaned, flags=re.IGNORECASE)

    # Clean up extra spaces
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # Capitalize first letter
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    # Add period at end if missing
    if cleaned and cleaned[-1] not in '.!?':
        cleaned += '.'

    return cleaned


def process_text(text, use_llm=True, context=None):
    """
    Main entry point for text processing

    Args:
        text: Raw transcribed text
        use_llm: Whether to use LLM processing (default: True)
        context: Optional dict with app context for tone adjustment

    Returns:
        Formatted text
    """
    if not text or len(text.strip()) == 0:
        return text

    if use_llm:
        return process_with_llm(text, context)
    else:
        return basic_cleanup(text)

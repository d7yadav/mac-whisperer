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

    # Conservative prompt focusing on grammar correction while preserving original meaning
    prompt = f"""You are an expert text editing assistant that corrects speech-to-text errors while strictly preserving the original meaning and intent.

Context: User is dictating in {app_name}. Use a tone that is {tone}.

Your task: CORRECT grammatical errors and clean up the transcribed speech while maintaining the exact meaning by:

1. **Grammar Correction**: Fix grammatical errors while keeping the original sentence structure:
   - Subject-verb agreement (e.g., "he go" → "he goes")
   - Tense consistency (maintain proper past/present/future)
   - Pronoun agreement
   - Article usage (add missing "a", "an", "the")
   - Preposition correction

2. **Punctuation & Capitalization**: Add proper punctuation marks and capitalize correctly (sentences, proper nouns, I)

3. **Homophone Correction**: Fix commonly confused words based on context:
   - their/there/they're, to/too/two, your/you're, its/it's, affect/effect, than/then

4. **Filler Word Removal**: Delete verbal fillers (um, uh, like, you know, basically, actually, literally)

5. **Self-Correction Handling**: When speaker corrects themselves, keep only the final version
   - Look for: "no wait", "actually", "I mean", "scratch that", "or rather", "let me rephrase"

6. **Number & Format Consistency**: Handle numbers, times, and emails appropriately

CRITICAL RULES:
- Output ONLY the corrected text with NO explanations, notes, or commentary
- DO NOT rephrase or restructure sentences - only fix grammar errors
- PRESERVE the original sentence structure and word choice unless grammatically incorrect
- NEVER change the meaning or intent of what was spoken
- Don't add information that wasn't spoken
- Minimal changes - only fix errors, don't rewrite

Examples demonstrating conservative grammar correction (preserving original structure):

Input: "um so i was thinking like we should probably schedule the meeting for um thursday at 2 pm you know"
Output: "So I was thinking we should probably schedule the meeting for Thursday at 2 PM."

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

Input: "can you please send me the document i need it for the meeting"
Output: "Can you please send me the document? I need it for the meeting."

Now correct this text (fix grammar only, preserve original structure and meaning):

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
                    'temperature': 0.1,  # Very low for minimal creative changes, preserves original text
                    'top_p': 0.8,  # Lower for more deterministic output
                    'top_k': 30,  # Lower to reduce variation
                    'repeat_penalty': 1.05,  # Lower to avoid over-correcting
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

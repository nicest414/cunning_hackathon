"""
Test script for verifying communication with the Gemini API directly.
Make sure you have an image file (e.g., test_question.png) in the root directory before running.
"""
import os
import sys

from dotenv import load_dotenv

# Add the project root to sys.path so we can import 'core'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core import ai_client

def main():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY is not set. Please check your .env file.")
        sys.exit(1)

    ai_client.init(api_key)
    print("[INFO] AI client initialized.")

    # We assume 'test_question.png' is placed in the project root
    test_image_path = os.path.join(os.path.dirname(__file__), '..', 'test_question.png')
    
    if not os.path.exists(test_image_path):
        print(f"[!] Warning: Test image not found at {test_image_path}")
        print("    Please place a 'test_question.png' file in the root to perform a real API request.")
        return

    print(f"[INFO] Reading test image from {test_image_path}...")
    with open(test_image_path, "rb") as f:
        img_bytes = f.read()

    print("[INFO] Asking Gemini...")
    try:
        answer = ai_client.ask(img_bytes)
        print(f"[SUCCESS] Received Answer: {answer}")
    except Exception as e:
        print(f"[ERROR] Failed to get an answer: {e}")

if __name__ == "__main__":
    main()

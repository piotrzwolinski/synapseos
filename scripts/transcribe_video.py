"""Transcribe and summarize a video using Google Gemini API."""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from google import genai
from google.genai import types

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ERROR: GEMINI_API_KEY not set")
    sys.exit(1)

client = genai.Client(api_key=api_key)

video_path = sys.argv[1] if len(sys.argv) > 1 else "/Users/piotrzwolinski/Downloads/Synapse-internal_2026-04-02.mp4"

t0 = time.time()

# Check if file was already uploaded (reuse to save time)
existing_file_name = os.getenv("GEMINI_FILE_NAME")  # e.g. "files/jmpdjqw5f98f"
if existing_file_name:
    print(f"Reusing already-uploaded file: {existing_file_name}")
    video_file = client.files.get(name=existing_file_name)
else:
    print(f"Uploading video: {video_path} ({os.path.getsize(video_path) / 1024 / 1024:.1f} MB)")
    video_file = client.files.upload(file=video_path)
    print(f"Upload complete in {time.time() - t0:.1f}s. File name: {video_file.name}, state: {video_file.state}")

# Wait for processing
while video_file.state.name == "PROCESSING":
    print(f"  Processing... ({time.time() - t0:.0f}s elapsed)")
    time.sleep(5)
    video_file = client.files.get(name=video_file.name)

if video_file.state.name == "FAILED":
    print(f"ERROR: Video processing failed: {video_file.state}")
    sys.exit(1)

print(f"Video ready (state: {video_file.state.name}). Sending to Gemini...")

# Generate transcription/summary
response = client.models.generate_content(
    model="gemini-3.1-pro-preview",
    contents=[
        types.Content(
            role="user",
            parts=[
                types.Part.from_uri(file_uri=video_file.uri, mime_type="video/mp4"),
                types.Part.from_text(
                    text=(
                        "Przygotuj szczegółową transkrypcję tego spotkania w języku polskim. "
                        "Podaj kto mówił (jeśli da się rozróżnić osoby) i co powiedział. "
                        "Na końcu dodaj podsumowanie kluczowych tematów, ustaleń i action items."
                    )
                ),
            ],
        )
    ],
    config=types.GenerateContentConfig(
        temperature=0.1,
        max_output_tokens=65536,
    ),
)

elapsed = time.time() - t0
print(f"\n{'='*80}")
print(f"Done in {elapsed:.1f}s")
print(f"{'='*80}\n")
print(response.text)

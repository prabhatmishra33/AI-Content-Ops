

import httpx
import json
import os

BASE = os.getenv("API_BASE", "http://127.0.0.1:8000/api/v1")


def test_options():
    """GET /audio-news/options — see available voices, locales, defaults."""
    print("=" * 60)
    print("1. GET /audio-news/options")
    print("=" * 60)
    r = httpx.get(f"{BASE}/audio-news/options")
    r.raise_for_status()
    data = r.json()
    print(json.dumps(data, indent=2))
    return data


def test_generate():
    """POST /audio-news/generate — send raw details, get script + audio."""
    print("\n" + "=" * 60)
    print("2. POST /audio-news/generate")
    print("=" * 60)

    payload = {
        "raw_details": (
            "Major fire breaks out at a chemical factory in Pune, Maharashtra. "
            "Incident happened around 3 AM on April 22. "
            "12 workers were inside the facility at the time. "
            "All workers evacuated safely, no casualties reported. "
            "5 fire tenders rushed to the spot. "
            "Fire brought under control after 4 hours. "
            "Toxic fumes reported in nearby residential areas. "
            "District collector orders evacuation of 200 families within 1 km radius. "
            "NDRF team deployed for chemical hazard assessment. "
            "Factory owner says short circuit in the storage unit may be the cause. "
            "Police have registered an FIR and investigation is underway."
        ),
        "language": "Hindi",
        "style": "professional broadcast reporter",
        "voice": "Kore",
        "locale": "hi-IN",
        # "tts_model": "gemini-3.1-flash-tts-preview",   # optional override
        # "script_model": "gemini-2.0-flash",             # optional override
    }

    print(f"\nSending raw details ({len(payload['raw_details'])} chars)...")
    print(f"Voice: {payload['voice']}  |  Locale: {payload['locale']}  |  Language: {payload['language']}")
    print()

    # Longer timeout — script gen + TTS can take 30-60s
    r = httpx.post(f"{BASE}/audio-news/generate", json=payload, timeout=120.0)
    r.raise_for_status()
    data = r.json()

    print("✅ Generation successful!\n")
    print(f"  ID:         {data['id']}")
    print(f"  Duration:   {data['duration_s']}s")
    print(f"  Voice:      {data['voice']}")
    print(f"  Locale:     {data['locale']}")
    print(f"  Language:   {data['language']}")
    print(f"  Filename:   {data['filename']}")
    print(f"  Download:   {data['download_url']}")
    print(f"  Created:    {data['created_at']}")
    print(f"\n{'─' * 40}")
    print("📝 GENERATED SCRIPT:")
    print(f"{'─' * 40}")
    print(data["script"])
    print(f"{'─' * 40}\n")

    return data


def test_download(filename: str):
    """GET /audio-news/download/{filename} — download the MP3 file."""
    print("=" * 60)
    print(f"3. GET /audio-news/download/{filename}")
    print("=" * 60)

    r = httpx.get(f"{BASE}/audio-news/download/{filename}", timeout=30.0)
    r.raise_for_status()

    out_path = f"test_download_{filename}"
    with open(out_path, "wb") as f:
        f.write(r.content)

    size_kb = len(r.content) / 1024
    print(f"✅ Downloaded {size_kb:.1f} KB → {out_path}\n")
    return out_path


def test_list():
    """GET /audio-news/list — list all generated audio files."""
    print("=" * 60)
    print("4. GET /audio-news/list")
    print("=" * 60)

    r = httpx.get(f"{BASE}/audio-news/list")
    r.raise_for_status()
    data = r.json()
    print(f"Found {len(data)} audio file(s):")
    for item in data:
        print(f"  • {item['filename']}  (id={item['id']})")
    print()
    return data


# ── Run all tests ────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🎙️  Audio News Reporter API — Test Suite\n")

    # 1. Check available options
    test_options()

    # 2. Generate script + audio
    result = test_generate()

    # 3. Download the generated file
    test_download(result["filename"])

    # 4. List all files
    test_list()

    print("🎉 All tests passed!")

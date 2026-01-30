# Qwen-3-TTS Universal API 🎙️

A production-ready, universal Text-to-Speech API powered by Qwen-3-TTS running on Modal with L40S GPU. Use it from anywhere, anytime, in any project!

## 🎉 Features - Phase 1

✅ **High-quality speech** - State-of-the-art Qwen-3-TTS models  
✅ **Multiple voices** - 9 pre-built professional voices  
✅ **Voice cloning** - Clone any voice with just 3+ seconds of audio  
✅ **Voice design** - Create custom voices from text descriptions  
✅ **Emotion control** - Control tone, emotion, and speaking style  
✅ **Multi-language** - Supports 10 languages with auto-detection  
✅ **Multiple formats** - MP3 or WAV output  
✅ **R2 Storage** - Automatic upload to Cloudflare R2 with public URLs  
✅ **GPU Accelerated** - L40S GPU for fast generation  

## 📋 Supported Features

### Voice Modes
- **Custom Voice**: Use pre-built voices with emotion control
- **Voice Design**: Create voices from natural language descriptions  
- **Voice Clone**: Clone voices from reference audio  

### Languages
Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian + Auto-detection

### Pre-built Voices
| Voice | Description | Native Language |
|-------|-------------|-----------------|
| Ryan | Dynamic male voice with strong rhythmic drive | English |
| Aiden | Sunny American male voice with clear midrange | English |
| Vivian | Bright, slightly edgy young female voice | Chinese |
| Serena | Warm, gentle young female voice | Chinese |
| Uncle_Fu | Seasoned male voice with low, mellow timbre | Chinese |
| Dylan | Youthful Beijing male voice | Chinese (Beijing) |
| Eric | Lively Chengdu male voice | Chinese (Sichuan) |
| Ono_Anna | Playful Japanese female voice | Japanese |
| Sohee | Warm Korean female voice with rich emotion | Korean |

## 🚀 Setup

### 1. Install Modal
```bash
pip install modal
modal setup  # Authenticate with your Modal account
```

### 2. Configure R2 Credentials

Create a Modal secret named `r2-credentials` with your Cloudflare R2 credentials:

```bash
modal secret create r2-credentials \
  R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com \
  R2_ACCESS_KEY_ID=your_access_key \
  R2_SECRET_ACCESS_KEY=your_secret_key \
  R2_BUCKET_NAME=your-bucket-name \
  R2_PUBLIC_URL=https://pub-xxxxx.r2.dev
```

**Important Security Note**: Never commit credential files or API keys to version control. Store sensitive information only in environment variables or secure secret management systems like Modal secrets.

**Note**: Make sure your R2 bucket has public access enabled to serve audio files.

### 3. Deploy to Modal

```bash
modal deploy qwen3_tts_api.py
```

This will give you your API endpoints:
- `https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run` (TTS endpoint)
- `https://your-workspace--qwen3-tts-api-health.modal.run` (Health check)
- `https://your-workspace--qwen3-tts-api-list-voices.modal.run` (List voices)

## 📖 Usage Examples

### Example 1: Basic TTS with Pre-built Voice

```python
import requests
import json

API_URL = "https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run"

request_data = {
    "text": "Hello! This is a test of the Qwen-3-TTS API.",
    "mode": "custom_voice",
    "speaker": "Ryan",
    "language": "English",
    "output_format": "mp3",
    "upload_to_r2": True
}

response = requests.post(API_URL, json=request_data)
result = response.json()

print(f"Audio URL: {result['audio_url']}")
print(f"Generated at: {result['generated_at']}")
```

### Example 2: Emotion Control

```python
request_data = {
    "text": "I can't believe you did this to me!",
    "mode": "custom_voice",
    "speaker": "Aiden",
    "language": "English",
    "instruct": "Very angry and furious, screaming",  # ← Emotion control
    "output_format": "mp3"
}

response = requests.post(API_URL, json=request_data)
result = response.json()
print(f"Angry speech: {result['audio_url']}")
```

### Example 3: Voice Design (Custom Voice from Description)

```python
request_data = {
    "text": "Back in my day, we didn't have much, but we knew how to make it last.",
    "mode": "voice_design",  # ← Voice design mode
    "language": "English",
    "voice_description": "A very old man with a raspy, weak voice. Slow speech with pauses. Sounds tired and nostalgic.",
    "output_format": "mp3"
}

response = requests.post(API_URL, json=request_data)
result = response.json()
print(f"Custom designed voice: {result['audio_url']}")
```

### Example 4: Voice Cloning

```python
request_data = {
    "text": "We're excited to announce groundbreaking new features!",
    "mode": "voice_clone",  # ← Voice clone mode
    "language": "English",
    "reference_audio_url": "https://your-r2-bucket.r2.dev/reference-voice.mp3",
    "reference_text": "This is the transcript of my reference audio.",
    "x_vector_only": False,  # Set to True if you don't have transcript (lower quality)
    "output_format": "mp3"
}

response = requests.post(API_URL, json=request_data)
result = response.json()
print(f"Cloned voice: {result['audio_url']}")
```

### Example 5: Multi-language

```python
# Chinese with emotion
request_data = {
    "text": "其实我真的有发现，我是一个特别善于观察别人情绪的人。",
    "mode": "custom_voice",
    "speaker": "Vivian",
    "language": "Chinese",
    "instruct": "用特别愤怒的语气说",  # "Say it in a very angry tone"
    "output_format": "mp3"
}

# Japanese
request_data = {
    "text": "こんにちは、今日はとても良い天気ですね！",
    "mode": "custom_voice",
    "speaker": "Ono_Anna",
    "language": "Japanese",
    "output_format": "mp3"
}

# Auto-detect language
request_data = {
    "text": "Bonjour! Comment allez-vous?",  # French
    "mode": "custom_voice",
    "speaker": "Ryan",
    "language": "Auto",  # ← Will auto-detect French
    "output_format": "mp3"
}
```

### Example 6: Using from cURL

```bash
curl -X POST "https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The quick brown fox jumps over the lazy dog.",
    "mode": "custom_voice",
    "speaker": "Ryan",
    "language": "English",
    "instruct": "Very happy and enthusiastic",
    "output_format": "mp3",
    "upload_to_r2": true
  }'
```

### Example 7: Without R2 (Base64 Audio Response)

If you don't want to use R2, you can get the audio as base64:

```python
request_data = {
    "text": "Hello world!",
    "mode": "custom_voice",
    "speaker": "Ryan",
    "language": "English",
    "upload_to_r2": False  # ← Get base64 audio instead
}

response = requests.post(API_URL, json=request_data)
result = response.json()

# Decode and save audio
import base64
audio_bytes = base64.b64decode(result['audio_base64'])

with open('output.mp3', 'wb') as f:
    f.write(audio_bytes)
```

## 🔧 API Reference

### POST /api_generate_speech

**Request Body:**
```json
{
  "text": "string (required)",
  "mode": "custom_voice | voice_design | voice_clone (default: custom_voice)",
  "language": "string (default: Auto)",
  
  // Custom Voice parameters
  "speaker": "string (default: Ryan)",
  "instruct": "string (optional)",
  
  // Voice Design parameters
  "voice_description": "string (required for voice_design mode)",
  
  // Voice Clone parameters
  "reference_audio_url": "string (required for voice_clone mode)",
  "reference_text": "string (optional, improves quality)",
  "x_vector_only": "boolean (default: false)",
  
  // Output parameters
  "output_format": "wav | mp3 (default: mp3)",
  "upload_to_r2": "boolean (default: true)",
  
  // Advanced parameters
  "model_size": "1.7B | 0.6B (default: 1.7B)",
  "top_p": "float (default: 1.0)",
  "temperature": "float (default: 1.0)"
}
```

**Response (with R2):**
```json
{
  "status": "success",
  "audio_url": "https://pub-xxxxx.r2.dev/outputs/tts/tts_20260125_123456.mp3",
  "filename": "tts_20260125_123456.mp3",
  "format": "mp3",
  "sample_rate": 12000,
  "mode": "custom_voice",
  "language": "English",
  "generated_at": "2026-01-25T12:34:56.789Z"
}
```

**Response (without R2):**
```json
{
  "status": "success",
  "audio_base64": "base64_encoded_audio_data...",
  "format": "mp3",
  "sample_rate": 12000,
  "mode": "custom_voice",
  "language": "English",
  "generated_at": "2026-01-25T12:34:56.789Z"
}
```

### GET /health

Returns API health status and supported features.

### GET /list_voices

Returns list of all available pre-built voices with descriptions.

## 💰 Cost Estimate

With L40S GPU on Modal:
- **Processing time**: ~5-15 seconds for typical sentences
- **Cost per request**: ~$0.01-0.05 (depending on text length)
- **For 100 requests/month**: ~$1-5/month

Much cheaper than commercial TTS APIs! 🎉

## 🐛 Troubleshooting

### "R2 credentials not configured"
Make sure you've created the Modal secret with all required R2 credentials.

### "FlashAttention installation failed"
This is expected and handled gracefully. The API will work without it, just slightly slower.

### Audio quality issues with voice cloning
- Provide the `reference_text` transcript for better quality
- Use at least 3-8 seconds of clean reference audio
- Set `x_vector_only=False` for best quality

### Model loading is slow
First request takes ~30-60 seconds to download models. Subsequent requests are fast (~5-15s).

## 📝 Next Steps (Phase 2+)

Future enhancements:
- [ ] Streaming audio generation
- [ ] Multi-speaker dialogue
- [ ] Fine-tuning support
- [ ] Prosody control (speed, pitch adjustment)
- [ ] Batch processing
- [ ] WebSocket support for real-time streaming

## 📄 License

This API wrapper is MIT licensed. Qwen-3-TTS models are licensed under Apache-2.0 by Alibaba.

## 🙏 Credits

- **Qwen-3-TTS**: Alibaba Cloud Qwen Team
- **Modal**: Serverless GPU infrastructure
- **You**: For building awesome AI-powered projects!

---

**Built with ❤️ for universal, production-ready TTS**

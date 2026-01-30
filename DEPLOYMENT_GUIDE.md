# Qwen-3-TTS API Deployment Guide 🚀

Step-by-step guide to deploy your universal TTS API to Modal.

## Prerequisites

- [ ] Modal account ([sign up free](https://modal.com))
- [ ] Cloudflare R2 bucket with public access enabled
- [ ] Python 3.8+ installed locally

## Step 1: Install Modal CLI

```bash
pip install modal
```

## Step 2: Authenticate with Modal

```bash
modal setup
```

This will open a browser window to authenticate. Follow the prompts.

## Step 3: Set Up R2 Bucket

### 3.1 Create R2 Bucket in Cloudflare

1. Go to Cloudflare Dashboard → R2 Object Storage
2. Create a new bucket (e.g., `qwen-tts-outputs`)
3. Note your Account ID from the URL

### 3.2 Enable Public Access

1. Go to your bucket → Settings
2. Find "Public Access" setting
3. Enable "Allow Access" or set up R2.dev subdomain
4. Your public URL will be: `https://pub-<hash>.r2.dev`

### 3.3 Create R2 API Token

1. Go to R2 → Manage R2 API Tokens
2. Create API Token with:
   - **Permissions**: Object Read & Write
   - **Bucket**: Your bucket name
3. Copy:
   - Access Key ID
   - Secret Access Key

### 3.4 Get R2 Endpoint URL

Your endpoint URL format:
```
https://<account-id>.r2.cloudflarestorage.com
```

Replace `<account-id>` with your Cloudflare Account ID.

## Step 4: Configure Modal Secrets

Create a Modal secret with your R2 credentials:

```bash
modal secret create r2-credentials \
  R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com \
  R2_ACCESS_KEY_ID=your_access_key_here \
  R2_SECRET_ACCESS_KEY=your_secret_key_here \
  R2_BUCKET_NAME=qwen-tts-outputs \
  R2_PUBLIC_URL=https://pub-xxxxx.r2.dev
```

**Replace:**
- `<account-id>` with your Cloudflare Account ID
- `your_access_key_here` with your R2 Access Key ID
- `your_secret_key_here` with your R2 Secret Access Key
- `qwen-tts-outputs` with your bucket name
- `pub-xxxxx` with your actual R2 public URL hash

**Example:**
```bash
modal secret create r2-credentials \
  R2_ENDPOINT_URL=https://abc123def456.r2.cloudflarestorage.com \
  R2_ACCESS_KEY_ID=1a2b3c4d5e6f7g8h9i0j \
  R2_SECRET_ACCESS_KEY=k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6 \
  R2_BUCKET_NAME=qwen-tts-outputs \
  R2_PUBLIC_URL=https://pub-a1b2c3d4e5f6.r2.dev
```

## Step 5: Deploy to Modal

```bash
modal deploy qwen3_tts_api.py
```

**Expected output:**
```
✓ Initialized. View run at https://modal.com/...
✓ Created objects.
├── 🔨 Created mount /home/user/qwen3_tts_api.py
├── 🔨 Created function generate_speech
├── 🔨 Created web endpoint api_generate_speech
├── 🔨 Created web endpoint health
└── 🔨 Created web endpoint list_voices
✓ App deployed! 🎉

View Deployment: https://modal.com/apps/...

Endpoints:
  https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run
  https://your-workspace--qwen3-tts-api-health.modal.run
  https://your-workspace--qwen3-tts-api-list-voices.modal.run
```

**Copy your endpoint URLs!** You'll need them.

## Step 6: Test Your API

### Test 1: Health Check

```bash
curl https://your-workspace--qwen3-tts-api-health.modal.run
```

Expected response:
```json
{
  "status": "healthy",
  "service": "qwen3-tts-api",
  "supported_modes": ["custom_voice", "voice_design", "voice_clone"],
  ...
}
```

### Test 2: List Voices

```bash
curl https://your-workspace--qwen3-tts-api-list-voices.modal.run
```

### Test 3: Generate Speech

```bash
curl -X POST "https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello! This is a test of the Qwen-3-TTS API.",
    "mode": "custom_voice",
    "speaker": "Ryan",
    "language": "English",
    "output_format": "mp3",
    "upload_to_r2": true
  }'
```

Expected response:
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

**Open the `audio_url` in your browser to hear the generated speech!**

## Step 7: Use in Your Projects

### Python Example

Update `example_client.py` with your actual endpoints and run:

```python
# example_client.py
API_URL = "https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run"

result = generate_tts(
    text="Your text here",
    mode="custom_voice",
    speaker="Ryan",
    language="English"
)

print(f"Listen at: {result['audio_url']}")
```

### JavaScript/Node.js Example

```javascript
const API_URL = "https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run";

async function generateSpeech(text) {
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: text,
      mode: "custom_voice",
      speaker: "Ryan",
      language: "English",
      output_format: "mp3",
      upload_to_r2: true
    })
  });
  
  const result = await response.json();
  console.log(`Audio URL: ${result.audio_url}`);
  return result.audio_url;
}

generateSpeech("Hello from JavaScript!");
```

### Discord Bot Example

```python
import discord
import requests

API_URL = "https://your-workspace--qwen3-tts-api-api-generate-speech.modal.run"

@bot.command()
async def speak(ctx, *, text: str):
    """Generate speech from text"""
    
    # Generate TTS
    response = requests.post(API_URL, json={
        "text": text,
        "mode": "custom_voice",
        "speaker": "Ryan",
        "language": "Auto",
        "output_format": "mp3"
    })
    
    result = response.json()
    
    # Send audio URL
    await ctx.send(f"🎙️ Generated speech: {result['audio_url']}")
```

## Step 8: Monitor Usage and Costs

View your Modal dashboard to monitor:
- Request count
- GPU usage time
- Costs

**Typical costs with L40S:**
- ~$0.01-0.05 per request
- ~$1-5 for 100 requests/month

## Troubleshooting

### Issue: "R2 credentials not configured"

**Solution:** Make sure you created the Modal secret correctly:
```bash
modal secret list  # Check if r2-credentials exists
```

If missing, recreate it using Step 4.

### Issue: "Failed to download audio file"

**Solution:** Your R2 bucket needs public access enabled. Check:
1. Bucket Settings → Public Access → Enabled
2. Or use R2.dev subdomain

### Issue: First request is very slow (30-60 seconds)

**Expected behavior!** The first request downloads the model (~4GB). Subsequent requests are fast (5-15 seconds).

### Issue: "AttributeError: module 'whisperx' has no attribute..."

**Wrong file!** You're running the transcription API instead of the TTS API. Make sure you're using `qwen3_tts_api.py`.

### Issue: Audio quality is poor with voice cloning

**Solutions:**
1. Provide the `reference_text` transcript
2. Use at least 5-8 seconds of clean reference audio
3. Set `x_vector_only=False` for best quality
4. Use the 1.7B model instead of 0.6B

## Next Steps

Now that your API is deployed:

1. ✅ Test all three modes (custom_voice, voice_design, voice_clone)
2. ✅ Try different emotions and languages
3. ✅ Integrate into your projects (bots, websites, apps)
4. ✅ Monitor costs and optimize model size if needed

## Advanced Configuration

### Use 0.6B Model (Faster, Cheaper)

In your API requests, set:
```json
{
  "model_size": "0.6B"  // Instead of default "1.7B"
}
```

**Trade-off:**
- 0.6B: Faster (~3-5s), cheaper (~$0.005/request), slightly lower quality
- 1.7B: Slower (~5-15s), more expensive (~$0.01-0.05/request), better quality

### Adjust Generation Parameters

Fine-tune speech generation:
```json
{
  "top_p": 0.9,        // Nucleus sampling (0.0-1.0)
  "temperature": 0.8,  // Randomness (0.0-2.0)
  "top_k": 50          // Top-k sampling
}
```

**Recommendations:**
- **More consistent**: `top_p=1.0, temperature=1.0` (default)
- **More creative**: `top_p=0.9, temperature=1.2`
- **More deterministic**: `top_p=0.95, temperature=0.8`

## Support

Questions? Issues?
- Check Modal logs: `modal app logs qwen3-tts-api`
- View deployments: https://modal.com/apps

---

**You're all set!** 🎉 You now have a universal TTS API that works anywhere, anytime!

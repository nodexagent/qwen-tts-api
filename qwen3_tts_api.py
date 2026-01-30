import modal
import os
import json
import tempfile
import io
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Literal

# Define the image with Qwen-3-TTS dependencies
image = (
    modal.Image.debian_slim()
    .apt_install(
        "git", "ffmpeg", "wget", "libsndfile1",
        "pkg-config", "libsox-dev", "sox"
    )
    .run_commands(
        "pip install --upgrade pip wheel setuptools",
        # Install PyTorch with CUDA support (using latest available version to avoid compatibility issues)
        "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121",
        # Install Qwen-TTS and dependencies
        "pip install qwen-tts transformers==4.57.3 accelerate soundfile librosa boto3",
        # Install flash-attention for efficiency (optional but recommended)
        "pip install flash-attn --no-build-isolation || echo 'FlashAttention installation failed, continuing without it'",
        # Install pydub for audio format conversion
        "pip install pydub"
    )
)

# Define Modal app
app = modal.App("qwen3-tts-api", image=image)

# Define request models
class TTSRequest(BaseModel):
    text: str
    mode: Literal["custom_voice", "voice_design", "voice_clone"] = "custom_voice"
    language: str = "Auto"  # Auto, Chinese, English, Japanese, Korean, etc.
    
    # Custom Voice parameters
    speaker: Optional[str] = "Ryan"  # Vivian, Serena, Uncle_Fu, Dylan, Eric, Ryan, Aiden, Ono_Anna, Sohee
    instruct: Optional[str] = None  # Emotion/style instruction (e.g., "Very happy and excited")
    
    # Voice Design parameters
    voice_description: Optional[str] = None  # Natural language voice description
    
    # Voice Clone parameters
    reference_audio_url: Optional[str] = None  # URL to reference audio for cloning
    reference_text: Optional[str] = None  # Transcript of reference audio
    x_vector_only: bool = False  # If True, reference_text not needed (lower quality)
    
    # Output parameters
    output_format: Literal["wav", "mp3"] = "mp3"
    upload_to_r2: bool = True
    
    # Advanced parameters
    model_size: Literal["1.7B", "0.6B"] = "1.7B"
    top_p: Optional[float] = 1.0
    top_k: Optional[int] = None
    temperature: Optional[float] = 1.0


@app.function(
    gpu="L40S",
    timeout=600,  # 10 minutes for longer text
    secrets=[modal.Secret.from_name("r2-credentials")]  # R2 credentials stored in Modal secrets
)
def generate_speech(request_data: dict):
    """
    Generate speech using Qwen-3-TTS with L40S GPU
    """
    import torch
    import torchaudio
    import soundfile as sf
    import boto3
    from pydub import AudioSegment
    import requests
    import collections
    import typing
    import os

    # ========== PYTORCH COMPATIBILITY PATCHES ==========
    # Patch torchaudio backend (may be removed in newer versions)
    if not hasattr(torchaudio, 'set_audio_backend'):
        # Monkey patch for compatibility
        torchaudio.set_audio_backend = lambda x: None

    # Monkey patch torch.load to disable weights_only if needed
    original_torch_load = torch.load

    def patched_torch_load(*args, **kwargs):
        if 'weights_only' in kwargs:
            kwargs['weights_only'] = False
        elif len(args) >= 3:  # If weights_only is passed as positional arg
            args = args[:2] + (False,) + args[3:]
        return original_torch_load(*args, **kwargs)

    torch.load = patched_torch_load
    # ========== END COMPATIBILITY PATCHES ==========
    
    # Parse request
    request = TTSRequest(**request_data)
    
    # Determine device
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    
    print(f"Using device: {device}, dtype: {dtype}")
    print(f"Mode: {request.mode}, Language: {request.language}")
    
    # Import Qwen3TTSModel
    from qwen_tts import Qwen3TTSModel
    
    # Determine model name based on mode and size
    if request.mode == "custom_voice":
        model_name = f"Qwen/Qwen3-TTS-12Hz-{request.model_size}-CustomVoice"
    elif request.mode == "voice_design":
        model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"  # Only 1.7B available for voice design
    else:  # voice_clone
        model_name = f"Qwen/Qwen3-TTS-12Hz-{request.model_size}-Base"
    
    print(f"Loading model: {model_name}")
    
    # Load model with flash attention if available
    try:
        model = Qwen3TTSModel.from_pretrained(
            model_name,
            device_map=device,
            dtype=dtype,
            attn_implementation="flash_attention_2",
        )
    except Exception as e:
        print(f"FlashAttention failed, loading without it: {e}")
        model = Qwen3TTSModel.from_pretrained(
            model_name,
            device_map=device,
            dtype=dtype,
        )
    
    # Prepare generation kwargs
    gen_kwargs = {}
    if request.top_p is not None:
        gen_kwargs['top_p'] = request.top_p
    if request.top_k is not None:
        gen_kwargs['top_k'] = request.top_k
    if request.temperature is not None:
        gen_kwargs['temperature'] = request.temperature
    
    # Generate speech based on mode
    if request.mode == "custom_voice":
        print(f"Generating with custom voice: {request.speaker}")
        wavs, sr = model.generate_custom_voice(
            text=request.text,
            language=request.language,
            speaker=request.speaker,
            instruct=request.instruct or "",
            **gen_kwargs
        )
    
    elif request.mode == "voice_design":
        if not request.voice_description:
            raise ValueError("voice_description is required for voice_design mode")
        
        print(f"Generating with voice design: {request.voice_description[:50]}...")
        wavs, sr = model.generate_voice_design(
            text=request.text,
            language=request.language,
            instruct=request.voice_description,
            **gen_kwargs
        )
    
    elif request.mode == "voice_clone":
        if not request.reference_audio_url:
            raise ValueError("reference_audio_url is required for voice_clone mode")

        print(f"Cloning voice from: {request.reference_audio_url}")

        # Download reference audio inside Modal to avoid external access issues
        import requests as req_lib
        import tempfile
        import os

        try:
            # Download the audio file from the URL
            response = req_lib.get(request.reference_audio_url)
            response.raise_for_status()  # Raise an exception for bad status codes

            # Create a temporary file to store the audio
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                temp_audio.write(response.content)
                temp_audio_path = temp_audio.name

            print(f"Downloaded reference audio to: {temp_audio_path}")

            # Use the local file path for voice cloning
            wavs, sr = model.generate_voice_clone(
                text=request.text,
                language=request.language,
                ref_audio=temp_audio_path,  # Use local file instead of URL
                ref_text=request.reference_text or "",
                x_vector_only_mode=request.x_vector_only,
                **gen_kwargs
            )

            # Clean up the temporary file after use
            os.unlink(temp_audio_path)

        except Exception as e:
            # Make sure to clean up even if there's an error
            if 'temp_audio_path' in locals():
                try:
                    os.unlink(temp_audio_path)
                except:
                    pass
            raise e
    
    # Save audio to temporary WAV file
    temp_wav_path = "/tmp/output.wav"
    sf.write(temp_wav_path, wavs[0], sr)
    
    # Convert to requested format if MP3
    if request.output_format == "mp3":
        temp_output_path = "/tmp/output.mp3"
        audio = AudioSegment.from_wav(temp_wav_path)
        audio.export(temp_output_path, format="mp3", bitrate="192k")
    else:
        temp_output_path = temp_wav_path
    
    # Upload to R2 if requested
    if request.upload_to_r2:
        # Get R2 credentials from Modal secrets
        r2_endpoint = os.environ.get("R2_ENDPOINT_URL")
        r2_access_key = os.environ.get("R2_ACCESS_KEY_ID")
        r2_secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
        r2_bucket = os.environ.get("R2_BUCKET_NAME")
        r2_public_url = os.environ.get("R2_PUBLIC_URL")  # e.g., "https://pub-xxxxx.r2.dev"
        
        if not all([r2_endpoint, r2_access_key, r2_secret_key, r2_bucket]):
            raise ValueError("R2 credentials not configured in Modal secrets")
        
        # Initialize R2 client
        s3_client = boto3.client(
            's3',
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key
        )
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"tts_{timestamp}.{request.output_format}"
        r2_key = f"outputs/tts/{filename}"
        
        # Upload to R2
        with open(temp_output_path, 'rb') as f:
            s3_client.upload_fileobj(
                f,
                r2_bucket,
                r2_key,
                ExtraArgs={'ContentType': f'audio/{request.output_format}'}
            )
        
        # Construct public URL
        audio_url = f"{r2_public_url}/{r2_key}"
        
        # Clean up temp files
        os.remove(temp_wav_path)
        if request.output_format == "mp3":
            os.remove(temp_output_path)
        
        return {
            "status": "success",
            "audio_url": audio_url,
            "filename": filename,
            "format": request.output_format,
            "sample_rate": sr,
            "mode": request.mode,
            "language": request.language,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    else:
        # Return audio as base64 (for direct download without R2)
        import base64
        with open(temp_output_path, 'rb') as f:
            audio_bytes = f.read()
        
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        # Clean up temp files
        os.remove(temp_wav_path)
        if request.output_format == "mp3":
            os.remove(temp_output_path)
        
        return {
            "status": "success",
            "audio_base64": audio_base64,
            "format": request.output_format,
            "sample_rate": sr,
            "mode": request.mode,
            "language": request.language,
            "generated_at": datetime.utcnow().isoformat()
        }


@app.function(timeout=600)
@modal.web_endpoint(method="POST")
async def api_generate_speech(request: TTSRequest):
    """
    Main TTS API endpoint
    
    Supports three modes:
    1. custom_voice: Use pre-built voices (Ryan, Aiden, Vivian, etc.)
    2. voice_design: Create custom voice from text description
    3. voice_clone: Clone voice from 3+ seconds of reference audio
    
    Returns audio URL (if upload_to_r2=True) or base64 audio data
    """
    # Spawn GPU function
    future = generate_speech.spawn(request.model_dump())
    
    # Wait for result
    result = future.get()
    
    return result


@app.function()
@modal.web_endpoint(method="GET")
def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "qwen3-tts-api",
        "supported_modes": ["custom_voice", "voice_design", "voice_clone"],
        "supported_languages": [
            "Auto", "Chinese", "English", "Japanese", "Korean",
            "German", "French", "Russian", "Portuguese", "Spanish", "Italian"
        ],
        "supported_speakers": [
            "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
            "Ryan", "Aiden", "Ono_Anna", "Sohee"
        ]
    }


@app.function()
@modal.web_endpoint(method="GET")
def list_voices():
    """List all available pre-built voices with descriptions"""
    voices = {
        "Vivian": {"description": "Bright, slightly edgy young female voice", "language": "Chinese"},
        "Serena": {"description": "Warm, gentle young female voice", "language": "Chinese"},
        "Uncle_Fu": {"description": "Seasoned male voice with low, mellow timbre", "language": "Chinese"},
        "Dylan": {"description": "Youthful Beijing male voice with clear, natural timbre", "language": "Chinese (Beijing)"},
        "Eric": {"description": "Lively Chengdu male voice with slightly husky brightness", "language": "Chinese (Sichuan)"},
        "Ryan": {"description": "Dynamic male voice with strong rhythmic drive", "language": "English"},
        "Aiden": {"description": "Sunny American male voice with clear midrange", "language": "English"},
        "Ono_Anna": {"description": "Playful Japanese female voice with light, nimble timbre", "language": "Japanese"},
        "Sohee": {"description": "Warm Korean female voice with rich emotion", "language": "Korean"}
    }
    
    return {
        "voices": voices,
        "total": len(voices)
    }


# Local test entrypoint
@app.local_entrypoint()
def test_locally():
    """Test the TTS API locally"""
    test_request = {
        "text": "Hello! This is a test of the Qwen-3-TTS API. The quick brown fox jumps over the lazy dog.",
        "mode": "custom_voice",
        "speaker": "Ryan",
        "language": "English",
        "instruct": "Very enthusiastic and energetic",
        "output_format": "mp3",
        "upload_to_r2": True
    }
    
    result = generate_speech.remote(test_request)
    print(json.dumps(result, indent=2))

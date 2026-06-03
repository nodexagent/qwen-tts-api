import modal
import os
import json
import tempfile
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Literal

# Define the image with Qwen-3-TTS dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "git", "ffmpeg", "wget", "libsndfile1",
        "pkg-config", "libsox-dev", "sox"
    )
    .run_commands(
        "pip install --upgrade pip wheel setuptools",
        "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121",
        "pip install qwen-tts transformers==4.57.3 accelerate soundfile librosa boto3",
        "pip install flash-attn --no-build-isolation || echo 'FlashAttention installation failed, continuing without it'",
        "pip install pydub"
    )
)

app = modal.App("qwen3-tts-api", image=image)

# Persistent volume — models are downloaded here once and reused across all
# container restarts.  Without this, every cold start re-downloads 2-5 GB
# from HuggingFace which takes 5-10 minutes and eats the method timeout.
model_volume = modal.Volume.from_name("qwen-tts-models", create_if_missing=True)
MODEL_CACHE_DIR = "/models"

# The two models we pre-load at container startup so the first request is fast.
PRELOAD_MODELS = [
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
]


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


@app.cls(
    gpu="L40S",
    timeout=900,                # 15 min — covers model load (5-10 min) + inference
    secrets=[modal.Secret.from_name("r2-credentials-tts")],
    min_containers=0,           # Scale to zero when idle
    scaledown_window=60,        # Sleep after 60s of no requests
    max_containers=5,           # Handle 5 concurrent jobs
    volumes={MODEL_CACHE_DIR: model_volume},
)
class TTSService:

    @modal.enter()
    def setup(self):
        """
        Runs once when the container starts.

        Key change: pre-loads the two most-used models here so the first
        request only does inference (fast) instead of model loading (slow).

        HF_HOME is pointed at the Modal Volume so downloaded model weights
        persist across container restarts — no re-downloading on cold start.
        """
        import torch
        import torchaudio

        # Point HuggingFace cache at the persistent volume
        os.environ["HF_HOME"] = MODEL_CACHE_DIR
        os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_DIR
        os.environ["HF_DATASETS_CACHE"] = MODEL_CACHE_DIR

        # Patch torchaudio backend (compatibility for older versions)
        if not hasattr(torchaudio, 'set_audio_backend'):
            torchaudio.set_audio_backend = lambda x: None

        # Patch torch.load weights_only flag
        original_torch_load = torch.load

        def patched_torch_load(*args, **kwargs):
            if 'weights_only' in kwargs:
                kwargs['weights_only'] = False
            elif len(args) >= 3:
                args = args[:2] + (False,) + args[3:]
            return original_torch_load(*args, **kwargs)

        torch.load = patched_torch_load

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        self._models = {}

        print(f"Container ready. Device: {self.device}, dtype: {self.dtype}")
        print(f"Model cache dir: {MODEL_CACHE_DIR}")

        # Pre-load models so the first request doesn't time out waiting
        for model_name in PRELOAD_MODELS:
            try:
                self._get_model(model_name)
                print(f"Pre-loaded: {model_name}")
            except Exception as e:
                print(f"WARNING: failed to pre-load {model_name}: {e}")

    def _get_model(self, model_name: str):
        """Load model on first use, then return cached version."""
        if model_name not in self._models:
            from qwen_tts import Qwen3TTSModel
            print(f"Loading model: {model_name}")
            try:
                model = Qwen3TTSModel.from_pretrained(
                    model_name,
                    device_map=self.device,
                    dtype=self.dtype,
                    attn_implementation="flash_attention_2",
                    cache_dir=MODEL_CACHE_DIR,
                )
            except Exception as e:
                print(f"FlashAttention failed, loading without it: {e}")
                model = Qwen3TTSModel.from_pretrained(
                    model_name,
                    device_map=self.device,
                    dtype=self.dtype,
                    cache_dir=MODEL_CACHE_DIR,
                )
            self._models[model_name] = model
            print(f"Model ready: {model_name}")
        return self._models[model_name]

    @modal.method()
    def generate(self, request_data: dict):
        """
        Generate speech using cached model.
        Called directly (e.g., from local_entrypoint or other Modal functions).
        """
        return self._run_generation(TTSRequest(**request_data))

    @modal.fastapi_endpoint(method="POST")
    def api_generate_speech(self, request: TTSRequest):
        """
        Main TTS API endpoint.

        Supports three modes:
        1. custom_voice: Use pre-built voices (Ryan, Aiden, Vivian, etc.)
        2. voice_design: Create custom voice from text description
        3. voice_clone: Clone voice from 3+ seconds of reference audio

        Returns audio URL (if upload_to_r2=True) or base64 audio data.
        """
        return self._run_generation(request)

    @modal.fastapi_endpoint(method="GET")
    def health_check(self):
        """Health check — confirms the service and pre-loaded models are ready."""
        return {
            "status": "healthy",
            "service": "qwen3-tts-api",
            "models_loaded": list(self._models.keys()),
            "device": self.device,
        }

    def _run_generation(self, request: TTSRequest):
        import soundfile as sf
        import boto3
        from pydub import AudioSegment
        import base64

        # Determine model name based on mode and size
        if request.mode == "custom_voice":
            model_name = f"Qwen/Qwen3-TTS-12Hz-{request.model_size}-CustomVoice"
        elif request.mode == "voice_design":
            model_name = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
        else:  # voice_clone
            model_name = f"Qwen/Qwen3-TTS-12Hz-{request.model_size}-Base"

        model = self._get_model(model_name)

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
            import requests as req_lib

            print(f"Cloning voice from: {request.reference_audio_url}")
            temp_audio_path = None
            try:
                response = req_lib.get(request.reference_audio_url)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                    tmp.write(response.content)
                    temp_audio_path = tmp.name

                wavs, sr = model.generate_voice_clone(
                    text=request.text,
                    language=request.language,
                    ref_audio=temp_audio_path,
                    ref_text=request.reference_text or "",
                    x_vector_only_mode=request.x_vector_only,
                    **gen_kwargs
                )
            finally:
                if temp_audio_path and os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)

        # Use unique temp paths to avoid collisions between concurrent requests
        tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp_wav.close()
        sf.write(tmp_wav.name, wavs[0], sr)

        if request.output_format == "mp3":
            tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tmp_out.close()
            AudioSegment.from_wav(tmp_wav.name).export(tmp_out.name, format="mp3", bitrate="192k")
            output_path = tmp_out.name
        else:
            output_path = tmp_wav.name

        try:
            if request.upload_to_r2:
                r2_endpoint = os.environ.get("R2_ENDPOINT_URL")
                r2_access_key = os.environ.get("R2_ACCESS_KEY_ID")
                r2_secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
                r2_bucket = os.environ.get("R2_BUCKET_NAME")
                r2_public_url = os.environ.get("R2_PUBLIC_URL")

                if not all([r2_endpoint, r2_access_key, r2_secret_key, r2_bucket]):
                    raise ValueError("R2 credentials not configured in Modal secrets")

                s3_client = boto3.client(
                    's3',
                    endpoint_url=r2_endpoint,
                    aws_access_key_id=r2_access_key,
                    aws_secret_access_key=r2_secret_key
                )

                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"tts_{timestamp}.{request.output_format}"
                r2_key = f"outputs/tts/{filename}"

                with open(output_path, 'rb') as f:
                    s3_client.upload_fileobj(
                        f, r2_bucket, r2_key,
                        ExtraArgs={'ContentType': f'audio/{request.output_format}'}
                    )

                return {
                    "status": "success",
                    "audio_url": f"{r2_public_url}/{r2_key}",
                    "filename": filename,
                    "format": request.output_format,
                    "sample_rate": sr,
                    "mode": request.mode,
                    "language": request.language,
                    "generated_at": datetime.utcnow().isoformat()
                }

            else:
                with open(output_path, 'rb') as f:
                    audio_base64 = __import__('base64').b64encode(f.read()).decode('utf-8')

                return {
                    "status": "success",
                    "audio_base64": audio_base64,
                    "format": request.output_format,
                    "sample_rate": sr,
                    "mode": request.mode,
                    "language": request.language,
                    "generated_at": datetime.utcnow().isoformat()
                }

        finally:
            for path in [tmp_wav.name, output_path]:
                if os.path.exists(path):
                    os.remove(path)


@app.function()
@modal.fastapi_endpoint(method="GET")
def health():
    """Lightweight health check (no model loading)."""
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
@modal.fastapi_endpoint(method="GET")
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
    return {"voices": voices, "total": len(voices)}


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

    service = TTSService()
    result = service.generate.remote(test_request)
    print(json.dumps(result, indent=2))

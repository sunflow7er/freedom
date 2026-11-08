"""Whisper-based audio analysis for voice call evaluation."""
import json
import os
import tempfile
from typing import Optional

import httpx

WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def is_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def analyze_call_audio(audio_url: str) -> dict:
    """
    Download audio from URL, run Whisper transcription, extract quality metrics.
    Returns a dict with metrics or raises on error.
    """
    # Download audio
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(audio_url)
        resp.raise_for_status()

    # Detect extension
    clean_url = audio_url.split("?")[0]
    ext = ".mp3"
    if "." in clean_url.split("/")[-1]:
        candidate = "." + clean_url.rsplit(".", 1)[-1].lower()
        if candidate in (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".webm", ".opus"):
            ext = candidate

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = tmp.name

    try:
        model = _get_model()
        segments_gen, info = model.transcribe(
            tmp_path,
            word_timestamps=True,
            vad_filter=True,
        )
        segments = list(segments_gen)

        all_words = []
        segment_list = []
        for seg in segments:
            words_data = []
            if seg.words:
                for w in seg.words:
                    words_data.append({
                        "word": w.word,
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "prob": round(w.probability, 3),
                    })
                    all_words.append(w)
            segment_list.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
                "avg_logprob": round(seg.avg_logprob, 3),
                "no_speech_prob": round(seg.no_speech_prob, 3),
                "words": words_data,
            })

        total_duration = round(info.duration, 1)
        speech_duration = sum(s["end"] - s["start"] for s in segment_list)

        # Speech rate (words per minute)
        wpm = round(len(all_words) / (speech_duration / 60)) if speech_duration > 0 else 0

        # Pauses between segments ≥ 2 seconds
        pauses = []
        for i in range(1, len(segment_list)):
            gap = segment_list[i]["start"] - segment_list[i - 1]["end"]
            if gap >= 2.0:
                pauses.append(round(gap, 1))

        # Diction score: mean word probability → scale 0-10
        word_probs = [w.probability for w in all_words]
        avg_prob = sum(word_probs) / len(word_probs) if word_probs else 0.0
        diction_score = round(avg_prob * 10, 1)

        # Avg logprob across segments (clarity proxy; closer to 0 = clearer)
        avg_logprob = (
            round(sum(s["avg_logprob"] for s in segment_list) / len(segment_list), 3)
            if segment_list else -1.0
        )

        # Filler words (Russian/Kazakh hesitation markers)
        fillers = {"ну", "э", "эм", "мм", "вот", "значит", "ну вот", "как бы", "типа", "это"}
        filler_count = sum(
            1 for w in all_words
            if w.word.strip(" .,!?").lower() in fillers
        )

        return {
            "total_duration_sec": total_duration,
            "speech_duration_sec": round(speech_duration, 1),
            "word_count": len(all_words),
            "speech_rate_wpm": wpm,
            "pause_count": len(pauses),
            "long_pause_count": sum(1 for p in pauses if p >= 5.0),
            "pauses_sec": sorted(pauses, reverse=True)[:5],
            "diction_score": diction_score,
            "avg_logprob": avg_logprob,
            "filler_word_count": filler_count,
            "model": f"faster-whisper-{WHISPER_MODEL_SIZE}",
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def build_audio_context(metrics: dict) -> str:
    """Format audio metrics as a context block for the LLM prompt."""
    if not metrics:
        return ""

    pause_info = ""
    if metrics.get("pause_count", 0) > 0:
        pauses = metrics.get("pauses_sec", [])
        longest = pauses[0] if pauses else 0
        pause_info = f"Pauses ≥2s: {metrics['pause_count']} (longest: {longest}s, long pauses ≥5s: {metrics['long_pause_count']})"
    else:
        pause_info = "Pauses ≥2s: none detected"

    diction = metrics.get("diction_score", 0)
    if diction >= 8.5:
        diction_label = "excellent"
    elif diction >= 7.0:
        diction_label = "good"
    elif diction >= 5.5:
        diction_label = "acceptable"
    else:
        diction_label = "poor (unclear speech)"

    fillers = metrics.get("filler_word_count", 0)
    filler_label = "none" if fillers == 0 else f"{fillers} occurrences"

    return f"""
[AUDIO ANALYSIS — Whisper {metrics.get('model', '')}]
Duration: {metrics.get('total_duration_sec', '?')}s | Speech: {metrics.get('speech_duration_sec', '?')}s
Speech rate: {metrics.get('speech_rate_wpm', '?')} words/min (normal: 100-160 wpm)
Diction clarity: {diction}/10 — {diction_label}
Filler words: {filler_label}
{pause_info}

Use these acoustic metrics when evaluating criterion c06 (dialog management, pauses, speech quality).
A diction score below 6.0 suggests unclear pronunciation. Excessive pauses (>5 each, or any ≥10s) indicate poor pacing.
"""

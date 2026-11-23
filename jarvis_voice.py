"""
Accio Jarvis — Sesli Etkilesimli Asistan (Zero-VRAM, Ultra-Lightweight)
Mimari:
- STT: Google Speech Recognition (Ucretsiz, Turkce)
- LLM: Groq / OpenAI / Gemini API (Ultra-hizli, Llama 3.3 70B veya GPT)
- TTS: Microsoft Edge Neural TTS (tr-TR-AhmetNeural) + winsound (Yerel Windows Audio)
"""

import os
import sys
import time
import wave
import asyncio
import subprocess
import winsound
import numpy as np
import sounddevice as sd
import speech_recognition as sr
import requests

# Ses Motoru Konfigurasyonu
VOICE_NAME = "tr-TR-EmelNeural" # Tatli, dogal kadin sesi (Microsoft Neural)
VOICE_RATE = "+5%"               # Akici konusma hizi
VOICE_PITCH = "+3Hz"             # Sicak ve dogal ton
SAMPLE_RATE = 16000
CHANNELS = 1

# API Konfigurasyonu (Ortam degiskeni veya dogrudan giris)
# Ucretsiz Groq anahtari almak icin: https://console.groq.com/keys
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# FFmpeg tespiti (imageio_ffmpeg veya sistem yolu)
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_EXE = "ffmpeg"

SYSTEM_PROMPT = """Sen Negr1'in (18 yasinda, YKS 2027 sayisal adayi) kisisel calisma asistanisin.
Karakterin ve konusma tarzin:
1. Tatli, enerjik, samimi ve arkadas canlisi bir kiz gibi konus.
2. Gereksiz resmiyet veya robotiklik yapma; cana yakin ve motive edici ol.
3. Matematik, fizik veya ders sorularinda cozum mantigini net, basit ve akici anlat.
4. Yanitlarin seslendirilecegi icin karmasik tablolar, formuller veya ozel semboller yerine dogrudan konusma diline uygun cumleler kur.
"""

def speak(text):
    """Metni Edge-TTS ile sese cevirir ve hoparlorden calar."""
    if not text or not text.strip():
        return
    print(f"\n[Asistan Konusuyor]: {text}")
    mp3_path = "temp_voice.mp3"
    wav_path = "temp_voice.wav"
    
    try:
        # 1. Edge-TTS sentezi (Kadin sesi + Akici ton)
        import edge_tts
        async def run_tts():
            comm = edge_tts.Communicate(text, VOICE_NAME, rate=VOICE_RATE, pitch=VOICE_PITCH)
            await comm.save(mp3_path)
        asyncio.run(run_tts())
        
        # 2. MP3 -> WAV donusumu (winsound icin)
        subprocess.run(
            [FFMPEG_EXE, "-y", "-i", mp3_path, wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        
        # 3. Ses cikisi
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
    except Exception as e:
        print(f"[TTS Hatasi]: {e}")
    finally:
        for f in [mp3_path, wav_path]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

def record_audio(duration=None):
    """Mikrofondan ses kaydeder (Enter ile baslat / bitir veya sabit sure)."""
    wav_file = "temp_input.wav"
    print("\n[Mikrofon]: Kayit basladi! Konusman bitince Enter'a bas...")
    
    audio_frames = []
    is_recording = True
    
    def callback(indata, frames, time_info, status):
        if is_recording:
            audio_frames.append(indata.copy())
            
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16', callback=callback)
    with stream:
        input() # Enter tusuna basana kadar kaydeder
        is_recording = False
        
    print("[Mikrofon]: Kayit tamamlandi, isleniyor...")
    if not audio_frames:
        return None
        
    audio_data = np.concatenate(audio_frames, axis=0)
    with wave.open(wav_file, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())
        
    return wav_file

def transcribe_audio(wav_path):
    """Kaydedilen sesi Google STT ile Turkce metne cevirir."""
    if not wav_path or not os.path.exists(wav_path):
        return ""
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio, language="tr-TR")
            return text
    except sr.UnknownValueError:
        print("[STT]: Ses anlasilamadi.")
        return ""
    except Exception as e:
        print(f"[STT Hatasi]: {e}")
        return ""
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass

def get_llm_response(prompt, conversation_history, api_key):
    """Groq API (Llama 3.3 70B) uzerinden ultra-hizli yanit alir."""
    if not api_key:
        return "Groq API anahtari tanimli degil. Lutfen API anahtarini gir veya komut satirina yaz."
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history[-6:]) # Son 3 turu koru
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": 400,
        "temperature": 0.5
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        else:
            return f"API Hatasi ({resp.status_code}): {resp.text}"
    except Exception as e:
        return f"Baglanti Hatasi: {e}"

def main():
    print("=" * 60)
    print("      ACCIO JARVIS — SESLI ILETISIM SISTEMI (v1.0)")
    print("=" * 60)
    print("Ses Motoru: Microsoft Edge Neural (tr-TR-AhmetNeural)")
    print("Girdi: sounddevice + Google Speech Recognition (STT)")
    print("Beyin: Groq Llama 3.3 70B Versatile (~300 tokens/sn)")
    print("-" * 60)
    
    global GROQ_API_KEY
    # 1. api_key.txt dosyasindan kontrol et
    if not GROQ_API_KEY and os.path.exists("api_key.txt"):
        try:
            with open("api_key.txt", "r", encoding="utf-8") as f:
                GROQ_API_KEY = f.read().strip()
            if GROQ_API_KEY:
                print("[Sistem]: API anahtari api_key.txt dosyasindan basariyla okundu.")
        except Exception:
            pass

    # 2. Hala yoksa konsoldan sor
    if not GROQ_API_KEY:
        key_input = input("Groq API Key gir (Enter'a basarsan cevrimdisi ses testi calisir): ").strip()
        if key_input:
            GROQ_API_KEY = key_input
            
    speak("Selam Negr1! Ben hazırım, dinliyorum.")
    
    history = []
    
    while True:
        print("\n[Menu]:")
        print("1. [Enter] Tusuna bas -> Konusmaya basla -> Bitince [Enter]'a bas")
        print("2. [Yazi]   Metin yazarak soru sor (t yaz)")
        print("3. [Cikis]  Kapatmak icin q yaz")
        
        choice = input("\nSecimin: ").strip().lower()
        if choice == 'q':
            speak("Gorusmek uzere. Iyi calismalar.")
            break
        elif choice == 't':
            user_text = input("Sorun: ").strip()
        else:
            wav_file = record_audio()
            if not wav_file:
                continue
            user_text = transcribe_audio(wav_file)
            
        if not user_text:
            continue
            
        print(f"\n[Sen]: {user_text}")
        
        if not GROQ_API_KEY:
            ans = f"Sesini duydum Negr1: '{user_text}'. Bir Groq API anahtari girersen sana dogrudan yanit verebilirim."
        else:
            print("[Jarvis]: Yanit uretiliyor...")
            ans = get_llm_response(user_text, history, GROQ_API_KEY)
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": ans})
            
        speak(ans)

if __name__ == "__main__":
    main()

import os
import sys
import soundfile as sf
import torch
import torchaudio

# [Windows Uyumluluk Yaması]
# Torchaudio 2.9+, Windows üzerinde derlenmiş DLL arayan torchcodec'e zorlar.
# soundfile kullanarak bu bağımlılığı sıfırlıyoruz.
def soundfile_load(uri, *args, **kwargs):
    data, sr = sf.read(uri)
    tensor = torch.from_numpy(data).float()
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)
    elif tensor.ndim == 2:
        tensor = tensor.t()
    return tensor, sr

def soundfile_save(uri, src, sample_rate, *args, **kwargs):
    if isinstance(src, torch.Tensor):
        src = src.detach().cpu().numpy()
    if src.ndim == 2:
        src = src.T
    sf.write(uri, src, sample_rate)

torchaudio.load = soundfile_load
torchaudio.save = soundfile_save

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(base_dir, "models")
    
    ckpt_file = os.path.join(models_dir, "f5_tts_turkish_1000000.safetensors")
    vocab_file = os.path.join(models_dir, "vocab.txt")
    ref_audio = os.path.join(models_dir, "reference_voice.wav")
    ref_text = "Severek ayrılalım. Hissetmek istiyorum. Aaa gözyaşları nerde ama? Ahh! Boş laf."
    gen_text = "Selam Negr1, ben hazırım. Bugün ne yapıyoruz?"
    output_dir = models_dir
    output_file = "test_output.wav"

    print("[1/2] F5-TTS Türkçe modeli ve referans ses yükleniyor...")
    print(f" -> Referans Ses:  {ref_audio}")
    print(f" -> Referans Metin: \"{ref_text}\"")
    print(f" -> Hedef Metin:    \"{gen_text}\"")
    print("\n[2/2] Çıkarım (Inference) başladı. CPU üzerinde hesaplanıyor...")

    sys.argv = [
        "infer_cli.py",
        "--ckpt_file", ckpt_file,
        "--vocab_file", vocab_file,
        "--ref_audio", ref_audio,
        "--ref_text", ref_text,
        "--gen_text", gen_text,
        "--output_dir", output_dir,
        "--output_file", output_file,
        "--device", "cpu"
    ]

    from f5_tts.infer.infer_cli import main as infer_main
    try:
        infer_main()
        out_path = os.path.join(output_dir, output_file)
        if os.path.exists(out_path):
            print(f"\n[✓ BAŞARILI] Ses başarıyla üretildi: {out_path}")
            print("Dosyayı doğrudan çift tıklayarak dinleyebilirsin.")
    except Exception as e:
        print(f"\n[! HATA] Çıkarım sırasında hata oluştu: {e}")

if __name__ == "__main__":
    main()

"""
ChatGPT Paylaşım Linkinden TXT Çıkarma Aracı
Kullanım:
    python extract_chatgpt_share.py [URL veya SHARE_ID] [CIKTI_DOSYASI.txt]

Örnek:
    python extract_chatgpt_share.py https://chatgpt.com/share/6af0a4cb-3dc8-83ed-891a-a4f63b3d1e71
"""

import sys
import re
import json
import urllib.request
import urllib.error


def extract_share_id(url_or_id: str) -> str:
    """URL veya doğrudan ID girdisinden share UUID'sini ayıklar."""
    match = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", url_or_id, re.IGNORECASE)
    if match:
        return match.group(1)
    raise ValueError(f"Geçersiz ChatGPT paylaşım bağlantısı veya ID: {url_or_id}")


def fetch_chatgpt_share(share_id: str) -> dict:
    """ChatGPT'nin resmi backend share uç noktasından ham JSON verisini çeker."""
    api_url = f"https://chatgpt.com/backend-api/share/{share_id}"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP Hatası: {resp.status}")
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ChatGPT API Hatası: {e.code} - {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Bağlantı hatası: {e}")


def parse_conversation(data: dict) -> list[dict]:
    """JSON düğüm grafiğini (mapping) kronolojik mesaj listesine dönüştürür."""
    mapping = data.get("mapping", {})
    current_node = data.get("current_node")
    
    linear_nodes = []
    curr = current_node
    while curr:
        node = mapping.get(curr)
        if not node:
            break
        linear_nodes.append(node)
        curr = node.get("parent")
    
    linear_nodes.reverse()

    messages = []
    for node in linear_nodes:
        msg = node.get("message")
        if not msg:
            continue
        
        author = msg.get("author", {})
        role = author.get("role", "unknown")
        
        # Sadece gerçek kullanıcı ve asistan mesajlarını al
        if role not in ("user", "assistant"):
            continue

        content = msg.get("content", {})
        content_type = content.get("content_type", "")
        if content_type not in ("text", "multimodal_text"):
            continue

        parts = content.get("parts", [])
        text_parts = []
        for p in parts:
            if isinstance(p, str):
                text_parts.append(p)
            elif isinstance(p, dict) and "text" in p:
                text_parts.append(p["text"])
        
        full_text = "\n".join(text_parts).strip()
        if not full_text or "The output of this plugin was redacted" in full_text:
            continue

        messages.append({
            "id": msg.get("id"),
            "role": role,
            "text": full_text,
            "timestamp": msg.get("create_time")
        })

    return messages


def export_to_txt(data: dict, messages: list[dict], output_path: str):
    """Mesajları okunabilir temiz bir TXT dosyasına yazar."""
    title = data.get("title", "ChatGPT Sohbeti")
    create_time = data.get("create_time", "")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"BAŞLIK: {title}\n")
        f.write(f"TARİH  : {create_time}\n")
        f.write(f"TOPLAM MESAJ SAYISI: {len(messages)}\n")
        f.write("=" * 80 + "\n\n")

        for idx, m in enumerate(messages, 1):
            role_label = "KULLANICI (USER)" if m["role"] == "user" else "CHATGPT (ASSISTANT)"
            f.write(f"[{idx}] {role_label}\n")
            f.write("-" * 80 + "\n")
            f.write(m["text"] + "\n\n")
            f.write("=" * 80 + "\n\n")


def main():
    default_url = "https://chatgpt.com/share/6af0a4cb-3dc8-83ed-891a-a4f63b3d1e71"
    url_input = sys.argv[1] if len(sys.argv) > 1 else default_url
    
    share_id = extract_share_id(url_input)
    default_output = f"chatgpt_share_{share_id[:8]}.txt"
    output_path = sys.argv[2] if len(sys.argv) > 2 else default_output

    print(f"[*] Share ID ayıklandı: {share_id}")
    print(f"[*] ChatGPT API'den veri çekiliyor...")
    data = fetch_chatgpt_share(share_id)
    
    title = data.get("title", "Bilinmeyen Başlık")
    print(f"[+] Başlık bulundu: {title}")
    
    messages = parse_conversation(data)
    print(f"[+] Toplam {len(messages)} adet mesaj çözümlendi.")
    
    export_to_txt(data, messages, output_path)
    print(f"[✔] Başarıyla kaydedildi: {output_path}")


if __name__ == "__main__":
    main()

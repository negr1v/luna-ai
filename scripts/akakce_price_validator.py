#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LUNA-AI: Akakçe Gerçek İndirim ve Fiyat Hatası Doğrulama Motoru
Harici botların şişirilmiş liste fiyatı üzerinden ürettiği sahte indirimleri (%22 vb.)
Akakçe piyasa dip fiyatı ve tarihsel taban verisiyle teyit eder/ayıklar.
"""

import sys
import re
import json
import urllib.request
from typing import Dict, Any, Optional, List

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Negr1 Donanım Alım Eşikleri (AM5 Hedef Sistemi)
HARDWARE_THRESHOLDS = {
    "7500f": {"ideal": 6500.0, "max_review": 7200.0, "label": "Ryzen 5 7500F"},
    "b650m-r": {"ideal": 4499.0, "max_review": 4899.0, "label": "ASUS Prime B650M-R"},
    "combo_ideal": 11000.0
}

def parse_price(main_part: str, decimal_part: str = "") -> Optional[float]:
    """Akakçe'nin '6.579' ve ',06' parçalarını temiz float sayıya çevirir."""
    try:
        clean_main = re.sub(r"[^\d]", "", main_part)
        clean_dec = re.sub(r"[^\d]", "", decimal_part) if decimal_part else "00"
        if not clean_main:
            return None
        return float(f"{clean_main}.{clean_dec}")
    except Exception:
        return None

def fetch_akakce_summary(akakce_url: str) -> Dict[str, Any]:
    """Akakçe ürün sayfasından güncel en ucuz fiyatı ve tarihsel dip fiyatı çeker."""
    req = urllib.request.Request(
        akakce_url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "tr-TR,tr;q=0.9"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"status": "error", "message": f"Akakçe bağlantı hatası: {e}"}

    # 1. Başlık
    title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else "Bilinmeyen Ürün"

    # 2. Güncel En Ucuz Fiyat: <span class="pt_v8 ">6.579<i>,06 TL</i>
    min_price = None
    pt_match = re.search(r'class="pt_v8[^"]*"[^>]*>\s*([\d\.]+)(?:<i>[,.](\d+)\s*TL</i>)?', html)
    if pt_match:
        min_price = parse_price(pt_match.group(1), pt_match.group(2) or "00")

    # 3. Tarihsel Fiyatlar Listesi (Akakçe tablosunda tarih yanındaki fiyat)
    # Örnek: <td>03.11.2026</td><td>6.700<i>,00 TL</i></td>
    all_prices: List[float] = []
    if min_price:
        all_prices.append(min_price)

    table_matches = re.finditer(r'\d{2}\.\d{2}\.\d{4}</td>\s*<td>\s*([\d\.]+)\s*<i>[,.](\d{2})\s*TL</i>', html)
    for tm in table_matches:
        p = parse_price(tm.group(1), tm.group(2))
        if p and p > 1000.0: # Donanım için geçerli taban fiyat
            all_prices.append(p)

    historical_min = min(all_prices) if all_prices else min_price

    return {
        "status": "ok",
        "title": title,
        "current_min_price": min_price,
        "historical_min_price": historical_min,
        "url": akakce_url
    }

def verify_deal(claimed_price_input: float, akakce_data: Dict[str, Any], bot_claimed_discount_pct: Optional[float] = None) -> Dict[str, Any]:
    """Botun iddiasını Akakçe gerçek verileriyle doğrular ve karar üretir."""
    curr_min = akakce_data.get("current_min_price")
    hist_min = akakce_data.get("historical_min_price")

    if not curr_min:
        return {
            "verdict": "VERI_YOK",
            "message": "Akakçe fiyat verisi okunamadı.",
            "alarm": False
        }

    claimed_price = float(claimed_price_input)

    # Gerçek İndirim Hesabı (Akakçe Güncel En Ucuz Fiyata Göre)
    diff_curr = curr_min - claimed_price
    diff_curr_pct = (diff_curr / curr_min) * 100 if curr_min > 0 else 0.0

    # Tarihsel Taban Fiyata Göre Durum
    diff_hist = (hist_min - claimed_price) if hist_min else 0.0
    diff_hist_pct = (diff_hist / hist_min) * 100 if (hist_min and hist_min > 0) else 0.0

    # Manipülasyon Analizi
    is_fake_discount = False
    manipulation_reason = ""
    if bot_claimed_discount_pct and bot_claimed_discount_pct >= 15.0 and diff_curr_pct < 5.0:
        is_fake_discount = True
        manipulation_reason = f"Bot %{bot_claimed_discount_pct:.0f} iddia etti, gerçek piyasa farkı %{diff_curr_pct:.1f}! Şişirilmiş liste fiyatı baz alınmış."

    # Karar ve Alarm Mantığı
    verdict = "NORMAL"
    alarm_level = "YOK"
    decision = "BEKLE"

    if claimed_price > curr_min:
        verdict = "PAHALI"
        decision = "KESİNLİKLE ALMA (Akakçe'de daha ucuzu var)"
    elif diff_curr_pct <= 1.0: # %1 ve altı oynama (örn 50 TL fark)
        verdict = "RUTIN_FIYAT"
        decision = "RUTİN PİYASA FİYATI / ALMA (FOMO Tuzağı)"
    elif diff_curr_pct > 1.0 and diff_hist_pct <= 0:
        verdict = "KUCUK_INDIRIM"
        decision = f"KÜÇÜK İNDİRİM (%{diff_curr_pct:.1f}). Dip seviyeyi kırmadı, bekle."
    elif diff_hist_pct > 0 and diff_hist_pct < 10.0:
        verdict = "DIP_SEVIYE"
        alarm_level = "SARI"
        decision = f"YENİ DİP FİYAT (%{diff_hist_pct:.1f} rekor). İhtiyaç varsa değerlendir."
    elif diff_hist_pct >= 10.0:
        verdict = "GERCEK_FIYAT_HATASI"
        alarm_level = "KIRMIZI"
        decision = f"GERÇEK FİYAT HATASI (%{diff_hist_pct:.1f} dip kırılımı). Fırsat!"

    return {
        "claimed_price": claimed_price,
        "akakce_current_min": curr_min,
        "akakce_historical_min": hist_min,
        "real_discount_vs_current_pct": round(diff_curr_pct, 2),
        "real_discount_vs_historical_pct": round(diff_hist_pct, 2),
        "is_fake_discount": is_fake_discount,
        "manipulation_reason": manipulation_reason,
        "verdict": verdict,
        "alarm_level": alarm_level,
        "final_decision": decision
    }

if __name__ == "__main__":
    # Test Senaryosu: Gigabyte B850M Force
    test_url = "https://www.akakce.com/anakart/en-ucuz-gigabyte-b850m-force-amd-am5-ddr5-micro-atx-fiyati,1188312280.html"
    claimed = 6649.0
    bot_pct = 22.0

    print(">>> Akakçe Doğrulama Motoru Test Ediliyor...")
    data = fetch_akakce_summary(test_url)
    print("Akakçe Verisi:", json.dumps(data, ensure_ascii=False, indent=2))
    
    analysis = verify_deal(claimed, data, bot_claimed_discount_pct=bot_pct)
    print("\n>>> Doğrulama Raporu:")
    print(json.dumps(analysis, ensure_ascii=False, indent=2))

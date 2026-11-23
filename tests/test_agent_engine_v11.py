"""
ZERO CORE OS - Autonomous Agent Core Engine Test Suite (V11)
Modül düzeyinde kapsamlı, güvenli ve gerçek test senaryoları.
"""

import asyncio
import os
import sys

# Proje dizinini ekle
proj_dir = os.path.dirname(os.path.abspath(__file__))
if proj_dir not in sys.path:
    sys.path.insert(0, proj_dir)

from luna_agent_engine import AgentController, TaskState, PermissionLevel

async def run_agent_tests():
    print("=== ZERO CORE OS V11 - AGENT ENGINE TESTLERİ BAŞLIYOR ===")
    controller = AgentController(proj_dir)

    # 1. Test: Telemetri Çok Adımlı Plan Oluşturma ve Yürütme
    print("\n[Test 1] 'ZERO, sistem durumunu kontrol et' Görevi...")
    t1 = controller.create_task("ZERO, sistem durumunu kontrol et.")
    assert t1.state == TaskState.CREATED
    assert len(t1.steps) == 2
    print(f" -> Plan oluşturuldu: {t1.description} ({len(t1.steps)} adım)")

    # Yürütme
    t1_res = await controller.execute_task(t1.task_id)
    assert t1_res.state == TaskState.COMPLETED
    assert t1_res.steps[0].status == "COMPLETED"
    assert t1_res.steps[1].status == "COMPLETED"
    print(f" -> Sonuç: {t1_res.state.value} | Özet: {t1_res.summary}")

    # 2. Test: Dosya Arama Görevi
    print("\n[Test 2] 'ZERO, bu projedeki belirli bir dosyayı bul' Görevi...")
    t2 = controller.create_task("ZERO, proje dosyalarında luna_config dosyasını bul.")
    t2_res = await controller.execute_task(t2.task_id)
    assert t2_res.state == TaskState.COMPLETED
    files = t2_res.steps[0].result.get("matched_files", [])
    print(f" -> Sonuç: {t2_res.state.value} | Eşleşen dosyalar ({len(files)}): {files[:3]}")

    # 3. Test: İzin ve Onay Döngüsü (AWAITING_APPROVAL)
    print("\n[Test 3] 'ZERO, bu ekran görüntüsünü analiz et' (Onay Gerektiren Görev)...")
    t3 = controller.create_task("ZERO, bu ekran görüntüsünü analiz et.")
    t3_pending = await controller.execute_task(t3.task_id)
    assert t3_pending.state == TaskState.AWAITING_APPROVAL
    assert t3_pending.steps[0].status == "AWAITING_APPROVAL"
    print(f" -> Güvenlik Koruması Devrede: Durum = {t3_pending.state.value}")

    # Kullanıcı Onayı Vermeden Önce Yürütme Durdurulur
    print(" -> Kullanıcı Onayı Simülasyonu Veriliyor...")
    approved = controller.approve_step(t3.task_id, 1)
    assert approved is True
    print(" -> Adım onaylandı, görev devam ettiriliyor...")

    # 4. Test: İptal (Cancel) Mekanizması
    print("\n[Test 4] Görev İptal Testi...")
    t4 = controller.create_task("ZERO, günlük görevlerimi listele.")
    cancelled = controller.cancel_task(t4.task_id)
    assert cancelled is True
    assert controller.tasks[t4.task_id].state == TaskState.CANCELLED
    print(f" -> İptal Başarılı: Durum = {controller.tasks[t4.task_id].state.value}")

    # 5. Test: Bilinmeyen ve Yetkisiz Araç Engelleme
    print("\n[Test 5] Bilinmeyen Araç Enjeksiyonu ve Güvenlik...")
    assert controller.registry.get("unrestricted_shell_exec") is None
    print(" -> 'unrestricted_shell_exec' kesinlikle kayıtlı değil ve engellendi.")

    print("\n=== TÜM V11 AJAN MOTORU TESTLERİ %100 BAŞARIYLA TAMAMLANDI ===")

if __name__ == "__main__":
    asyncio.run(run_agent_tests())

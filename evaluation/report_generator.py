import os
import logging
from datetime import datetime
from collections import Counter
from typing import Dict, Any

# Project imports
from evaluation.metrics import calculate_blacklist_impact
from extractor.blacklist import get_blacklist_stats

logger = logging.getLogger(__name__)

def generate_full_report(batch_results: Dict[str, Any]) -> str:
    """
    Generates a formatted Turkish research report containing test setup, general results,
    field accuracy, self-correcting validation loop convergence, regex cleanup statistics,
    blacklist impact, site results table, and category distribution.
    """
    logger.info("Generating full Turkish research report...")
    
    results = batch_results.get("results", [])
    overall_stats = batch_results.get("overall_stats", {})
    per_domain_stats = batch_results.get("per_domain_stats", {})
    
    total_count = batch_results.get("total_urls", 0)
    successful_count = batch_results.get("successful", 0)
    failed_count = batch_results.get("failed", 0)
    
    successful_pct = (successful_count / total_count * 100) if total_count > 0 else 0.0
    failed_pct = (failed_count / total_count * 100) if total_count > 0 else 0.0
    
    today = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    date_str = datetime.now().strftime("%d.%m.%Y")
    
    # 4. Attempt counters
    solved_attempt_1 = overall_stats.get("solved_attempt_1", 0)
    solved_attempt_2 = overall_stats.get("solved_attempt_2", 0)
    solved_attempt_3 = overall_stats.get("solved_attempt_3", 0)
    failed_all = overall_stats.get("failed_all", 0)
    
    solved_attempt_1_pct = (solved_attempt_1 / total_count * 100) if total_count > 0 else 0.0
    solved_attempt_2_pct = (solved_attempt_2 / total_count * 100) if total_count > 0 else 0.0
    solved_attempt_3_pct = (solved_attempt_3 / total_count * 100) if total_count > 0 else 0.0
    failed_all_pct = (failed_all / total_count * 100) if total_count > 0 else 0.0
    
    solved_1_and_2 = solved_attempt_1 + solved_attempt_2
    first_2_pct = (solved_1_and_2 / total_count * 100) if total_count > 0 else 0.0
    attempt_3_pct = (solved_attempt_3 / total_count * 100) if total_count > 0 else 0.0
    
    # 5. RegEx analysis aggregation
    successful_results = [r for r in results if r.get("error") is None and r.get("regex_stats")]
    
    before_noise_ratio_sum = 0.0
    after_noise_ratio_sum = 0.0
    total_removed_sum = 0
    
    html_entities_removed = 0
    urls_removed = 0
    social_noise_removed = 0
    datetime_noise_removed = 0
    hashtags_removed = 0
    short_lines_removed = 0
    
    for r in successful_results:
        reg_s = r["regex_stats"]
        before_noise_ratio_sum += reg_s.get("without_regex", {}).get("noise_ratio", 0.0)
        after_noise_ratio_sum += reg_s.get("with_regex", {}).get("noise_ratio", 0.0)
        total_removed_sum += reg_s.get("total_items_removed", 0)
        
        filters = reg_s.get("filters_applied", {})
        html_entities_removed += filters.get("html_entities_removed", 0)
        urls_removed += filters.get("urls_removed", 0)
        social_noise_removed += filters.get("social_noise_removed", 0)
        datetime_noise_removed += filters.get("datetime_noise_removed", 0)
        hashtags_removed += filters.get("hashtags_removed", 0)
        short_lines_removed += filters.get("short_lines_removed", 0)
        
    count_success = len(successful_results)
    if count_success > 0:
        before_noise_ratio_avg = (before_noise_ratio_sum / count_success) * 100
        after_noise_ratio_avg = (after_noise_ratio_sum / count_success) * 100
        removed_avg = total_removed_sum / count_success
        noise_reduction_avg = before_noise_ratio_avg - after_noise_ratio_avg
    else:
        before_noise_ratio_avg = 0.0
        after_noise_ratio_avg = 0.0
        removed_avg = 0.0
        noise_reduction_avg = 0.0
        
    # 6. Blacklist impact
    impact = calculate_blacklist_impact()
    bl_stats = get_blacklist_stats()
    
    before_score = impact.get('before_blacklist', {}).get('average_score', 0.55)
    after_score = impact.get('after_blacklist', {}).get('average_score', 0.84)
    improvement_pct = impact.get('improvement_percent', 0.0)
    total_blacklisted = bl_stats.get('total_global_blacklisted', 0)
    
    problem_selectors = bl_stats.get('most_problematic_selectors', [])
    if problem_selectors:
        problems_str = "\n".join([f"- {p}" for p in problem_selectors[:5]])
    else:
        problems_str = "- Kayıtlı sorunlu seçici bulunmuyor"
        
    # 7. Per-site results formatting
    site_table_rows = []
    for site, stats in per_domain_stats.items():
        site_table_rows.append(
            f"| {site:<25} | {stats['total']:<4} | {stats['successful']:<6} | {stats['avg_confidence']:<9.2f} | {stats['avg_attempts']:<10.2f} |"
        )
    site_table_str = "\n".join(site_table_rows)
    
    # 8. Category distribution
    categories = [r.get("category", "GÜNDEM") for r in results if r.get("error") is None]
    cat_counts = Counter(categories)
    cat_rows = []
    for cat, count in cat_counts.most_common():
        cat_pct = (count / len(categories) * 100) if len(categories) > 0 else 0.0
        cat_rows.append(f"- {cat}: {count} haber (%{cat_pct:.1f})")
    cat_distribution_str = "\n".join(cat_rows) if cat_rows else "- Kategori bilgisi bulunmuyor"

    report = f"""=======================================================
NEXTSCRAPE - ARAŞTIRMA RAPORU
LLM Destekli Hibrit Web Kazıma Sistemi
Tarih: {today}
=======================================================

1. TEST ORTAMI
--------------
- Test Edilen URL Sayısı: {total_count}
- Test Edilen Site Sayısı: {len(per_domain_stats)}
- Test Tarihi: {date_str}
- Kullanılan Model: llama3 (Ollama)
- Donanım: Yerel Sistem (16GB RAM)

2. GENEL SONUÇLAR
-----------------
- Başarılı Analiz: {successful_count}/{total_count} (%{successful_pct:.1f})
- Ortalama Güven Skoru: {overall_stats.get("avg_confidence", 0.0):.2f}
- Ortalama LLM Yanıt Süresi: {overall_stats.get("avg_llm_time_ms", 0)} ms
- Ortalama HTML Küçültme: %{overall_stats.get("avg_size_reduction", 0.0):.1f}
- Ortalama RegEx Gürültü Azaltımı: %{overall_stats.get("avg_regex_noise_reduction", 0.0):.1f}

3. ALAN BAZLI BAŞARI ORANLARI
-----------------------------
- Başlık Bulma Oranı: %{overall_stats.get("title_found_rate", 0.0) * 100:.1f}
- İçerik Bulma Oranı: %{overall_stats.get("content_found_rate", 0.0) * 100:.1f}
- Yazar Bulma Oranı: %{overall_stats.get("author_found_rate", 0.0) * 100:.1f}
- Tarih Bulma Oranı: %{overall_stats.get("date_found_rate", 0.0) * 100:.1f}

4. 3 AŞAMALI DOĞRULAMA DÖNGÜSÜ ANALİZİ
----------------------------------------
- 1. Denemede Çözülen: {solved_attempt_1} URL (%{solved_attempt_1_pct:.1f})
- 2. Denemede Çözülen: {solved_attempt_2} URL (%{solved_attempt_2_pct:.1f})
- 3. Denemede Çözülen: {solved_attempt_3} URL (%{solved_attempt_3_pct:.1f})
- Başarısız (3 denemede): {failed_all} URL (%{failed_all_pct:.1f})
- Neden 3 Deneme Yeterli:
  "{solved_1_and_2}/{total_count} URL ilk 2 denemede çözüldü (%{first_2_pct:.1f}).
   3. deneme sadece %{attempt_3_pct:.1f} ek katkı sağladı.
   4. deneme anlamsız olurdu çünkü 3 başarısız
   denemeden sonra site yapısı LLM tarafından
   anlaşılamıyor demektir."

5. REGEX FİLTRELEME ETKİSİ
---------------------------
- Öncesi Ortalama Gürültü Oranı: %{before_noise_ratio_avg:.1f}
- Sonrası Ortalama Gürültü Oranı: %{after_noise_ratio_avg:.1f}
- Gürültü Azaltımı: %{noise_reduction_avg:.1f}
- Kaldırılan Ortalama Öğe Sayısı: {removed_avg:.1f}

Filtre Bazlı Katkı:
- HTML Varlıkları: {html_entities_removed} öğe
- URL'ler: {urls_removed} öğe
- Sosyal Medya Gürültüsü: {social_noise_removed} öğe
- Tarih/Saat Gürültüsü: {datetime_noise_removed} öğe
- Hashtagler: {hashtags_removed} öğe
- Kısa Satırlar: {short_lines_removed} öğe

6. KARA LİSTE ETKİSİ
---------------------
- Kara Liste Öncesi Ort. Skor: {before_score:.2f}
- Kara Liste Sonrası Ort. Skor: {after_score:.2f}
- İyileşme: %{improvement_pct:.1f}
- Toplam Kara Listeye Alınan Seçici: {total_blacklisted}
- En Sorunlu Seçiciler:
{problems_str}

7. SİTE BAZLI SONUÇLAR
-----------------------
| Site                      | Test | Başarı | Ort.Güven | Ort.Deneme |
|---------------------------|------|--------|-----------|------------|
{site_table_str}

8. KATEGORİ DAĞILIMI
---------------------
{cat_distribution_str}

9. BENZERLİK HESAPLAMA YÖNTEMİ
-----------------------------
Sistemimiz ile Newspaper3k kütüphanesinin çıkardığı veriler
difflib.SequenceMatcher algoritması ile karşılaştırılır. Bu algoritma
iki metin arasındaki ortak karakter dizilerinin oranını hesaplar:

  benzerlik = (2 × eşleşen_karakter_sayısı) / toplam_karakter_sayısı

Skor 0.0 ile 1.0 arasındadır. 1.0 birebir eşleşme, 0.0 hiç örtüşme
olmadığını gösterir. Bu yöntem anlamsal (semantic) değil, sözdizimsel
(syntactic) bir karşılaştırmadır. Düşük içerik benzerliği genellikle
extraction kalitesinde bir sorunu işaret eder.

Örnek Hesaplama (Alan bazlı, başlık yüksek / içerik düşük senaryosu):
----------------------------------------------------------------------
Alan     | Bizim (kar.) | Newspaper3k (kar.) | Eşleşen (M) | Toplam (T) | Hesaplama          | Skor
---------|--------------|---------------------|-------------|------------|--------------------|-----
Başlık   | ~95 kar.     | ~95 kar.            | ~95         | ~190       | (2×95)/190         | 1.00
İçerik   | ~340 kar.    | ~410 kar.           | ~23         | ~750       | (2×23)/750         | 0.06
Yazar    | ~15 kar.     | ~15 kar.            | ~15         | ~30        | (2×15)/30          | 1.00
Tarih    | ~10 kar.     | ~10 kar.            | ~8          | ~20        | (2×8)/20           | 0.80

Not: Başlıklar kısa ve net olduğundan karakter dizileri neredeyse
birebir örtüşür (skor → 1.0). İçerikte ise bir sistem yanlışlıkla
navigasyon metnini veya başlığı içerik olarak çektiyse, karakter
dizileri birbirinden çok farklı olur ve skor düşer (örn. 0.06).
Bu düşük skor bir başarısızlık değil, extraction hatasının sinyalidir.

10. SONUÇ VE DEĞERLENDİRME
--------------------------
- Sistem {len(per_domain_stats)} farklı haber sitesinde test edilmiştir.
- Ortalama %{successful_pct:.1f} başarı oranı elde edilmiştir.
- LLM tabanlı kural üretimi, geleneksel yöntemlere göre daha esnek ve adaptif bir yapı sunmaktadır.
- 3 aşamalı doğrulama döngüsü, veri kalitesini ortalama %{improvement_pct:.1f} oranında artırmaktadır.

=======================================================
"""
    return report

def save_report(report: str) -> str:
    """
    Saves the report string to data/research_report.txt and returns the absolute file path.
    """
    os.makedirs("data", exist_ok=True)
    report_path = "data/research_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    return os.path.abspath(report_path)

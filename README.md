# NextScrape 🕷️
## LLM Destekli Hibrit Web Kazıma Sistemi

TÜBİTAK 2209-A Üniversitesi Öğrencileri Araştırma Projeleri Desteği Programı  
Tekirdağ Namık Kemal Üniversitesi - Bilgisayar Mühendisliği

---

## 📋 Proje Özeti

NextScrape, web sayfalarından bilgi çıkarımını Büyük Dil Modelleri (LLM) kullanarak 
otomatize eden hibrit bir sistemdir. Geleneksel scraping yöntemlerinin aksine, 
LLM'leri veriyi okumak için değil, veri çıkarım kuralları üretmek için kullanır.

## 🏗️ Sistem Mimarisi
```
URL Girişi
↓
HTML Çekme & Temizleme (fetcher.py + cleaner.py)
↓
LLM → CSS/XPath Kural Üretimi (rule_generator.py)
↓
3 Aşamalı Doğrulama Döngüsü (validator.py)
↓
Kara Liste Filtresi (blacklist.py)
↓
RegEx Gürültü Filtreleme (regex_filter.py)
↓
Newspaper3k Çapraz Doğrulama (cross_checker.py)
↓
Sonuç + Güven Skoru
```

## 📊 Test Sonuçları (50 URL, 10 Site)

| Metrik | Değer |
|--------|-------|
| Toplam Test | 50 URL |
| Başarı Oranı | %88 |
| Ortalama Güven Skoru | 0.60 |
| Başlık Bulma Oranı | %76 |
| İçerik Bulma Oranı | %68 |
| Yazar Bulma Oranı | %58 |
| Tarih Bulma Oranı | %62 |
| Kara Liste İyileşmesi | %74.5 |
| HTML Küçültme Oranı | %88 |
| RegEx Gürültü Azaltımı | %43.9 |

## 🔧 Kurulum

### Gereksinimler
- Python 3.10+
- Ollama (llama3 modeli)
- 8GB+ RAM önerilir

### Adımlar

```bash
# 1. Repoyu klonla
git clone https://github.com/username/nextscrape.git
cd nextscrape

# 2. Bağımlılıkları kur
pip3 install -r requirements.txt

# 3. Ollama'yı başlat
ollama serve
ollama pull llama3

# 4. Uygulamayı çalıştır
streamlit run ui/app.py
```

## 📦 Proje Yapısı
```
nextscrape/
├── scraper/
│   ├── fetcher.py        # HTTP istekleri, user-agent rotasyonu
│   ├── cleaner.py        # HTML temizleme, DOM küçültme
│   └── detector.py       # Dil ve site tipi tespiti
├── extractor/
│   ├── rule_generator.py # LLM tabanlı CSS kural üretimi
│   ├── validator.py      # 3 aşamalı doğrulama döngüsü
│   ├── blacklist.py      # Kara liste yöneticisi
│   ├── categorizer.py    # Otomatik kategori etiketleme
│   ├── list_extractor.py # Liste sayfası haber başlığı çıkarımı
│   └── regex_filter.py   # RegEx gürültü filtreleme
├── evaluation/
│   ├── cross_checker.py  # Newspaper3k çapraz doğrulama
│   ├── metrics.py        # Precision, Recall, F1 hesaplama
│   ├── batch_tester.py   # Toplu test motoru
│   └── report_generator.py # Araştırma raporu üretici
├── data/
│   ├── rules_cache/      # Site bazlı kural önbelleği
│   ├── blacklist.json    # Kara liste seçiciler
│   └── batch_results.json # Test sonuçları
├── ui/
│   └── app.py            # Streamlit arayüzü
└── requirements.txt
```

## 🎯 Özellikler

- **Tekil URL Analizi**: Herhangi bir haber sayfasından başlık, içerik, yazar, tarih çıkarımı
- **Liste Modu**: Anasayfa ve kategori sayfalarından haber başlıkları listesi
- **Kategori Etiketleme**: Otomatik SPOR, EKONOMİ, SİYASET, TEKNOLOJİ kategorileri
- **3 Aşamalı Doğrulama**: Kural kalitesi, içerik kalitesi, çapraz doğrulama
- **Kara Liste**: Kalitesiz seçicileri otomatik engelleme
- **RegEx Filtreleme**: Gürültülü içeriği temizleme
- **Kural Önbelleği**: Aynı site için LLM maliyeti sıfır
- **İstatistik Dashboard**: Tüm test sonuçları görselleştirme

## 👥 Ekip

- Emir Şahin (2220656013)
- Yusuf Samet Karlıdağ (2240656802)  
- İlayda Yardımcı (2220656037)

**Danışman**: Prof. Dr. Erdinç UZUN  
**Kurum**: Tekirdağ Namık Kemal Üniversitesi

🏆 Football Data App: Kapsamlı Sistem Rehberi
Bu uygulama, dünya genelindeki futbol liglerini takip eden, verileri otonom olarak analiz eden ve Yapay Zeka (AI) kullanarak yüksek doğruluklu maç tahminleri üreten gelişmiş bir ekosistemdir.

🚀 Genel Bakış
Sistem, insan müdahalesine ihtiyaç duymadan veri toplar, model eğitir ve tahminlerini her gün günceller. "AutoResearcher" modülü sayesinde sürekli olarak en iyi algoritmayı arayan, kendi kendini geliştiren bir yapıya sahiptir.

🏗️ Temel Bileşenler
1. 📊 Veri Merkezi (Data Ingestion)
Sistem, verilerini üç ana koldan toplar:

Tarihsel Veriler: football-data.co.uk üzerinden 50+ ligin geçmiş maç sonuçları, istatistikleri ve bahis oranları.
Canlı Sonuçlar: ESPN API ve Football-Data.org üzerinden biten maçların skorları anlık olarak senkronize edilir.
Gelişmiş Metrikler: Understat ve ClubElo entegrasyonu ile maçlara xG (Beklenen Gol) ve ELO Güç Puanı eklenir.
2. 🧠 Yapay Zeka Laboratuvarı (ML Engine)
Sistemin kalbi olan bu bölüm iki ana parçadan oluşur:

AutoResearcher: Kaggle seviyesinde hiper-parametre optimizasyonu (Optuna) kullanarak XGBoost, LightGBM ve CatBoost modellerini yarıştırır.
Champion Model: En yüksek kâr ve doğruluk oranına sahip model otomatik olarak "Şampiyon" ilan edilir ve aktif tahminlerde kullanılır.
3. 🎯 Tahmin Motoru (Predictor)
Bir maç tahmin edilirken sadece ML kullanılmaz, hibrit bir analiz yapılır:

Layer 1 (Form): Takımların son 5-10 maçtaki puan ve gol performansı.
Layer 2 (xG & Trend): Takımların gol beklentisi ve form grafiği.
Layer 3 (Context): Puan durumu baskısı (Düşme hattı, Şampiyonluk yarışı).
Tier Sistemi: Tahminler güven derecesine göre 💎 PLATINUM, 🥇 GOLD, 🥈 SILVER ve 🥉 BRONZE olarak kategorize edilir.
4. 🌐 Web Dashboard
Kullanıcı dostu arayüz üzerinden şu işlemleri yapabilirsiniz:

Haftalık Bülten: Yaklaşan maçların AI tahminlerini ve kupon önerilerini görüntüleyin.
Predictor: İstediğiniz iki takımı manuel olarak kapıştırıp detaylı rapor alın.
Başarı Analizi: Modelin geçmişte hangi oranda başarılı olduğunu şeffaf bir şekilde takip edin.
🛠️ Nasıl Kullanılır?
Günlük Rutin (Otomatik)
Programı çalıştırmanız yeterlidir (
baslat.bat
). Arka planda şu işlemler otomatik gerçekleşir:

Sabah 09:00: Biten maçlar sonuçlandırılır, başarı skorları güncellenir ve günün bülteni çıkarılır.
Akşam 19:00: Son dakika sakatlık/form değişikliklerine göre tahminler finalize edilir.
Manuel Kontrol
Veri Güncelleme: Dashboard üzerinden "Veri Çek" butonuna basarak en güncel CSV dosyalarını indirebilirsiniz.
Model Eğitimi: "Auto Research" panelinden istediğiniz sayıda deney başlatarak sistemin daha iyi bir model bulmasını sağlayabilirsiniz.
🧪 Teknik Detaylar (Geliştiriciler İçin)
Backend: Python, Flask
Veritabanı: SQLite (WAL Modu aktif, yüksek okuma/yazma hızı)
ML Stack: Scikit-Learn, XGBoost, LightGBM, CatBoost, Optuna
Mimari: Otonom Mikro-Servis Yapısı (Scrapers, Research, Prediction, API)
IMPORTANT

Sistem tamamen yerel (local) çalışacak şekilde tasarlanmıştır. ngrok entegrasyonu ile isterseniz dış dünyaya güvenli bir şekilde

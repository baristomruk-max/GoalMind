import re
import json
import logging
import urllib.request
from bs4 import BeautifulSoup
from difflib import get_close_matches
from datetime import datetime

logger = logging.getLogger(__name__)

class IddaaScraper:
    """Açık API'lerden (ESPN vb.) o günün futbol maç programını tarayıp DB takımlarıyla eşleştirir."""

    def __init__(self, db, predictor):
        self.db = db
        self.predictor = predictor
        # ESPN API'si genel ve ücretsizdir, günlük tüm futbol liglerindeki maçları listeler.
        self.url = "https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_upcoming_matches(self, days=7):
        """Açık ESPN API'sini tarayarak önümüzdeki N günlük futbol maçlarını listeler."""
        from datetime import timedelta
        now = datetime.now()
        start_date = now.strftime("%Y%m%d")
        end_date = (now + timedelta(days=days)).strftime("%Y%m%d")
        
        url_with_range = f"{self.url}?dates={start_date}-{end_date}"
        logger.info(f"📡 Açık Kaynak API'den haftalık maç programı çekiliyor ({start_date}-{end_date})...")
        try:
            req = urllib.request.Request(url_with_range, headers=self.headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))

            raw_matches = []
            
            # ESPN API yanıtı 'events' adında bir liste döner
            events = data.get('events', [])
            for event in events:
                try:
                    competitions = event.get('competitions', [])
                    if not competitions:
                        continue
                        
                    competitors = competitions[0].get('competitors', [])
                    if len(competitors) != 2:
                        continue
                    
                    home_team = ""
                    away_team = ""
                    
                    for comp in competitors:
                        team_name = comp.get('team', {}).get('name', '')
                        if comp.get('homeAway') == 'home':
                            home_team = team_name
                        elif comp.get('homeAway') == 'away':
                            away_team = team_name
                            
                    if home_team and away_team:
                        event_id = str(event.get('id', ''))
                        event_date = str(event.get('date', ''))[:10] # Sadece YYYY-MM-DD
                        
                        raw_matches.append({
                            "id": event_id,
                            "date": event_date,
                            "home": home_team,
                            "away": away_team
                        })
                except Exception as inner_e:
                    logger.debug(f"Event parse hatası: {inner_e}")
                    continue

            # Temizle (Aynı maçları tekrar alma)
            unique_matches = []
            seen = set()
            for m in raw_matches:
                key = f"{m['home']}_{m['away']}"
                if key not in seen:
                    seen.add(key)
                    unique_matches.append(m)

            logger.info(f"✅ API'den {len(unique_matches)} güncel maç çıkarıldı (Haftalık).")
            return unique_matches

        except Exception as e:
            logger.error(f"❌ Günlük maç tarama hatası: {e}", exc_info=True)
            return []

    def fetch_injuries(self, team_name):
        """Takımın eksik (sakat/cezalı) oyuncu durumunu API üzerinden çeker (veya mock döner)."""
        import os
        api_key = os.environ.get("API_FOOTBALL_KEY")
        if not api_key:
            return "Bilinmiyor (API Anahtarı Yok)"
        # TODO: Gerçek API-Football /injuries endpoint kullanımı
        return "1 Sakatlık İhtimali"

    def get_weekly_predictions(self):
        """Haftalık maçları çeker, DB takımlarıyla eşler ve ML tahmini üretir."""
        from analyzer import Analyzer
        analyzer = Analyzer(self.db)
        
        # En güncel Production (Champion) modelinin kullanıldığından emin ol
        self.predictor.load_model()
        
        raw_matches = self.fetch_upcoming_matches()
        if not raw_matches:
            return {"error": "Maç verisi çekilemedi veya bülten boş."}

        db_teams = self.db.get_teams()
        if not db_teams:
            return {"error": "Veritabanında takım yok. Önce verileri indirin."}

        tum_tahminler = []
        tum_tahminler_batch = []
        bankolar = []
        mapped_count = 0

        for match in raw_matches:
            # Fuzzy match ile en yakın takımı bul %40 benzerlik kafi
            home_matches = get_close_matches(match['home'], db_teams, n=1, cutoff=0.4)
            away_matches = get_close_matches(match['away'], db_teams, n=1, cutoff=0.4)

            # Sadece her iki takım da veri tabanımızda varsa tahmin edebiliriz
            if home_matches and away_matches:
                db_home = home_matches[0]
                db_away = away_matches[0]
                
                # Extracted Features (Olasılıkları anlamlandırarak göstermek için UI datası)
                h_form = analyzer.get_team_form(db_home, last_n=10)
                a_form = analyzer.get_team_form(db_away, last_n=10)
                h2h = analyzer.get_head_to_head(db_home, db_away)
                h_inj = self.fetch_injuries(db_home)
                a_inj = self.fetch_injuries(db_away)

                # Tahmin yap (Modelin kendi içinde rolling avg ve Tier hesaplanır)
                # Phase 14: Lig ve Sezon context'i ekle
                league_id = match.get('league_id', 0)
                pred = self.predictor.predict_match_ml(db_home, db_away, league_id=league_id)
                if pred and not pred.get("error"):
                    mapped_count += 1
                    
                    # Güven Skoru ve Olasılıklar
                    probs = pred.get("probabilities", {})
                    hw = probs.get("home", 0.0)
                    dw = probs.get("draw", 0.0)
                    aw = probs.get("away", 0.0)
                    
                    prediction_code = pred.get("prediction", "X")
                    highest_prob = pred.get("confidence", dw)
                    
                    # Tier ve Status Belirleme
                    tier = pred.get("tier", "🥉 BRONZE")
                    status = "Riskli"
                    is_banko = False
                    
                    if "PLATINUM" in tier:
                        status = "💎 PLATINUM (Sniper)"
                        is_banko = True
                    elif "GOLD" in tier:
                        status = "🥇 GOLD (Yüksek Güven)"
                        is_banko = True if highest_prob > 75 else False
                    elif "SILVER" in tier:
                        status = "🥈 SILVER (Spekülatif)"

                    # Tahmin Verisini Listeye Ekle (Batch için)
                    if match.get('id') and match.get('date'):
                        tum_tahminler_batch.append({
                            'id': match['id'],
                            'match_date': match['date'],
                            'home_team': db_home,
                            'away_team': db_away,
                            'predicted_result': prediction_code,
                            'confidence': highest_prob,
                            'goals_market': pred.get("goals_market", {}),
                            'win_probabilities': probs,
                            'league_id': match.get('league_id', 0),
                            'model_version': 'v1.2 (Tiered)',
                            'tier': tier,
                            'tier_confidence': pred.get("tier_confidence"),
                            'advanced_metrics': pred.get("advanced_metrics")
                        })

                    match_data = {
                        "original_home": match['home'],
                        "original_away": match['away'],
                        "db_home": db_home,
                        "db_away": db_away,
                        "match_date": match.get('date', ''),
                        "prediction": f"{prediction_code} ({tier})",
                        "win_probability": f"%{highest_prob}",
                        "status": status,
                        "tier": tier,
                        "features": {
                            "home_form_last_10": h_form.get("form_string", ""),
                            "away_form_last_10": a_form.get("form_string", ""),
                            "h2h_history": f"{db_home} {h2h.get('team1_wins',0)}W - {h2h.get('draws',0)}D - {h2h.get('team2_wins',0)}W {db_away}",
                            "home_injuries": h_inj,
                            "away_injuries": a_inj,
                            "advanced_layers": pred.get("advanced_metrics", {}).get("layers", {})
                        },
                        "probabilities": probs,
                        "goals_market": pred.get("goals_market", {})
                    }
                    
                    tum_tahminler.append(match_data)
                    
                    if is_banko:
                        bankolar.append(match_data)

        # Güven skoruna göre sırala (Önce en yüksek yüzdeliler)
        tum_tahminler.sort(key=lambda x: float(str(x['win_probability']).replace('%','')), reverse=True)
        bankolar.sort(key=lambda x: float(str(x['win_probability']).replace('%','')), reverse=True)

        # Tüm tahminleri tek bir transaction'da kaydet (Concurrency/Lock hatalarını önler)
        if tum_tahminler_batch:
            self.db.save_predictions_batch(tum_tahminler_batch)

        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_scraped": len(raw_matches),
            "total_mapped": mapped_count,
            "bankolar_count": len(bankolar),
            "bankos": bankolar,
            "predictions": tum_tahminler
        }

    def fetch_match_summary(self, match_id):
        """Tek bir maçın detaylarını (summary API) çeker."""
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={match_id}"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            logger.debug(f"Maç {match_id} özeti çekilemedi: {e}")
            return None

    def fetch_match_from_api_football(self, date, home, away):
        """API-Football (veya public alternatifler) üzerinden alternatif skor çekimi (Fallback)."""
        import os
        api_key = os.environ.get("API_FOOTBALL_KEY")
        if not api_key:
            return None
            
        url = f"https://v3.football.api-sports.io/fixtures?date={date}"
        req = urllib.request.Request(url, headers={
            'x-apisports-key': api_key,
            'x-rapidapi-host': "v3.football.api-sports.io"
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                for f in data.get("response", []):
                    h_team = f["teams"]["home"]["name"]
                    a_team = f["teams"]["away"]["name"]
                    
                    if home[:5].lower() in h_team.lower() and away[:5].lower() in a_team.lower():
                        if f["fixture"]["status"]["short"] in ["FT", "AET", "PEN"]:
                            return {
                                "home_score": f["goals"]["home"],
                                "away_score": f["goals"]["away"]
                            }
        except Exception as e:
            logger.debug(f"API-Football fallback hatası: {e}")
        return None

    def resolve_pending_predictions(self):
        """Bekleyen tahminleri ESPN API veya Fallback API'den skor sorarak sonuçlandırır."""
        resolved_count = 0
        
        # Sadece dün ve daha önceki günlerin maçlarını kontrol et (Bugün oynananlar 'pending' kalmalı)
        today = datetime.now().strftime("%Y-%m-%d")
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT id, match_date, home_team, away_team FROM predictions_history WHERE status = 'pending' AND match_date < ?", (today,))
        pending_matches = cursor.fetchall()
        
        if not pending_matches:
            logger.info("Bekleyen tahmin yok.")
            return 0
            
        # Tarihe göre gruplandır (batch request için)
        matches_by_date = {}
        for m in pending_matches:
            d = m['match_date']
            if d not in matches_by_date:
                matches_by_date[d] = []
            matches_by_date[d].append(m)
            
        for m_date, m_list in matches_by_date.items():
            try:
                # ESPN Scoreboard API - Tarih formatı: YYYYMMDD
                api_date = m_date.replace('-', '')
                url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={api_date}"
                
                events_map = {}
                try:
                    req = urllib.request.Request(url, headers=self.headers)
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode('utf-8'))
                        events = data.get('events', [])
                        events_map = {str(e.get('id')): e for e in events}
                except Exception as board_e:
                    logger.warning(f"Scoreboard API hatası ({m_date}): {board_e}")
                
                for m in m_list:
                    pid = str(m['id'])
                    event_data = events_map.get(pid)
                    
                    if not event_data:
                        # ⚡ Phase 15: Fuzzy Match by Teams/Date (id matching failed)
                        for eid, ev in events_map.items():
                            competitors = ev.get('competitions', [{}])[0].get('competitors', [])
                            ev_home = ""
                            ev_away = ""
                            for c in competitors:
                                name = c.get('team', {}).get('name', '')
                                if c.get('homeAway') == 'home': ev_home = name
                                else: ev_away = name
                            
                            # TeamMapper ile normalleştirip karşılaştır
                            if self.db.mapper.normalize(ev_home) == self.db.mapper.normalize(m['home_team']) and \
                               self.db.mapper.normalize(ev_away) == self.db.mapper.normalize(m['away_team']):
                                event_data = ev
                                logger.info(f"🔗 Maç ID uyuşmadı ama Takımlardan eşleşti: {m['home_team']} vs {m['away_team']}")
                                break

                    if not event_data:
                        logger.debug(f"Maç {pid} ({m['home_team']} vs {m['away_team']}) bulunamadı.")
                        continue
                        
                    competitions = event_data.get('competitions', [])
                    if not competitions:
                        continue
                        
                    comp = competitions[0] if competitions else {}
                    status_obj = comp.get('status', {})
                    status_type = status_obj.get('type', {}).get('name', '')
                    status_state = status_obj.get('type', {}).get('state', '')
                    
                    home_score = 0
                    away_score = 0
                    
                    # Eğer ESPN post (bitti) demezse, Fallback API deneyelim
                    fallback_used = False
                    if status_state != 'post':
                        fallback_data = self.fetch_match_from_api_football(m['match_date'], m['home_team'], m['away_team'])
                        if fallback_data:
                            home_score = fallback_data["home_score"]
                            away_score = fallback_data["away_score"]
                            status_state = 'post'
                            fallback_used = True
                    
                    if status_state == 'post':
                        if not fallback_used:
                            competitors = comp.get('competitors', [])
                            for c in competitors:
                                side = c.get('homeAway')
                                score_val = c.get('score', 0)
                                try:
                                    score = int(score_val)
                                except:
                                    score = 0
                                    
                                if side == 'home': home_score = score
                                elif side == 'away': away_score = score
                                
                        actual_res = "1" if home_score > away_score else ("2" if away_score > home_score else "X")
                        
                        # Tahmini DB'den oku
                        cursor = conn.execute("SELECT predicted_result FROM predictions_history WHERE id=?", (pid,))
                        row = cursor.fetchone()
                        if row:
                            pred_res = row['predicted_result']
                            final_status = "won" if pred_res == actual_res else "lost"
                            
                            logger.info(f"⚽ Sonuçlandı: {m['home_team']} {home_score}-{away_score} {m['away_team']} | Tahmin: {pred_res} | Gerçek: {actual_res} -> {final_status.upper()}")
                            self.db.update_prediction_result(pid, home_score, away_score, final_status)
                            resolved_count += 1
                    else:
                        logger.debug(f"Maç {pid} ({m['home_team']} vs {m['away_team']}) sonuçlanmamış. Durum: {status_type}")
                        
            except Exception as e:
                logger.error(f"Tarih {m_date} için sonuç kontrolü hatası: {e}", exc_info=True)
                
        # Tüm güncellemeler bittiyse başarı metriklerini (Accuracy vb.) güncelle
        if resolved_count > 0:
            logger.info("📈 Yeni sonuçlanan maçlar var, Başarı Metrikleri (Accuracy, F1 vs.) hesaplanıyor...")
            self.db.calculate_and_save_metrics()
            
        return resolved_count

"""
Elo Rating Sistemi
Takımların güçlerini dinamik olarak hesaplar.
Her maçtan sonra Elo'lar güncellenir, ev sahibi avantajı dahil edilir.

Referans: https://en.wikipedia.org/wiki/Elo_rating_system#Football_(soccer)
"""
import math
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Varsayılan Elo parametreleri
DEFAULT_ELO = 1500
K_FACTOR = 32          # Maç başına maksimum puan değişimi
HOME_ADVANTAGE = 100   # Ev sahibi avantajı (Elo puanı olarak)
K_FACTOR_CUP = 64      # Kupa maçları için daha yüksek K


class EloSystem:
    """
    Dinamik Elo rating sistemi.
    Her takımın ev ve deplasman için ayrı Elo'su tutulur.
    """

    def __init__(self, db=None, k_factor=K_FACTOR, home_advantage=HOME_ADVANTAGE):
        self.db = db
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.ratings = {}            # {team_name: {"home": elo, "away": elo, "matches": n}}
        self.ratings_file = os.path.join("data", "elo_ratings.json")
        self._load_ratings()

    def _load_ratings(self):
        """Kayıtlı Elo'ları JSON'dan yükler."""
        if os.path.exists(self.ratings_file):
            try:
                with open(self.ratings_file, "r", encoding="utf-8") as f:
                    self.ratings = json.load(f)
                logger.info(f"Elo ratings yüklendi: {len(self.ratings)} takım")
            except Exception as e:
                logger.error(f"Elo yükleme hatası: {e}")
                self.ratings = {}
        else:
            self.ratings = {}

    def _save_ratings(self):
        """Elo'ları JSON'a kaydeder."""
        try:
            os.makedirs(os.path.dirname(self.ratings_file), exist_ok=True)
            with open(self.ratings_file, "w", encoding="utf-8") as f:
                json.dump(self.ratings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Elo kaydetme hatası: {e}")

    def get_team_elo(self, team, venue="home"):
        """Takımın mevcut Elo'sunu döner."""
        if team not in self.ratings:
            self.ratings[team] = {"home": DEFAULT_ELO, "away": DEFAULT_ELO, "matches": 0}
        return self.ratings[team].get(venue, DEFAULT_ELO)

    def get_elo_difference(self, home_team, away_team):
        """İki takım arasındaki Elo farkını döner (ev sahibi avantajı dahil)."""
        home_elo = self.get_team_elo(home_team, "home") + self.home_advantage
        away_elo = self.get_team_elo(away_team, "away")
        return home_elo - away_elo

    def expected_score(self, elo_diff):
        """Elo farkından beklenen skoru hesaplar (0-1 arası)."""
        return 1.0 / (1.0 + math.pow(10, -elo_diff / 400))

    def update_after_match(self, home_team, away_team, home_goals, away_goals, k_factor=None):
        """
        Maç sonucuna göre Elo'ları günceller.

        Args:
            home_team: Ev sahibi takım adı
            away_team: Deplasman takım adı
            home_goals: Ev sahibi gol sayısı
            away_goals: Deplasman gol sayısı
            k_factor: Opsiyonel K faktörü (varsayılan: self.k_factor)
        """
        if k_factor is None:
            k_factor = self.k_factor

        # Takımları初始化 et
        for team in [home_team, away_team]:
            if team not in self.ratings:
                self.ratings[team] = {"home": DEFAULT_ELO, "away": DEFAULT_ELO, "matches": 0}

        # Beklenen skorları hesapla
        home_elo = self.ratings[home_team]["home"] + self.home_advantage
        away_elo = self.ratings[away_team]["away"]
        elo_diff = home_elo - away_elo

        expected_home = self.expected_score(elo_diff)
        expected_away = 1 - expected_home

        # Gerçek sonucu belirle
        if home_goals > away_goals:
            actual_home, actual_away = 1.0, 0.0
        elif home_goals < away_goals:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        # Gol farkı bonusu (büyük farklar için)
        goal_diff = abs(home_goals - away_goals)
        if goal_diff >= 4:
            multiplier = 1.5
        elif goal_diff == 3:
            multiplier = 1.25
        else:
            multiplier = 1.0

        # Elo güncellemeleri
        delta_home = k_factor * multiplier * (actual_home - expected_home)
        delta_away = k_factor * multiplier * (actual_away - expected_away)

        self.ratings[home_team]["home"] += delta_home
        self.ratings[away_team]["away"] += delta_away
        self.ratings[home_team]["matches"] = self.ratings[home_team].get("matches", 0) + 1
        self.ratings[away_team]["matches"] = self.ratings[away_team].get("matches", 0) + 1

        return {
            "home_expected": round(expected_home, 4),
            "away_expected": round(expected_away, 4),
            "home_delta": round(delta_home, 2),
            "away_delta": round(delta_away, 2),
            "home_new_elo": round(self.ratings[home_team]["home"], 1),
            "away_new_elo": round(self.ratings[away_team]["away"], 1),
        }

    def predict_match(self, home_team, away_team):
        """
        Maç öncesi Elo bazlı tahmin üretir.

        Returns:
            dict: {"home_win": float, "draw": float, "away_win": float}
        """
        elo_diff = self.get_elo_difference(home_team, away_team)
        p_home = self.expected_score(elo_diff)

        # Elo'dan beraberlik olasılığını tahmin et (empirik formül)
        # Ortalama Elo'ya bağlı beraberlik olasılığı
        avg_elo = (self.get_team_elo(home_team, "home") + self.home_advantage +
                   self.get_team_elo(away_team, "away")) / 2

        # Düşük Elo farkı = daha yüksek beraberlik olasılığı
        draw_factor = max(0.15, 0.26 - 0.0001 * abs(elo_diff))

        # 1X2 olasılıkları
        p_draw = draw_factor
        p_home_adj = p_home * (1 - p_draw)
        p_away_adj = (1 - p_home) * (1 - p_draw)

        # Normalize et
        total = p_home_adj + p_draw + p_away_adj
        if total > 0:
            p_home_adj /= total
            p_draw /= total
            p_away_adj /= total

        return {
            "home_win": round(p_home_adj, 4),
            "draw": round(p_draw, 4),
            "away_win": round(p_away_adj, 4),
            "elo_diff": round(elo_diff, 1),
            "home_elo": self.get_team_elo(home_team, "home"),
            "away_elo": self.get_team_elo(away_team, "away"),
        }

    def train_from_matches(self, matches, save=True):
        """
        Maç listesinden Elo'ları eğitir (tarihsel veri için).

        Args:
            matches: [{"home_team": str, "away_team": str, "home_goals": int, "away_goals": int, "date": str}]
            save: Kaydetme flagı
        """
        # Tarihe göre sırala
        sorted_matches = sorted(matches, key=lambda x: x.get("date") or x.get("match_date", ""))

        for m in sorted_matches:
            home = m.get("home_team", "")
            away = m.get("away_team", "")
            hg = m.get("home_goals") or m.get("fthg")
            ag = m.get("away_goals") or m.get("ftag")

            if not all([home, away, hg is not None, ag is not None]):
                continue

            try:
                self.update_after_match(home, away, int(hg), int(ag))
            except (ValueError, TypeError):
                continue

        if save:
            self._save_ratings()

        logger.info(f"Elo eğitimi tamamlandı: {len(self.ratings)} takım, {len(sorted_matches)} maç")
        return self.ratings

    def get_top_teams(self, n=20):
        """En yüksek Elo'ya sahip takımları listeler."""
        team_scores = []
        for team, data in self.ratings.items():
            avg_elo = (data.get("home", DEFAULT_ELO) + data.get("away", DEFAULT_ELO)) / 2
            team_scores.append({
                "team": team,
                "home_elo": data.get("home", DEFAULT_ELO),
                "away_elo": data.get("away", DEFAULT_ELO),
                "avg_elo": round(avg_elo, 1),
                "matches": data.get("matches", 0),
            })
        return sorted(team_scores, key=lambda x: x["avg_elo"], reverse=True)[:n]

    def get_features(self, home_team, away_team):
        """
        ML için feature dict döner.
        """
        home_elo = self.get_team_elo(home_team, "home")
        away_elo = self.get_team_elo(away_team, "away")
        elo_diff = self.get_elo_difference(home_team, away_team)
        prediction = self.predict_match(home_team, away_team)

        return {
            "home_elo": home_elo,
            "away_elo": away_elo,
            "elo_diff": elo_diff,
            "elo_home_win_prob": prediction["home_win"],
            "elo_draw_prob": prediction["draw"],
            "elo_away_win_prob": prediction["away_win"],
        }

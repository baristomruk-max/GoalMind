import math
from database import Database

class Predictor:
    """Maç tahminleri için Poisson Dağılımı tabanlı analiz motoru."""

    def __init__(self, db: Database):
        self.db = db

    def predict_match(self, home_team, away_team, league_id=None, season_id=None):
        """
        İki takım arasındaki maç için Poisson dağılımı ile sonuç tahminleri üretir.
        """
        # 1. Ligin genel ortalamalarını hesapla
        matches = self.db.get_matches(league_id=league_id, season_id=season_id, limit=100000)
        if not matches:
            return None

        total_home_goals = sum(m["fthg"] for m in matches if m["fthg"] is not None)
        total_away_goals = sum(m["ftag"] for m in matches if m["ftag"] is not None)
        total_matches = len(matches)

        avg_home_goals = total_home_goals / total_matches if total_matches > 0 else 1.5
        avg_away_goals = total_away_goals / total_matches if total_matches > 0 else 1.2

        # 2. Ev sahibi takımın evdeki gücünü hesapla
        home_matches = [m for m in matches if m["home_team"] == home_team]
        if not home_matches:
            # Takım bulunamadı - lig ortalamaları ile fallback
            home_attack_strength = 1.0
            home_defense_strength = 1.0
            num_home = 0
        else:
            home_goals_scored = sum(m["fthg"] for m in home_matches if m["fthg"] is not None)
            home_goals_conceded = sum(m["ftag"] for m in home_matches if m["ftag"] is not None)
            num_home = len(home_matches)
            home_attack_strength = (home_goals_scored / num_home) / avg_home_goals if avg_home_goals > 0 else 1.0
            home_defense_strength = (home_goals_conceded / num_home) / avg_away_goals if avg_away_goals > 0 else 1.0

        # 3. Deplasman takımının deplasmandaki gücünü hesapla
        away_matches = [m for m in matches if m["away_team"] == away_team]
        if not away_matches:
            # Takım bulunamadı - lig ortalamaları ile fallback
            away_attack_strength = 1.0
            away_defense_strength = 1.0
            num_away = 0
        else:
            away_goals_scored = sum(m["ftag"] for m in away_matches if m["ftag"] is not None)
            away_goals_conceded = sum(m["fthg"] for m in away_matches if m["fthg"] is not None)
            num_away = len(away_matches)
            away_attack_strength = (away_goals_scored / num_away) / avg_away_goals if avg_away_goals > 0 else 1.0
            away_defense_strength = (away_goals_conceded / num_away) / avg_home_goals if avg_home_goals > 0 else 1.0

        # 4. Beklenen Gol (xG) hesapla
        hg_expected = home_attack_strength * away_defense_strength * avg_home_goals
        ag_expected = away_attack_strength * home_defense_strength * avg_away_goals

        # 5. Poisson olasılık matrisini oluştur (0-5 gol arası)
        MAX_GOALS = 6
        matrix = [[0.0 for _ in range(MAX_GOALS)] for _ in range(MAX_GOALS)]
        prob_home_win = 0.0
        prob_draw = 0.0
        prob_away_win = 0.0

        for i in range(MAX_GOALS):
            for j in range(MAX_GOALS):
                prob = self._poisson(hg_expected, i) * self._poisson(ag_expected, j)
                matrix[i][j] = prob

                if i > j:
                    prob_home_win += prob
                elif i == j:
                    prob_draw += prob
                else:
                    prob_away_win += prob

        # En olası skoru bul
        most_likely_score = {"h": 0, "a": 0, "prob": 0.0}
        score_probs = []

        for i in range(MAX_GOALS):
            for j in range(MAX_GOALS):
                p = matrix[i][j]
                if p > most_likely_score["prob"]:
                    most_likely_score = {"h": i, "a": j, "prob": p}
                    
                score_probs.append({
                    "score": f"{i}-{j}",
                    "prob": round(p * 100, 2)
                })

        # İlk 5 olası skoru sırala
        score_probs.sort(key=lambda x: x["prob"], reverse=True)
        top_scores = score_probs[:5]

        # Sonuçları normalleştir
        total_1x2_prob = prob_home_win + prob_draw + prob_away_win
        
        # Ower/Under hesapla
        over_25 = 0.0
        under_25 = 0.0
        btts_yes = 0.0
        
        for i in range(MAX_GOALS):
            for j in range(MAX_GOALS):
                p = matrix[i][j]
                if i + j > 2.5:
                    over_25 += p
                else:
                    under_25 += p
                    
                if i > 0 and j > 0:
                    btts_yes += p

        return {
            "teams": {"home": home_team, "away": away_team},
            "expected_goals": {
                "home": round(hg_expected, 2),
                "away": round(ag_expected, 2)
            },
            "win_probabilities": {
                "home_win": round((prob_home_win / total_1x2_prob) * 100, 1),
                "draw": round((prob_draw / total_1x2_prob) * 100, 1),
                "away_win": round((prob_away_win / total_1x2_prob) * 100, 1)
            },
            "most_likely_score": f"{most_likely_score['h']}-{most_likely_score['a']}",
            "top_scores": top_scores,
            "goals_market": {
                "over_25": round(over_25 * 100, 1),
                "under_25": round(under_25 * 100, 1),
                "btts_yes": round(btts_yes * 100, 1),
                "btts_no": round((1 - btts_yes) * 100, 1)
            }
        }

    def _poisson(self, expected_events, actual_events):
        """Poisson dağılımı olasılık formülü."""
        return (math.exp(-expected_events) * (expected_events ** actual_events)) / math.factorial(actual_events)

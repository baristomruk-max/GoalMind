"""
Football Data App - Analiz Motoru
==================================
Takım istatistikleri, form analizi, H2H, oran analizi gibi
gelişmiş analizler sunar.
"""

import logging
from database import Database

logger = logging.getLogger(__name__)


class Analyzer:
    """Futbol verisi analiz motoru."""

    def __init__(self, db=None):
        self.db = db or Database()
        self.db.get_connection()

    def get_team_stats(self, team_name, league_id=None, season_id=None):
        """
        Bir takımın genel istatistiklerini hesaplar.
        """
        conn = self.db.get_connection()

        query = """
            SELECT * FROM matches
            WHERE (home_team = ? OR away_team = ?)
            AND fthg IS NOT NULL AND ftag IS NOT NULL
        """
        params = [team_name, team_name]

        if league_id:
            query += " AND league_id = ?"
            params.append(league_id)
        if season_id:
            query += " AND season_id = ?"
            params.append(season_id)

        query += " ORDER BY match_date DESC"
        cursor = conn.execute(query, params)
        matches = [dict(row) for row in cursor.fetchall()]

        if not matches:
            return None

        stats = {
            "team": team_name,
            "total_matches": len(matches),
            "wins": 0, "draws": 0, "losses": 0,
            "goals_for": 0, "goals_against": 0,
            "home_matches": 0, "home_wins": 0,
            "away_matches": 0, "away_wins": 0,
            "clean_sheets": 0,
            "avg_goals_scored": 0,
            "avg_goals_conceded": 0,
            "win_percentage": 0,
        }

        for m in matches:
            is_home = m["home_team"] == team_name
            if is_home:
                gf = m["fthg"]
                ga = m["ftag"]
                stats["home_matches"] += 1
                if m["ftr"] == "H":
                    stats["wins"] += 1
                    stats["home_wins"] += 1
                elif m["ftr"] == "D":
                    stats["draws"] += 1
                else:
                    stats["losses"] += 1
            else:
                gf = m["ftag"]
                ga = m["fthg"]
                stats["away_matches"] += 1
                if m["ftr"] == "A":
                    stats["wins"] += 1
                    stats["away_wins"] += 1
                elif m["ftr"] == "D":
                    stats["draws"] += 1
                else:
                    stats["losses"] += 1

            stats["goals_for"] += gf
            stats["goals_against"] += ga
            if ga == 0:
                stats["clean_sheets"] += 1

        n = stats["total_matches"]
        stats["goal_diff"] = stats["goals_for"] - stats["goals_against"]
        stats["points"] = stats["wins"] * 3 + stats["draws"]
        stats["avg_goals_scored"] = round(stats["goals_for"] / n, 2)
        stats["avg_goals_conceded"] = round(stats["goals_against"] / n, 2)
        stats["win_percentage"] = round(stats["wins"] / n * 100, 1)

        return stats

    def get_team_form(self, team_name, last_n=10, league_id=None, season_id=None):
        """
        Takımın son N maçtaki formunu döndürür.
        Returns: Maç listesi (en yeniden en eskiye) + form dizisi (W/D/L)
        """
        conn = self.db.get_connection()

        query = """
            SELECT m.*, l.name as league_name
            FROM matches m
            JOIN leagues l ON l.id = m.league_id
            WHERE (m.home_team = ? OR m.away_team = ?)
            AND m.fthg IS NOT NULL AND m.ftag IS NOT NULL
        """
        params = [team_name, team_name]

        if league_id:
            query += " AND m.league_id = ?"
            params.append(league_id)
        if season_id:
            query += " AND m.season_id = ?"
            params.append(season_id)

        query += f" ORDER BY m.match_date DESC LIMIT ?"
        params.append(last_n)

        cursor = conn.execute(query, params)
        matches = [dict(row) for row in cursor.fetchall()]

        form = []
        for m in matches:
            is_home = m["home_team"] == team_name
            if is_home:
                result = "W" if m["ftr"] == "H" else ("D" if m["ftr"] == "D" else "L")
            else:
                result = "W" if m["ftr"] == "A" else ("D" if m["ftr"] == "D" else "L")
            form.append(result)
            m["form_result"] = result

        return {
            "matches": matches,
            "form": form,
            "form_string": "".join(form),
            "wins": form.count("W"),
            "draws": form.count("D"),
            "losses": form.count("L"),
            "points": form.count("W") * 3 + form.count("D"),
        }

    def get_head_to_head(self, team1, team2, league_id=None):
        """İki takım arasındaki karşılaşma geçmişi."""
        conn = self.db.get_connection()

        query = """
            SELECT m.*, l.name as league_name, s.code as season_code
            FROM matches m
            JOIN leagues l ON l.id = m.league_id
            LEFT JOIN seasons s ON s.id = m.season_id
            WHERE (
                (m.home_team = ? AND m.away_team = ?) OR
                (m.home_team = ? AND m.away_team = ?)
            )
            AND m.fthg IS NOT NULL AND m.ftag IS NOT NULL
        """
        params = [team1, team2, team2, team1]

        if league_id:
            query += " AND m.league_id = ?"
            params.append(league_id)

        query += " ORDER BY m.match_date DESC"
        cursor = conn.execute(query, params)
        matches = [dict(row) for row in cursor.fetchall()]

        stats = {
            "team1": team1,
            "team2": team2,
            "total_matches": len(matches),
            "team1_wins": 0,
            "team2_wins": 0,
            "draws": 0,
            "team1_goals": 0,
            "team2_goals": 0,
            "matches": matches,
        }

        for m in matches:
            if m["home_team"] == team1:
                stats["team1_goals"] += m["fthg"]
                stats["team2_goals"] += m["ftag"]
                if m["ftr"] == "H":
                    stats["team1_wins"] += 1
                elif m["ftr"] == "A":
                    stats["team2_wins"] += 1
                else:
                    stats["draws"] += 1
            else:
                stats["team1_goals"] += m["ftag"]
                stats["team2_goals"] += m["fthg"]
                if m["ftr"] == "A":
                    stats["team1_wins"] += 1
                elif m["ftr"] == "H":
                    stats["team2_wins"] += 1
                else:
                    stats["draws"] += 1

        return stats

    def get_league_goal_stats(self, league_id, season_id=None):
        """Lig bazında gol istatistikleri."""
        conn = self.db.get_connection()

        query = """
            SELECT
                COUNT(*) as total_matches,
                SUM(fthg) as total_home_goals,
                SUM(ftag) as total_away_goals,
                SUM(fthg + ftag) as total_goals,
                ROUND(AVG(fthg + ftag), 2) as avg_goals,
                ROUND(AVG(fthg), 2) as avg_home_goals,
                ROUND(AVG(ftag), 2) as avg_away_goals,
                MAX(fthg + ftag) as max_goals_in_match,
                SUM(CASE WHEN fthg + ftag > 2.5 THEN 1 ELSE 0 END) as over_25,
                SUM(CASE WHEN fthg > 0 AND ftag > 0 THEN 1 ELSE 0 END) as btts,
                SUM(CASE WHEN ftr = 'H' THEN 1 ELSE 0 END) as home_wins,
                SUM(CASE WHEN ftr = 'D' THEN 1 ELSE 0 END) as draws,
                SUM(CASE WHEN ftr = 'A' THEN 1 ELSE 0 END) as away_wins
            FROM matches
            WHERE league_id = ? AND fthg IS NOT NULL AND ftag IS NOT NULL
        """
        params = [league_id]
        if season_id:
            query += " AND season_id = ?"
            params.append(season_id)

        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        if not row or row["total_matches"] == 0:
            return None

        result = dict(row)
        n = result["total_matches"]
        result["over_25_pct"] = round(result["over_25"] / n * 100, 1)
        result["btts_pct"] = round(result["btts"] / n * 100, 1)
        result["home_win_pct"] = round(result["home_wins"] / n * 100, 1)
        result["draw_pct"] = round(result["draws"] / n * 100, 1)
        result["away_win_pct"] = round(result["away_wins"] / n * 100, 1)

        return result

    def get_top_scorers_teams(self, league_id, season_id=None, limit=10):
        """En çok gol atan takımlar."""
        table = self.db.get_league_table(league_id, season_id)
        sorted_by_goals = sorted(table, key=lambda x: x["goals_for"], reverse=True)
        return sorted_by_goals[:limit]

    def get_odds_analysis(self, league_id=None, season_id=None):
        """Oran analizi - ortalama oranlar ve sonuç karşılaştırması."""
        conn = self.db.get_connection()

        query = """
            SELECT ftr,
                   ROUND(AVG(avgh), 2) as avg_home_odds,
                   ROUND(AVG(avgd), 2) as avg_draw_odds,
                   ROUND(AVG(avga), 2) as avg_away_odds,
                   COUNT(*) as count
            FROM matches
            WHERE avgh IS NOT NULL AND avgd IS NOT NULL AND avga IS NOT NULL
            AND ftr IS NOT NULL AND ftr != ''
        """
        params = []
        if league_id:
            query += " AND league_id = ?"
            params.append(league_id)
        if season_id:
            query += " AND season_id = ?"
            params.append(season_id)

        query += " GROUP BY ftr"
        cursor = conn.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]

        return results

    def get_goals_by_league(self, season_id=None):
        """
        Tüm liglerin gol ortalamalarını döndürür.
        Dashboard'da karşılaştırma grafiği için kullanılır.
        """
        conn = self.db.get_connection()

        query = """
            SELECT l.name as league_name, l.id as league_id,
                   COUNT(*) as matches,
                   ROUND(AVG(m.fthg + m.ftag), 2) as avg_goals
            FROM matches m
            JOIN leagues l ON l.id = m.league_id
            WHERE m.fthg IS NOT NULL AND m.ftag IS NOT NULL
        """
        params = []
        if season_id:
            query += " AND m.season_id = ?"
            params.append(season_id)

        query += """
            GROUP BY l.id
            HAVING COUNT(*) > 10
            ORDER BY avg_goals DESC
        """
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_recent_matches(self, limit=20):
        """En son oynanan maçları döndürür."""
        conn = self.db.get_connection()
        cursor = conn.execute("""
            SELECT m.*, l.name as league_name, s.code as season_code
            FROM matches m
            JOIN leagues l ON l.id = m.league_id
            LEFT JOIN seasons s ON s.id = m.season_id
            WHERE m.fthg IS NOT NULL
            ORDER BY m.match_date DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


if __name__ == "__main__":
    analyzer = Analyzer()
    stats = analyzer.get_team_stats("Liverpool")
    if stats:
        print(f"Team: {stats['team']}")
        print(f"Matches: {stats['total_matches']}")
        print(f"W/D/L: {stats['wins']}/{stats['draws']}/{stats['losses']}")
        print(f"Goals: {stats['goals_for']}:{stats['goals_against']}")
    else:
        print("Veri bulunamadı. Önce verileri indirin ve import edin.")

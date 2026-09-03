"""
Football Data App - Analiz Motoru (CSV/Pandas Tabanlı)
======================================================
SQLite bağımlılığı kaldırılmıştır. Analizler Pandas DataFrames üzerinden yapılır.
"""

import logging
import pandas as pd
import numpy as np
from database import Database

logger = logging.getLogger(__name__)

class Analyzer:
    """Futbol verisi analiz motoru."""

    def __init__(self, db=None):
        self.db = db or Database()

    def _get_filtered_matches(self, league_id=None, season_id=None, team=None):
        """Filtrelenmiş maçları DataFrame olarak döner."""
        if self.db.matches_df.empty:
            return pd.DataFrame()
            
        df = self.db.matches_df.copy()
        
        # Skorlu maçları filtrele
        df = df[df['fthg'].notna() & df['ftag'].notna()]
        
        if team:
            df = df[(df['home_team'] == team) | (df['away_team'] == team)]
        if league_id:
            # league_id filtresi şimdilik pasif veya Div üzerinden yapılabilir
            pass
            
        return df

    def get_team_stats(self, team_name, league_id=None, season_id=None):
        df = self._get_filtered_matches(league_id, season_id, team=team_name)
        if df.empty: return None

        matches = df.to_dict('records')
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
            gf = m["fthg"] if is_home else m["ftag"]
            ga = m["ftag"] if is_home else m["fthg"]
            
            if is_home:
                stats["home_matches"] += 1
                if m["ftr"] == "H": stats["home_wins"] += 1
            else:
                stats["away_matches"] += 1
                if m["ftr"] == "A": stats["away_wins"] += 1

            if (is_home and m["ftr"] == "H") or (not is_home and m["ftr"] == "A"):
                stats["wins"] += 1
            elif m["ftr"] == "D":
                stats["draws"] += 1
            else:
                stats["losses"] += 1

            stats["goals_for"] += gf
            stats["goals_against"] += ga
            if ga == 0: stats["clean_sheets"] += 1

        n = stats["total_matches"]
        stats["goal_diff"] = stats["goals_for"] - stats["goals_against"]
        stats["points"] = stats["wins"] * 3 + stats["draws"]
        stats["avg_goals_scored"] = round(stats["goals_for"] / n, 2)
        stats["avg_goals_conceded"] = round(stats["goals_against"] / n, 2)
        stats["win_percentage"] = round(stats["wins"] / n * 100, 1)
        return stats

    def get_team_form(self, team_name, last_n=10, league_id=None, season_id=None):
        df = self._get_filtered_matches(league_id, season_id, team=team_name)
        if df.empty: return {"matches": [], "form": []}
        
        df = df.sort_values(by='match_date', ascending=False).head(last_n)
        matches = df.to_dict('records')
        
        form = []
        for m in matches:
            is_home = m["home_team"] == team_name
            if (is_home and m["ftr"] == "H") or (not is_home and m["ftr"] == "A"):
                res = "W"
            elif m["ftr"] == "D":
                res = "D"
            else:
                res = "L"
            form.append(res)
            m["form_result"] = res
            m["league_name"] = m.get("league_div", "Unknown")

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
        df = self.db.matches_df
        if df.empty: return {"matches": []}
        
        df = df[((df['home_team'] == team1) & (df['away_team'] == team2)) | 
                ((df['home_team'] == team2) & (df['away_team'] == team1))]
        df = df[df['fthg'].notna() & df['ftag'].notna()].sort_values(by='match_date', ascending=False)
        
        matches = df.to_dict('records')
        stats = {
            "team1": team1, "team2": team2, "total_matches": len(matches),
            "team1_wins": 0, "team2_wins": 0, "draws": 0,
            "team1_goals": 0, "team2_goals": 0, "matches": matches,
        }

        for m in matches:
            if m["home_team"] == team1:
                stats["team1_goals"] += m["fthg"]; stats["team2_goals"] += m["ftag"]
                if m["ftr"] == "H": stats["team1_wins"] += 1
                elif m["ftr"] == "A": stats["team2_wins"] += 1
                else: stats["draws"] += 1
            else:
                stats["team1_goals"] += m["ftag"]; stats["team2_goals"] += m["fthg"]
                if m["ftr"] == "A": stats["team1_wins"] += 1
                elif m["ftr"] == "H": stats["team2_wins"] += 1
                else: stats["draws"] += 1
        return stats

    def get_league_goal_stats(self, league_id, season_id=None):
        df = self.db.matches_df
        if df.empty: return None
        # league_id mapping needs to be implemented or using league_div
        # For now, generic stats
        df = df[df['fthg'].notna()]
        if df.empty: return None
        
        n = len(df)
        h_goals = df['fthg'].sum()
        a_goals = df['ftag'].sum()
        over25 = len(df[(df['fthg'] + df['ftag']) > 2.5])
        btts = len(df[(df['fthg'] > 0) & (df['ftag'] > 0)])
        
        return {
            "total_matches": n,
            "total_home_goals": int(h_goals),
            "total_away_goals": int(a_goals),
            "total_goals": int(h_goals + a_goals),
            "avg_goals": round((h_goals + a_goals) / n, 2),
            "over_25_pct": round(over25 / n * 100, 1),
            "btts_pct": round(btts / n * 100, 1),
            "home_win_pct": round(len(df[df['ftr'] == 'H']) / n * 100, 1),
            "draw_pct": round(len(df[df['ftr'] == 'D']) / n * 100, 1),
            "away_win_pct": round(len(df[df['ftr'] == 'A']) / n * 100, 1)
        }

    def get_recent_matches(self, limit=20):
        if self.db.matches_df.empty: return []
        df = self.db.matches_df[self.db.matches_df['fthg'].notna()]
        df = df.sort_values(by='match_date', ascending=False).head(limit)
        df['match_date'] = df['match_date'].dt.strftime('%Y-%m-%d')
        res = df.to_dict('records')
        for r in res:
            r['league_name'] = r.get('league_div', 'Unknown')
        return res

    def get_goals_by_league(self, season_id=None):
        if self.db.matches_df.empty: return []
        df = self.db.matches_df[self.db.matches_df['fthg'].notna()]
        # Group by Div
        grouped = df.groupby('league_div').agg(
            matches=('fthg', 'count'),
            avg_goals=('fthg', lambda x: round((x + df.loc[x.index, 'ftag']).mean(), 2))
        ).reset_index()
        grouped = grouped[grouped['matches'] > 10].sort_values(by='avg_goals', ascending=False)
        return grouped.rename(columns={'league_div': 'league_name'}).to_dict('records')

if __name__ == "__main__":
    analyzer = Analyzer()
    print("Analyzer ready.")

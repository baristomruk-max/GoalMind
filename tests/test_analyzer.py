import sys
import os
import pytest
import pandas as pd
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer import Analyzer


class TestAnalyzer:
    """Analyzer fonksiyonları için testler."""

    def setup_method(self):
        self.db = MagicMock()
        self.analyzer = Analyzer(self.db)

    def test_empty_df_returns_none_for_team_stats(self):
        """Boş DataFrame ile takım istatistiği None dönmeli."""
        self.db.matches_df = pd.DataFrame()
        result = self.analyzer.get_team_stats("TeamA")
        assert result is None

    def test_team_stats_basic(self, sample_matches_df):
        """Temel takım istatistiği hesaplama."""
        self.db.matches_df = sample_matches_df
        result = self.analyzer.get_team_stats("Galatasaray")

        assert result is not None
        assert result["team"] == "Galatasaray"
        assert result["total_matches"] == 5
        assert result["wins"] == 4
        assert result["draws"] == 1
        assert result["losses"] == 0
        assert result["goals_for"] == 9
        assert result["goals_against"] == 2
        assert result["win_percentage"] == 80.0

    def test_team_stats_points(self, sample_matches_df):
        """Puan hesaplama testi."""
        self.db.matches_df = sample_matches_df
        result = self.analyzer.get_team_stats("Galatasaray")
        assert result["points"] == 13  # 4*3 + 1

    def test_team_stats_goal_diff(self, sample_matches_df):
        """Gol farkı hesaplama testi."""
        self.db.matches_df = sample_matches_df
        result = self.analyzer.get_team_stats("Galatasaray")
        assert result["goal_diff"] == 7  # 9 - 2

    def test_team_stats_home_away(self, sample_matches_df):
        """Ev/deplasman ayrımı testi."""
        self.db.matches_df = sample_matches_df
        result = self.analyzer.get_team_stats("Galatasaray")
        assert result["home_matches"] == 3
        assert result["away_matches"] == 2

    def test_team_form(self, sample_matches_df):
        """Takım form analizi testi."""
        self.db.matches_df = sample_matches_df
        result = self.analyzer.get_team_form("Galatasaray", last_n=5)

        assert "form" in result
        assert "form_string" in result
        assert len(result["form"]) == 5
        assert result["wins"] == 4
        assert result["draws"] == 1
        assert result["points"] == 13

    def test_head_to_head(self, sample_matches_df):
        """Karşılıklı maç analizi testi."""
        self.db.matches_df = sample_matches_df
        result = self.analyzer.get_head_to_head("Galatasaray", "Fenerbahce")

        assert result["total_matches"] == 2
        assert result["team1"] == "Galatasaray"
        assert result["team2"] == "Fenerbahce"

    def test_head_to_head_empty(self):
        """Karşılıklı maç yoksa boş sonuç dönmeli."""
        self.db.matches_df = pd.DataFrame()
        result = self.analyzer.get_head_to_head("TeamA", "TeamB")
        assert result["matches"] == []

    def test_get_goals_by_league(self):
        """Lig bazında gol istatistikleri testi."""
        df = pd.DataFrame([
            {"home_team": "A", "away_team": "B", "fthg": 2, "ftag": 1, "ftr": "H", "match_date": "2025-01-01", "league_div": "E0"},
        ] * 15)
        self.db.matches_df = df
        result = self.analyzer.get_goals_by_league()
        assert len(result) > 0

    def test_get_recent_matches(self):
        """Son maçları getirme testi."""
        import pandas as pd
        df = pd.DataFrame([
            {"home_team": "A", "away_team": "B", "fthg": 2, "ftag": 1, "ftr": "H", "match_date": pd.Timestamp("2025-01-01"), "league_div": "E0"},
            {"home_team": "C", "away_team": "D", "fthg": 1, "ftag": 0, "ftr": "H", "match_date": pd.Timestamp("2025-02-01"), "league_div": "E0"},
            {"home_team": "E", "away_team": "F", "fthg": 3, "ftag": 2, "ftr": "H", "match_date": pd.Timestamp("2025-03-01"), "league_div": "E0"},
        ])
        self.db.matches_df = df
        result = self.analyzer.get_recent_matches(limit=3)
        assert len(result) == 3

    def test_team_not_found(self, sample_matches_df):
        """Takım bulunamadığında boş istatistik dönmeli."""
        self.db.matches_df = sample_matches_df
        result = self.analyzer.get_team_stats("NonExistentTeam")
        assert result is None

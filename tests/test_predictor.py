import math
import sys
import os
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from predictor import Predictor


class TestPoisson:
    """Poisson dağılımı fonksiyonu için testler."""

    def setup_method(self):
        self.db = MagicMock()
        self.predictor = Predictor(self.db)

    def test_poisson_zero_events(self):
        """0 gol olasılığı testi."""
        result = self.predictor._poisson(1.5, 0)
        expected = math.exp(-1.5)
        assert abs(result - expected) < 1e-10

    def test_poisson_one_event(self):
        """1 gol olasılığı testi."""
        result = self.predictor._poisson(1.5, 1)
        expected = math.exp(-1.5) * 1.5
        assert abs(result - expected) < 1e-10

    def test_poisson_two_events(self):
        """2 gol olasılığı testi."""
        result = self.predictor._poisson(2.0, 2)
        expected = math.exp(-2.0) * (2.0 ** 2) / math.factorial(2)
        assert abs(result - expected) < 1e-10

    def test_poisson_probabilities_sum_to_one(self):
        """Tüm olasılıkların toplamı 1'e yakın olmalı."""
        total = sum(self.predictor._poisson(1.5, i) for i in range(20))
        assert abs(total - 1.0) < 1e-6

    def test_poisson_zero_expected(self):
        """Beklenen gol 0 iken sadece 0 gol olasılığı 1 olmalı."""
        assert self.predictor._poisson(0, 0) == 1.0
        assert self.predictor._poisson(0, 1) == 0.0


class TestPredictMatch:
    """predict_match fonksiyonu için testler."""

    def setup_method(self):
        self.db = MagicMock()
        self.predictor = Predictor(self.db)

    def test_no_matches_returns_none(self):
        """Maç yoksa None dönmeli."""
        self.db.get_matches.return_value = []
        result = self.predictor.predict_match("TeamA", "TeamB")
        assert result is None

    def test_returns_valid_structure(self):
        """Geçerli veri ile doğru yapı dönmeli."""
        self.db.get_matches.return_value = [
            {"home_team": "TeamA", "away_team": "TeamB", "fthg": 2, "ftag": 1},
            {"home_team": "TeamB", "away_team": "TeamA", "fthg": 1, "ftag": 2},
        ]
        result = self.predictor.predict_match("TeamA", "TeamB")

        assert result is not None
        assert "teams" in result
        assert "expected_goals" in result
        assert "win_probabilities" in result
        assert "goals_market" in result
        assert result["teams"]["home"] == "TeamA"
        assert result["teams"]["away"] == "TeamB"

    def test_probabilities_sum_to_100(self):
        """1X2 olasılıklarının toplamı ~100 olmalı."""
        self.db.get_matches.return_value = [
            {"home_team": "TeamA", "away_team": "TeamB", "fthg": 2, "ftag": 1},
        ]
        result = self.predictor.predict_match("TeamA", "TeamB")
        probs = result["win_probabilities"]
        total = probs["home_win"] + probs["draw"] + probs["away_win"]
        assert abs(total - 100.0) < 1.0

    def test_over_under_complement(self):
        """Over 2.5 + Under 2.5 toplamı yaklaşık 100 olmalı (MAX_GOALS=6 truncation)."""
        self.db.get_matches.return_value = [
            {"home_team": "TeamA", "away_team": "TeamB", "fthg": 3, "ftag": 1},
        ]
        result = self.predictor.predict_match("TeamA", "TeamB")
        gm = result["goals_market"]
        total = gm["over_25"] + gm["under_25"]
        assert 85.0 < total <= 100.0

    def test_unknown_team_uses_league_average(self):
        """Bilinmeyen takım lig ortalamasıyla hesaplanmalı."""
        self.db.get_matches.return_value = [
            {"home_team": "TeamA", "away_team": "TeamB", "fthg": 2, "ftag": 1},
        ]
        result = self.predictor.predict_match("UnknownTeam", "TeamB")
        assert result is not None
        assert "expected_goals" in result

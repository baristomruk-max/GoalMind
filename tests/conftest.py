import sys
import os
import pytest
import pandas as pd
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_db():
    """Mock Database instance."""
    db = MagicMock()
    db.matches_df = pd.DataFrame()
    return db


@pytest.fixture
def sample_matches_df():
    """Örnek maç verisi içeren DataFrame."""
    return pd.DataFrame([
        {"home_team": "Galatasaray", "away_team": "Fenerbahce", "fthg": 2, "ftag": 1, "ftr": "H", "match_date": "2025-01-15", "league_div": "T1"},
        {"home_team": "Galatasaray", "away_team": "Besiktas", "fthg": 3, "ftag": 0, "ftr": "H", "match_date": "2025-01-20", "league_div": "T1"},
        {"home_team": "Fenerbahce", "away_team": "Galatasaray", "fthg": 1, "ftag": 1, "ftr": "D", "match_date": "2025-02-01", "league_div": "T1"},
        {"home_team": "Trabzonspor", "away_team": "Galatasaray", "fthg": 0, "ftag": 2, "ftr": "A", "match_date": "2025-02-10", "league_div": "T1"},
        {"home_team": "Galatasaray", "away_team": "Trabzonspor", "fthg": 1, "ftag": 0, "ftr": "H", "match_date": "2025-02-15", "league_div": "T1"},
        {"home_team": "Besiktas", "away_team": "Fenerbahce", "fthg": 2, "ftag": 2, "ftr": "D", "match_date": "2025-02-20", "league_div": "T1"},
        {"home_team": "Fenerbahce", "away_team": "Trabzonspor", "fthg": 3, "ftag": 1, "ftr": "H", "match_date": "2025-03-01", "league_div": "T1"},
        {"home_team": "Trabzonspor", "away_team": "Besiktas", "fthg": 0, "ftag": 1, "ftr": "A", "match_date": "2025-03-05", "league_div": "T1"},
    ])


@pytest.fixture
def sample_matches_list():
    """Örnek maç verisi içeren dict listesi."""
    return [
        {"home_team": "Galatasaray", "away_team": "Fenerbahce", "fthg": 2, "ftag": 1, "ftr": "H", "match_date": "2025-01-15"},
        {"home_team": "Galatasaray", "away_team": "Besiktas", "fthg": 3, "ftag": 0, "ftr": "H", "match_date": "2025-01-20"},
        {"home_team": "Fenerbahce", "away_team": "Galatasaray", "fthg": 1, "ftag": 1, "ftr": "D", "match_date": "2025-02-01"},
        {"home_team": "Trabzonspor", "away_team": "Galatasaray", "fthg": 0, "ftag": 2, "ftr": "A", "match_date": "2025-02-10"},
    ]

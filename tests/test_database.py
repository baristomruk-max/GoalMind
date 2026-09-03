import sys
import os
import pytest
import pandas as pd
import tempfile
import shutil
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDatabaseCSVReading:
    """CSV okuma fonksiyonları için testler."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_read_csv_utf8(self):
        """UTF-8 encoding ile CSV okuma."""
        csv_path = os.path.join(self.test_dir, "test_utf8.csv")
        content = "home_team,away_team,fthg,ftag,ftr\nTeamA,TeamB,2,1,H\n"
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(content)

        df = pd.read_csv(csv_path, encoding="utf-8")
        assert len(df) == 1
        assert df.iloc[0]["home_team"] == "TeamA"

    def test_read_csv_latin1(self):
        """Latin-1 encoding ile CSV okuma."""
        csv_path = os.path.join(self.test_dir, "test_latin1.csv")
        content = "home_team,away_team,fthg,ftag,ftr\nTeamA,TeamB,2,1,H\n"
        with open(csv_path, "w", encoding="latin-1") as f:
            f.write(content)

        df = pd.read_csv(csv_path, encoding="latin-1")
        assert len(df) == 1
        assert df.iloc[0]["home_team"] == "TeamA"

    def test_empty_csv(self):
        """Boş CSV dosyası."""
        csv_path = os.path.join(self.test_dir, "empty.csv")
        with open(csv_path, "w") as f:
            f.write("")

        try:
            df = pd.read_csv(csv_path)
            assert df.empty
        except pd.errors.EmptyDataError:
            pass  # Bu da kabul edilebilir

    def test_column_rename_map(self):
        """Sütun isimleri doğru eşlenmeli."""
        csv_path = os.path.join(self.test_dir, "test_rename.csv")
        content = "HomeTeam,AwayTeam,FTHG,FTAG,FTR,Date,Div\nTeamA,TeamB,2,1,H,2025-01-01,T1\n"
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(content)

        df = pd.read_csv(csv_path, encoding="utf-8")
        rename_map = {
            'HomeTeam': 'home_team',
            'AwayTeam': 'away_team',
            'FTHG': 'fthg',
            'FTAG': 'ftag',
            'FTR': 'ftr',
            'Date': 'match_date',
            'Div': 'league_div',
        }
        df = df.rename(columns=rename_map)

        assert "home_team" in df.columns
        assert "away_team" in df.columns
        assert df.iloc[0]["home_team"] == "TeamA"


class TestDatabaseOperations:
    """Veritabanı işlemleri için testler."""

    def test_dataframe_filtering(self):
        """DataFrame filtreleme testi."""
        df = pd.DataFrame([
            {"home_team": "A", "away_team": "B", "fthg": 2, "ftag": 1},
            {"home_team": "C", "away_team": "D", "fthg": None, "ftag": None},
        ])

        filtered = df[df['fthg'].notna() & df['ftag'].notna()]
        assert len(filtered) == 1
        assert filtered.iloc[0]["home_team"] == "A"

    def test_groupby_operations(self):
        """GroupBy işlemleri testi."""
        df = pd.DataFrame([
            {"league_div": "E0", "fthg": 2, "ftag": 1},
            {"league_div": "E0", "fthg": 3, "ftag": 0},
            {"league_div": "SP1", "fthg": 1, "ftag": 1},
        ])

        grouped = df.groupby('league_div').agg(
            matches=('fthg', 'count'),
            avg_goals=('fthg', 'mean')
        ).reset_index()

        assert len(grouped) == 2
        e0 = grouped[grouped['league_div'] == 'E0']
        assert e0.iloc[0]['matches'] == 2

    def test_prediction_json_serialization(self):
        """JSON serializasyonu testi."""
        import json
        data = {
            "home_win": 45.5,
            "draw": 25.0,
            "away_win": 29.5
        }
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["home_win"] == 45.5

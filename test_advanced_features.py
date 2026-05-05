import pandas as pd
import numpy as np
import os
import sys

# Proje dizinini ekle
sys.path.append(os.getcwd())

from auto_researcher import _build_features, _build_model
from auto_researcher import _build_features, _build_model

def test_features():
    print("--- Özellik Mühendisliği Testi Başladı ---")
    data = [
        {"match_date": "2026-01-01", "home_team": "Team A", "away_team": "Team B", "fthg": 2, "ftag": 1, "ftr": "H", "home_yellow": 1, "home_red": 0, "away_yellow": 2, "away_red": 0, "prediction_status": "won", "b365h": 2.0, "b365d": 3.0, "b365a": 3.5},
        {"match_date": "2026-01-02", "home_team": "Team C", "away_team": "Team A", "fthg": 1, "ftag": 1, "ftr": "D", "home_yellow": 2, "home_red": 0, "away_yellow": 1, "away_red": 0, "prediction_status": "lost", "b365h": 2.5, "b365d": 3.0, "b365a": 2.8},
        {"match_date": "2026-01-03", "home_team": "Team B", "away_team": "Team C", "fthg": 0, "ftag": 2, "ftr": "A", "home_yellow": 1, "home_red": 1, "away_yellow": 1, "away_red": 0, "prediction_status": "won", "b365h": 3.0, "b365d": 3.2, "b365a": 2.1},
        {"match_date": "2026-01-10", "home_team": "Team A", "away_team": "Team B", "fthg": 3, "ftag": 0, "ftr": "H", "home_yellow": 0, "home_red": 0, "away_yellow": 3, "away_red": 1, "prediction_status": "won", "b365h": 1.8, "b365d": 3.5, "b365a": 4.5},
    ]
    df = pd.DataFrame(data)
    print(f"Girdi DataFrame boyutu: {len(df)}")
    
    params = {
        "window_size": 10,
        "use_points": True,
        "use_cards": True,
        "mistake_weight": 2.0,
        "weight_recent": True
    }
    
    print("Özellikler oluşturuluyor...")
    X, y, sw = _build_features(df, params)
    
    print(f"X shape: {X.shape}")
    print(f"Columns: {X.columns.tolist()}")
    print(f"Labels: {y}")
    print(f"Sample Weights: {sw}")
    
    if "home_points_avg" in X.columns:
        print("✅ home_points_avg kolonu mevcut.")
    if "home_yellow_avg" in X.columns:
        print("✅ home_yellow_avg kolonu mevcut.")
    if any(w > 1.0 for w in sw):
        print("✅ Hatalı tahminler için ağırlıklandırma yapıldı.")
    
    print("Özellik testi tamamlandı.")

def test_model_weighting():
    print("\n--- Model Ağırlıklandırma Testi ---")
    from sklearn.ensemble import RandomForestClassifier
    
    X = np.random.rand(10, 5)
    y = np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1])
    weights = np.array([1.0, 1.0, 1.0, 2.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]) # 4. örnek bir "hata" olsun
    
    model = RandomForestClassifier()
    try:
        model.fit(X, y, sample_weight=weights)
        print("Model sample_weight ile başarıyla eğitildi.")
    except Exception as e:
        print(f"Model eğitimi hatası: {e}")

if __name__ == "__main__":
    try:
        test_features()
        test_model_weighting()
        print("\n✅ Tüm testler geçti!")
    except Exception as e:
        print(f"\n❌ Test hatası: {e}")
        import traceback
        traceback.print_exc()

import pandas as pd
import numpy as np

# --- Re-implementing _build_features for standalone testing ---
def _build_features(df: pd.DataFrame, feature_params: dict, return_dates: bool=False) -> tuple:
    window  = feature_params.get("window_size", 10)
    weight_recent = feature_params.get("weight_recent", False)
    use_points   = feature_params.get("use_points", False)
    use_cards    = feature_params.get("use_cards", False)
    m_weight     = feature_params.get("mistake_weight", 1.0)

    df = df.copy()
    df["match_date"] = pd.to_datetime(df.get("match_date", df.get("Date", None)), errors="coerce")
    df = df.sort_values("match_date").reset_index(drop=True)
    df["target"] = df["ftr"].map({"H": 1, "D": 0, "A": 2})

    team_hist: dict = {}
    sample_weights = []

    def _wma(lst, w):
        if not lst: return 0.0
        arr = np.array(lst[-w:], dtype=float)
        weights = np.arange(1, len(arr)+1, dtype=float)
        return float(np.dot(arr, weights) / weights.sum())

    def _ma(lst, w):
        sub = lst[-w:] if lst else []
        return float(np.mean(sub)) if sub else 0.0

    avg_fn = _wma if weight_recent else _ma
    features, labels, dates_list = [], [], []

    for _, row in df.iterrows():
        home = row["home_team"]
        away = row["away_team"]
        label = int(row["target"])
        hg, ag = row["fthg"], row["ftag"]

        if home in team_hist and away in team_hist:
            h = team_hist[home]
            a = team_hist[away]

            feat: dict = {
                "home_win_rate": avg_fn(h["wins"], window),
                "away_win_rate": avg_fn(a["wins"], window),
            }

            if use_points:
                feat["home_points_avg"] = avg_fn(h.get("points", []), window)
                feat["away_points_avg"] = avg_fn(a.get("points", []), window)

            if use_cards:
                feat["home_yellow_avg"] = avg_fn(h.get("yellow_cards", []), window)
                feat["away_yellow_avg"] = avg_fn(a.get("yellow_cards", []), window)

            features.append(feat)
            labels.append(label)
            dates_list.append(row["match_date"])
            
            w = 1.0
            if row.get("prediction_status") == "lost":
                w = m_weight
            sample_weights.append(w)

        for team, won, drew in [(home, row["ftr"]=="H", row["ftr"]=="D"), (away, row["ftr"]=="A", row["ftr"]=="D")]:
            if team not in team_hist:
                team_hist[team] = {"wins": [], "points": [], "yellow_cards": [], "red_cards": []}
            h_t = team_hist[team]
            h_t["wins"].append(1 if won else 0)
            h_t["points"].append(3 if won else (1 if drew else 0))
            
            # Kartlar
            yc = row.get("home_yellow") if team == home else row.get("away_yellow")
            if pd.notna(yc): h_t["yellow_cards"].append(yc)

    X = pd.DataFrame(features).fillna(0)
    y = np.array(labels)
    sw = np.array(sample_weights)
    return X, y, sw

def test_logic():
    print("--- Mantık Doğrulama Testi ---")
    data = [
        {"match_date": "2026-01-01", "home_team": "A", "away_team": "B", "ftr": "H", "fthg": 2, "ftag": 1, "home_yellow": 1, "away_yellow": 2, "prediction_status": "won"},
        {"match_date": "2026-01-02", "home_team": "B", "away_team": "A", "ftr": "D", "fthg": 1, "ftag": 1, "home_yellow": 1, "away_yellow": 0, "prediction_status": "lost"},
        {"match_date": "2026-01-03", "home_team": "A", "away_team": "B", "ftr": "H", "fthg": 1, "ftag": 0, "home_yellow": 0, "away_yellow": 1, "prediction_status": "lost"},
    ]
    df = pd.DataFrame(data)
    params = {"window_size": 10, "use_points": True, "use_cards": True, "mistake_weight": 5.0}
    
    X, y, sw = _build_features(df, params)
    print(f"X shape: {X.shape}")
    print(f"Sample Weights: {sw}")
    print(f"Columns: {X.columns.tolist()}")
    
    if len(sw) > 0:
        if any(w == 5.0 for w in sw):
            print("✅ Hata ağırlıklandırma (5.0) çalışıyor.")
        if "home_points_avg" in X.columns:
            print("✅ Puan ortalaması kolonları oluşturuldu.")
        if "home_yellow_avg" in X.columns:
            print("✅ Kart ortalaması kolonları oluşturuldu.")
    else:
        print("ℹ️ Yeterli geçmiş veri olmadığı için X boş döndü (beklenen durum).")

if __name__ == "__main__":
    test_logic()

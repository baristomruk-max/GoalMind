"""
xG Hesaplama Modülü
===================
Mevcut maç verilerinden temel xG (Expected Goals) hesaplar.

Basit Model:
- xG = (şutlar * 0.10) + (isabete şutlar * 0.15) + (goller * 0.05)
- Bu, istatistiksel bir tahmindir, profesyonel xG modelleri kadar doğru değildir.
"""

# Lig bazında ortalama conversion rate (gol/şut)
LEAGUE_CONVERSION_RATES = {
    "Premier League": 0.12,
    "La Liga": 0.11,
    "Bundesliga": 0.13,
    "Serie A": 0.10,
    "Ligue 1": 0.11,
    "Super Lig": 0.10,
    "Championship": 0.09,
    "Eredivisie": 0.12,
    "Liga Nos": 0.10,
    "Jupiler League": 0.11,
    "Brasileirao Serie A": 0.10,
    "Brasileirao Serie B": 0.09,
    "Liga MX": 0.10,
    "MLS": 0.11,
    "Scottish Premiership": 0.10,
    "Super League": 0.10,
    "Categoría Primera A": 0.09,
    "Copa do Brasil": 0.10,
    "USL Championship": 0.09,
}

# Varsayılan conversion rate
DEFAULT_CONVERSION = 0.10


def calculate_xg(home_shots=0, away_shots=0, home_shots_on_target=0, away_shots_on_target=0,
                  home_goals=0, away_goals=0, league_name=None):
    """
    Maç verilerinden temel xG hesaplar.
    
    Args:
        home_shots: Ev sahibi toplam şut
        away_shots: Deplasman toplam şut
        home_shots_on_target: Ev sahibi isabete şut
        away_shots_on_target: Deplasman isabete şut
        home_goals: Ev sahibi gol
        away_goals: Deplasman gol
        league_name: Lig adı (conversion rate için)
    
    Returns:
        dict: {"home_xg": float, "away_xg": float}
    """
    # Lig conversion rate'ini al
    conversion = DEFAULT_CONVERSION
    if league_name:
        for league, rate in LEAGUE_CONVERSION_RATES.items():
            if league.lower() in league_name.lower() or league_name.lower() in league.lower():
                conversion = rate
                break
    
    # Basit xG modeli:
    # - Şut başına beklenen gol: conversion rate
    # - İsabete şut: 2x daha değerli
    # - Gol:小小的 bonus (gerçek xG'de gol = 1.0, ama burada tahmin ediyoruz)
    
    if home_shots > 0 or home_shots_on_target > 0:
        home_xg = (home_shots * conversion * 0.5) + (home_shots_on_target * conversion * 1.5)
    else:
        # Şut verisi yoksa, gol ve İY skoruna bakarak tahmin et
        home_xg = home_goals * 0.85  # Gol başına ~0.85 xG (biraz eksik)


    
    if away_shots > 0 or away_shots_on_target > 0:
        away_xg = (away_shots * conversion * 0.5) + (away_shots_on_target * conversion * 1.5)
    else:
        away_xg = away_goals * 0.85
    
    return {
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2)
    }


def estimate_xg_from_match(match_data):
    """
    Maç verisi dict'inden xG hesaplar.
    
    Args:
        match_data: Dict with keys like 'home_shots', 'away_shots', 'home_goals', etc.
    
    Returns:
        dict: {"home_xg": float, "away_xg": float}
    """
    return calculate_xg(
        home_shots=match_data.get('home_shots', 0) or 0,
        away_shots=match_data.get('away_shots', 0) or 0,
        home_shots_on_target=match_data.get('home_shots_on_target', 0) or 0,
        away_shots_on_target=match_data.get('away_shots_on_target', 0) or 0,
        home_goals=match_data.get('home_goals', 0) or match_data.get('FTHG', 0) or 0,
        away_goals=match_data.get('away_goals', 0) or match_data.get('FTAG', 0) or 0,
        league_name=match_data.get('Div', '') or match_data.get('league', ''),
    )


# Test
if __name__ == "__main__":
    # Premier League maçı örneği
    result = calculate_xg(
        home_shots=15, away_shots=10,
        home_shots_on_target=6, away_shots_on_target=4,
        home_goals=2, away_goals=1,
        league_name="Premier League"
    )
    print(f"Premier League: Home xG={result['home_xg']}, Away xG={result['away_xg']}")
    
    # Şut verisi olmayan maç
    result2 = calculate_xg(
        home_goals=3, away_goals=2,
        league_name="Super Lig"
    )
    print(f"Super Lig (no shots): Home xG={result2['home_xg']}, Away xG={result2['away_xg']}")

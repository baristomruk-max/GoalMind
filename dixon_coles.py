"""
Dixon-Coles Modeli (1997)
Poisson dağılımının gelişmiş hali. Düşük skorlu beraberlikleri (0-0, 1-1)
daha doğru tahmin eder çünkü ev ve deplasman gollerini bağımsız varsaymaz.

Referans: Dixon, M.J. & Coles, S.G. (1997). "Modelling Association Football
Scores and Inefficiencies in the Football Betting Market".
Journal of the Royal Statistical Society: Series C, 46, 265-280.
"""
import math
import logging
import numpy as np
from scipy.optimize import minimize
from scipy.special import factorial

logger = logging.getLogger(__name__)

MAX_GOALS = 8  # Maksimum gol sayısı (matris boyutu)


def _poisson_pmf(k, lam):
    """Poisson olasılık kütle fonksiyonu."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam ** k) * math.exp(-lam) / factorial(k, exact=False)


def _tau(x, y, lambda_val, mu_val, rho):
    """
    Dixon-Coles tau fonksiyonu.
    Düşük skorlu sonuçlar için korelasyon düzeltmesi uygular.

    Args:
        x: Ev sahibi gol sayısı
        y: Deplasman gol sayısı
        lambda_val: Ev sahibi beklenen gol
        mu_val: Deplasman beklenen gol
        rho: Korelasyon parametresi (-1 ile 1 arası)
    """
    if x == 0 and y == 0:
        return 1 - lambda_val * mu_val * rho
    elif x == 0 and y == 1:
        return 1 + lambda_val * rho
    elif x == 1 and y == 0:
        return 1 + mu_val * rho
    elif x == 1 and y == 1:
        return 1 - rho
    else:
        return 1.0


def dixon_coles_prob_matrix(lambda_val, mu_val, rho, max_goals=MAX_GOALS):
    """
    Dixon-Coles olasılık matrisini hesaplar.

    Args:
        lambda_val: Ev sahibi beklenen gol sayısı
        mu_val: Deplasman beklenen gol sayısı
        rho: Korelasyon parametresi
        max_goals: Matris boyutu

    Returns:
        (max_goals+1) x (max_goals+1) olasılık matrisi
    """
    matrix = np.zeros((max_goals + 1, max_goals + 1))

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p_poisson = _poisson_pmf(i, lambda_val) * _poisson_pmf(j, mu_val)
            tau = _tau(i, j, lambda_val, mu_val, rho)
            matrix[i, j] = p_poisson * tau

    # Normalize et (toplam 1 olmalı)
    total = matrix.sum()
    if total > 0:
        matrix /= total

    return matrix


def extract_1x2(matrix):
    """Matrisden 1X2 olasılıklarını hesaplar."""
    p_home = np.sum(np.tril(matrix, -1))  # Ev sahibi galibiyet (alt üçgen)
    p_away = np.sum(np.triu(matrix, 1))   # Deplasman galibiyet (üst üçgen)
    p_draw = 1 - p_home - p_away           # Beraberlik (diyagonal)

    return {
        "home_win": round(float(p_home), 4),
        "draw": round(float(p_draw), 4),
        "away_win": round(float(p_away), 4),
    }


def extract_over_under(matrix, line=2.5):
    """Matrisden Over/Under olasılıklarını hesaplar."""
    over = 0.0
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            if i + j > line:
                over += matrix[i, j]

    return {
        "over": round(float(over), 4),
        "under": round(float(1 - over), 4),
    }


def extract_btts(matrix):
    """Matrisden Both Teams to Score olasılıklarını hesaplar."""
    btts_yes = 0.0
    for i in range(1, matrix.shape[0]):
        for j in range(1, matrix.shape[1]):
            btts_yes += matrix[i, j]

    return {
        "yes": round(float(btts_yes), 4),
        "no": round(float(1 - btts_yes), 4),
    }


def extract_expected_goals(matrix):
    """Matrisden beklenen golleri hesaplar."""
    home_xg = 0.0
    away_xg = 0.0
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            home_xg += i * matrix[i, j]
            away_xg += j * matrix[i, j]

    return {
        "home_xg": round(float(home_xg), 2),
        "away_xg": round(float(away_xg), 2),
    }


def extract_correct_scores(matrix, top_n=5):
    """En olası skor tahminlerini döner."""
    scores = []
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            scores.append({
                "home": i,
                "away": j,
                "prob": round(float(matrix[i, j]), 4),
            })
    scores.sort(key=lambda x: x["prob"], reverse=True)
    return scores[:top_n]


class DixonColes:
    """
    Dixon-Coles modeli.
    Maximum likelihood ile parametreleri (attack, defense, home, rho) eğitir.
    """

    def __init__(self, max_goals=MAX_GOALS):
        self.max_goals = max_goals
        self.rho = -0.13  # Varsayılan korelasyon (tipik değer: -0.13 ile -0.20)
        self.team_params = {}  # {team: {"attack": float, "defense": float}}
        self.home_advantage = 0.25  # Varsayılan ev avantajı
        self.is_fitted = False

    def _log_likelihood(self, params, matches, team_names):
        """
        Log-likelihood fonksiyonu (optimizasyon için).
        """
        n_teams = len(team_names)
        team_idx = {name: i for i, name in enumerate(team_names)}

        # Attack params (ilk n_teams)
        attacks = params[:n_teams]
        # Defense params (sonraki n_teams)
        defenses = params[n_teams:2*n_teams]
        # Home advantage
        home = params[2*n_teams]
        # Rho
        rho = params[2*n_teams + 1]

        # Rho sınırla
        rho = max(-0.99, min(0.99, rho))

        ll = 0.0
        for m in matches:
            home_team = m["home_team"]
            away_team = m["away_team"]
            home_goals = int(m["home_goals"])
            away_goals = int(m["away_goals"])

            if home_team not in team_idx or away_team not in team_idx:
                continue

            hi = team_idx[home_team]
            ai = team_idx[away_team]

            # Beklenen goller
            lambda_val = math.exp(attacks[hi] - defenses[ai] + home)
            mu_val = math.exp(attacks[ai] - defenses[hi])

            # Poisson olasılığı + tau düzeltmesi
            p_poisson = _poisson_pmf(home_goals, lambda_val) * _poisson_pmf(away_goals, mu_val)
            tau = _tau(home_goals, away_goals, lambda_val, mu_val, rho)

            prob = p_poisson * tau
            if prob > 1e-10:
                ll += math.log(prob)
            else:
                ll += math.log(1e-10)

        return -ll  # minimize için negatif

    def fit(self, matches):
        """
        Modeli maç verileriyle eğitir.

        Args:
            matches: [{"home_team": str, "away_team": str, "home_goals": int, "away_goals": int}]
        """
        # Benzersiz takımları bul
        team_set = set()
        for m in matches:
            team_set.add(m["home_team"])
            team_set.add(m["away_team"])
        team_names = sorted(team_set)
        n_teams = len(team_names)

        if n_teams < 2:
            logger.warning("Yeterli takım yok, Dixon-Coles eğitilemez.")
            return False

        # Başlangıç parametreleri
        x0 = np.zeros(2 * n_teams + 2)
        x0[2*n_teams] = 0.25     # home advantage
        x0[2*n_teams + 1] = -0.13  # rho

        # Optimizasyon
        try:
            result = minimize(
                self._log_likelihood,
                x0,
                args=(matches, team_names),
                method="L-BFGS-B",
                options={"maxiter": 1000, "ftol": 1e-8},
            )

            # Sonuçları kaydet
            opt_params = result.x
            self.rho = max(-0.99, min(0.99, opt_params[2*n_teams + 1]))
            self.home_advantage = opt_params[2*n_teams]

            for i, name in enumerate(team_names):
                self.team_params[name] = {
                    "attack": float(opt_params[i]),
                    "defense": float(opt_params[i + n_teams]),
                }

            self.is_fitted = True
            logger.info(f"Dixon-Coles eğitildi: {n_teams} takım, {len(matches)} maç, "
                       f"rho={self.rho:.3f}, home_adv={self.home_advantage:.3f}")
            return True

        except Exception as e:
            logger.error(f"Dixon-Coles optimizasyon hatası: {e}")
            return False

    def predict(self, home_team, away_team):
        """
        Maç tahmini üretir.

        Returns:
            dict: 1X2, O/U, BTTS, xG, skor olasılıkları
        """
        if not self.is_fitted:
            logger.warning("Dixon-Coles modeli eğitilmemiş.")
            return None

        # Attack/defense parametrelerini al (olmayan takımlar için 0)
        home_params = self.team_params.get(home_team, {"attack": 0, "defense": 0})
        away_params = self.team_params.get(away_team, {"attack": 0, "defense": 0})

        # Beklenen goller
        lambda_val = math.exp(home_params["attack"] - away_params["defense"] + self.home_advantage)
        mu_val = math.exp(away_params["attack"] - home_params["defense"])

        # Olasılık matrisi
        matrix = dixon_coles_prob_matrix(lambda_val, mu_val, self.rho, self.max_goals)

        # Tüm pazarları çıkar
        result = {
            **extract_1x2(matrix),
            **extract_over_under(matrix, 2.5),
            **extract_btts(matrix),
            **extract_expected_goals(matrix),
            "correct_scores": extract_correct_scores(matrix, top_n=5),
            "lambda": round(lambda_val, 3),
            "mu": round(mu_val, 3),
            "rho": round(self.rho, 3),
        }

        return result

    def get_team_params(self, team):
        """Takımın attack/defense parametrelerini döner."""
        return self.team_params.get(team, {"attack": 0, "defense": 0})

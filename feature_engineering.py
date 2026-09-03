"""
Gelişmiş Feature Engineering Motoru
25 temel feature'dan 100+'a çıkış.

Kategoriler:
1. Multi-Window Form (3/5/10/20 maç)
2. Momentum & Trend
3. H2H Patent Pattern
4. Gol Dağılım Paternleri
5. Sezon Fazı & Yorgunluk
6. Defansif Stabilite
7. Hücum Verimliliği
8. Tutarlılık & Volatilite
9. Bahis Piyasası Sinyalleri
10.elo & Rating Features
"""
import numpy as np
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """
    Gelişmiş feature extraction motoru.
    Her maç için 100+ feature üretir.
    """

    WINDOWS = [3, 5, 10, 20]

    def __init__(self):
        pass

    def extract_features(self, team_matches: List[Dict], team_name: str,
                         opponent_name: str = None,
                         is_home: bool = True) -> Dict[str, float]:
        """
        Bir takımın son maçlarından kapsamlı feature çıkarır.

        Args:
            team_matches: Takımın son maçları (en yeniden en eskiye)
            team_name: Takım adı
            opponent_name: Rakip adı (H2H için)
            is_home: Ev sahibi mi?

        Returns:
            100+ feature içeren dict
        """
        features = {}
        if not team_matches:
            return self._empty_features()

        # Temel istatistikleri hesapla
        stats = self._compute_base_stats(team_matches, team_name)

        # ─── 1. Multi-Window Form ───
        for w in self.WINDOWS:
            window = stats['all'][:w]
            if window:
                features.update(self._form_features(window, f"w{w}"))
            else:
                features.update(self._empty_form_features(f"w{w}"))

        # ─── 2. Momentum & Trend ───
        features.update(self._momentum_features(stats['all']))

        # ─── 3. H2H Patent Pattern ───
        if opponent_name:
            features.update(self._h2h_features(team_matches, team_name, opponent_name))
        else:
            features.update(self._empty_h2h_features())

        # ─── 4. Gol Dağılım Paternleri ───
        features.update(self._scoring_pattern_features(stats['all']))

        # ─── 5. Sezon Fazı ───
        features.update(self._season_phase_features(stats['all']))

        # ─── 6. Defansif Stabilite ───
        features.update(self._defensive_features(stats['all']))

        # ─── 7. Hücum Verimliliği ───
        features.update(self._attack_features(stats['all']))

        # ─── 8. Tutarlılık & Volatilite ───
        features.update(self._consistency_features(stats['all']))

        # ─── 9. Ev/Deplasman Ayrımı ───
        home_matches = stats.get('home', [])
        away_matches = stats.get('away', [])
        features.update(self._home_away_split_features(home_matches, away_matches))

        # ─── 10. Kart & Disiplin ───
        features.update(self._discipline_features(stats['all']))

        return features

    def _compute_base_stats(self, matches: List[Dict], team_name: str) -> Dict:
        """Temel istatistikleri hesaplar."""
        stats = {'all': [], 'home': [], 'away': []}

        for m in matches:
            if m.get('home_team') != team_name and m.get('away_team') != team_name:
                continue

            is_team_home = m.get('home_team') == team_name

            goals_scored = m.get('fthg') if is_team_home else m.get('ftag')
            goals_conceded = m.get('ftag') if is_team_home else m.get('fthg')
            ftr = m.get('ftr', '')

            if is_team_home:
                result = 'W' if ftr == 'H' else ('D' if ftr == 'D' else 'L')
            else:
                result = 'W' if ftr == 'A' else ('D' if ftr == 'D' else 'L')

            entry = {
                'scored': int(goals_scored) if goals_scored is not None else 0,
                'conceded': int(goals_conceded) if goals_conceded is not None else 0,
                'result': result,
                'points': 3 if result == 'W' else (1 if result == 'D' else 0),
                'is_home': is_team_home,
                'shots': float(m.get('home_shots', 0) if is_team_home else m.get('away_shots', 0) or 0),
                'sot': float(m.get('home_shots_on_target', 0) if is_team_home else m.get('away_shots_on_target', 0) or 0),
                'corners': float(m.get('home_corners', 0) if is_team_home else m.get('away_corners', 0) or 0),
                'yellow': float(m.get('home_yellow', 0) if is_team_home else m.get('away_yellow', 0) or 0),
                'red': float(m.get('home_red', 0) if is_team_home else m.get('away_red', 0) or 0),
                'b365h': float(m.get('b365h', 0) or 0),
                'b365d': float(m.get('b365d', 0) or 0),
                'b365a': float(m.get('b365a', 0) or 0),
            }
            stats['all'].append(entry)
            if is_team_home:
                stats['home'].append(entry)
            else:
                stats['away'].append(entry)

        return stats

    # ─── Multi-Window Form ───

    def _form_features(self, matches: List[Dict], prefix: str) -> Dict[str, float]:
        """Çoklu pencere form feature'ları."""
        if not matches:
            return self._empty_form_features(prefix)

        n = len(matches)
        f = {}

        # Puan ortalaması
        points = [m['points'] for m in matches]
        f[f'{prefix}_ppg'] = np.mean(points)
        f[f'{prefix}_ppg_trend'] = np.mean(points[:3]) - np.mean(points[3:]) if n > 3 else 0

        # Kazanma oranı
        wins = [1 if m['result'] == 'W' else 0 for m in matches]
        f[f'{prefix}_win_rate'] = np.mean(wins)
        f[f'{prefix}_win_streak'] = self._max_streak([m['result'] == 'W' for m in matches])

        # Beraberlik oranı
        draws = [1 if m['result'] == 'D' else 0 for m in matches]
        f[f'{prefix}_draw_rate'] = np.mean(draws)

        # Kaybetme oranı
        losses = [1 if m['result'] == 'L' else 0 for m in matches]
        f[f'{prefix}_loss_rate'] = np.mean(losses)
        f[f'{prefix}_loss_streak'] = self._max_streak([m['result'] == 'L' for m in matches])

        # Gol ortalaması
        scored = [m['scored'] for m in matches]
        conceded = [m['conceded'] for m in matches]
        f[f'{prefix}_goals_scored_avg'] = np.mean(scored)
        f[f'{prefix}_goals_conceded_avg'] = np.mean(conceded)
        f[f'{prefix}_goal_diff_avg'] = np.mean(scored) - np.mean(conceded)

        # Clean sheet & BTTS
        clean_sheets = [1 if m['conceded'] == 0 else 0 for m in matches]
        btts = [1 if m['scored'] > 0 and m['conceded'] > 0 else 0 for m in matches]
        f[f'{prefix}_clean_sheet_rate'] = np.mean(clean_sheets)
        f[f'{prefix}_btts_rate'] = np.mean(btts)

        # Over 2.5
        over_25 = [1 if m['scored'] + m['conceded'] > 2.5 else 0 for m in matches]
        f[f'{prefix}_over_25_rate'] = np.mean(over_25)

        # Son 3 maç formu (ağırlıklı)
        if n >= 3:
            weights = [0.5, 0.3, 0.2]  # En yeni ağırlıklı
            f[f'{prefix}_weighted_ppg'] = sum(p * w for p, w in zip(points[:3], weights[:n]))

        return f

    def _empty_form_features(self, prefix: str) -> Dict[str, float]:
        """Boş form feature'ları."""
        return {
            f'{prefix}_ppg': 1.0, f'{prefix}_ppg_trend': 0.0,
            f'{prefix}_win_rate': 0.33, f'{prefix}_win_streak': 0,
            f'{prefix}_draw_rate': 0.33, f'{prefix}_loss_rate': 0.33,
            f'{prefix}_loss_streak': 0,
            f'{prefix}_goals_scored_avg': 1.2, f'{prefix}_goals_conceded_avg': 1.2,
            f'{prefix}_goal_diff_avg': 0.0,
            f'{prefix}_clean_sheet_rate': 0.2, f'{prefix}_btts_rate': 0.5,
            f'{prefix}_over_25_rate': 0.45, f'{prefix}_weighted_ppg': 1.0,
        }

    # ─── Momentum & Trend ───

    def _momentum_features(self, matches: List[Dict]) -> Dict[str, float]:
        """Momentum ve trend feature'ları."""
        if len(matches) < 5:
            return {
                'momentum_points': 0.0, 'momentum_goals': 0.0,
                'form_acceleration': 0.0, 'recent_dominance': 0.0,
                'turnaround_trend': 0.0, 'consistency_score': 0.0,
            }

        n = len(matches)
        points = [m['points'] for m in matches]
        scored = [m['scored'] for m in matches]
        conceded = [m['conceded'] for m in matches]

        f = {}

        # Momentum: Son 5 vs Son 10 puan farkı
        if n >= 10:
            f['momentum_points'] = np.mean(points[:5]) - np.mean(points[5:10])
        else:
            f['momentum_points'] = np.mean(points[:min(5, n)]) - np.mean(points[min(5, n):])

        # Gol momentumu
        if n >= 10:
            f['momentum_goals'] = np.mean(scored[:5]) - np.mean(scored[5:10])
        else:
            f['momentum_goals'] = np.mean(scored[:min(5, n)]) - np.mean(scored[min(5, n):])

        # Form ivmesi (hızlanma/yavaşlama)
        if n >= 6:
            first_half = np.mean(points[:n//2])
            second_half = np.mean(points[n//2:])
            f['form_acceleration'] = first_half - second_half
        else:
            f['form_acceleration'] = 0.0

        # Son maç dominansı (fark ortalaması)
        recent_5 = matches[:min(5, n)]
        goal_diffs = [m['scored'] - m['conceded'] for m in recent_5]
        f['recent_dominance'] = np.mean(goal_diffs)

        # Geri dönüş trendi
        if n >= 4:
            losses_then_wins = sum(1 for i in range(min(4, n)-1) if matches[i]['result'] == 'W' and matches[i+1]['result'] == 'L')
            f['turnaround_trend'] = float(losses_then_wins) / min(4, n)
        else:
            f['turnaround_trend'] = 0.0

        # Tutarlılık skoru (düşük std = yüksek tutarlılık)
        f['consistency_score'] = 1.0 / (1.0 + np.std(points[:min(10, n)]))

        return f

    # ─── H2H Patent Pattern ───

    def _h2h_features(self, all_matches: List[Dict], team_name: str, opponent: str) -> Dict[str, float]:
        """Head-to-Head patent pattern feature'ları."""
        h2h = [m for m in all_matches
               if (m.get('home_team') == team_name and m.get('away_team') == opponent)
               or (m.get('home_team') == opponent and m.get('away_team') == team_name)]

        if not h2h:
            return self._empty_h2h_features()

        n = len(h2h)
        f = {}

        # H2H kazanma oranı
        wins = sum(1 for m in h2h[:10]
                   if (m.get('home_team') == team_name and m.get('ftr') == 'H')
                   or (m.get('away_team') == team_name and m.get('ftr') == 'A'))
        f['h2h_win_rate'] = float(wins) / min(n, 10)

        # H2H son 5
        recent_5 = h2h[:5]
        f['h2h_recent_5_wins'] = float(sum(1 for m in recent_5
                                           if (m.get('home_team') == team_name and m.get('ftr') == 'H')
                                           or (m.get('away_team') == team_name and m.get('ftr') == 'A'))) / len(recent_5)

        # H2H gol ortalaması
        h2h_goals = []
        for m in h2h[:10]:
            if m.get('home_team') == team_name:
                h2h_goals.append(m.get('fthg', 0) - m.get('ftag', 0))
            else:
                h2h_goals.append(m.get('ftag', 0) - m.get('fthg', 0))
        f['h2h_goal_diff_avg'] = np.mean(h2h_goals) if h2h_goals else 0.0

        # H2H Over 2.5 oranı
        over_25 = [1 for m in h2h[:10] if (m.get('fthg', 0) + m.get('ftag', 0)) > 2.5]
        f['h2h_over_25_rate'] = float(len(over_25)) / min(n, 10)

        # H2H BTTS oranı
        btts = [1 for m in h2h[:10] if m.get('fthg', 0) > 0 and m.get('ftag', 0) > 0]
        f['h2h_btts_rate'] = float(len(btts)) / min(n, 10)

        # H2H patern: Ev sahibi galibiyet serisi
        home_wins_streak = 0
        for m in h2h[:5]:
            if m.get('ftr') == 'H':
                home_wins_streak += 1
            else:
                break
        f['h2h_home_win_streak'] = float(home_wins_streak)

        return f

    def _empty_h2h_features(self) -> Dict[str, float]:
        return {
            'h2h_win_rate': 0.5, 'h2h_recent_5_wins': 0.4,
            'h2h_goal_diff_avg': 0.0, 'h2h_over_25_rate': 0.5,
            'h2h_btts_rate': 0.5, 'h2h_home_win_streak': 0.0,
        }

    # ─── Gol Dağılım Paternleri ───

    def _scoring_pattern_features(self, matches: List[Dict]) -> Dict[str, float]:
        """Gol atma/saklanma paterni feature'ları."""
        if not matches:
            return {
                'scoring_consistency': 0.0, 'conceding_consistency': 0.0,
                'high_scoring_rate': 0.0, 'low_scoring_rate': 0.0,
                'first_half_goals_est': 0.0, 'second_half_goals_est': 0.0,
                'goal_timing_score': 0.0, 'shutout_streak': 0,
                'scoring_streak': 0, 'big_win_rate': 0.0,
                'big_loss_rate': 0.0, 'draw_tendency': 0.0,
            }

        scored = [m['scored'] for m in matches]
        conceded = [m['conceded'] for m in matches]
        n = len(matches)
        f = {}

        # Gol tutarlılığı (düşük std = tutarlı)
        f['scoring_consistency'] = 1.0 / (1.0 + np.std(scored)) if len(scored) > 1 else 0.5
        f['conceding_consistency'] = 1.0 / (1.0 + np.std(conceded)) if len(conceded) > 1 else 0.5

        # Yüksek/alçak skorlu maç oranları
        total_goals = [s + c for s, c in zip(scored, conceded)]
        f['high_scoring_rate'] = float(sum(1 for g in total_goals if g >= 3)) / n
        f['low_scoring_rate'] = float(sum(1 for g in total_goals if g <= 1)) / n

        # İkinci yarı gol tahmini (son vuruş etkinliği)
        if n >= 3:
            late_goals = sum(1 for m in matches[:5] if m['scored'] >= 2)
            f['second_half_goals_est'] = float(late_goals) / min(5, n)
        else:
            f['second_half_goals_est'] = 0.0

        f['first_half_goals_est'] = np.mean(scored) * 0.45  # Ortalama %45 ilk yarıda

        # Gol zamanlama skoru
        f['goal_timing_score'] = float(sum(scored)) / (float(sum(total_goals)) + 0.001)

        # Seriler
        f['shutout_streak'] = float(self._max_streak([m['conceded'] == 0 for m in matches]))
        f['scoring_streak'] = float(self._max_streak([m['scored'] > 0 for m in matches]))

        # Büyük galibiyet/mağlubiyet
        f['big_win_rate'] = float(sum(1 for m in matches if m['scored'] - m['conceded'] >= 2)) / n
        f['big_loss_rate'] = float(sum(1 for m in matches if m['conceded'] - m['scored'] >= 2)) / n

        # Beraberlik eğilimi
        f['draw_tendency'] = float(sum(1 for m in matches if m['result'] == 'D')) / n

        return f

    # ─── Sezon Fazı ───

    def _season_phase_features(self, matches: List[Dict]) -> Dict[str, float]:
        """Sezon fazı ve seyirci etkisi feature'ları."""
        n = len(matches)
        f = {}

        # Sezon ilerlemesi (0-1 arası)
        f['season_progress'] = min(1.0, n / 38.0)

        # Sezon fazı encoded
        if n < 10:
            f['phase_early'] = 1.0
            f['phase_mid'] = 0.0
            f['phase_late'] = 0.0
        elif n < 25:
            f['phase_early'] = 0.0
            f['phase_mid'] = 1.0
            f['phase_late'] = 0.0
        else:
            f['phase_early'] = 0.0
            f['phase_mid'] = 0.0
            f['phase_late'] = 1.0

        # Basınç altında performans (son 10 maçtaki puan/kazanma)
        if n >= 10:
            late_season = matches[max(0, n-10):]
            f['pressure_performance'] = np.mean([m['points'] for m in late_season])
        else:
            f['pressure_performance'] = np.mean([m['points'] for m in matches])

        return f

    # ─── Defansif Stabilite ───

    def _defensive_features(self, matches: List[Dict]) -> Dict[str, float]:
        """Defansif stabilite feature'ları."""
        if not matches:
            return {
                'defensive_stability': 0.0, 'clean_sheet_streak': 0,
                'goals_conceded_trend': 0.0, 'defensive_impact': 0.0,
                'press_resistance': 0.0, 'recovery_rate': 0.0,
            }

        conceded = [m['conceded'] for m in matches]
        scored = [m['scored'] for m in matches]
        n = len(matches)
        f = {}

        # Defansif stabilite (temiz sayfa oranı + gol yeme trendi)
        clean_sheets = [1 if c == 0 else 0 for c in conceded]
        f['defensive_stability'] = np.mean(clean_sheets)

        # Temiz sayfa serisi
        f['clean_sheet_streak'] = float(self._max_streak([c == 0 for c in conceded]))

        # Gol yeme trendi (son 5 vs ilk 5)
        if n >= 10:
            f['goals_conceded_trend'] = np.mean(conceded[:5]) - np.mean(conceded[5:10])
        else:
            f['goals_conceded_trend'] = 0.0

        # Defansif etki skoru
        f['defensive_impact'] = float(sum(scored)) / (float(sum(conceded)) + 0.001)

        # Basınç altında savunma
        f['press_resistance'] = 1.0 - (np.mean(conceded[:min(5, n)]) / (np.mean(conceded) + 0.001))

        # Geri dönüş oranı
        if n >= 4:
            recoveries = sum(1 for i in range(min(4, n)-1) if matches[i]['result'] == 'L' and matches[i+1]['result'] in ['W', 'D'])
            f['recovery_rate'] = float(recoveries) / min(4, n)
        else:
            f['recovery_rate'] = 0.0

        return f

    # ─── Hücum Verimliliği ───

    def _attack_features(self, matches: List[Dict]) -> Dict[str, float]:
        """Hücum verimliliği feature'ları."""
        if not matches:
            return {
                'attack_efficiency': 0.0, 'shot_conversion': 0.0,
                'sot_accuracy': 0.0, 'attacking_threat': 0.0,
                'goal_per_shot': 0.0, 'dominance_index': 0.0,
            }

        scored = [m['scored'] for m in matches]
        shots = [m['shots'] for m in matches if m['shots'] > 0]
        sot = [m['sot'] for m in matches if m['sot'] > 0]
        n = len(matches)
        f = {}

        # Hücum verimliliği (gol/fırsat)
        f['attack_efficiency'] = float(sum(scored)) / (float(sum(shots)) + 0.001) if shots else 0.0

        # Şut isabet oranı
        f['shot_conversion'] = float(sum(sot)) / (float(sum(shots)) + 0.001) if shots else 0.0

        # SOT isabet oranı
        f['sot_accuracy'] = float(sum(scored)) / (float(sum(sot)) + 0.001) if sot else 0.0

        # Hücum tehdidi (gol beklentisi)
        f['attacking_threat'] = np.mean(scored) * f['attack_efficiency']

        # Gol/şut oranı
        f['goal_per_shot'] = float(sum(scored)) / (float(sum(shots)) + 0.001) if shots else 0.0

        # Dominans indeksi (pozisyon + gol)
        f['dominance_index'] = (np.mean(shots) if shots else 10) / 15.0

        return f

    # ─── Tutarlılık & Volatilite ───

    def _consistency_features(self, matches: List[Dict]) -> Dict[str, float]:
        """Tutarlılık ve volatilite feature'ları."""
        if len(matches) < 5:
            return {
                'result_consistency': 0.5, 'goal_volatility': 0.5,
                'performance_range': 0.0, 'surprise_factor': 0.0,
                'upset_potential': 0.0, 'form_stability': 0.5,
            }

        points = [m['points'] for m in matches]
        scored = [m['scored'] for m in matches]
        conceded = [m['conceded'] for m in matches]
        f = {}

        # Sonuç tutarlılığı
        f['result_consistency'] = 1.0 - (np.std(points) / 1.5)

        # Gol volatilitesi
        total = [s + c for s, c in zip(scored, conceded)]
        f['goal_volatility'] = np.std(total) / (np.mean(total) + 0.001)

        # Performans aralığı
        f['performance_range'] = max(points) - min(points) if len(points) > 1 else 0.0

        # Sürpriz potansiyeli (beklenmedik sonuçlar)
        expected = np.mean(points)
        surprises = sum(1 for p in points if abs(p - expected) > 1.5)
        f['surprise_factor'] = float(surprises) / len(points)

        # Sürpriz yaratma potansiyeli
        f['upset_potential'] = float(sum(1 for p in points if p == 3)) / len(points) if points else 0.0

        # Form kararlılığı (LINEAR REGRESSION SLOPE)
        x = np.arange(min(10, len(points)))
        y = np.array(points[:min(10, len(points))])
        if len(x) > 1:
            slope = np.polyfit(x, y, 1)[0]
            f['form_stability'] = 1.0 / (1.0 + abs(slope))
        else:
            f['form_stability'] = 0.5

        return f

    # ─── Ev/Deplasman Ayrımı ───

    def _home_away_split_features(self, home_matches: List[Dict], away_matches: List[Dict]) -> Dict[str, float]:
        """Ev sahibi/deplasman ayrımı feature'ları."""
        f = {}

        # Ev sahibi performansı
        if home_matches:
            f['home_form_ppg'] = np.mean([m['points'] for m in home_matches])
            f['home_form_scored'] = np.mean([m['scored'] for m in home_matches])
            f['home_form_conceded'] = np.mean([m['conceded'] for m in home_matches])
        else:
            f['home_form_ppg'] = 1.5
            f['home_form_scored'] = 1.3
            f['home_form_conceded'] = 1.1

        # Deplasman performansı
        if away_matches:
            f['away_form_ppg'] = np.mean([m['points'] for m in away_matches])
            f['away_form_scored'] = np.mean([m['scored'] for m in away_matches])
            f['away_form_conceded'] = np.mean([m['conceded'] for m in away_matches])
        else:
            f['away_form_ppg'] = 1.0
            f['away_form_scored'] = 1.0
            f['away_form_conceded'] = 1.3

        # Ev/deplasman farkı
        f['home_away_ppg_diff'] = f['home_form_ppg'] - f['away_form_ppg']
        f['home_away_scored_diff'] = f['home_form_scored'] - f['away_form_scored']

        return f

    # ─── Kart & Disiplin ───

    def _discipline_features(self, matches: List[Dict]) -> Dict[str, float]:
        """Kart ve disiplin feature'ları."""
        if not matches:
            return {
                'yellow_card_avg': 1.5, 'red_card_avg': 0.1,
                'discipline_score': 0.5, 'aggression_index': 0.5,
            }

        yellows = [m['yellow'] for m in matches]
        reds = [m['red'] for m in matches]
        n = len(matches)
        f = {}

        f['yellow_card_avg'] = np.mean(yellows)
        f['red_card_avg'] = np.mean(reds)

        # Disiplin skoru (düşük kart = iyi disiplin)
        f['discipline_score'] = 1.0 / (1.0 + np.mean(yellows) + np.mean(reds) * 3)

        # Agresyon indeksi
        f['aggression_index'] = (np.mean(yellows) + np.mean(reds) * 3) / 5.0

        return f

    # ─── Yardımcı Fonksiyonlar ───

    @staticmethod
    def _max_streak(bool_list: List[bool]) -> int:
        """Maksimum true serisi."""
        max_s = 0
        current = 0
        for b in bool_list:
            if b:
                current += 1
                max_s = max(max_s, current)
            else:
                current = 0
        return max_s

    def _empty_features(self) -> Dict[str, float]:
        """Boş veri için tüm feature'ları döner."""
        f = {}
        for w in self.WINDOWS:
            f.update(self._empty_form_features(f'w{w}'))
        f.update({
            'momentum_points': 0.0, 'momentum_goals': 0.0,
            'form_acceleration': 0.0, 'recent_dominance': 0.0,
            'turnaround_trend': 0.0, 'consistency_score': 0.5,
        })
        f.update(self._empty_h2h_features())
        f.update({
            'scoring_consistency': 0.5, 'conceding_consistency': 0.5,
            'high_scoring_rate': 0.45, 'low_scoring_rate': 0.2,
            'first_half_goals_est': 0.5, 'second_half_goals_est': 0.5,
            'goal_timing_score': 0.5, 'shutout_streak': 0,
            'scoring_streak': 0, 'big_win_rate': 0.2,
            'big_loss_rate': 0.2, 'draw_tendency': 0.25,
        })
        f.update({
            'season_progress': 0.5, 'phase_early': 0.0,
            'phase_mid': 1.0, 'phase_late': 0.0, 'pressure_performance': 1.5,
        })
        f.update({
            'defensive_stability': 0.3, 'clean_sheet_streak': 0,
            'goals_conceded_trend': 0.0, 'defensive_impact': 1.0,
            'press_resistance': 0.5, 'recovery_rate': 0.3,
        })
        f.update({
            'attack_efficiency': 0.1, 'shot_conversion': 0.3,
            'sot_accuracy': 0.3, 'attacking_threat': 0.3,
            'goal_per_shot': 0.1, 'dominance_index': 0.6,
        })
        f.update({
            'result_consistency': 0.5, 'goal_volatility': 0.5,
            'performance_range': 1.0, 'surprise_factor': 0.2,
            'upset_potential': 0.33, 'form_stability': 0.5,
        })
        f.update({
            'home_form_ppg': 1.5, 'home_form_scored': 1.3, 'home_form_conceded': 1.1,
            'away_form_ppg': 1.0, 'away_form_scored': 1.0, 'away_form_conceded': 1.3,
            'home_away_ppg_diff': 0.5, 'home_away_scored_diff': 0.3,
        })
        f.update({
            'yellow_card_avg': 1.5, 'red_card_avg': 0.1,
            'discipline_score': 0.5, 'aggression_index': 0.5,
        })
        return f

    def get_feature_names(self) -> List[str]:
        """Tüm feature isimlerini döner."""
        sample = self._empty_features()
        return sorted(sample.keys())

    def get_feature_count(self) -> int:
        """Toplam feature sayısını döner."""
        return len(self.get_feature_names())

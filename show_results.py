import sqlite3
import pandas as pd

def fetch_top_results():
    try:
        conn = sqlite3.connect('football_data.db')
        query = """
        SELECT id, is_champion, 
               json_extract(config_json, '$.model_type') as model,
               cv_score as 'cv_test_acc', 
               backtest_accuracy as 'accuracy', 
               backtest_profit as 'profit (unit)',
               duration_sec as 'time (s)'
        FROM experiments
        WHERE error_msg IS NULL
        ORDER BY backtest_profit DESC, backtest_accuracy DESC
        LIMIT 10
        """
        df = pd.read_sql_query(query, conn)
        print("\n--- AUTO-RESEARCHER TOP 10 SONUÇLARI ---")
        if df.empty:
            print("Kayıtlı başarılı deney bulunamadı.")
        else:
            print(df.to_string(index=False))
            
        champion = pd.read_sql_query("SELECT id, backtest_profit, backtest_accuracy FROM experiments WHERE is_champion=1", conn)
        if not champion.empty:
            print(f"\n🏆 AKTİF ŞAMPİYON: Deney ID {champion.iloc[0]['id']} | Kâr: {champion.iloc[0]['backtest_profit']}U | İsabet: %{round(champion.iloc[0]['backtest_accuracy']*100, 2)}")
        else:
            print("\n⚠️ Henüz Şampiyon atanmadı (Büyük ihtimalle kâr eden bir model bulunamadı veya ilk atama yapılmadı).")
            
        conn.close()
    except Exception as e:
        print(f"Hata: {e}")

if __name__ == '__main__':
    fetch_top_results()

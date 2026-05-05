import sqlite3
import pandas as pd
import os

def analyze_experiments():
    conn = sqlite3.connect('football_data.db')
    query = "SELECT id, config_json, cv_score, backtest_accuracy, backtest_profit, run_at FROM experiments ORDER BY backtest_profit DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print("--- Experiment Results ---")
    print(df.to_string())
    
    # List archive files
    archive_dir = 'models_archive'
    if os.path.exists(archive_dir):
        files = os.listdir(archive_dir)
        print(f"\n--- Files in {archive_dir} ---")
        for f in files:
            print(f)
    else:
        print(f"\n--- {archive_dir} directory not found ---")

if __name__ == '__main__':
    analyze_experiments()

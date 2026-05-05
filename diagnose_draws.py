import pickle
import pandas as pd
import numpy as np
import sqlite3
import os

model_path = r'e:\KODLAMA\PROJE\FootballData\ml_model.pkl'
db_path = r'e:\KODLAMA\PROJE\FootballData\football_data.db'

def diagnose_draws():
    print("--- 🤖 Model Diagnostic ---")
    if os.path.exists(model_path):
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        print(f"Model Type: {type(model)}")
        if hasattr(model, 'classes_'):
            print(f"Model Classes: {model.classes_}")
            # classes are often [0, 1, 2] corresponding to [Draw, Home, Away]
        else:
            print("Model doesn't have classes_ attribute (maybe a Booster?)")
    else:
        print("Model file not found!")

    print("\n--- 🏟️ Data Diagnostic ---")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        
        print("\nPredicted Distribution in History:")
        cursor = conn.execute("SELECT predicted_result, COUNT(*) FROM predictions_history GROUP BY predicted_result")
        for row in cursor.fetchall():
            print(f"Result {row[0]}: {row[1]}")
            
        print("\nActual Result Distribution in Matches (Last 1000):")
        cursor = conn.execute("SELECT ftr, COUNT(*) FROM (SELECT ftr FROM matches LIMIT 1000) GROUP BY ftr")
        for row in cursor.fetchall():
            print(f"FTR {row[0]}: {row[1]}")
            
        conn.close()

if __name__ == "__main__":
    diagnose_draws()

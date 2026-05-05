
import os
import shutil
from database import Database
from auto_researcher import AutoResearcher
from ml_predictor import MLPredictor

def test_sync():
    db = Database()
    db.connect()
    
    ar = AutoResearcher(db)
    
    print("--- Testing Sync ---")
    # Check if pkl exists
    if os.path.exists("ml_model.pkl"):
        print("ml_model.pkl already exists. Deleting to test sync...")
        os.remove("ml_model.pkl")
    
    # Run sync
    ar.sync_active_model_with_champion()
    
    if os.path.exists("ml_model.pkl"):
        print("✅ Sync successful: ml_model.pkl was recreated from champion config.")
    else:
        print("❌ Sync failed: ml_model.pkl was not created.")

def test_archiving():
    print("--- Testing Archiving Logic ---")
    db = Database()
    db.connect()
    ar = AutoResearcher(db)
    
    # Mocking data or just checking current state
    archive_dir = "models_archive"
    before_count = len(os.listdir(archive_dir)) if os.path.exists(archive_dir) else 0
    
    # We won't run a full research loop here as it takes time, 
    # but we can call promote_champion manually and check.
    
    champ = db.get_best_historical_experiment()
    if champ:
        print(f"Promoting champion ID: {champ['id']}")
        ar.promote_champion(champ['id'])
        
        after_count = len(os.listdir(archive_dir)) if os.path.exists(archive_dir) else 0
        if after_count > before_count:
            print(f"✅ Archiving successful: New model added to archive ({after_count} total).")
        else:
            print("❌ Archiving failed: No new model in archive.")
    else:
        print("No champion found in DB to test promotion.")

if __name__ == "__main__":
    try:
        test_sync()
        test_archiving()
    except Exception as e:
        print(f"Test error: {e}")

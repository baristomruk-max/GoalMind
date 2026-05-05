import os
import sqlite3
import pandas as pd
import logging
from datetime import datetime

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def cleanup_models(archive_dir='models_archive', db_path='football_data.db', dry_run=False):
    if not os.path.exists(archive_dir):
        logger.warning(f"Archive directory {archive_dir} not found. Nothing to cleanup.")
        return

    conn = sqlite3.connect(db_path)
    
    # Get top performing experiments
    # Some older experiments might have NaN for profit/accuracy, so we fallback to cv_score
    query = """
        SELECT id, run_at, backtest_profit, backtest_accuracy, cv_score 
        FROM experiments 
        ORDER BY backtest_profit DESC, backtest_accuracy DESC, cv_score DESC
        LIMIT 20
    """
    top_exps = pd.read_sql_query(query, conn)
    conn.close()

    logger.info(f"Top 20 experiments identified in DB.")
    
    # Files in archive
    files = [f for f in os.listdir(archive_dir) if f.endswith('.pkl')]
    logger.info(f"Found {len(files)} models in {archive_dir}.")

    # Strategy: 
    # 1. Always keep the 10 most recent files (safety)
    # 2. Keep any file that matches a top performance timestamp (approximate)
    # 3. Delete the rest
    
    files_with_mtime = []
    for f in files:
        full_path = os.path.join(archive_dir, f)
        files_with_mtime.append((f, os.path.getmtime(full_path)))
    
    # Sort by mtime descending
    files_with_mtime.sort(key=lambda x: x[1], reverse=True)
    
    keep_list = set()
    
    # Rule 1: Keep 10 most recent
    recent_count = min(10, len(files_with_mtime))
    for i in range(recent_count):
        keep_list.add(files_with_mtime[i][0])
    
    # Rule 2: Keep top performers (this is harder because filenames are timestamps)
    # The filenames are ml_model_vYYYYMMDD_HHMMSS.pkl
    # Experiments run_at is YYYY-MM-DD HH:MM:SS
    # We can try to match them.
    
    for _, row in top_exps.iterrows():
        run_at_dt = datetime.strptime(row['run_at'], "%Y-%m-%d %H:%M:%S")
        stamp = run_at_dt.strftime("%Y%m%d_%H%M") # Match up to the minute
        for f in files:
            if stamp in f:
                keep_list.add(f)
                logger.debug(f"Keeping high-performing model: {f} (Profit: {row['backtest_profit']})")

    # Final Deletion
    deleted_count = 0
    for f in files:
        if f not in keep_list:
            full_path = os.path.join(archive_dir, f)
            if dry_run:
                logger.info(f"[DRY RUN] Would delete: {f}")
            else:
                try:
                    os.remove(full_path)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {f}: {e}")

    if not dry_run:
        logger.info(f"Cleanup complete. Deleted {deleted_count} models. Kept {len(keep_list)} models.")
    else:
        logger.info(f"Dry run complete. Found {len(files) - len(keep_list)} models to delete.")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help="Don't delete files, just show what would be deleted")
    args = parser.parse_args()
    
    cleanup_models(dry_run=args.dry_run)

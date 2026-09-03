"""
Football Data App - Otonom AI Agent Sistemi
============================================
Groq + litellm ile 5 agentlı otonom yönetim sistemi.

Agent'lar:
1. Data Guardian   - Eksik maç sonuçlarını web'den çeker
2. Code Doctor     - Kod hatalarını otomatik algılar ve düzeltir
3. Learning Engine  - Yanlış tahminleri analiz eder, modeli iyileştirir
4. Orchestrator    - Tüm agentları koordine eder
5. Prediction Agent- Yeni tahminler üretir
"""

import os
import sys
import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# .env dosyasini ust klasorunde ara
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

# ─── Groq LLM Yapılandırması ───
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("NGROK_AUTH_TOKEN")
GROQ_MODEL = "llama-3.3-70b-versatile"

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY tanimli degil. Agent sistemi Groq LLM kullanamayacak.")


def ask_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
    """Groq LLM'ine soru sorar, cevabi doner."""
    import litellm
    litellm.drop_params = True
    
    response = litellm.completion(
        model=f"groq/{GROQ_MODEL}",
        api_key=GROQ_API_KEY,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content


# ═══════════════════════════════════════════
#  AGENT 1: DATA GUARDIAN
# ═══════════════════════════════════════════

def run_data_guardian():
    """Eksik mac sonuclarini ceker ve sonuclandirir."""
    logger.info("[DATA GUARDIAN] Eksik sonuclar kontrol ediliyor...")
    
    system = """Sen bir futbol veri koruyucususun. Gorevin:
1. Eksik mac sonuclarini BSD API'den cekmek
2. Pending tahminleri sonuclandirmak
3. Veritabaninda tutarlilik saglamak"""
    
    user = """FootballData projesindeki eksik mac sonuclarini kontrol et ve raporla.
Calismadi alan: E:/KODLAMA/BARİS YAPAY ZEKA/FootballData/

Adimlar:
1. database.py'den pending tahminleri listele
2. bsd_api_scraper.py ile sonuclari cek
3. scraper.py'deki resolve_pending_predictions() metodunu calistir
4. Sonuclari logla

Veritabani yolu: E:/KODLAMA/BARİS YAPAY ZEKA/FootballData/data/football.db"""
    
    try:
        # Direkt Python ile calistir (LLM gerekmez, mevcut fonksiyonlari kullan)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from database import Database
        from scraper import IddaaScraper
        from predictor import Predictor
        from ml_predictor import MLPredictor
        
        db = Database()
        predictor = Predictor(db)
        ml_predictor = MLPredictor(db)
        scraper = IddaaScraper(db, predictor)
        
        result = scraper.resolve_pending_predictions()
        logger.info(f"[DATA GUARDIAN] {result} mac sonuclandirildi")
        return {"resolved": result}
    except Exception as e:
        logger.error(f"[DATA GUARDIAN] Hata: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════
#  AGENT 2: CODE DOCTOR
# ═══════════════════════════════════════════

def run_code_doctor():
    """Kod hatalarini algilar ve raporlar."""
    logger.info("[CODE DOCTOR] Syntax kontrolu basliyor...")
    
    import py_compile
    
    files_to_check = [
        "ai_agents.py", "bsd_api_scraper.py", "scraper.py",
        "database.py", "ml_predictor.py", "predictor.py",
        "app.py", "calibrator.py", "self_learning.py",
    ]
    
    results = {"ok": [], "errors": []}
    
    for f in files_to_check:
        try:
            py_compile.compile(f, doraise=True)
            results["ok"].append(f)
        except py_compile.PyCompileError as e:
            results["errors"].append({"file": f, "error": str(e)})
    
    if results["errors"]:
        logger.warning(f"[CODE DOCTOR] {len(results['errors'])} hata bulundu")
        # LLM'den duzeltme onerisi al
        try:
            error_summary = "\n".join([f"- {e['file']}: {e['error']}" for e in results["errors"]])
            suggestion = ask_llm(
                "Sen bir Python kod doktorusun. Verilen hatalari analiz et ve kisa duzeltme onerileri sun.",
                f"Hatalar:\n{error_summary}"
            )
            results["suggestion"] = suggestion
        except Exception:
            pass
    else:
        logger.info(f"[CODE DOCTOR] {len(results['ok'])} dosya temiz")
    
    return results


# ═══════════════════════════════════════════
#  AGENT 3: LEARNING ENGINE
# ═══════════════════════════════════════════

def run_learning_engine():
    """Tahmin performansini analiz eder."""
    logger.info("[LEARNING ENGINE] Performans analizi basliyor...")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from database import Database
        
        db = Database()
        
        # Tahmin istatistikleri
        with db._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            resolved = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='resolved'").fetchone()[0]
            correct = conn.execute("""
                SELECT COUNT(*) FROM predictions 
                WHERE status='resolved' 
                AND actual_home_score IS NOT NULL 
                AND actual_away_score IS NOT NULL
                AND (
                    (predicted_result = 'HOME' AND actual_home_score > actual_away_score) OR
                    (predicted_result = 'AWAY' AND actual_home_score < actual_away_score) OR
                    (predicted_result = 'DRAW' AND actual_home_score = actual_away_score)
                )
            """).fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM predictions WHERE status='pending'").fetchone()[0]
        
        accuracy = (correct / resolved * 100) if resolved > 0 else 0
        
        stats = {
            "total_predictions": total,
            "resolved": resolved,
            "correct": correct,
            "pending": pending,
            "accuracy_pct": round(accuracy, 1),
        }
        
        logger.info(f"[LEARNING ENGINE] Dogruluk: %{accuracy:.1f} ({correct}/{resolved})")
        
        # LLM'den analiz al
        try:
            analysis = ask_llm(
                "Sen bir futbol tahmin analistisin. Verilen istatistikleri analiz et ve kisa oneriler sun.",
                f"Tahmin istatistikleri: {json.dumps(stats, ensure_ascii=False)}"
            )
            stats["analysis"] = analysis
        except Exception:
            pass
        
        return stats
    except Exception as e:
        logger.error(f"[LEARNING ENGINE] Hata: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════
#  AGENT 4: ORCHESTRATOR
# ═══════════════════════════════════════════

def run_orchestrator():
    """Tum agentlari koordine eder."""
    logger.info("[ORCHESTRATOR] Rutin baslatiliyor...")
    
    results = {}
    
    # 1. Data Guardian
    try:
        results["data_guardian"] = run_data_guardian()
    except Exception as e:
        results["data_guardian"] = {"error": str(e)}
    
    # 2. Code Doctor
    try:
        results["code_doctor"] = run_code_doctor()
    except Exception as e:
        results["code_doctor"] = {"error": str(e)}
    
    # 3. Learning Engine
    try:
        results["learning_engine"] = run_learning_engine()
    except Exception as e:
        results["learning_engine"] = {"error": str(e)}
    
    # Ozet
    errors = sum(1 for v in results.values() if isinstance(v, dict) and "error" in v)
    logger.info(f"[ORCHESTRATOR] Tamamlandi. {len(results)} agent calisti, {errors} hata.")
    
    return results


# ═══════════════════════════════════════════
#  AGENT 5: PREDICTION AGENT
# ═══════════════════════════════════════════

def run_prediction_agent():
    """Yeni tahminler uretir."""
    logger.info("[PREDICTION AGENT] Tahmin uretimi basliyor...")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from database import Database
        from bsd_api_scraper import BSDScraper
        from predictor import Predictor
        from ml_predictor import MLPredictor
        from scraper import IddaaScraper
        
        db = Database()
        predictor = Predictor(db)
        ml_predictor = MLPredictor(db)
        scraper = IddaaScraper(db, predictor)
        
        result = scraper.get_weekly_predictions()
        pred_count = len(result.get("predictions", [])) if isinstance(result, dict) else 0
        
        logger.info(f"[PREDICTION AGENT] {pred_count} tahmin uretildi")
        return {"predictions_count": pred_count}
    except Exception as e:
        logger.error(f"[PREDICTION AGENT] Hata: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════
#  ANA CALISTIRICI
# ═══════════════════════════════════════════

def run_full_routine():
    """Tum agentlari sirasiyla calistirir."""
    logger.info("[AI AGENTS] Otonom rutin baslatiliyor...")
    return run_orchestrator()


def run_quick_diagnostic():
    """Hizli tanilama: Sadece Code Doctor."""
    logger.info("[AI AGENTS] Hizli tanilama baslatiliyor...")
    return run_code_doctor()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Football Data AI Agent System")
    parser.add_argument("--mode", choices=["full", "diagnostic", "guardian", "doctor", "learner", "predictor"],
                       default="full", help="Calistirma modu")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.mode == "full":
        result = run_full_routine()
    elif args.mode == "diagnostic":
        result = run_quick_diagnostic()
    elif args.mode == "guardian":
        result = run_data_guardian()
    elif args.mode == "doctor":
        result = run_code_doctor()
    elif args.mode == "learner":
        result = run_learning_engine()
    elif args.mode == "predictor":
        result = run_prediction_agent()
    
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

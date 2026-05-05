import traceback
import json
import logging
import sys

sys.path.append(r"e:\KODLAMA\PROJE\FootballData")

from database import Database
from predictor import Predictor
from ml_predictor import MLPredictor

logging.basicConfig(level=logging.DEBUG)

db = Database(r"e:\KODLAMA\PROJE\FootballData\football_data.db")
db.connect()

p1 = Predictor(db)
res1 = p1.predict_match("Besiktas", "Kasimpasa")
print("Poisson result:", json.dumps(res1, indent=2))

p2 = MLPredictor(db)
res2 = p2.predict_match_ml("Besiktas", "Kasimpasa")
print("ML result:", json.dumps(res2, indent=2))

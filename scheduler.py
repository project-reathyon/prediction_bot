from datetime import datetime
import os
import json

DATA_PATH = "daily_log.json"

def _load_data():
    if not os.path.exists(DATA_PATH):
        return {"date": "", "count": 0}
    with open(DATA_PATH, "r") as f:
        return json.load(f)

def _save_data(data):
    with open(DATA_PATH, "w") as f:
        json.dump(data, f)

def can_predict_today():
    data = _load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if data["date"] != today:
        return True
    return data["count"] < 10

def register_prediction():
    data = _load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if data["date"] != today:
        data = {"date": today, "count": 1}
    else:
        data["count"] += 1
    _save_data(data)

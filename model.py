import random

def get_top_predictions():
    matches = [
        "Real Madrid vs Barcelona - Real Win",
        "Man City vs Liverpool - Draw",
        "Boca Juniors vs River Plate - River Win",
        "Mamelodi Sundowns vs Kaizer Chiefs - Sundowns Win",
        "Ajax vs PSV - Over 2.5 Goals"
    ]
    predictions = [{"label": match, "confidence": random.randint(80, 99)} for match in matches]
    predictions.sort(key=lambda x: -x["confidence"])
    return predictions[:5]

import random
import requests
import unicodedata
from django.conf import settings

# Duración total (minutos) por experiencia
def calcular_duracion_total(experience):
    if experience == "principiante":
        return random.randint(30, 40)
    if experience == "intermedio":
        return random.randint(45, 55)
    return random.randint(60, 75)  # avanzado

# Series/reps/rest según objetivo y experiencia
def calcular_series_reps_rest(goal, experience):
    # default values
    if goal == "ganar_musculo":
        if experience == "principiante":
            return 3, 10, 60
        if experience == "intermedio":
            return 4, 10, 75
        return 5, 8, 90
    if goal == "perder_peso":
        if experience == "principiante":
            return 3, 12, 45
        if experience == "intermedio":
            return 4, 12, 45
        return 4, 15, 30
    if goal == "tonificar" or goal == "mantener_forma":
        if experience == "principiante":
            return 3, 12, 60
        if experience == "intermedio":
            return 4, 10, 60
        return 4, 8, 75
    # default fallback
    return 4, 10, 60

# Obtener ejercicios por músculo (from Exercises MS)
def normalize_text(t):
    """
    Normaliza removiendo acentos, espacios extra y convirtiendo a snake_case simple.
    """
    if not t:
        return ""

    # Quitar acentos
    t = ''.join(
        c for c in unicodedata.normalize('NFD', t)
        if unicodedata.category(c) != 'Mn'
    )

    return t.strip().lower().replace(" ", "_")

def fetch_exercises_by_muscle(muscle_group, difficulty, token):
    base = settings.EXERCISES_SERVICE_URL

    # 1) try muscle-group endpoint
    try:
        res = requests.get(
            f"{base}exercises/muscle-group/",
            params={"muscle_group": muscle_group},
            headers={"Authorization": f"Bearer {token}"},
            timeout=50
        )

        if res.status_code == 200:
            return res.json()
    except:
        pass

    # 2) fallback: /all/
    try:
        res = requests.get(
            f"{base}exercises/all/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=50
        )
        if res.status_code != 200:
            return []

        items = res.json()

        # Normalizar músculo solicitado
        target_muscle = normalize_text(muscle_group)

        filtered = []
        for i in items:
            mg = normalize_text(
                i.get("muscle_group") or i.get("muscle_group_display")
            )

            if mg == target_muscle:
                filtered.append(i)

        # Filtrar por dificultad si se pidió
        if difficulty:
            target_diff = normalize_text(difficulty)
            filtered = [
                i for i in filtered
                if normalize_text(i.get("difficulty") or i.get("difficulty_display"))
                   == target_diff
            ]

        return filtered

    except Exception:
        return []

    return []
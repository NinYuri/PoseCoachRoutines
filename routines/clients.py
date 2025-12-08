import requests
import logging
from pcroutines import settings

logger = logging.getLogger(__name__)

class UsersServiceClient:
    """ Cliente para el microservicio de usuarios """
    def __init__(self):
        self.base_url = settings.USERS_SERVICE_URL

    def get_user_profile(self, token):
        """Obtiene el perfil completo del usuario desde el token"""
        headers = {'Authorization': f'Bearer {token}'}
        try:
            response = requests.get(
                f"{self.base_url}users/profile/",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error getting user profile: {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling users service: {e}")
        return None


class ExercisesServiceClient:
    """ Cliente para el microservicio de ejercicios """
    def __init__(self):
        self.base_url = settings.EXERCISES_SERVICE_URL

    def get_exercises_by_muscle_group(self, muscle_groups, token):
        """Obtiene ejercicios por grupos musculares"""
        headers = {'Authorization': f'Bearer {token}'}
        try:
            if isinstance(muscle_groups, list):
                muscle_groups_str = ','.join(muscle_groups)
            else:
                muscle_groups_str = muscle_groups

            response = requests.get(
                f"{self.base_url}exercises/muscle-group/",
                params={'muscle_group': muscle_groups_str},
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling exercises service: {e}")
        return []

    def get_exercises_by_difficulty(self, difficulty, token):
        """Obtiene ejercicios por nivel de dificultad"""
        headers = {'Authorization': f'Bearer {token}'}
        try:
            response = requests.get(
                f"{self.base_url}exercises/difficulty/",
                params={'difficulty': difficulty},
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling exercises service: {e}")
        return []

    def get_filtered_exercises(self, muscle_groups=None, difficulty=None, token=None):
        """Obtiene ejercicios filtrados por músculo y dificultad"""
        if not token:
            return []

        # Primero obtener ejercicios por músculo
        exercises = []
        if muscle_groups:
            exercises = self.get_exercises_by_muscle_group(muscle_groups, token)

        # Si también hay filtro de dificultad, filtrar localmente
        if difficulty and exercises:
            filtered = [ex for ex in exercises if ex.get('difficulty') == difficulty]
            return filtered

        return exercises

    def get_random_exercises(self, muscle_group, difficulty, count, token):
        """Obtiene ejercicios aleatorios de un grupo muscular y dificultad"""
        exercises = self.get_filtered_exercises(
            muscle_groups=muscle_group,
            difficulty=difficulty,
            token=token
        )

        import random
        if len(exercises) <= count:
            return exercises
        else:
            return random.sample(exercises, count)
import random
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from .models import Rutina, DiaRutina, DiaEjercicio
from .serializers import RutinaSerializer
from .utils import (
    calcular_duracion_total,
    calcular_series_reps_rest,
    fetch_exercises_by_muscle
)
import requests

DEFAULT_SPLIT = {
    "lunes": "pierna",
    "martes": "pecho",
    "miercoles": "espalda",
    "jueves": "brazos",
    "viernes": "cuerpo_completo"
}

NOMBRES_RUTINA_DIA = {
    "pierna": [
        "Piernas de Acero",
        "Fuerza Inferior",
    ],
    "pecho": [
        "Empuje Superior",
        "Tono y Volumen"
    ],
    "espalda": [
        "Espalda Definida",
        "Fortaleza Dorsal"
    ],
    "brazos": [
        "Brazos de Acero",
        "Esculpe tus Brazos"
    ],
    "cuerpo_completo": [
        "Entrenamiento Total",
        "Cuerpo Completo",
    ]
}


class GenerateRoutineView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            print("\n===== GENERANDO RUTINA =====")

            token = request.headers.get("Authorization")
            if token and token.startswith("Bearer "):
                token = token.split(" ")[1]

            # 1. Obtener perfil desde MS Usuarios
            profile_res = requests.get(
                f"{settings.USERS_SERVICE_URL}users/profile/",
                headers={"Authorization": f"Bearer {token}"}
            )

            print("PROFILE STATUS:", profile_res.status_code)
            print("PROFILE JSON:", profile_res.json())

            profile = profile_res.json()["user"]
            difficulty = profile["experience"]
            goal = profile["goal"]

            print("EXPERIENCIA:", difficulty)
            print("OBJETIVO:", goal)

            # 2. Crear la rutina
            total_duration = calcular_duracion_total(difficulty)
            rutina = Rutina.objects.create(
                user_id=request.user.id,
                duracion_minutos=total_duration
            )

            # 3. Crear los días
            for dia_nombre, musculo in DEFAULT_SPLIT.items():
                ejercicios = fetch_exercises_by_muscle(musculo, difficulty, token)

                if len(ejercicios) < 5:
                    return Response(
                        {"error": f"No hay suficientes ejercicios para {musculo}. Se recibieron {len(ejercicios)}"},
                        status=400
                    )

                # Mezclar
                random.shuffle(ejercicios)
                ejercicios = ejercicios[:5]
                nombre_dia = random.choice(NOMBRES_RUTINA_DIA.get(musculo, ["Día de Entrenamiento"]))

                dia = DiaRutina.objects.create(
                    rutina=rutina,
                    dia=dia_nombre,
                    musculo=musculo,
                    nombre=nombre_dia,
                )

                series, reps, rest = calcular_series_reps_rest(goal, difficulty)

                for ex in ejercicios:
                    DiaEjercicio.objects.create(
                        dia=dia,
                        ejercicio_id=ex["id"],
                        name=ex["name"],
                        muscle_group=ex["muscle_group_display"],
                        difficulty=ex["difficulty_display"],
                        equipment=ex["equipment_display"],
                        image_url=ex["image_url"],
                        series=series,
                        reps=reps,
                        rest_seconds=rest
                    )

            return Response({"message": "Rutina generada correctamente", "rutina_id": str(rutina.id)})

        except Exception as e:
            print("\nERROR EN LA RUTINA")
            print("Detalle:", e)
            return Response({"error": str(e)}, status=500)


class ListRutinasView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = int(request.user.id)
        rutinas = Rutina.objects.filter(user_id=user_id).order_by("-created_at")
        data = RutinaSerializer(rutinas, many=True).data
        return Response(data)


class GetRutinaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, rutina_id):
        user_id = int(request.user.id)
        try:
            rutina = Rutina.objects.get(id=rutina_id, user_id=user_id)
        except Rutina.DoesNotExist:
            return Response({"detail": "Rutina no encontrada"}, status=404)
        return Response(RutinaSerializer(rutina).data)


class CheckRoutineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.id
        rutina = Rutina.objects.filter(user_id=user_id).order_by("-created_at").first()

        if rutina:
            return Response({"rutina_id": str(rutina.id)})
        return Response({"rutina_id": None})


class GetRoutineByDays(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, rutina_id):
        try:
            rutina = Rutina.objects.get(id=rutina_id, user_id=request.user.id)
            dias = {}
            for dia in rutina.dias.all():
                dias[dia.dia] = {
                    "nombre": dia.nombre,
                    "musculo": dia.musculo,
                    "detalles": [
                        {
                            "ejercicio_id": ex.ejercicio_id,
                            "name": ex.name,
                            "image_url": ex.image_url,
                            "series": ex.series,
                            "reps": ex.reps,
                            "rest_seconds": ex.rest_seconds
                        } for ex in dia.detalles.all()
                    ]
                }
            return Response({"id": str(rutina.id), "dias": dias})
        except Rutina.DoesNotExist:
            return Response({"error": "Rutina no encontrada"}, status=404)
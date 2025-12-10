from rest_framework import serializers
from .models import Rutina, DiaRutina, DiaEjercicio

class DiaEjercicioSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiaEjercicio
        fields = ["ejercicio_id", "name", "image_url", "series", "reps", "rest_seconds"]

class DiaRutinaSerializer(serializers.ModelSerializer):
    detalles = DiaEjercicioSerializer(many=True)
    class Meta:
        model = DiaRutina
        fields = ["dia", "musculo", "nombre", "detalles"]

class RutinaSerializer(serializers.ModelSerializer):
    dias = DiaRutinaSerializer(many=True)
    class Meta:
        model = Rutina
        fields = ["id", "user_id", "created_at", "duracion_minutos", "dias"]

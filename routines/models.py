from django.db import models
import uuid

class Rutina(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.IntegerField()  # id que viene en el JWT
    created_at = models.DateTimeField(auto_now_add=True)
    duracion_minutos = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Rutina {self.id} - user {self.user_id} - {self.created_at.date()}"


class DiaRutina(models.Model):
    DIAS = [
        ("lunes","Lunes"),("martes","Martes"),("miercoles","Miércoles"),
        ("jueves","Jueves"),("viernes","Viernes"),("sabado","Sábado"),("domingo","Domingo")
    ]
    MUSCULOS = [
        ('pierna', 'Pierna'),
        ('gluteo', 'Glúteo'),
        ('pecho', 'Pecho'),
        ('espalda', 'Espalda'),
        ('hombros', 'Hombros'),
        ('brazos', 'Brazos'),
        ('abdomen', 'Abdomen'),
        ('cuerpo_completo', 'Cuerpo Completo')
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rutina = models.ForeignKey(Rutina, on_delete=models.CASCADE, related_name="dias")
    dia = models.CharField(max_length=20, choices=DIAS)
    musculo = models.CharField(max_length=30, choices=MUSCULOS)
    nombre = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.dia} - {self.musculo}"


class DiaEjercicio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dia = models.ForeignKey(DiaRutina, on_delete=models.CASCADE, related_name="detalles")

    ejercicio_id = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    muscle_group = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=100)
    equipment = models.CharField(max_length=100)
    image_url = models.URLField(max_length=500, null=True, blank=True)

    series = models.PositiveSmallIntegerField()
    reps = models.PositiveSmallIntegerField()
    rest_seconds = models.PositiveIntegerField(default=60)

    def __str__(self):
        return f"{self.name} - {self.series}x{self.reps}"
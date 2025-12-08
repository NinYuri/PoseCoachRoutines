import uuid
from django.db import models

class WorkoutRoutine(models.Model):
    ROUTINE_TYPE = [
        ('cuerpo_completo', 'Cuerpo Completo'),
        ('superior', 'Tren Superior'),
        ('inferior', 'Tren Inferior'),
        ('sup_inf', 'Tren Superior e Inferior'),
        ('bro_split', 'Por Músculo'),
        ('custom', 'Personalizada'),
    ]

    DAYS_OF_WEEK = [
        ('lunes', 'Lunes'),
        ('martes', 'Martes'),
        ('miercoles', 'Miércoles'),
        ('jueves', 'Jueves'),
        ('viernes', 'Viernes'),
        ('sabado', 'Sábado'),
        ('domingo', 'Domingo'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    user_id = models.BigIntegerField(null=False, blank=False, db_index=True)

    name = models.CharField(max_length=100, null=False, blank=False)
    description = models.TextField(null=True, blank=True)
    routine_type = models.CharField(max_length=50, choices=ROUTINE_TYPE, default='custom')
    user_difficulty = models.CharField(max_length=20, null=False, blank=False, default='principiante')

    days = models.JSONField(default=list, help_text="Días de la semana: ['monday', 'wednesday', 'friday']")

    weeks_duration = models.IntegerField(default=4, help_text="Duración en semanas")
    is_active = models.BooleanField(default=True)
    is_template = models.BooleanField(default=False, help_text="Si es una plantilla reutilizable")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - User ID: {self.user_id}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Rutina'
        verbose_name_plural = 'Rutinas'


class WorkoutDay(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    routine = models.ForeignKey(WorkoutRoutine, on_delete=models.CASCADE, related_name='workout_days')

    day_name = models.CharField(max_length=100, null=False, blank=False, help_text="Ej: Día 1 - Pecho y Tríceps")
    day_of_week = models.CharField(max_length=20, choices=WorkoutRoutine.DAYS_OF_WEEK, null=True, blank=True)
    order = models.IntegerField(default=0, help_text="Orden dentro de la rutina")

    warmup_duration = models.IntegerField(default=5, help_text="Duración calentamiento en minutos")
    workout_duration = models.IntegerField(default=45, help_text="Duración entrenamiento en minutos")
    cooldown_duration = models.IntegerField(default=5, help_text="Duración enfriamiento en minutos")

    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Día de Entrenamiento'
        verbose_name_plural = 'Días de Entrenamiento'

    def __str__(self):
        return f"{self.day_name} - {self.routine.name}"


class RoutineExercise(models.Model):
    SET_TYPE = [
        ('rectos', 'Sets rectos'),
        ('piramide', 'Pirámide'),
        ('drop', 'Drop sets'),
        ('super', 'Superseries'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    workout_day = models.ForeignKey(WorkoutDay, on_delete=models.CASCADE, related_name='exercises')
    exercise_id = models.CharField(max_length=255, null=False, blank=False, db_index=True)

    # Metadatos del ejercicio para mostrar sin necesidad de llamar al otro servicio
    exercise_name = models.CharField(max_length=100, null=True, blank=True)
    exercise_muscle_group = models.CharField(max_length=50, null=True, blank=True)
    exercise_difficulty = models.CharField(max_length=20, null=True, blank=True)

    order = models.IntegerField(default=0, help_text="Orden dentro del día")
    sets = models.IntegerField(default=3)
    reps = models.CharField(max_length=50, default='8-12', help_text="Ej: '8-12', '10', '15-20'")
    rest_time = models.IntegerField(default=60, help_text="Descanso en segundos entre sets")
    set_type = models.CharField(max_length=20, choices=SET_TYPE, default='straight')

    target_weight = models.FloatField(null=True, blank=True, help_text="Peso objetivo en kg")
    target_rpe = models.IntegerField(null=True, blank=True, help_text="RPE objetivo (1-10)")

    notes = models.TextField(null=True, blank=True)
    coaching_tips = models.TextField(null=True, blank=True, help_text="Consejos para la ejecución")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        verbose_name = 'Ejercicio de Rutina'
        verbose_name_plural = 'Ejercicios de Rutina'

    def __str__(self):
        return f"{self.exercise_name or self.exercise_id} - {self.workout_day.day_name}"


class UserWorkoutSession(models.Model):
    SESSION_STATUS = [
        ('planificada', 'Planificada'),
        ('progreso', 'En progreso'),
        ('completo', 'Completada'),
        ('saltada', 'Saltada'),
        ('fallida', 'Fallida'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    user_id = models.BigIntegerField(null=False, blank=False, db_index=True)

    routine = models.ForeignKey(WorkoutRoutine, on_delete=models.CASCADE, related_name='sessions')
    workout_day = models.ForeignKey(WorkoutDay, on_delete=models.CASCADE, related_name='sessions')

    scheduled_date = models.DateField(null=False, blank=False)
    actual_date = models.DateField(null=True, blank=True)

    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=SESSION_STATUS, default='planned')
    rating = models.IntegerField(null=True, blank=True, help_text="Calificación 1-5")
    notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_date']
        verbose_name = 'Sesión de Entrenamiento'
        verbose_name_plural = 'Sesiones de Entrenamiento'

    def __str__(self):
        return f"{self.user_id} - {self.workout_day.day_name} - {self.scheduled_date}"


class ExercisePerformance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(UserWorkoutSession, on_delete=models.CASCADE, related_name='performances')
    routine_exercise = models.ForeignKey(RoutineExercise, on_delete=models.CASCADE, related_name='performances')

    sets_data = models.JSONField(default=list, help_text="""[
        {"set_number": 1, "reps": 10, "weight": 50, "rpe": 7},
        {"set_number": 2, "reps": 8, "weight": 55, "rpe": 8}
    ]""")

    total_volume = models.FloatField(null=True, blank=True, help_text="Volumen total (sets * reps * peso)")
    avg_rpe = models.FloatField(null=True, blank=True)
    pr_achieved = models.BooleanField(default=False)
    pr_note = models.TextField(null=True, blank=True)

    feedback = models.TextField(null=True, blank=True)
    pain_level = models.IntegerField(null=True, blank=True, help_text="Nivel de dolor 1-10")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Desempeño de Ejercicio'
        verbose_name_plural = 'Desempeños de Ejercicio'

    def __str__(self):
        return f"{self.routine_exercise.exercise_name} - {self.session.scheduled_date}"
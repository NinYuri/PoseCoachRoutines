from rest_framework import serializers
from .models import (
    WorkoutRoutine, WorkoutDay, RoutineExercise,
    UserWorkoutSession, ExercisePerformance
)

class RoutineExerciseSerializer(serializers.ModelSerializer):
    exercise_details = serializers.SerializerMethodField()

    class Meta:
        model = RoutineExercise
        fields = [
            'id', 'exercise_id', 'exercise_name', 'exercise_muscle_group',
            'exercise_difficulty', 'exercise_details', 'order', 'sets', 'reps',
            'rest_time', 'set_type', 'target_weight', 'target_rpe',
            'notes', 'coaching_tips', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_exercise_details(self, obj):
        """Obtiene detalles completos del ejercicio desde el otro microservicio"""
        return {
            'id': obj.exercise_id,
            'name': obj.exercise_name,
            'muscle_group': obj.exercise_muscle_group,
            'difficulty': obj.exercise_difficulty
        }


class RoutineExerciseCreateSerializer(serializers.ModelSerializer):
    # Campos para buscar ejercicio automáticamente si no se proporciona ID
    muscle_group = serializers.CharField(write_only=True, required=False)
    difficulty = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = RoutineExercise
        fields = [
            'exercise_id', 'muscle_group', 'difficulty',
            'order', 'sets', 'reps', 'rest_time', 'set_type',
            'target_weight', 'target_rpe', 'notes', 'coaching_tips'
        ]
        extra_kwargs = {
            'exercise_id': {'required': False}
        }


# ============ SERIALIZERS PARA DÍAS DE ENTRENAMIENTO ============

class WorkoutDaySerializer(serializers.ModelSerializer):
    exercises = RoutineExerciseSerializer(many=True, read_only=True)
    exercises_count = serializers.SerializerMethodField()

    class Meta:
        model = WorkoutDay
        fields = [
            'id', 'day_name', 'day_of_week', 'order',
            'warmup_duration', 'workout_duration', 'cooldown_duration',
            'notes', 'exercises', 'exercises_count'
        ]
        read_only_fields = ['id']

    def get_exercises_count(self, obj):
        return obj.exercises.count()


class WorkoutDayCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutDay
        fields = [
            'day_name', 'day_of_week', 'order',
            'warmup_duration', 'workout_duration', 'cooldown_duration', 'notes'
        ]


# ============ SERIALIZERS PARA RUTINAS ============

class WorkoutRoutineSerializer(serializers.ModelSerializer):
    workout_days = WorkoutDaySerializer(many=True, read_only=True)
    days_count = serializers.SerializerMethodField()
    total_exercises = serializers.SerializerMethodField()

    class Meta:
        model = WorkoutRoutine
        fields = [
            'id', 'user_id', 'name', 'description', 'user_difficulty',
            'routine_type', 'days', 'weeks_duration', 'is_active',
            'is_template', 'days_count', 'total_exercises',
            'workout_days', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_days_count(self, obj):
        return obj.workout_days.count()

    def get_total_exercises(self, obj):
        return sum(day.exercises.count() for day in obj.workout_days.all())


class WorkoutRoutineCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkoutRoutine
        fields = [
            'name', 'description', 'routine_type', 'days',
            'weeks_duration', 'user_difficulty', 'is_template'
        ]


# ============ SERIALIZERS PARA SESIONES DE ENTRENAMIENTO ============

class UserWorkoutSessionSerializer(serializers.ModelSerializer):
    routine_details = WorkoutRoutineSerializer(source='routine', read_only=True)
    workout_day_details = WorkoutDaySerializer(source='workout_day', read_only=True)
    duration = serializers.SerializerMethodField()

    class Meta:
        model = UserWorkoutSession
        fields = [
            'id', 'user_id', 'routine', 'routine_details',
            'workout_day', 'workout_day_details', 'scheduled_date',
            'actual_date', 'start_time', 'end_time', 'status',
            'rating', 'notes', 'duration', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_duration(self, obj):
        if obj.start_time and obj.end_time:
            return (obj.end_time - obj.start_time).total_seconds() // 60
        return None


class UserWorkoutSessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserWorkoutSession
        fields = [
            'routine', 'workout_day', 'scheduled_date',
            'notes'
        ]


# ============ SERIALIZERS PARA DESEMPEÑO DE EJERCICIOS ============

class ExercisePerformanceSerializer(serializers.ModelSerializer):
    routine_exercise_details = RoutineExerciseSerializer(source='routine_exercise', read_only=True)

    class Meta:
        model = ExercisePerformance
        fields = [
            'id', 'session', 'routine_exercise', 'routine_exercise_details',
            'sets_data', 'total_volume', 'avg_rpe', 'pr_achieved',
            'pr_note', 'feedback', 'pain_level', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class ExercisePerformanceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExercisePerformance
        fields = [
            'routine_exercise', 'sets_data', 'total_volume',
            'avg_rpe', 'pr_achieved', 'pr_note', 'feedback', 'pain_level'
        ]
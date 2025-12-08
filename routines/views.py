import uuid
import random
from datetime import datetime, timedelta

from rest_framework import generics, status, filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction

from . import models
from .models import (
    WorkoutRoutine, WorkoutDay, RoutineExercise,
    UserWorkoutSession, ExercisePerformance
)
from .serializers import (
    WorkoutRoutineSerializer, WorkoutRoutineCreateSerializer,
    WorkoutDaySerializer, WorkoutDayCreateSerializer,
    RoutineExerciseSerializer, RoutineExerciseCreateSerializer,
    UserWorkoutSessionSerializer, UserWorkoutSessionCreateSerializer,
    ExercisePerformanceSerializer, ExercisePerformanceCreateSerializer
)
from .permissions import IsAuthenticated, IsRoutineOwner
from .clients import ExercisesServiceClient, UsersServiceClient


# ============================
# RUTINAS PRINCIPALES
# ============================

class RoutineListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'routine_type']
    ordering_fields = ['created_at', 'name', 'weeks_duration']

    def get_queryset(self):
        queryset = WorkoutRoutine.objects.filter(
            user_id=self.request.user_id,
            is_active=True
        )

        # Filtro por tipo de rutina
        routine_type = self.request.query_params.get('type', None)
        if routine_type:
            queryset = queryset.filter(routine_type=routine_type)

        # Filtro por plantillas
        is_template = self.request.query_params.get('is_template', None)
        if is_template:
            queryset = queryset.filter(is_template=is_template.lower() == 'true')

        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return WorkoutRoutineCreateSerializer
        return WorkoutRoutineSerializer

    def perform_create(self, serializer):
        serializer.save(user_id=self.request.user_id)


class RoutineDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsRoutineOwner]
    queryset = WorkoutRoutine.objects.all()
    serializer_class = WorkoutRoutineSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


class RoutineActivateView(APIView):
    permission_classes = [IsAuthenticated, IsRoutineOwner]

    def post(self, request, pk):
        routine = get_object_or_404(WorkoutRoutine, id=pk)
        self.check_object_permissions(request, routine)

        # Desactivar todas las otras rutinas del usuario
        WorkoutRoutine.objects.filter(
            user_id=request.user_id,
            is_active=True
        ).update(is_active=False)

        # Activar esta rutina
        routine.is_active = True
        routine.save()

        return Response({
            "message": "Rutina activada exitosamente",
            "routine": WorkoutRoutineSerializer(routine).data
        })


# ============================
# DÍAS DE RUTINA
# ============================

class WorkoutDayListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsRoutineOwner]

    def get_queryset(self):
        routine_id = self.kwargs['routine_id']
        routine = get_object_or_404(WorkoutRoutine, id=routine_id)
        self.check_object_permissions(self.request, routine)
        return WorkoutDay.objects.filter(routine=routine).order_by('order')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return WorkoutDayCreateSerializer
        return WorkoutDaySerializer

    def perform_create(self, serializer):
        routine_id = self.kwargs['routine_id']
        routine = get_object_or_404(WorkoutRoutine, id=routine_id)

        # Calcular el próximo orden
        last_order = WorkoutDay.objects.filter(routine=routine).aggregate(
            models.Max('order')
        )['order__max'] or 0

        serializer.save(routine=routine, order=last_order + 1)


class WorkoutDayDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsRoutineOwner]

    def get_object(self):
        day = get_object_or_404(WorkoutDay, id=self.kwargs['day_id'])
        self.check_object_permissions(self.request, day.routine)
        return day

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return WorkoutDayCreateSerializer
        return WorkoutDaySerializer

    def perform_destroy(self, instance):
        # Reordenar los días restantes
        routine = instance.routine
        instance.delete()

        days = WorkoutDay.objects.filter(routine=routine).order_by('order')
        for index, day in enumerate(days):
            day.order = index
            day.save()


# ============================
# EJERCICIOS EN DÍAS
# ============================

class RoutineExerciseListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsRoutineOwner]

    def get_queryset(self):
        day_id = self.kwargs['day_id']
        day = get_object_or_404(WorkoutDay, id=day_id)
        self.check_object_permissions(self.request, day.routine)
        return RoutineExercise.objects.filter(workout_day=day).order_by('order')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return RoutineExerciseCreateSerializer
        return RoutineExerciseSerializer

    def create(self, request, *args, **kwargs):
        day_id = self.kwargs['day_id']
        day = get_object_or_404(WorkoutDay, id=day_id)
        self.check_object_permissions(self.request, day.routine)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Obtener la dificultad del usuario desde la rutina
        user_difficulty = day.routine.user_difficulty

        # Si no se proporciona exercise_id, buscar uno por criterios
        exercise_id = serializer.validated_data.get('exercise_id')
        muscle_group = serializer.validated_data.get('muscle_group')

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''

        if not exercise_id and muscle_group:
            # Buscar ejercicio apropiado según dificultad del usuario
            client = ExercisesServiceClient()
            exercise = client.get_random_exercise_by_difficulty(
                difficulty=user_difficulty,
                token=token,
                muscle_group=muscle_group
            )

            if exercise:
                exercise_id = exercise['id']
                # Almacenar metadatos para mostrar sin necesidad de llamar al servicio
                serializer.validated_data['exercise_id'] = exercise_id
                serializer.validated_data['exercise_name'] = exercise.get('name')
                serializer.validated_data['exercise_muscle_group'] = exercise.get('muscle_group')
                serializer.validated_data['exercise_difficulty'] = exercise.get('difficulty')
            else:
                return Response(
                    {"error": "No se encontró un ejercicio adecuado para la dificultad del usuario"},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Calcular el próximo orden
        last_order = RoutineExercise.objects.filter(workout_day=day).aggregate(
            models.Max('order')
        )['order__max'] or 0

        # Crear el ejercicio de rutina
        routine_exercise = RoutineExercise.objects.create(
            workout_day=day,
            order=last_order + 1,
            **serializer.validated_data
        )

        response_serializer = RoutineExerciseSerializer(routine_exercise)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class RoutineExerciseDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsRoutineOwner]

    def get_object(self):
        exercise = get_object_or_404(RoutineExercise, id=self.kwargs['exercise_id'])
        self.check_object_permissions(self.request, exercise.workout_day.routine)
        return exercise

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return RoutineExerciseCreateSerializer
        return RoutineExerciseSerializer

    def perform_destroy(self, instance):
        # Reordenar los ejercicios restantes
        workout_day = instance.workout_day
        instance.delete()

        exercises = RoutineExercise.objects.filter(workout_day=workout_day).order_by('order')
        for index, exercise in enumerate(exercises):
            exercise.order = index
            exercise.save()


class ReorderExercisesView(APIView):
    permission_classes = [IsAuthenticated, IsRoutineOwner]

    def post(self, request, day_id):
        day = get_object_or_404(WorkoutDay, id=day_id)
        self.check_object_permissions(request, day.routine)

        exercise_order = request.data.get('exercise_order', [])
        if not exercise_order:
            return Response(
                {"error": "Se requiere la lista de orden de ejercicios"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            for order_data in exercise_order:
                exercise_id = order_data.get('exercise_id')
                new_order = order_data.get('order')

                if exercise_id and new_order is not None:
                    try:
                        exercise = RoutineExercise.objects.get(
                            id=exercise_id,
                            workout_day=day
                        )
                        exercise.order = new_order
                        exercise.save()
                    except RoutineExercise.DoesNotExist:
                        continue

        # Reordenar para asegurar consistencia
        exercises = RoutineExercise.objects.filter(workout_day=day).order_by('order')
        for index, exercise in enumerate(exercises):
            exercise.order = index
            exercise.save()

        return Response({"message": "Ejercicios reordenados exitosamente"})


# ============================
# SESIONES DE ENTRENAMIENTO
# ============================

class WorkoutSessionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = UserWorkoutSession.objects.filter(
            user_id=self.request.user_id
        ).select_related('routine', 'workout_day')

        # Filtros
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        date_from = self.request.query_params.get('date_from', None)
        if date_from:
            try:
                date_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(scheduled_date__gte=date_obj)
            except ValueError:
                pass

        date_to = self.request.query_params.get('date_to', None)
        if date_to:
            try:
                date_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(scheduled_date__lte=date_obj)
            except ValueError:
                pass

        return queryset.order_by('-scheduled_date')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return UserWorkoutSessionCreateSerializer
        return UserWorkoutSessionSerializer

    def perform_create(self, serializer):
        serializer.save(user_id=self.request.user_id)


class WorkoutSessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserWorkoutSession.objects.filter(user_id=self.request.user_id)

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return UserWorkoutSessionCreateSerializer
        return UserWorkoutSessionSerializer

    def perform_update(self, serializer):
        instance = self.get_object()

        # Si se marca como completada, establecer fecha actual
        if serializer.validated_data.get('status') == 'completo' and not instance.actual_date:
            serializer.validated_data['actual_date'] = timezone.now().date()
            serializer.validated_data['end_time'] = timezone.now()

        # Si se inicia la sesión, establecer start_time
        if serializer.validated_data.get('status') == 'progreso' and not instance.start_time:
            serializer.validated_data['start_time'] = timezone.now()

        serializer.save()


class StartWorkoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(
            UserWorkoutSession,
            id=session_id,
            user_id=request.user_id
        )

        if session.status == 'completo':
            return Response(
                {"error": "Esta sesión ya está completada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        session.status = 'progreso'
        session.start_time = timezone.now()
        session.save()

        return Response({
            "message": "Sesión iniciada",
            "session": UserWorkoutSessionSerializer(session).data
        })


class CompleteWorkoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(
            UserWorkoutSession,
            id=session_id,
            user_id=request.user_id
        )

        if session.status == 'completo':
            return Response(
                {"error": "Esta sesión ya está completada"},
                status=status.HTTP_400_BAD_REQUEST
            )

        session.status = 'completo'
        session.actual_date = timezone.now().date()
        session.end_time = timezone.now()
        session.save()

        return Response({
            "message": "Sesión completada exitosamente",
            "session": UserWorkoutSessionSerializer(session).data
        })


# ============================
# DESEMPEÑO DE EJERCICIOS
# ============================

class ExercisePerformanceListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        session_id = self.kwargs['session_id']
        return ExercisePerformance.objects.filter(
            session__id=session_id,
            session__user_id=self.request.user_id
        ).select_related('routine_exercise')

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ExercisePerformanceCreateSerializer
        return ExercisePerformanceSerializer

    def perform_create(self, serializer):
        session_id = self.kwargs['session_id']
        session = get_object_or_404(
            UserWorkoutSession,
            id=session_id,
            user_id=self.request.user_id
        )

        # Calcular volumen total
        sets_data = serializer.validated_data.get('sets_data', [])
        total_volume = 0
        total_rpe = 0
        pr_achieved = False

        for set_data in sets_data:
            reps = set_data.get('reps', 0)
            weight = set_data.get('weight', 0)
            rpe = set_data.get('rpe', 0)

            total_volume += reps * weight
            total_rpe += rpe

            # Detectar PR (Personal Record)
            if weight > (serializer.validated_data.get('routine_exercise').target_weight or 0):
                pr_achieved = True

        avg_rpe = total_rpe / len(sets_data) if sets_data else 0

        serializer.save(
            total_volume=total_volume,
            avg_rpe=avg_rpe,
            pr_achieved=pr_achieved
        )


class ExercisePerformanceDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ExercisePerformance.objects.filter(
            session__user_id=self.request.user_id
        )

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ExercisePerformanceCreateSerializer
        return ExercisePerformanceSerializer


# ============================
# ENDPOINTS ESPECIALES
# ENDPOINT PARA GENERAR RUTINA AUTOMÁTICA POR DIFICULTAD
# ============================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def generate_smart_routine(request):
    """
    Genera una rutina personalizada basada en el perfil del usuario.

    Obtiene los datos del usuario (experiencia, equipo disponible, etc.)
    y genera una rutina semanal con ejercicios apropiados.
    """
    try:
        print(f"=== INICIANDO GENERACIÓN DE RUTINA INTELIGENTE ===")
        print(f"User ID: {request.user_id}")

        # 1. Obtener perfil del usuario desde el microservicio de usuarios
        users_client = UsersServiceClient()
        user_profile = users_client.get_user_profile(
            request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', '')
        )

        if not user_profile:
            return Response(
                {"error": "No se pudo obtener el perfil del usuario"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        print(f"Perfil del usuario obtenido: {user_profile}")

        # 2. Extraer datos importantes del usuario
        user_data = user_profile.get('user', {})
        user_experience = user_data.get('experience', 'principiante')
        user_equipment = user_data.get('equipment', 'cuerpo')
        user_goal = user_data.get('goal', 'mantener_forma')
        user_sex = user_data.get('sex', 'M')

        print(f"Experiencia del usuario: {user_experience}")
        print(f"Equipo disponible: {user_equipment}")
        print(f"Objetivo: {user_goal}")

        # 3. Definir plantillas de rutina según experiencia y objetivo
        routine_template = get_routine_template(user_experience, user_goal, user_sex)

        if not routine_template:
            return Response(
                {"error": "No se pudo generar una plantilla para el usuario"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Crear la rutina principal
        routine = WorkoutRoutine.objects.create(
            user_id=request.user_id,
            name=routine_template['name'],
            description=routine_template.get('description', ''),
            routine_type=routine_template['type'],
            days=routine_template['days'],
            weeks_duration=routine_template['weeks'],
            user_difficulty=user_experience,
            is_template=False,
            is_active=True
        )

        print(f"Rutina creada: {routine.id} - {routine.name}")

        # 5. Obtener ejercicios del microservicio de ejercicios
        exercises_client = ExercisesServiceClient()
        auth_token = request.META.get('HTTP_AUTHORIZATION', '').replace('Bearer ', '')

        # 6. Crear los días de entrenamiento con ejercicios
        for day_index, day_template in enumerate(routine_template['workout_days']):
            # Crear el día
            workout_day = WorkoutDay.objects.create(
                routine=routine,
                day_name=day_template['day_name'],
                day_of_week=day_template['day_of_week'],
                order=day_index,
                warmup_duration=day_template.get('warmup', 10),
                workout_duration=day_template.get('duration', 60),
                cooldown_duration=day_template.get('cooldown', 10),
                notes=day_template.get('notes', '')
            )

            print(f"Día creado: {workout_day.day_name}")

            # Para cada grupo muscular en este día, obtener ejercicios
            exercise_index = 0
            for muscle_data in day_template['muscle_groups']:
                muscle_group = muscle_data['name']
                exercise_count = muscle_data['count']

                # Obtener ejercicios filtrados por músculo, dificultad y equipo
                exercises = exercises_client.get_filtered_exercises(
                    muscle_groups=muscle_group,
                    difficulty=user_experience,
                    token=auth_token
                )

                # Filtrar adicionalmente por equipo disponible
                if exercises and user_equipment != 'gimnasio':
                    filtered_exercises = []
                    for ex in exercises:
                        ex_equipment = ex.get('equipment', '')
                        if user_equipment == 'cuerpo' and ex_equipment == 'cuerpo':
                            filtered_exercises.append(ex)
                        elif user_equipment == 'mancuernas' and ex_equipment in ['mancuernas', 'cuerpo']:
                            filtered_exercises.append(ex)
                        elif user_equipment == 'bandas' and ex_equipment in ['bandas', 'cuerpo']:
                            filtered_exercises.append(ex)
                    exercises = filtered_exercises

                # Seleccionar la cantidad de ejercicios requerida
                selected_exercises = []
                if len(exercises) >= exercise_count:
                    selected_exercises = random.sample(exercises, exercise_count)
                elif exercises:
                    selected_exercises = exercises
                else:
                    # Si no hay ejercicios, usar un ejercicio genérico
                    selected_exercises = [{
                        'id': f'default_{muscle_group}_{exercise_index}',
                        'name': f'Ejercicio de {muscle_group}',
                        'muscle_group': muscle_group,
                        'difficulty': user_experience,
                        'equipment': user_equipment
                    }]

                # Crear los ejercicios en la rutina
                for exercise_data in selected_exercises:
                    # Determinar series y repeticiones según experiencia
                    sets, reps = get_sets_reps_by_experience(user_experience, muscle_group)

                    RoutineExercise.objects.create(
                        workout_day=workout_day,
                        exercise_id=exercise_data.get('id', str(uuid.uuid4())),
                        exercise_name=exercise_data.get('name', 'Ejercicio'),
                        exercise_muscle_group=exercise_data.get('muscle_group', muscle_group),
                        exercise_difficulty=exercise_data.get('difficulty', user_experience),
                        order=exercise_index,
                        sets=sets,
                        reps=reps,
                        rest_time=get_rest_time_by_experience(user_experience),
                        set_type='rectos',
                        target_weight=None,
                        target_rpe=None,
                        notes=get_exercise_notes(muscle_group, user_experience),
                        coaching_tips=get_coaching_tips(muscle_group, user_experience)
                    )
                    exercise_index += 1

        # 7. Serializar y retornar la rutina
        serializer = WorkoutRoutineSerializer(routine)

        print(f"=== RUTINA GENERADA EXITOSAMENTE ===")

        return Response({
            "message": "Rutina generada exitosamente",
            "routine": serializer.data,
            "user_profile": {
                "experience": user_experience,
                "equipment": user_equipment,
                "goal": user_goal
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        import traceback
        print(f"ERROR en generate_smart_routine: {str(e)}")
        print(traceback.format_exc())

        return Response(
            {
                "error": "Error al generar la rutina inteligente",
                "detail": str(e)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def get_routine_template(experience, goal, sex):
    """Devuelve una plantilla de rutina según experiencia, objetivo y sexo"""

    # Rutina para hombres (5 días para todos los niveles)
    if sex.upper() == 'M':
        templates = {
            'principiante': {
                'name': 'Rutina Principiante - 5 Días',
                'description': 'Rutina completa para empezar en el fitness con enfoque en aprendizaje',
                'type': 'cuerpo_completo',
                'days': ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
                'weeks': 4,
                'workout_days': [
                    {
                        'day_name': 'Lunes - Cuerpo Completo A',
                        'day_of_week': 'lunes',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 2},
                            {'name': 'pecho', 'count': 2},
                            {'name': 'espalda', 'count': 2},
                            {'name': 'abdomen', 'count': 1}
                        ]
                    },
                    {
                        'day_name': 'Martes - Cuerpo Completo B',
                        'day_of_week': 'martes',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 2},
                            {'name': 'hombros', 'count': 2},
                            {'name': 'brazos', 'count': 2},
                            {'name': 'abdomen', 'count': 1}
                        ]
                    },
                    {
                        'day_name': 'Miércoles - Cardio Activo',
                        'day_of_week': 'miercoles',
                        'warmup': 10,
                        'duration': 40,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'cardio', 'count': 3},
                            {'name': 'abdomen', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Jueves - Cuerpo Completo C',
                        'day_of_week': 'jueves',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'gluteo', 'count': 2},
                            {'name': 'espalda', 'count': 2},
                            {'name': 'pecho', 'count': 2},
                            {'name': 'abdomen', 'count': 1}
                        ]
                    },
                    {
                        'day_name': 'Viernes - Fuerza Fundamental',
                        'day_of_week': 'viernes',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 3},
                            {'name': 'brazos', 'count': 2},
                            {'name': 'hombros', 'count': 2}
                        ]
                    }
                ]
            },
            'intermedio': {
                'name': 'Rutina Intermedia - 5 Días',
                'description': 'Split superior/inferior con volumen aumentado',
                'type': 'sup_inf',
                'days': ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
                'weeks': 6,
                'workout_days': [
                    {
                        'day_name': 'Lunes - Tren Superior (Empuje)',
                        'day_of_week': 'lunes',
                        'warmup': 10,
                        'duration': 65,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pecho', 'count': 3},
                            {'name': 'hombros', 'count': 3},
                            {'name': 'triceps', 'count': 2},
                            {'name': 'abdomen', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Martes - Pierna Completa',
                        'day_of_week': 'martes',
                        'warmup': 10,
                        'duration': 65,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 4},
                            {'name': 'gluteo', 'count': 2},
                            {'name': 'pantorrillas', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Miércoles - Cardio HIIT',
                        'day_of_week': 'miercoles',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'cardio', 'count': 4},
                            {'name': 'abdomen', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Jueves - Tren Superior (Jalón)',
                        'day_of_week': 'jueves',
                        'warmup': 10,
                        'duration': 65,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'espalda', 'count': 4},
                            {'name': 'biceps', 'count': 3},
                            {'name': 'antebrazos', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Viernes - Pierna + Glúteo',
                        'day_of_week': 'viernes',
                        'warmup': 10,
                        'duration': 65,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 3},
                            {'name': 'gluteo', 'count': 3},
                            {'name': 'abdomen', 'count': 3}
                        ]
                    }
                ]
            },
            'avanzado': {
                'name': 'Rutina Avanzado - 5 Días',
                'description': 'Split avanzado para máximo desarrollo muscular',
                'type': 'bro_split',
                'days': ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
                'weeks': 8,
                'workout_days': [
                    {
                        'day_name': 'Lunes - Pecho y Tríceps',
                        'day_of_week': 'lunes',
                        'warmup': 15,
                        'duration': 75,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pecho', 'count': 4},
                            {'name': 'triceps', 'count': 3},
                            {'name': 'abdomen', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Martes - Espalda y Bíceps',
                        'day_of_week': 'martes',
                        'warmup': 15,
                        'duration': 75,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'espalda', 'count': 4},
                            {'name': 'biceps', 'count': 3},
                            {'name': 'antebrazos', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Miércoles - Pierna Completa',
                        'day_of_week': 'miercoles',
                        'warmup': 15,
                        'duration': 80,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 5},
                            {'name': 'gluteo', 'count': 3},
                            {'name': 'pantorrillas', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Jueves - Hombros y Trapecios',
                        'day_of_week': 'jueves',
                        'warmup': 15,
                        'duration': 70,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'hombros', 'count': 5},
                            {'name': 'trapecio', 'count': 3},
                            {'name': 'abdomen', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Viernes - Brazos y Abdomen',
                        'day_of_week': 'viernes',
                        'warmup': 15,
                        'duration': 70,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'biceps', 'count': 3},
                            {'name': 'triceps', 'count': 3},
                            {'name': 'abdomen', 'count': 4},
                            {'name': 'antebrazos', 'count': 2}
                        ]
                    }
                ]
            }
        }
    else:
        # Rutina para mujeres (5 días para todos los niveles)
        templates = {
            'principiante': {
                'name': 'Rutina Principiante - 5 Días',
                'description': 'Rutina para tonificar y fortalecer con enfoque integral',
                'type': 'cuerpo_completo',
                'days': ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
                'weeks': 4,
                'workout_days': [
                    {
                        'day_name': 'Lunes - Pierna y Glúteo A',
                        'day_of_week': 'lunes',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'gluteo', 'count': 3},
                            {'name': 'pierna', 'count': 2},
                            {'name': 'abdomen', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Martes - Tren Superior',
                        'day_of_week': 'martes',
                        'warmup': 10,
                        'duration': 45,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'espalda', 'count': 2},
                            {'name': 'pecho', 'count': 2},
                            {'name': 'hombros', 'count': 1},
                            {'name': 'brazos', 'count': 1}
                        ]
                    },
                    {
                        'day_name': 'Miércoles - Cardio y Core',
                        'day_of_week': 'miercoles',
                        'warmup': 10,
                        'duration': 40,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'cardio', 'count': 3},
                            {'name': 'abdomen', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Jueves - Pierna y Glúteo B',
                        'day_of_week': 'jueves',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 3},
                            {'name': 'gluteo', 'count': 2},
                            {'name': 'pantorrillas', 'count': 1},
                            {'name': 'abdomen', 'count': 1}
                        ]
                    },
                    {
                        'day_name': 'Viernes - Full Body',
                        'day_of_week': 'viernes',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 5,
                        'muscle_groups': [
                            {'name': 'espalda', 'count': 2},
                            {'name': 'gluteo', 'count': 2},
                            {'name': 'brazos', 'count': 2},
                            {'name': 'abdomen', 'count': 2}
                        ]
                    }
                ]
            },
            'intermedio': {
                'name': 'Rutina Intermedia - 5 Días',
                'description': 'Rutina con enfoque en glúteos, piernas y definición',
                'type': 'upper_lower',
                'days': ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
                'weeks': 6,
                'workout_days': [
                    {
                        'day_name': 'Lunes - Glúteo Pesado',
                        'day_of_week': 'lunes',
                        'warmup': 10,
                        'duration': 65,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'gluteo', 'count': 4},
                            {'name': 'pierna', 'count': 2},
                            {'name': 'pantorrillas', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Martes - Tren Superior Definición',
                        'day_of_week': 'martes',
                        'warmup': 10,
                        'duration': 60,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'espalda', 'count': 3},
                            {'name': 'pecho', 'count': 2},
                            {'name': 'hombros', 'count': 2},
                            {'name': 'brazos', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Miércoles - Cardio Intenso',
                        'day_of_week': 'miercoles',
                        'warmup': 10,
                        'duration': 50,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'cardio', 'count': 4},
                            {'name': 'abdomen', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Jueves - Pierna Completa',
                        'day_of_week': 'jueves',
                        'warmup': 10,
                        'duration': 65,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 4},
                            {'name': 'gluteo', 'count': 3},
                            {'name': 'pantorrillas', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Viernes - Tren Superior + Core',
                        'day_of_week': 'viernes',
                        'warmup': 10,
                        'duration': 60,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'brazos', 'count': 3},
                            {'name': 'hombros', 'count': 3},
                            {'name': 'abdomen', 'count': 4}
                        ]
                    }
                ]
            },
            'avanzado': {
                'name': 'Rutina Avanzada - 5 Días',
                'description': 'Rutina completa para desarrollo avanzado y fuerza',
                'type': 'bro_split',
                'days': ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'],
                'weeks': 8,
                'workout_days': [
                    {
                        'day_name': 'Lunes - Glúteo Avanzado',
                        'day_of_week': 'lunes',
                        'warmup': 15,
                        'duration': 75,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'gluteo', 'count': 5},
                            {'name': 'pantorrillas', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Martes - Espalda y Bíceps',
                        'day_of_week': 'martes',
                        'warmup': 15,
                        'duration': 70,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'espalda', 'count': 4},
                            {'name': 'biceps', 'count': 3},
                            {'name': 'antebrazos', 'count': 2}
                        ]
                    },
                    {
                        'day_name': 'Miércoles - Pierna Pesada',
                        'day_of_week': 'miercoles',
                        'warmup': 15,
                        'duration': 75,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pierna', 'count': 5},
                            {'name': 'gluteo', 'count': 2},
                            {'name': 'pantorrillas', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Jueves - Pecho, Hombros y Tríceps',
                        'day_of_week': 'jueves',
                        'warmup': 15,
                        'duration': 70,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'pecho', 'count': 3},
                            {'name': 'hombros', 'count': 3},
                            {'name': 'triceps', 'count': 3}
                        ]
                    },
                    {
                        'day_name': 'Viernes - Full Body + Abdomen',
                        'day_of_week': 'viernes',
                        'warmup': 15,
                        'duration': 70,
                        'cooldown': 10,
                        'muscle_groups': [
                            {'name': 'gluteo', 'count': 3},
                            {'name': 'pierna', 'count': 2},
                            {'name': 'brazos', 'count': 2},
                            {'name': 'abdomen', 'count': 4}
                        ]
                    }
                ]
            }
        }

    # Ajustar según objetivo
    if goal == 'perder_peso':
        # Añadir más cardio/alta intensidad
        for template in templates.values():
            for day in template['workout_days']:
                day['duration'] += 10  # Aumentar duración
                if 'cardio' not in [mg['name'] for mg in day['muscle_groups']]:
                    # Añadir un ejercicio de cardio
                    day['muscle_groups'].append({'name': 'cardio', 'count': 1})
    elif goal == 'ganar_musculo':
        # Más volumen y menos cardio
        for template in templates.values():
            for day in template['workout_days']:
                for muscle in day['muscle_groups']:
                    if muscle['name'] != 'cardio':
                        muscle['count'] = min(muscle['count'] + 1, 6)  # Máximo 6 ejercicios

    return templates.get(experience)


def get_sets_reps_by_experience(experience, muscle_group):
    """Devuelve sets y repeticiones según experiencia y grupo muscular"""
    if experience == 'principiante':
        if muscle_group in ['abdomen', 'pantorrillas', 'antebrazos']:
            return 3, '12-15'
        elif muscle_group == 'cardio':
            return 3, '30-45 segundos'
        return 3, '10-12'
    elif experience == 'intermedio':
        if muscle_group in ['abdomen', 'pantorrillas', 'antebrazos']:
            return 4, '12-15'
        elif muscle_group == 'cardio':
            return 4, '45-60 segundos'
        return 4, '8-12'
    else:  # avanzado
        if muscle_group in ['abdomen', 'pantorrillas', 'antebrazos']:
            return 4, '10-15'
        elif muscle_group == 'cardio':
            return 4, '60-90 segundos'
        return 4, '6-10'


def get_rest_time_by_experience(experience):
    """Devuelve tiempo de descanso según experiencia"""
    if experience == 'principiante':
        return 90  # segundos
    elif experience == 'intermedio':
        return 75
    else:  # avanzado
        return 60


def get_exercise_notes(muscle_group, experience):
    """Devuelve notas según grupo muscular y experiencia"""
    notes = {
        'principiante': {
            'pierna': 'Enfócate en la técnica, no en el peso. Mantén las rodillas alineadas.',
            'gluteo': 'Siente la contracción en cada repetición. No uses impulso.',
            'pecho': 'Controla el movimiento completo. Baja lentamente.',
            'espalda': 'Mantén el pecho alto y los hombros atrás.',
            'brazos': 'Aísla el músculo. No balancees el cuerpo.',
            'abdomen': 'Exhala al contraer. Mantén el core activo.',
            'hombros': 'No encorves los hombros. Controla el movimiento.',
            'cardio': 'Mantén un ritmo constante. Controla la respiración.',
            'pantorrillas': 'Estira completamente en cada repetición.',
            'antebrazos': 'Controla el movimiento en ambas direcciones.'
        },
        'intermedio': {
            'pierna': 'Mantén la tensión muscular. Varía los ángulos.',
            'gluteo': 'Enfócate en la conexión mente-músculo. Añade pausas.',
            'pecho': 'Varía el tempo. Controla la fase excéntrica.',
            'espalda': 'Completa el rango de movimiento. Jala con los codos.',
            'brazos': 'Varía los agarres. Control total del movimiento.',
            'abdomen': 'Mantén la tensión constante. Varía los ángulos.',
            'hombros': 'Aísla el deltoides. No uses trampa.',
            'cardio': 'Varía la intensidad. Intervalos controlados.',
            'pantorrillas': 'Añade pausas en la contracción máxima.',
            'antebrazos': 'Varía los agarres para mayor estimulación.'
        },
        'avanzado': {
            'pierna': 'Busca el fallo muscular con técnica perfecta.',
            'gluteo': 'Añade técnicas de intensidad. Pausas y contracciones.',
            'pecho': 'Varía ángulos y tempos. Máxima conexión mente-músculo.',
            'espalda': 'Enfócate en la contracción máxima. Control excéntrico.',
            'brazos': 'Superseries y dropsets. Aislamiento total.',
            'abdomen': 'Tensión constante. Sin descanso entre ejercicios.',
            'hombros': 'Aísla cada haz del deltoides. Técnica impecable.',
            'cardio': 'HIIT de alta intensidad. Recuperación activa.',
            'pantorrillas': 'Rango completo con pausas. Variedad de ángulos.',
            'antebrazos': 'Técnicas avanzadas de intensidad.'
        }
    }
    return notes.get(experience, {}).get(muscle_group, 'Mantén la técnica correcta en cada repetición.')


def get_coaching_tips(muscle_group, experience):
    """Devuelve tips de coaching según grupo muscular y experiencia"""
    tips = {
        'pierna': 'Mantén las rodillas alineadas con los pies durante todo el movimiento.',
        'gluteo': 'Empuja con los talones y enfócate en contraer el glúteo al máximo.',
        'pecho': 'Mantén los hombros retraídos y el pecho alto durante el movimiento.',
        'espalda': 'Imagina que estás sacando el pecho y jala con los codos, no con los brazos.',
        'brazos': 'Controla el movimiento en ambas fases, especialmente la excéntrica.',
        'abdomen': 'Mete el ombligo hacia la columna para activar el transverso abdominal.',
        'hombros': 'Mantén una ligera flexión en los codos para proteger las articulaciones.',
        'cardio': 'Controla tu respiración - inhala por la nariz, exhala por la boca.',
        'pantorrillas': 'Estira completamente en la parte baja y contrae al máximo en la alta.',
        'antebrazos': 'Siente el estiramiento y la contracción en cada repetición.',
        'trapecio': 'Evita encoger los hombros hacia las orejas, enfócate en retraerlos.'
    }
    return tips.get(muscle_group, 'Mantén la postura correcta y controla el movimiento en todo momento.')


# Obtener rutina del día actual
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_todays_routine(request):
    """
    Obtiene la rutina activa del usuario para hoy
    """
    # Mapeo de días de la semana
    day_mapping = {
        0: 'lunes',
        1: 'martes',
        2: 'miercoles',
        3: 'jueves',
        4: 'viernes',
        5: 'sabado',
        6: 'domingo'
    }

    today = timezone.now().date()
    today_weekday = today.weekday()
    today_day = day_mapping[today_weekday]

    # Buscar rutina activa
    routine = WorkoutRoutine.objects.filter(
        user_id=request.user_id,
        is_active=True,
        days__contains=[today_day]
    ).first()

    if not routine:
        return Response(
            {"message": "Hoy es día de descanso o no tienes rutina activa programada para hoy"},
            status=status.HTTP_200_OK
        )

    # Buscar día de rutina para hoy
    workout_day = WorkoutDay.objects.filter(
        routine=routine,
        day_of_week=today_day
    ).first()

    if not workout_day:
        # Si no hay día específico para hoy, tomar el primero de la rutina
        workout_day = WorkoutDay.objects.filter(routine=routine).first()

    serializer = WorkoutDaySerializer(workout_day)
    return Response(serializer.data)


@api_view(['GET'])
def health_check(request):
    """Endpoint simple para verificar que el servidor funciona"""
    return Response({
        "status": "ok",
        "service": "routines",
        "timestamp": timezone.now().isoformat()
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_todays_routine(request):
    """
    Obtiene la rutina activa del usuario para hoy
    """
    # Mapeo de días de la semana
    day_mapping = {
        0: 'lunes',
        1: 'martes',
        2: 'miercoles',
        3: 'jueves',
        4: 'viernes',
        5: 'sabado',
        6: 'domingo'
    }

    today = timezone.now().date()
    today_weekday = today.weekday()
    today_day = day_mapping[today_weekday]

    # Buscar rutina activa
    routine = WorkoutRoutine.objects.filter(
        user_id=request.user_id,
        is_active=True,
        days__contains=[today_day]
    ).first()

    if not routine:
        return Response(
            {"message": "Hoy es día de descanso o no tienes rutina activa programada para hoy"},
            status=status.HTTP_200_OK
        )

    # Buscar día de rutina para hoy
    workout_day = WorkoutDay.objects.filter(
        routine=routine,
        day_of_week=today_day
    ).first()

    if not workout_day:
        # Si no hay día específico para hoy, tomar el primero de la rutina
        workout_day = WorkoutDay.objects.filter(routine=routine).first()

    serializer = WorkoutDaySerializer(workout_day)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def schedule_weekly_sessions(request):
    """
    Programa todas las sesiones de la semana para la rutina activa
    """
    user_id = request.user_id
    routine = WorkoutRoutine.objects.filter(
        user_id=user_id,
        is_active=True
    ).first()

    if not routine:
        return Response(
            {"error": "No tienes una rutina activa"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Calcular fechas de la semana
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday())

    # Mapeo de días
    day_mapping = {
        'lunes': 0,
        'martes': 1,
        'miercoles': 2,
        'jueves': 3,
        'viernes': 4,
        'sabado': 5,
        'domingo': 6
    }

    created_sessions = []

    with transaction.atomic():
        # Eliminar sesiones futuras no completadas
        UserWorkoutSession.objects.filter(
            user_id=user_id,
            scheduled_date__gte=today,
            status__in=['planificada', 'progreso']
        ).delete()

        # Crear nuevas sesiones
        for day_name in routine.days:
            day_offset = day_mapping.get(day_name)
            if day_offset is not None:
                scheduled_date = start_of_week + timedelta(days=day_offset)

                # Buscar el día de entrenamiento correspondiente
                workout_day = WorkoutDay.objects.filter(
                    routine=routine,
                    day_of_week=day_name
                ).first()

                if workout_day:
                    session = UserWorkoutSession.objects.create(
                        user_id=user_id,
                        routine=routine,
                        workout_day=workout_day,
                        scheduled_date=scheduled_date,
                        status='planificada'
                    )
                    created_sessions.append(session)

    serializer = UserWorkoutSessionSerializer(created_sessions, many=True)
    return Response({
        "message": f"{len(created_sessions)} sesiones programadas",
        "sessions": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_workout_stats(request):
    """
    Obtiene estadísticas de entrenamiento del usuario
    """
    user_id = request.user_id

    # Sesiones completadas
    completed_sessions = UserWorkoutSession.objects.filter(
        user_id=user_id,
        status='completo'
    )

    total_sessions = completed_sessions.count()

    if total_sessions == 0:
        return Response({
            "total_sessions": 0,
            "total_volume": 0,
            "average_session_duration": 0,
            "completion_rate": 0,
            "favorite_muscle_group": None,
            "pr_count": 0,
            "streak_days": 0
        })

    # Calcular volumen total
    total_volume = ExercisePerformance.objects.filter(
        session__user_id=user_id
    ).aggregate(models.Sum('total_volume'))['total_volume__sum'] or 0

    # Calcular duración promedio de sesiones
    duration_sum = timedelta()
    for session in completed_sessions:
        if session.start_time and session.end_time:
            duration_sum += session.end_time - session.start_time

    average_duration = duration_sum.total_seconds() / total_sessions if total_sessions > 0 else 0

    # Calcular tasa de completitud (últimas 4 semanas)
    four_weeks_ago = timezone.now().date() - timedelta(weeks=4)
    scheduled_sessions = UserWorkoutSession.objects.filter(
        user_id=user_id,
        scheduled_date__gte=four_weeks_ago
    ).count()

    completed_recent = completed_sessions.filter(
        actual_date__gte=four_weeks_ago
    ).count()

    completion_rate = (completed_recent / scheduled_sessions * 100) if scheduled_sessions > 0 else 0

    # Grupo muscular favorito
    favorite_muscle = RoutineExercise.objects.filter(
        workout_day__routine__user_id=user_id,
        exercise_muscle_group__isnull=False
    ).values('exercise_muscle_group').annotate(
        count=models.Count('id')
    ).order_by('-count').first()

    # Contar PRs
    pr_count = ExercisePerformance.objects.filter(
        session__user_id=user_id,
        pr_achieved=True
    ).count()

    # Calcular racha de entrenamiento
    today = timezone.now().date()
    streak = 0

    for i in range(30):  # Verificar últimos 30 días
        check_date = today - timedelta(days=i)
        has_session = UserWorkoutSession.objects.filter(
            user_id=user_id,
            actual_date=check_date,
            status='completo'
        ).exists()

        if has_session:
            streak += 1
        else:
            break

    return Response({
        "total_sessions": total_sessions,
        "total_volume": total_volume,
        "average_session_duration": average_duration,
        "completion_rate": round(completion_rate, 1),
        "favorite_muscle_group": favorite_muscle['exercise_muscle_group'] if favorite_muscle else None,
        "pr_count": pr_count,
        "streak_days": streak
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_upcoming_sessions(request):
    """
    Obtiene las próximas sesiones de entrenamiento
    """
    today = timezone.now().date()

    upcoming_sessions = UserWorkoutSession.objects.filter(
        user_id=request.user_id,
        scheduled_date__gte=today
    ).select_related('routine', 'workout_day').order_by('scheduled_date')[:10]

    serializer = UserWorkoutSessionSerializer(upcoming_sessions, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def duplicate_routine(request, routine_id):
    """
    Duplica una rutina existente
    """
    original_routine = get_object_or_404(
        WorkoutRoutine,
        id=routine_id,
        user_id=request.user_id
    )

    with transaction.atomic():
        # Duplicar la rutina
        new_routine = WorkoutRoutine.objects.create(
            user_id=request.user_id,
            name=f"{original_routine.name} (Copia)",
            description=original_routine.description,
            routine_type=original_routine.routine_type,
            user_difficulty=original_routine.user_difficulty,
            days=original_routine.days,
            weeks_duration=original_routine.weeks_duration,
            is_active=False,
            is_template=False
        )

        # Duplicar los días
        for day in original_routine.workout_days.all():
            new_day = WorkoutDay.objects.create(
                routine=new_routine,
                day_name=day.day_name,
                day_of_week=day.day_of_week,
                order=day.order,
                warmup_duration=day.warmup_duration,
                workout_duration=day.workout_duration,
                cooldown_duration=day.cooldown_duration,
                notes=day.notes
            )

            # Duplicar los ejercicios
            for exercise in day.exercises.all():
                RoutineExercise.objects.create(
                    workout_day=new_day,
                    exercise_id=exercise.exercise_id,
                    exercise_name=exercise.exercise_name,
                    exercise_muscle_group=exercise.exercise_muscle_group,
                    exercise_difficulty=exercise.exercise_difficulty,
                    order=exercise.order,
                    sets=exercise.sets,
                    reps=exercise.reps,
                    rest_time=exercise.rest_time,
                    set_type=exercise.set_type,
                    target_weight=exercise.target_weight,
                    target_rpe=exercise.target_rpe,
                    notes=exercise.notes,
                    coaching_tips=exercise.coaching_tips
                )

    serializer = WorkoutRoutineSerializer(new_routine)
    return Response({
        "message": "Rutina duplicada exitosamente",
        "routine": serializer.data
    })


@api_view(['GET'])
def search_exercises(request):
    """
    Busca ejercicios en el microservicio de ejercicios
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''

    if not token:
        return Response(
            {"error": "Token de autorización requerido"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    client = ExercisesServiceClient()

    # Parámetros de búsqueda
    muscle_group = request.query_params.get('muscle_group', None)
    difficulty = request.query_params.get('difficulty', None)
    equipment = request.query_params.get('equipment', None)
    search = request.query_params.get('search', None)

    exercises = client.search_exercises(
        token=token,
        muscle_group=muscle_group,
        difficulty=difficulty,
        equipment=equipment,
        search=search
    )

    return Response(exercises)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_routine_progress(request, routine_id):
    """
    Obtiene el progreso de una rutina específica
    """
    routine = get_object_or_404(
        WorkoutRoutine,
        id=routine_id,
        user_id=request.user_id
    )

    # Sesiones completadas de esta rutina
    completed_sessions = UserWorkoutSession.objects.filter(
        routine=routine,
        status='completo'
    )

    total_days = routine.days.count() * routine.weeks_duration
    completed_days = completed_sessions.count()

    # Progreso por semana
    week_progress = []
    for week in range(1, routine.weeks_duration + 1):
        week_start = routine.created_at.date() + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(weeks=1)

        week_sessions = completed_sessions.filter(
            actual_date__gte=week_start,
            actual_date__lt=week_end
        ).count()

        week_progress.append({
            "week": week,
            "completed_sessions": week_sessions,
            "target_sessions": routine.days.count(),
            "completion_percentage": (week_sessions / routine.days.count() * 100) if routine.days.count() > 0 else 0
        })

    # Volumen por músculo
    muscle_volume = {}
    performances = ExercisePerformance.objects.filter(
        session__routine=routine
    ).select_related('routine_exercise')

    for perf in performances:
        muscle = perf.routine_exercise.exercise_muscle_group
        volume = perf.total_volume or 0

        if muscle:
            if muscle not in muscle_volume:
                muscle_volume[muscle] = 0
            muscle_volume[muscle] += volume

    return Response({
        "routine_name": routine.name,
        "total_days": total_days,
        "completed_days": completed_days,
        "completion_percentage": (completed_days / total_days * 100) if total_days > 0 else 0,
        "week_progress": week_progress,
        "muscle_volume": muscle_volume,
        "start_date": routine.created_at.date(),
        "estimated_end_date": routine.created_at.date() + timedelta(weeks=routine.weeks_duration)
    })


@api_view(['GET'])
def health_check(request):
    """Endpoint simple para verificar que el servidor funciona"""
    # Verificar conexión a base de datos
    try:
        WorkoutRoutine.objects.count()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return Response({
        "status": "ok",
        "service": "routines",
        "database": db_status,
        "timestamp": timezone.now().isoformat()
    })


# ============================
# ENDPOINTS ADMIN
# ============================

@api_view(['GET'])
def admin_routines_list(request):
    """
    Lista todas las rutinas (para administradores)
    """
    # Verificar si es admin (simplificado - en producción usar permisos adecuados)
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return Response(
            {"error": "Token requerido"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    token = auth_header.replace('Bearer ', '')

    # Verificar token admin (simplificado)
    if token != "admin_token_secreto":
        return Response(
            {"error": "No autorizado"},
            status=status.HTTP_403_FORBIDDEN
        )

    routines = WorkoutRoutine.objects.all().order_by('-created_at')[:100]
    serializer = WorkoutRoutineSerializer(routines, many=True)
    return Response(serializer.data)


@api_view(['POST'])
def create_template_routine(request):
    """
    Crea una rutina plantilla (para administradores)
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return Response(
            {"error": "Token requerido"},
            status=status.HTTP_401_UNAUTHORIZED
        )

    token = auth_header.replace('Bearer ', '')

    if token != "admin_token_secreto":
        return Response(
            {"error": "No autorizado"},
            status=status.HTTP_403_FORBIDDEN
        )

    serializer = WorkoutRoutineCreateSerializer(data=request.data)
    if serializer.is_valid():
        routine = serializer.save(is_template=True, user_id=0)  # user_id 0 para plantillas
        return Response(WorkoutRoutineSerializer(routine).data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def list_template_routines(request):
    """
    Lista todas las rutinas plantilla
    """
    templates = WorkoutRoutine.objects.filter(is_template=True).order_by('-created_at')
    serializer = WorkoutRoutineSerializer(templates, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def apply_template(request, template_id):
    """
    Aplica una plantilla de rutina al usuario
    """
    template = get_object_or_404(WorkoutRoutine, id=template_id, is_template=True)

    # Duplicar la plantilla para el usuario
    return duplicate_routine(request._request, template_id)


# ============================
# IMPORT/EXPORT
# ============================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_routine(request, routine_id):
    """
    Exporta una rutina en formato JSON
    """
    routine = get_object_or_404(
        WorkoutRoutine,
        id=routine_id,
        user_id=request.user_id
    )

    routine_data = WorkoutRoutineSerializer(routine).data

    # Añadir días y ejercicios
    days_data = []
    for day in routine.workout_days.all():
        day_data = WorkoutDaySerializer(day).data
        exercises_data = RoutineExerciseSerializer(day.exercises.all(), many=True).data
        day_data['exercises'] = exercises_data
        days_data.append(day_data)

    routine_data['workout_days'] = days_data

    return Response({
        "format": "workout_routine_v1",
        "routine": routine_data,
        "export_date": timezone.now().isoformat()
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def import_routine(request):
    """
    Importa una rutina desde formato JSON
    """
    data = request.data

    if data.get('format') != 'workout_routine_v1':
        return Response(
            {"error": "Formato no soportado"},
            status=status.HTTP_400_BAD_REQUEST
        )

    routine_data = data.get('routine', {})

    # Crear rutina
    routine = WorkoutRoutine.objects.create(
        user_id=request.user_id,
        name=routine_data.get('name', 'Rutina Importada'),
        description=routine_data.get('description', ''),
        routine_type=routine_data.get('routine_type', 'custom'),
        user_difficulty=routine_data.get('user_difficulty', 'principiante'),
        days=routine_data.get('days', []),
        weeks_duration=routine_data.get('weeks_duration', 4),
        is_active=False,
        is_template=False
    )

    # Crear días y ejercicios
    for day_data in routine_data.get('workout_days', []):
        day = WorkoutDay.objects.create(
            routine=routine,
            day_name=day_data.get('day_name', ''),
            day_of_week=day_data.get('day_of_week', None),
            order=day_data.get('order', 0),
            warmup_duration=day_data.get('warmup_duration', 5),
            workout_duration=day_data.get('workout_duration', 45),
            cooldown_duration=day_data.get('cooldown_duration', 5),
            notes=day_data.get('notes', '')
        )

        for exercise_data in day_data.get('exercises', []):
            RoutineExercise.objects.create(
                workout_day=day,
                exercise_id=exercise_data.get('exercise_id', ''),
                exercise_name=exercise_data.get('exercise_name', ''),
                exercise_muscle_group=exercise_data.get('exercise_muscle_group', ''),
                exercise_difficulty=exercise_data.get('exercise_difficulty', ''),
                order=exercise_data.get('order', 0),
                sets=exercise_data.get('sets', 3),
                reps=exercise_data.get('reps', '8-12'),
                rest_time=exercise_data.get('rest_time', 60),
                set_type=exercise_data.get('set_type', 'rectos'),
                target_weight=exercise_data.get('target_weight', None),
                target_rpe=exercise_data.get('target_rpe', None),
                notes=exercise_data.get('notes', ''),
                coaching_tips=exercise_data.get('coaching_tips', '')
            )

    serializer = WorkoutRoutineSerializer(routine)
    return Response({
        "message": "Rutina importada exitosamente",
        "routine": serializer.data
    }, status=status.HTTP_201_CREATED)
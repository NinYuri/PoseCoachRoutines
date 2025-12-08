from django.urls import path
from . import views

urlpatterns = [
    # Rutinas
    path('all/', views.RoutineListCreateView.as_view(), name='routine-list-create'),
    path('<uuid:id>/', views.RoutineDetailView.as_view(), name='routine-detail'),

    # Días de rutina
    path('<uuid:routine_id>/days/', views.WorkoutDayListCreateView.as_view(), name='workout-day-list'),

    # Ejercicios en días
    path('days/<uuid:day_id>/exercises/', views.RoutineExerciseListCreateView.as_view(), name='routine-exercise-list'),

    # Endpoints inteligentes
    path('generate-smart-routine/', views.generate_smart_routine, name='generate-smart-routine'),
    path('today/', views.get_todays_routine, name='todays-routine'),

    path('health/', views.health_check, name='health-check'),
]
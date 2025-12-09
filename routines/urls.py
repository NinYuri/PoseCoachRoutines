from django.urls import path
from .views import GenerateRoutineView, ListRutinasView, GetRutinaView

urlpatterns = [
    path("generate/", GenerateRoutineView.as_view(), name="generar_rutina"),
    path("all/", ListRutinasView.as_view(), name="listar_rutinas"),
    path("<uuid:rutina_id>/", GetRutinaView.as_view(), name="obtener_rutina"),
]
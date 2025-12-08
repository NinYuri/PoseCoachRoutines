from django.urls import path, include

urlpatterns = [
    path('routines/', include('routines.urls')),
]
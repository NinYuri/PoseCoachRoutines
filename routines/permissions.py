import jwt
from django.conf import settings
from rest_framework import permissions
from django.core.cache import cache


class IsAuthenticated(permissions.BasePermission):
    """
    Verifica que el token JWT sea válido y extrae el user_id.
    Guarda el token en el request para usarlo en las vistas.
    """

    def has_permission(self, request, view):
        # Extraer el token del header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        token = None

        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token:
            return False

        try:
            # Decodificar el token con la misma SECRET_KEY
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=['HS256']
            )

            # Extraer user_id del payload
            user_id = payload.get('user_id') or payload.get('sub') or payload.get('id')

            if not user_id:
                return False

            # Convertir a entero si es posible
            try:
                user_id = int(user_id)
            except (ValueError, TypeError):
                pass

            # Guardar user_id y token en el request para uso posterior
            request.user_id = user_id
            request.token = token  # Guardamos el token aquí

            return True

        except jwt.ExpiredSignatureError:
            return False
        except jwt.InvalidTokenError:
            return False


class IsRoutineOwner(permissions.BasePermission):
    """
    Verifica que el usuario sea dueño de la rutina.
    """

    def has_object_permission(self, request, view, obj):
        # Si el objeto tiene user_id directamente
        if hasattr(obj, 'user_id'):
            return str(obj.user_id) == request.user_id

        # Si es un día de rutina, verificar a través de la rutina
        if hasattr(obj, 'routine'):
            return str(obj.routine.user_id) == request.user_id

        # Si es un ejercicio de rutina, verificar a través del día y rutina
        if hasattr(obj, 'workout_day'):
            return str(obj.workout_day.routine.user_id) == request.user_id

        # Si es una sesión
        if hasattr(obj, 'user_id'):
            return str(obj.user_id) == request.user_id

        return False
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from django.contrib.auth.models import AbstractBaseUser


class MicroserviceUser(AbstractBaseUser):
    USERNAME_FIELD = "id"

    def __init__(self, user_id):
        super().__init__()
        self.id = int(user_id)
        self.username = f"user_{user_id}"

    @property
    def is_authenticated(self):
        return True


class MicroserviceJWTAuthentication(JWTAuthentication):
    """
    Valida el token y devuelve un MicroserviceUser que DRF considerará autenticado.
    No intenta cargar el usuario desde la DB local.
    """
    def get_user(self, validated_token):
        user_id = validated_token.get("user_id") or validated_token.get("user") or validated_token.get("sub")
        if user_id is None:
            raise InvalidToken("user_id no encontrado en el token")
        return MicroserviceUser(user_id)
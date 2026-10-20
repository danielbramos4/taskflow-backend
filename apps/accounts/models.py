from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Usuário autenticável da plataforma TaskFlow."""

    class Meta:
        db_table = "users"
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self) -> str:
        return self.username
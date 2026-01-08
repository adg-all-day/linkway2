from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.products.models import Product

from .permissions import IsAdmin
from .serializers import RegisterSerializer, UserSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
  serializer_class = RegisterSerializer
  permission_classes = [permissions.AllowAny]


class LoginView(APIView):
  permission_classes = [AllowAny]

  def post(self, request):
    email = (request.data.get("email") or "").strip().lower()
    password = request.data.get("password") or ""

    if not email or not password:
      return Response({"detail": "Email and password are required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
      user = User.objects.get(email=email)
    except User.DoesNotExist:
      return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
      return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
      return Response({"detail": "User account is inactive."}, status=status.HTTP_403_FORBIDDEN)

    refresh = RefreshToken.for_user(user)
    return Response(
      {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
      },
      status=status.HTTP_200_OK,
    )


class MeView(generics.RetrieveUpdateAPIView):
  serializer_class = UserSerializer
  permission_classes = [permissions.IsAuthenticated]

  def get_object(self):
    return self.request.user


class UserListView(generics.ListAPIView):
  """
  Admin-only list of all users for the dashboard Users page.
  Only active users are returned.
  """

  serializer_class = UserSerializer
  permission_classes = [permissions.IsAuthenticated, IsAdmin]
  queryset = User.objects.filter(is_active=True).order_by("-created_at")


class UserDeleteView(generics.DestroyAPIView):
  """
  Admin-only deletion endpoint.

  - Cannot delete admin users.
  - Marks any seller's products as inactive so they appear as unavailable.
  - Soft-disables the user (is_active=False) and anonymises the email to free it up.
  """

  serializer_class = UserSerializer
  permission_classes = [permissions.IsAuthenticated, IsAdmin]
  queryset = User.objects.all()

  def destroy(self, request, *args, **kwargs):
    password = request.data.get("password")
    if not password:
      raise ValidationError({"detail": "Admin password is required to delete a user."})
    if not request.user.check_password(password):
      raise ValidationError({"detail": "Invalid admin password."})

    return super().destroy(request, *args, **kwargs)

  def perform_destroy(self, instance: User):
    if instance.role == "admin":
      raise ValidationError("Admin accounts cannot be deleted.")

    # Mark all products for this seller as inactive so they no longer appear
    # in listings, but affiliate links can still resolve and show 'unavailable'.
    Product.objects.filter(seller=instance).update(is_active=False)

    # Soft-delete the user: disable login and free the email for reuse.
    email = instance.email or ""
    local, _, domain = email.partition("@")
    if domain:
      instance.email = f"deleted+{instance.id}@{domain}"
    else:
      instance.email = f"deleted+{instance.id}@deleted.local"

    instance.is_active = False
    instance.save(update_fields=["email", "is_active"])

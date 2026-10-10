from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response

from .serializers import LoginSerializer, RegisterSerializer, UserSerializer

User = get_user_model()


class IsSelf(BasePermission):
    message = "You can only modify your own account."

    def has_object_permission(self, request, view, obj):
        return obj == request.user


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("username")

    def get_serializer_class(self):
        if self.action == "create":
            return RegisterSerializer
        if self.action == "login":
            return LoginSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action in ("create", "login"):
            return [AllowAny()]
        if self.action in ("update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsSelf()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        search = params.get("search")
        if search:  # Q object: OR filtering
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))
        ids = params.get("ids")
        if ids:  # __in lookup
            qs = qs.filter(id__in=ids.split(","))
        joined_after = params.get("joined_after")
        if joined_after:  # __gte lookup
            qs = qs.filter(date_joined__gte=joined_after)
        return qs

    def create(self, request, *args, **kwargs):
        """POST /api/users/  -> register."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        data = UserSerializer(user).data
        data["token"] = token.key
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def login(self, request):
        """POST /api/users/login/  -> token."""
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})

    @action(detail=False, methods=["get"])
    def me(self, request):
        """GET /api/users/me/  -> logged-in user."""
        return Response(UserSerializer(request.user).data)

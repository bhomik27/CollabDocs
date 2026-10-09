from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsWorkspaceAdmin, IsWorkspaceMember
from core.utils import parse_query_value
from .models import Workspace, WorkspaceMember
from .serializers import AddMemberSerializer, WorkspaceMemberSerializer, WorkspaceSerializer

User = get_user_model()


class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer
    pagination_class = None  # list keeps returning a plain JSON array (Person A's API contract)

    def get_permissions(self):
        # Adding a member (POST .../members/) is admin-only; checked in _add_member().
        if self.action in ("update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsWorkspaceAdmin()]
        if self.action in ("retrieve", "members", "stats"):
            return [IsAuthenticated(), IsWorkspaceMember()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        params = self.request.query_params

        # Only workspaces the user belongs to (values_list for ids only)
        memberships = WorkspaceMember.objects.filter(user=user)
        role = params.get("role")
        if role:  # __in lookup, e.g. ?role=admin,editor
            memberships = memberships.filter(role__in=role.split(","))
        workspace_ids = memberships.values_list("workspace_id", flat=True)

        qs = (
            Workspace.objects.filter(id__in=workspace_ids)
            .select_related("owner")
            .annotate(member_count=Count("members"))  # annotate + Count
        )

        search = params.get("search")
        if search:  # Q object: OR filtering
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        is_active = params.get("is_active")
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        if params.get("created_after"):  # __gte
            qs = qs.filter(created_at__gte=parse_query_value(Workspace, "created_at", "created_after", params["created_after"]))
        if params.get("created_before"):  # __lte
            qs = qs.filter(created_at__lte=parse_query_value(Workspace, "created_at", "created_before", params["created_before"]))
        return qs

    def create(self, request, *args, **kwargs):
        """POST /api/workspaces/ -> workspace + admin member in ONE atomic block."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                workspace = serializer.save(owner=request.user)
                WorkspaceMember.objects.create(
                    workspace=workspace, user=request.user, role=WorkspaceMember.Role.ADMIN
                )
        except IntegrityError:
            return Response(
                {"detail": "Could not create workspace (integrity error). Nothing was saved."},
                status=status.HTTP_409_CONFLICT,
            )
        workspace.member_count = 1
        return Response(self.get_serializer(workspace).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        """GET  /api/workspaces/{id}/members/ -> list members
        POST /api/workspaces/{id}/members/ -> add member (admin only)"""
        workspace = self.get_object()
        if request.method == "POST":
            return self._add_member(request, workspace)
        members = (
            WorkspaceMember.objects.filter(workspace=workspace)
            .select_related("user")
            .order_by("joined_at")
        )
        return Response(WorkspaceMemberSerializer(members, many=True).data)

    def _add_member(self, request, workspace):
        if not IsWorkspaceAdmin().has_object_permission(request, self, workspace):
            return Response(
                {"detail": IsWorkspaceAdmin.message}, status=status.HTTP_403_FORBIDDEN
            )
        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email__iexact=serializer.validated_data["email"])
        except User.DoesNotExist:
            return Response(
                {"detail": "No user found with this email."}, status=status.HTTP_404_NOT_FOUND
            )
        try:
            with transaction.atomic():
                member = WorkspaceMember.objects.create(
                    workspace=workspace, user=user, role=serializer.validated_data["role"]
                )
        except IntegrityError:
            return Response(
                {"detail": "This user is already a member of the workspace."},
                status=status.HTTP_409_CONFLICT,
            )
        member = WorkspaceMember.objects.select_related("user").get(pk=member.pk)
        return Response(WorkspaceMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """GET /api/workspaces/{id}/stats/ -> member counts using aggregate()."""
        workspace = self.get_object()
        R = WorkspaceMember.Role
        data = WorkspaceMember.objects.filter(workspace=workspace).aggregate(
            total_members=Count("id"),
            admins=Count("id", filter=Q(role=R.ADMIN)),
            editors=Count("id", filter=Q(role=R.EDITOR)),
            viewers=Count("id", filter=Q(role=R.VIEWER)),
        )
        data.update({"workspace_id": workspace.id, "name": workspace.name, "is_active": workspace.is_active})
        return Response(data)

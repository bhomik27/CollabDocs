from django.contrib import admin

from documents.models import Document, DocumentVersion


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    can_delete = False
    fields = ["version_number", "saved_by", "saved_at", "restored_from"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        # Versions are only created through documents.services, which locks the document.
        return False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "workspace", "status", "created_by", "updated_at"]
    list_filter = ["status"]
    search_fields = ["title"]
    list_select_related = ["workspace", "created_by"]
    inlines = [DocumentVersionInline]

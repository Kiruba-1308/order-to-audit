from django.contrib import admin

from .models import ProductionRun, ProductionRunLine


class RunLineInline(admin.TabularInline):
    model = ProductionRunLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in ProductionRunLine._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProductionRun)
class ProductionRunAdmin(admin.ModelAdmin):
    list_display = ("date", "product", "expected_output", "actual_output",
                    "yield_variance_pct", "yield_flagged")
    inlines = [RunLineInline]
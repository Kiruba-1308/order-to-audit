from django.contrib import admin

from .models import Invoice, InvoiceLine, Order, OrderLine, Payment


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "customer", "salesman", "status")
    inlines = [OrderLineInline]


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in InvoiceLine._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "date", "customer", "total", "dispatched_on")
    inlines = [InvoiceLineInline]

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Payment)
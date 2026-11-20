from django.contrib import admin

from .models import BOM, BOMLine, Customer, Item, Supplier, Unit


class BOMLineInline(admin.TabularInline):
    model = BOMLine


@admin.register(BOM)
class BOMAdmin(admin.ModelAdmin):
    inlines = [BOMLineInline]


for m in (Unit, Item, Customer, Supplier):
    admin.site.register(m)
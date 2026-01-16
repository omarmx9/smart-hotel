from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Employee, ActivityLog


@admin.register(Employee)
class EmployeeAdmin(UserAdmin):
    list_display = ['username', 'employee_id', 'first_name', 'last_name', 'role', 'shift', 'is_active']
    list_filter = ['role', 'shift', 'is_active']
    search_fields = ['username', 'employee_id', 'first_name', 'last_name', 'email']
    ordering = ['last_name', 'first_name']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Employee Info', {
            'fields': ('employee_id', 'role', 'shift', 'phone_number', 'hire_date', 'created_by')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Employee Info', {
            'fields': ('employee_id', 'role', 'shift', 'phone_number', 'hire_date')
        }),
    )


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'employee', 'action', 'description', 'ip_address']
    list_filter = ['action', 'timestamp']
    search_fields = ['employee__username', 'description']
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']

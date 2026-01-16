from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.utils import timezone

from .models import Employee, ActivityLog
from .forms import (
    EmployeeLoginForm, EmployeeCreationForm, 
    EmployeeUpdateForm, PasswordChangeForm
)


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_activity(employee, action, description='', request=None, related_model='', related_id=None):
    """Create an activity log entry."""
    ip_address = get_client_ip(request) if request else None
    ActivityLog.objects.create(
        employee=employee,
        action=action,
        description=description,
        ip_address=ip_address,
        related_model=related_model,
        related_id=related_id
    )


def login_view(request):
    """Employee login page."""
    if request.user.is_authenticated:
        return redirect('reservations:dashboard')
    
    if request.method == 'POST':
        form = EmployeeLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            user.update_activity()
            log_activity(user, ActivityLog.ACTION_LOGIN, request=request)
            messages.success(request, f'Welcome back, {user.get_full_name()}!')
            return redirect('reservations:dashboard')
    else:
        form = EmployeeLoginForm()
    
    return render(request, 'employees/login.html', {'form': form})


@login_required
def logout_view(request):
    """Employee logout."""
    log_activity(request.user, ActivityLog.ACTION_LOGOUT, request=request)
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('employees:login')


@login_required
def profile_view(request):
    """View and edit own profile."""
    if request.method == 'POST':
        # Handle password change
        if 'change_password' in request.POST:
            form = PasswordChangeForm(request.POST, user=request.user)
            if form.is_valid():
                request.user.set_password(form.cleaned_data['new_password'])
                request.user.save()
                messages.success(request, 'Password changed successfully. Please log in again.')
                return redirect('employees:login')
        else:
            messages.error(request, 'Invalid form submission.')
    
    password_form = PasswordChangeForm(user=request.user)
    return render(request, 'employees/profile.html', {
        'password_form': password_form
    })


@login_required
def employee_list(request):
    """List all employees (admin only)."""
    if not request.user.can_manage_employees:
        messages.error(request, 'You do not have permission to manage employees.')
        return redirect('reservations:dashboard')
    
    employees = Employee.objects.all().order_by('last_name', 'first_name')
    
    # Filter by role
    role = request.GET.get('role')
    if role:
        employees = employees.filter(role=role)
    
    # Filter by status
    status = request.GET.get('status')
    if status == 'active':
        employees = employees.filter(is_active=True)
    elif status == 'inactive':
        employees = employees.filter(is_active=False)
    
    paginator = Paginator(employees, 20)
    page = request.GET.get('page', 1)
    employees = paginator.get_page(page)
    
    return render(request, 'employees/employee_list.html', {
        'employees': employees,
        'role_choices': Employee.ROLE_CHOICES
    })


@login_required
def employee_create(request):
    """Create new employee (admin only)."""
    if not request.user.can_manage_employees:
        messages.error(request, 'You do not have permission to create employees.')
        return redirect('reservations:dashboard')
    
    if request.method == 'POST':
        form = EmployeeCreationForm(request.POST, created_by=request.user)
        if form.is_valid():
            employee = form.save()
            log_activity(
                request.user,
                ActivityLog.ACTION_CREATE_EMPLOYEE,
                f'Created employee: {employee.get_full_name()}',
                request=request,
                related_model='Employee',
                related_id=employee.pk
            )
            messages.success(request, f'Employee {employee.get_full_name()} created successfully.')
            return redirect('employees:list')
    else:
        form = EmployeeCreationForm(created_by=request.user)
    
    return render(request, 'employees/employee_form.html', {
        'form': form,
        'title': 'Create New Employee'
    })


@login_required
def employee_edit(request, pk):
    """Edit employee details (admin only)."""
    if not request.user.can_manage_employees:
        messages.error(request, 'You do not have permission to edit employees.')
        return redirect('reservations:dashboard')
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        form = EmployeeUpdateForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            log_activity(
                request.user,
                ActivityLog.ACTION_UPDATE_EMPLOYEE,
                f'Updated employee: {employee.get_full_name()}',
                request=request,
                related_model='Employee',
                related_id=employee.pk
            )
            messages.success(request, f'Employee {employee.get_full_name()} updated successfully.')
            return redirect('employees:list')
    else:
        form = EmployeeUpdateForm(instance=employee)
    
    return render(request, 'employees/employee_form.html', {
        'form': form,
        'employee': employee,
        'title': f'Edit Employee: {employee.get_full_name()}'
    })


@login_required
def employee_reset_password(request, pk):
    """Reset employee password (admin only)."""
    if not request.user.can_manage_employees:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    employee = get_object_or_404(Employee, pk=pk)
    
    if request.method == 'POST':
        import secrets
        new_password = secrets.token_urlsafe(12)
        employee.set_password(new_password)
        employee.save()
        
        log_activity(
            request.user,
            ActivityLog.ACTION_UPDATE_EMPLOYEE,
            f'Reset password for: {employee.get_full_name()}',
            request=request,
            related_model='Employee',
            related_id=employee.pk
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Password reset for {employee.get_full_name()}',
            'temporary_password': new_password
        })
    
    return JsonResponse({'error': 'POST required'}, status=405)


@login_required
def activity_logs(request):
    """View activity logs (admin/manager only)."""
    if not request.user.can_access_reports:
        messages.error(request, 'You do not have permission to view activity logs.')
        return redirect('reservations:dashboard')
    
    logs = ActivityLog.objects.select_related('employee').all()
    
    # Filter by employee
    employee_id = request.GET.get('employee')
    if employee_id:
        logs = logs.filter(employee_id=employee_id)
    
    # Filter by action
    action = request.GET.get('action')
    if action:
        logs = logs.filter(action=action)
    
    # Filter by date
    date_from = request.GET.get('date_from')
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)
    
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs = paginator.get_page(page)
    
    employees = Employee.objects.all().order_by('last_name')
    
    return render(request, 'employees/activity_logs.html', {
        'logs': logs,
        'employees': employees,
        'action_choices': ActivityLog.ACTION_CHOICES
    })

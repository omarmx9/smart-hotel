from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('employees/', views.employee_list, name='list'),
    path('employees/create/', views.employee_create, name='create'),
    path('employees/<int:pk>/edit/', views.employee_edit, name='edit'),
    path('employees/<int:pk>/reset-password/', views.employee_reset_password, name='reset_password'),
    path('activity-logs/', views.activity_logs, name='activity_logs'),
]

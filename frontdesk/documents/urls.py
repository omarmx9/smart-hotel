from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.document_list, name='list'),
    path('<int:pk>/', views.document_detail, name='detail'),
    path('<int:pk>/download/', views.document_download, name='download'),
    path('<int:pk>/verify/', views.document_verify, name='verify'),
    path('guest/<int:guest_id>/', views.guest_documents, name='guest_documents'),
    path('guest/<int:guest_id>/upload/', views.document_upload, name='upload'),
    path('guest/<int:guest_id>/sync-kiosk/', views.sync_from_kiosk, name='sync_from_kiosk'),
    path('passports/today/', views.passports_today, name='passports_today'),
]

from django.urls import path
from . import views

app_name = 'kiosk'

urlpatterns = [
    # Main kiosk flow
    path('', views.advertisement, name='advertisement'),
    path('language/', views.choose_language, name='choose_language'),
    path('checkin/', views.checkin, name='checkin'),
    path('passport/', views.start, name='start'),
    path('passport/scan/', views.passport_scan, name='passport_scan'),  # New browser camera scan
    path('upload-scan/', views.upload_scan, name='upload_scan'),
    path('extract/status/<int:task_id>/', views.extract_status, name='extract_status'),
    path('verify/', views.verify_info, name='verify_info'),
    
    # DW Registration Card (DW R.C.) routes
    path('dw-registration/', views.dw_registration_card, name='dw_registration_card'),
    path('dw-registration/sign/', views.dw_sign_document, name='dw_sign_document'),
    path('dw-registration/print/', views.dw_generate_pdf, name='dw_generate_pdf'),
    
    # Legacy document routes (kept for compatibility)
    path('document/', views.documentation, name='documentation'),
    path('document/sign/', views.document_signing, name='document_signing'),
    
    # Reservation and access
    path('reservation/', views.reservation_entry, name='reservation_entry'),
    path('choose-access/<int:reservation_id>/', views.choose_access, name='choose_access'),
    path('enroll-face/<int:reservation_id>/', views.enroll_face, name='enroll_face'),
    path('face-capture/<int:reservation_id>/', views.face_capture, name='face_capture'),  # New browser camera face capture
    path('save-faces/<int:reservation_id>/', views.save_faces, name='save_faces'),  # Save captured faces
    path('final/<int:reservation_id>/', views.finalize, name='finalize'),
    path('submit-keycards/<int:reservation_id>/', views.submit_keycards, name='submit_keycards'),
    
    # API endpoints
    path('api/save-passport-data/', views.save_passport_extraction, name='save_passport_extraction'),
    
    # Guest Account API (Authentik integration)
    path('api/guest/create/', views.create_guest_account_api, name='create_guest_account'),
    path('api/guest/deactivate/', views.deactivate_guest_account_api, name='deactivate_guest_account'),
    
    # MRZ Backend API proxy endpoints (browser camera sends images to these)
    path('api/mrz/detect/', views.mrz_detect, name='mrz_detect'),
    path('api/mrz/extract/', views.mrz_extract, name='mrz_extract'),
    path('api/mrz/health/', views.mrz_service_health, name='mrz_service_health'),
]

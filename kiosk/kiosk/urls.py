from django.urls import path
from . import views

app_name = 'kiosk'

urlpatterns = [
    # Error page (Call Front Desk)
    path('error/', views.error_page, name='error'),
    
    # Main kiosk flow
    path('', views.advertisement, name='advertisement'),
    path('language/', views.choose_language, name='choose_language'),
    path('checkin/', views.checkin, name='checkin'),
    path('passport/', views.start, name='start'),
    path('passport/scan/', views.passport_scan, name='passport_scan'),  # New browser camera scan
    path('upload-scan/', views.upload_scan, name='upload_scan'),
    path('extract/status/<int:task_id>/', views.extract_status, name='extract_status'),
    path('verify/', views.verify_info, name='verify_info'),
    
    # Document Signing (unified PDF flow)
    path('document/sign/', views.pdf_sign_document, name='pdf_sign_document'),  # Main signing route
    path('document/preview-pdf/', views.serve_preview_pdf, name='serve_preview_pdf'),  # Serve preview PDF
    path('document/print/', views.dw_generate_pdf, name='dw_generate_pdf'),  # Print PDF
    
    # Access Method Selection (separate page)
    path('select-access-method/', views.select_access_method, name='select_access_method'),
    
    # Legacy routes (redirect to new flow for backwards compatibility)
    path('dw-registration/', views.redirect_to_pdf_sign, name='dw_registration_card'),
    path('dw-registration/sign/', views.redirect_to_pdf_sign, name='dw_sign_document'),
    path('dw-registration/pdf-sign/', views.redirect_to_pdf_sign, name='dw_pdf_sign'),
    path('document/', views.redirect_to_pdf_sign, name='documentation'),
    path('document/signing/', views.redirect_to_pdf_sign, name='document_signing'),
    
    # Walk-in and Reservation
    path('walkin/', views.walkin, name='walkin'),
    path('reservation/', views.reservation_entry, name='reservation_entry'),
    path('choose-access/<int:reservation_id>/', views.choose_access, name='choose_access'),
    path('enroll-face/<int:reservation_id>/', views.enroll_face, name='enroll_face'),
    path('face-capture/<int:reservation_id>/', views.face_capture, name='face_capture'),  # New browser camera face capture
    path('save-faces/<int:reservation_id>/', views.save_faces, name='save_faces'),  # Save captured faces
    path('final/<int:reservation_id>/', views.finalize, name='finalize'),
    path('submit-keycards/<int:reservation_id>/', views.submit_keycards, name='submit_keycards'),
    path('report-card/<int:reservation_id>/', views.report_stolen_card, name='report_stolen_card'),  # Report stolen/lost card
    
    # API endpoints
    path('api/save-passport-data/', views.save_passport_extraction, name='save_passport_extraction'),
    
    # Document Management API (kiosk handles signatures and storage)
    path('api/document/update/', views.document_update_api, name='document_update_api'),
    path('api/document/preview/', views.document_preview_api, name='document_preview_api'),
    path('api/document/sign/', views.document_sign_api, name='document_sign_api'),
    path('api/document/submit-physical/', views.document_submit_physical_api, name='document_submit_physical_api'),
    path('api/document/list/', views.list_signed_documents_api, name='list_signed_documents_api'),
    path('api/document/<str:document_id>/', views.get_signed_document_api, name='get_signed_document_api'),
    
    # Passport Image Storage API
    path('api/passport/list/', views.list_passport_images_api, name='list_passport_images_api'),
    path('api/passport/<str:passport_image_id>/', views.get_passport_image_api, name='get_passport_image_api'),
    
    # Guest Account API (Dashboard integration)
    path('api/guest/create/', views.create_guest_account_api, name='create_guest_account'),
    path('api/guest/deactivate/', views.deactivate_guest_account_api, name='deactivate_guest_account'),
    
    # RFID Card Management API
    path('api/rfid/revoke/', views.revoke_rfid_card_api, name='revoke_rfid_card'),
    
    # MRZ Backend API proxy endpoints (browser camera sends images to these)
    path('api/mrz/detect/', views.mrz_detect, name='mrz_detect'),
    path('api/mrz/extract/', views.mrz_extract, name='mrz_extract'),
    path('api/mrz/health/', views.mrz_service_health, name='mrz_service_health'),
]

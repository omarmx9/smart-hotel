def kiosk_language(request):
    return {'kiosk_language': request.session.get('language', 'en')}

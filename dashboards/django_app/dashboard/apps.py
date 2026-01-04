from django.apps import AppConfig
import os


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'
    
    def ready(self):
        # Only start in main process (not in migration commands)
        if os.environ.get('RUN_MAIN') == 'true' or os.environ.get('DAPHNE_PROCESS'):
            from . import influx_client
            from . import mqtt_client
            influx_client.start_influx_client()
            mqtt_client.start_mqtt_client()

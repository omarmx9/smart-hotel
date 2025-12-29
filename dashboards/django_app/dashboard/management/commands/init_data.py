from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from rooms.models import Room

User = get_user_model()


class Command(BaseCommand):
    help = 'Initialize the database with sample rooms and admin users'

    def handle(self, *args, **options):
        self.stdout.write('Creating initial data...')
        
        # Create rooms
        rooms_data = [
            {'room_number': '101', 'floor': 1},
            {'room_number': '102', 'floor': 1},
            {'room_number': '103', 'floor': 1},
            {'room_number': '104', 'floor': 1},
            {'room_number': '201', 'floor': 2},
            {'room_number': '202', 'floor': 2},
            {'room_number': '203', 'floor': 2},
            {'room_number': '204', 'floor': 2},
        ]
        
        for room_data in rooms_data:
            room, created = Room.objects.get_or_create(
                room_number=room_data['room_number'],
                defaults={
                    'floor': room_data['floor'],
                    'temperature': 22.0,
                    'humidity': 50.0,
                    'luminosity': 300,
                    'gas_level': 150,
                }
            )
            if created:
                self.stdout.write(f'  Created room {room.room_number}')
            else:
                self.stdout.write(f'  Room {room.room_number} already exists')
        
        # Create admin user
        if not User.objects.filter(username='admin').exists():
            admin = User.objects.create_superuser(
                username='admin',
                email='admin@smarthotel.local',
                password='admin123',
                role=User.ROLE_ADMIN
            )
            self.stdout.write(self.style.SUCCESS(f'Created admin user: admin / admin123'))
        else:
            self.stdout.write('Admin user already exists')
        
        # Create monitor user
        if not User.objects.filter(username='monitor').exists():
            monitor = User.objects.create_user(
                username='monitor',
                email='monitor@smarthotel.local',
                password='monitor123',
                role=User.ROLE_MONITOR
            )
            self.stdout.write(self.style.SUCCESS(f'Created monitor user: monitor / monitor123'))
        else:
            self.stdout.write('Monitor user already exists')
        
        self.stdout.write(self.style.SUCCESS('Initial data created successfully!'))
        self.stdout.write('')
        self.stdout.write('Default credentials:')
        self.stdout.write('  Admin:   admin / admin123')
        self.stdout.write('  Monitor: monitor / monitor123')

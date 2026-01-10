"""
Management command to create sample rooms for testing.
"""
from django.core.management.base import BaseCommand
from reservations.models import Room


class Command(BaseCommand):
    help = 'Create sample rooms for testing'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--floors',
            type=int,
            default=3,
            help='Number of floors (default: 3)'
        )
        parser.add_argument(
            '--rooms-per-floor',
            type=int,
            default=10,
            help='Rooms per floor (default: 10)'
        )
    
    def handle(self, *args, **options):
        floors = options['floors']
        rooms_per_floor = options['rooms_per_floor']
        
        created_count = 0
        
        room_types = [
            (Room.ROOM_TYPE_SINGLE, 80.00, 1),
            (Room.ROOM_TYPE_DOUBLE, 120.00, 2),
            (Room.ROOM_TYPE_SUITE, 200.00, 4),
            (Room.ROOM_TYPE_DELUXE, 350.00, 4),
        ]
        
        for floor in range(1, floors + 1):
            for room_num in range(1, rooms_per_floor + 1):
                room_number = f"{floor}{room_num:02d}"
                
                # Determine room type based on position
                if room_num <= 2:
                    room_type, base_rate, max_guests = room_types[3]  # Deluxe
                elif room_num <= 4:
                    room_type, base_rate, max_guests = room_types[2]  # Suite
                elif room_num <= 7:
                    room_type, base_rate, max_guests = room_types[1]  # Double
                else:
                    room_type, base_rate, max_guests = room_types[0]  # Single
                
                # Check if room exists
                if Room.objects.filter(room_number=room_number).exists():
                    continue
                
                Room.objects.create(
                    room_number=room_number,
                    floor=floor,
                    room_type=room_type,
                    status=Room.STATUS_AVAILABLE,
                    max_guests=max_guests,
                    base_rate=base_rate,
                    has_balcony=(room_num <= 4),
                    has_sea_view=(floor >= 2 and room_num <= 5),
                    has_kitchen=(room_type in [Room.ROOM_TYPE_SUITE, Room.ROOM_TYPE_DELUXE])
                )
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} rooms across {floors} floors.')
        )

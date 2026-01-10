"""
Sync rooms between frontdesk and dashboard databases.
Creates rooms in dashboard that exist in frontdesk.
"""
import os
import psycopg2
from django.core.management.base import BaseCommand
from django.utils import timezone
from reservations.models import Room


class Command(BaseCommand):
    help = 'Sync rooms from frontdesk to dashboard database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Dashboard database connection details
        dashboard_db = {
            'host': os.environ.get('DASHBOARD_DB_HOST', 'postgres'),
            'port': os.environ.get('DASHBOARD_DB_PORT', '5432'),
            'dbname': os.environ.get('DASHBOARD_DB', 'smarthotel'),
            'user': os.environ.get('DASHBOARD_DB_USER', 'smarthotel'),
            'password': os.environ.get('DASHBOARD_DB_PASSWORD', ''),
        }
        
        # Get all frontdesk rooms
        frontdesk_rooms = Room.objects.all()
        self.stdout.write(f"Found {frontdesk_rooms.count()} rooms in frontdesk")
        
        if not dashboard_db['password']:
            self.stderr.write(self.style.ERROR(
                'DASHBOARD_DB_PASSWORD not set. Cannot connect to dashboard database.'
            ))
            return
        
        try:
            conn = psycopg2.connect(**dashboard_db)
            cursor = conn.cursor()
            
            # Get existing rooms in dashboard
            cursor.execute("SELECT room_number FROM rooms_room")
            dashboard_rooms = {row[0] for row in cursor.fetchall()}
            self.stdout.write(f"Found {len(dashboard_rooms)} rooms in dashboard")
            
            created = 0
            updated = 0
            
            for room in frontdesk_rooms:
                # Map frontdesk status to dashboard status
                status_map = {
                    'available': 'vacant',
                    'occupied': 'occupied',
                    'maintenance': 'maintenance',
                    'cleaning': 'vacant',
                }
                dashboard_status = status_map.get(room.status, 'vacant')
                
                if room.room_number in dashboard_rooms:
                    # Update existing room
                    if not dry_run:
                        cursor.execute("""
                            UPDATE rooms_room 
                            SET floor = %s, status = %s, last_update = %s
                            WHERE room_number = %s
                        """, (room.floor, dashboard_status, timezone.now(), room.room_number))
                    updated += 1
                    self.stdout.write(f"  Updated: Room {room.room_number}")
                else:
                    # Create new room
                    if not dry_run:
                        cursor.execute("""
                            INSERT INTO rooms_room (
                                room_number, floor, status, 
                                temperature, humidity, luminosity, ldr_percentage, gas_level,
                                led1_status, led2_status,
                                climate_mode, target_temperature, fan_speed, heating_status,
                                light_mode, door_open,
                                mqtt_topic_prefix, created_at, last_update
                            ) VALUES (
                                %s, %s, %s,
                                22.0, 50.0, 0, 0, 0,
                                false, false,
                                'auto', 22.0, 'medium', false,
                                'auto', false,
                                %s, %s, %s
                            )
                        """, (
                            room.room_number, room.floor, dashboard_status,
                            f"/hotel/{room.room_number}",
                            timezone.now(), timezone.now()
                        ))
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"  Created: Room {room.room_number}"))
            
            if not dry_run:
                conn.commit()
            
            cursor.close()
            conn.close()
            
            prefix = "[DRY RUN] " if dry_run else ""
            self.stdout.write(self.style.SUCCESS(
                f"\n{prefix}Sync complete: {created} created, {updated} updated"
            ))
            
        except psycopg2.Error as e:
            self.stderr.write(self.style.ERROR(f"Database error: {e}"))

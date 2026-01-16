"""
Management command to create a default admin user for front desk.
"""
import os
from django.core.management.base import BaseCommand
from employees.models import Employee


class Command(BaseCommand):
    help = 'Create a default admin user if none exists'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default=os.environ.get('FRONTDESK_ADMIN_USER', 'admin'),
            help='Admin username (default: admin or FRONTDESK_ADMIN_USER env var)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=os.environ.get('FRONTDESK_ADMIN_PASSWORD', 'admin123'),
            help='Admin password (default: admin123 or FRONTDESK_ADMIN_PASSWORD env var)'
        )
        parser.add_argument(
            '--email',
            type=str,
            default=os.environ.get('FRONTDESK_ADMIN_EMAIL', 'admin@hotel.local'),
            help='Admin email (default: admin@hotel.local or FRONTDESK_ADMIN_EMAIL env var)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force creation even if admin already exists'
        )
    
    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']
        force = options['force']
        
        # Check if any admin exists
        admins_exist = Employee.objects.filter(role=Employee.ROLE_ADMIN).exists()
        
        if admins_exist and not force:
            self.stdout.write(
                self.style.WARNING('An admin user already exists. Use --force to create another.')
            )
            return
        
        # Check if username already exists
        if Employee.objects.filter(username=username).exists():
            if force:
                # Update existing user to admin
                user = Employee.objects.get(username=username)
                user.role = Employee.ROLE_ADMIN
                user.is_staff = True
                user.is_superuser = True
                user.set_password(password)
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Updated existing user "{username}" to admin role.')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'User "{username}" already exists. Use --force to update.')
                )
            return
        
        # Create admin user
        admin = Employee.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name='Admin',
            last_name='User',
            role=Employee.ROLE_ADMIN,
            is_staff=True,
            is_superuser=True
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created admin user: {username}')
        )
        self.stdout.write(
            self.style.WARNING(f'Default password is "{password}" - please change it immediately!')
        )

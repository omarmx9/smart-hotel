# Smart Hotel Dashboard - Django Application

A professional hotel management dashboard with role-based access control, real-time sensor monitoring, and temporary guest account generation.

## Features

- **Role-Based Access Control**
  - **Admin**: Full access to all rooms, can control temperature, manage guest accounts
  - **Monitor**: View-only access to all rooms, cannot control settings
  - **Guest**: Access to assigned room only, can control their room's temperature

- **Real-time Monitoring**
  - Temperature, humidity, luminosity, and gas level sensors
  - WebSocket-based live updates
  - Historical data charts

- **Guest Account Management**
  - Generate temporary guest accounts via WebSocket
  - Auto-expire after configurable duration
  - Credentials sent via Telegram (SMS placeholder)

## Quick Start

### 1. Install Dependencies

```bash
cd dashboards/django_app
pip install -r requirements.txt
```

### 2. Initialize Database

```bash
python manage.py migrate
python manage.py init_data
```

### 3. Run the Server

```bash
python manage.py runserver
# or with Daphne for WebSocket support:
daphne -b 0.0.0.0 -p 8000 smart_hotel.asgi:application
```

### 4. Access the Dashboard

- URL: http://localhost:8000
- Admin: `admin` / `admin123`
- Monitor: `monitor` / `monitor123`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | dev key (change in production) |
| `DJANGO_DEBUG` | Debug mode | True |
| `MQTT_BROKER` | MQTT broker hostname | mqtt.saddevastator.qzz.io |
| `MQTT_PORT` | MQTT broker port | 1883 |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | (empty) |
| `TELEGRAM_CHAT_ID` | Telegram chat ID | (empty) |

### Telegram Setup (Optional)

1. Create a Telegram bot via @BotFather
2. Get your chat ID
3. Set environment variables:
   ```bash
   export TELEGRAM_BOT_TOKEN="your-bot-token"
   export TELEGRAM_CHAT_ID="your-chat-id"
   ```

## MQTT Topics

The dashboard subscribes to the following MQTT topics:

```
hotel/room/{room_number}/temperature
hotel/room/{room_number}/humidity
hotel/room/{room_number}/luminosity
hotel/room/{room_number}/gas
hotel/room/{room_number}/heating
```

Control topics:
```
hotel/room/{room_number}/control  # Target temperature
hotel/room/{room_number}/target   # Target temperature (duplicate)
```

## API Endpoints

| Endpoint | Method | Description | Access |
|----------|--------|-------------|--------|
| `/api/rooms/` | GET | List accessible rooms | Authenticated |
| `/api/room/<id>/` | GET | Room details with history | Room access |
| `/api/room/<id>/set_target/` | POST | Set target temperature | Can control |
| `/api/room/<id>/history/` | GET | Sensor history | Room access |
| `/api/generate-guest/` | POST | Generate guest account | Admin only |

## WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ws/dashboard/` | Dashboard-wide updates |
| `/ws/room/<id>/` | Single room updates |
| `/ws/admin/` | Admin operations (guest generation) |

## Project Structure

```
django_app/
├── manage.py
├── requirements.txt
├── smart_hotel/          # Project settings
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── accounts/             # User authentication
│   ├── models.py         # Custom User model with roles
│   ├── views.py          # Login/logout views
│   └── admin.py
├── rooms/                # Room management
│   ├── models.py         # Room and SensorHistory models
│   └── admin.py
├── dashboard/            # Main dashboard app
│   ├── views.py          # Dashboard views and APIs
│   ├── consumers.py      # WebSocket consumers
│   ├── mqtt_client.py    # MQTT integration
│   ├── telegram.py       # Telegram notifications
│   └── routing.py        # WebSocket routes
└── templates/            # HTML templates
    ├── base.html
    ├── accounts/
    │   └── login.html
    └── dashboard/
        ├── index.html
        ├── room_detail.html
        └── guest_management.html
```

## Security Notes

- Change the default admin password in production
- Set a proper `DJANGO_SECRET_KEY` in production
- Use HTTPS in production
- Consider rate limiting for API endpoints

## Password Management

### Changing Passwords (After Login)

Admin and Monitor users can change their passwords via:
1. Navigate to **Settings** (gear icon in sidebar)
2. Click **Change Password**
3. Enter current password and new password

### Manually Resetting Admin/Monitor Passwords

For security reasons, admin and monitor accounts **cannot** use the "Forgot Password" feature. To reset these passwords manually:

#### Using Django Shell (Recommended)

```bash
cd dashboards/django_app
python manage.py shell
```

```python
from accounts.models import User

# Reset admin password
admin = User.objects.get(username='admin')
admin.set_password('new_secure_password')
admin.save()

# Reset monitor password
monitor = User.objects.get(username='monitor')
monitor.set_password('new_secure_password')
monitor.save()

exit()
```

#### Using Django Management Command

```bash
python manage.py changepassword admin
# You will be prompted to enter a new password

python manage.py changepassword monitor
```

#### In Docker Container

```bash
# Access the running container
docker exec -it dashboard python manage.py shell

# Then use the Python commands above
# Or use changepassword command:
docker exec -it dashboard python manage.py changepassword admin
```

### Guest Password Reset

Guest accounts can use the "Forgot Password" link on the login page. A reset link will be sent via Telegram to the configured chat.

## Theme Support

The dashboard supports both dark and light themes:
- Users can switch themes via **Settings** page
- Theme preference is saved in browser localStorage
- Theme persists across sessions

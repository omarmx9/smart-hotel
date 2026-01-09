"""
Pytest configuration and fixtures for MRZ Backend tests.
"""
import pytest
import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture
def app():
    """Create Flask test application."""
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def sample_base64_image():
    """Sample base64 encoded image (1x1 white pixel PNG)."""
    # Minimal valid PNG (1x1 white pixel)
    return (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


@pytest.fixture
def sample_mrz_td3():
    """Sample TD3 MRZ (passport)."""
    return [
        "P<USASMITH<<JOHN<JAMES<<<<<<<<<<<<<<<<<<<<<<",
        "AB12345678USA8501011M3001012<<<<<<<<<<<<<<06"
    ]

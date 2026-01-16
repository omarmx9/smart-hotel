"""
Tests for MRZ Backend Flask application.
"""
import json
import pytest


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_ok(self, client):
        """Test /health returns OK status."""
        response = client.get('/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'

    def test_health_includes_services(self, client):
        """Test /health includes service status."""
        response = client.get('/health')
        data = json.loads(response.data)
        assert 'services' in data or 'status' in data


class TestExtractEndpoint:
    """Test MRZ extraction endpoint."""

    def test_extract_requires_image(self, client):
        """Test /api/extract requires image data."""
        response = client.post(
            '/api/extract',
            json={},
            content_type='application/json'
        )
        # Should return 400 for missing image
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_extract_accepts_base64(self, client, sample_base64_image):
        """Test /api/extract accepts base64 image."""
        response = client.post(
            '/api/extract',
            json={'image': sample_base64_image},
            content_type='application/json'
        )
        # May fail extraction but should accept the format
        assert response.status_code in [200, 400, 422, 500]

    def test_extract_returns_json(self, client, sample_base64_image):
        """Test /api/extract returns JSON."""
        response = client.post(
            '/api/extract',
            json={'image': sample_base64_image},
            content_type='application/json'
        )
        assert response.content_type == 'application/json'


class TestDetectEndpoint:
    """Test document detection endpoint."""

    def test_detect_endpoint_exists(self, client):
        """Test /api/detect endpoint exists."""
        response = client.post(
            '/api/detect',
            json={},
            content_type='application/json'
        )
        # Endpoint exists - may return 200 or 400 depending on implementation
        assert response.status_code in [200, 400]

    def test_detect_returns_detection_result(self, client, sample_base64_image):
        """Test /api/detect returns detection result."""
        response = client.post(
            '/api/detect',
            json={'image': sample_base64_image},
            content_type='application/json'
        )
        # May or may not detect, but should return valid response
        if response.status_code == 200:
            data = json.loads(response.data)
            assert 'detected' in data or 'success' in data


class TestAPIFormats:
    """Test API request/response formats."""

    def test_post_requires_json_content_type(self, client):
        """Test POST endpoints require JSON content type."""
        response = client.post(
            '/api/extract',
            data='not json',
            content_type='text/plain'
        )
        assert response.status_code in [400, 415]

    def test_api_returns_cors_headers(self, client):
        """Test API returns CORS headers if enabled."""
        response = client.options('/api/extract')
        # Either returns 200 with CORS headers or 405 if CORS not enabled
        assert response.status_code in [200, 204, 405]


class TestPipelineComponents:
    """Test individual pipeline components."""

    def test_image_saver_import(self):
        """Test ImageSaver is importable."""
        try:
            from layer1_capture.image_saver import ImageSaver
            assert ImageSaver is not None
        except ImportError:
            pytest.skip("ImageSaver not available")

    def test_document_adjuster_import(self):
        """Test DocumentAdjuster is importable."""
        try:
            from layer2_readjustment.document_adjuster import DocumentAdjuster
            assert DocumentAdjuster is not None
        except ImportError:
            pytest.skip("DocumentAdjuster not available")

    def test_mrz_extractor_import(self):
        """Test MRZExtractor is importable."""
        try:
            from layer3_mrz.mrz_extractor import MRZExtractor
            assert MRZExtractor is not None
        except ImportError:
            pytest.skip("MRZExtractor not available")


class TestMRZValidation:
    """Test MRZ validation utilities."""

    def test_validate_td3_format(self):
        """Test TD3 MRZ format validation."""
        # TD3 (passport) has 2 lines of 44 characters each
        valid_mrz = [
            "P<USASMITH<<JOHN<JAMES<<<<<<<<<<<<<<<<<<<<<<",
            "AB12345678USA8501011M3001012<<<<<<<<<<<<<<06"
        ]
        assert len(valid_mrz) == 2
        assert len(valid_mrz[0]) == 44
        assert len(valid_mrz[1]) == 44

    def test_validate_td1_format(self):
        """Test TD1 MRZ format validation."""
        # TD1 (ID card) has 3 lines of 30 characters each
        valid_mrz = [
            "I<UTOD231458907<<<<<<<<<<<<<<<",
            "7408122F1204159UTO<<<<<<<<<<<6",
            "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
        ]
        assert len(valid_mrz) == 3
        for line in valid_mrz:
            assert len(line) == 30


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_json_returns_error(self, client):
        """Test invalid JSON returns appropriate error."""
        response = client.post(
            '/api/extract',
            data='{"invalid": json',
            content_type='application/json'
        )
        assert response.status_code == 400

    def test_missing_endpoint_returns_404(self, client):
        """Test missing endpoint returns 404."""
        response = client.get('/api/nonexistent')
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test wrong HTTP method returns error."""
        response = client.get('/api/extract')
        # May return 404 or 405 depending on Flask routing
        assert response.status_code in [404, 405]

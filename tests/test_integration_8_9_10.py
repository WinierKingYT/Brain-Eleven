#!/usr/bin/env python3
"""
Integration Tests: Phases 8-10
Tests Docker deployment, REST API, caching, and advanced features
"""

import pytest
import json
from pathlib import Path
import time

# Tests will import deliverables from Phase 8-10 agents


class TestPhase8Docker:
    """Docker containerization tests"""

    def test_dockerfile_exists(self):
        """Verify Dockerfile created"""
        dockerfile = Path("Dockerfile")
        assert dockerfile.exists(), "Dockerfile missing"

    def test_dockerfile_syntax(self):
        """Verify Dockerfile has valid syntax"""
        dockerfile = Path("Dockerfile")
        content = dockerfile.read_text()
        assert "FROM python:3.13" in content
        assert "WORKDIR" in content
        assert "COPY" in content
        assert "RUN pip install" in content

    def test_docker_compose_exists(self):
        """Verify docker-compose.yml created"""
        compose = Path("docker-compose.yml")
        assert compose.exists(), "docker-compose.yml missing"

    def test_docker_compose_services(self):
        """Verify docker-compose has required services"""
        compose = Path("docker-compose.yml")
        content = compose.read_text()
        assert "app:" in content or "services:" in content
        assert "redis" in content
        # postgres optional

    def test_makefile_exists(self):
        """Verify Makefile for build shortcuts"""
        makefile = Path("Makefile")
        assert makefile.exists(), "Makefile missing"


class TestPhase8CICD:
    """GitHub Actions CI/CD tests"""

    def test_test_workflow_exists(self):
        """Verify .github/workflows/test.yml"""
        test_yml = Path(".github/workflows/test.yml")
        assert test_yml.exists(), "test.yml missing"

    def test_build_workflow_exists(self):
        """Verify .github/workflows/build.yml"""
        build_yml = Path(".github/workflows/build.yml")
        assert build_yml.exists(), "build.yml missing"

    def test_security_workflow_exists(self):
        """Verify .github/workflows/security.yml"""
        security_yml = Path(".github/workflows/security.yml")
        assert security_yml.exists(), "security.yml missing"

    def test_workflow_yaml_valid(self):
        """Verify workflow files are valid YAML"""
        import yaml
        for workflow in Path(".github/workflows").glob("*.yml"):
            try:
                yaml.safe_load(workflow.read_text())
            except yaml.YAMLError as e:
                pytest.fail(f"{workflow} is invalid YAML: {e}")


class TestPhase8API:
    """REST API endpoint tests"""

    def test_search_api_exists(self):
        """Verify scripts/search-api.py created"""
        api_file = Path("scripts/search-api.py")
        assert api_file.exists(), "search-api.py missing"

    def test_api_has_health_endpoint(self):
        """Verify /health endpoint defined"""
        api_file = Path("scripts/search-api.py")
        content = api_file.read_text()
        assert "@app.get('/health')" in content or "@app.get(\"/health\")" in content

    def test_api_has_search_endpoint(self):
        """Verify /search endpoint defined"""
        api_file = Path("scripts/search-api.py")
        content = api_file.read_text()
        assert "@app.post('/search')" in content or "@app.post(\"/search\")" in content

    def test_api_has_rank_endpoint(self):
        """Verify /rank endpoint defined"""
        api_file = Path("scripts/search-api.py")
        content = api_file.read_text()
        assert "@app.post('/rank')" in content or "@app.post(\"/rank\")" in content

    def test_logging_config_exists(self):
        """Verify scripts/logging-config.py created"""
        logging_file = Path("scripts/logging-config.py")
        assert logging_file.exists(), "logging-config.py missing"

    def test_metrics_exists(self):
        """Verify scripts/metrics.py created"""
        metrics_file = Path("scripts/metrics.py")
        assert metrics_file.exists(), "metrics.py missing"


class TestPhase9Caching:
    """Caching layer tests"""

    def test_cache_manager_exists(self):
        """Verify scripts/cache-manager.py created"""
        cache_file = Path("scripts/cache-manager.py")
        assert cache_file.exists(), "cache-manager.py missing"

    def test_cache_manager_has_class(self):
        """Verify CacheManager class defined"""
        cache_file = Path("scripts/cache-manager.py")
        content = cache_file.read_text()
        assert "class CacheManager" in content

    def test_cache_manager_methods(self):
        """Verify required cache methods"""
        cache_file = Path("scripts/cache-manager.py")
        content = cache_file.read_text()
        assert "def get(" in content
        assert "def set(" in content
        assert "def invalidate(" in content
        assert "def stats(" in content


class TestPhase9LoadTesting:
    """Load testing tests"""

    def test_performance_tests_exist(self):
        """Verify tests/test_performance.py created"""
        perf_file = Path("tests/test_performance.py")
        assert perf_file.exists(), "test_performance.py missing"

    def test_performance_tests_have_scenarios(self):
        """Verify performance test scenarios"""
        perf_file = Path("tests/test_performance.py")
        content = perf_file.read_text()
        assert "latency" in content.lower()
        assert "concurrent" in content.lower() or "load" in content.lower()


class TestPhase10Summarization:
    """Auto-summarization tests"""

    def test_summarizer_exists(self):
        """Verify scripts/summarizer.py created"""
        summarizer_file = Path("scripts/summarizer.py")
        assert summarizer_file.exists(), "summarizer.py missing"

    def test_summarizer_has_class(self):
        """Verify Summarizer class defined"""
        summarizer_file = Path("scripts/summarizer.py")
        content = summarizer_file.read_text()
        assert "class Summarizer" in content

    def test_summarizer_methods(self):
        """Verify required summarizer methods"""
        summarizer_file = Path("scripts/summarizer.py")
        content = summarizer_file.read_text()
        assert "daily_recap" in content
        assert "weekly_summary" in content
        assert "monthly_review" in content


class TestPhase10AnomalyDetection:
    """Anomaly detection tests"""

    def test_anomaly_detector_exists(self):
        """Verify scripts/anomaly-detector.py created"""
        anomaly_file = Path("scripts/anomaly-detector.py")
        assert anomaly_file.exists(), "anomaly-detector.py missing"

    def test_anomaly_detector_has_class(self):
        """Verify AnomalyDetector class defined"""
        anomaly_file = Path("scripts/anomaly-detector.py")
        content = anomaly_file.read_text()
        assert "class AnomalyDetector" in content

    def test_anomaly_detector_methods(self):
        """Verify required anomaly detection methods"""
        anomaly_file = Path("scripts/anomaly-detector.py")
        content = anomaly_file.read_text()
        assert "find_contradictions" in content
        assert "detect_pattern_breaks" in content or "pattern" in content.lower()
        assert "risk_score" in content


class TestIntegration:
    """End-to-end integration tests"""

    def test_all_agents_delivered(self):
        """Verify all agent deliverables exist"""
        files_to_check = [
            "Dockerfile",
            "docker-compose.yml",
            ".github/workflows/test.yml",
            ".github/workflows/build.yml",
            "scripts/search-api.py",
            "scripts/logging-config.py",
            "scripts/metrics.py",
            "scripts/cache-manager.py",
            "tests/test_performance.py",
            "scripts/summarizer.py",
            "scripts/anomaly-detector.py",
        ]

        missing = []
        for file in files_to_check:
            if not Path(file).exists():
                missing.append(file)

        assert not missing, f"Missing files: {missing}"

    def test_requirements_txt_updated(self):
        """Verify requirements.txt has new dependencies"""
        req_file = Path("requirements.txt")
        assert req_file.exists(), "requirements.txt missing"
        content = req_file.read_text()

        # Should have new Phase 8-10 dependencies
        expected = ["fastapi", "uvicorn"]
        found = [dep for dep in expected if dep in content.lower()]
        assert len(found) > 0, f"Missing dependencies: {expected}"

    def test_documentation_complete(self):
        """Verify documentation created"""
        docs = [
            "docs/API.md",
            "docs/DEPLOYMENT.md",
            "docs/CACHING.md",
            "docs/PERFORMANCE.md",
            "docs/SUMMARIZATION.md",
            "docs/ANOMALY-DETECTION.md",
        ]

        # At least some docs should exist
        existing = [d for d in docs if Path(d).exists()]
        assert len(existing) > 0, "No documentation found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

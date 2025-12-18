import os
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--ocr",
        action="store",
        default="env",
        choices=["on", "off", "env"],
        help="Control OCR usage globally: on, off, or inherit USE_OCR env (default)",
    )


def pytest_configure(config):
    # Register marker to avoid warnings on strict column tests
    config.addinivalue_line("markers", "columns: tests that must not accept OCR extras")


@pytest.fixture(autouse=True)
def _set_ocr_env(request):
    """
    Set OCR usage per test based on CLI flag.

    - on   -> USE_OCR=1
    - off  -> USE_OCR=0
    - env  -> inherit environment
    """
    mode = request.config.getoption("--ocr")

    if mode == "on":
        os.environ["USE_OCR"] = "1"
    elif mode == "off":
        os.environ["USE_OCR"] = "0"

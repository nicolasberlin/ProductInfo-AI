import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.evaluation import normalization
from agent.evaluation.normalization import normalize_pat


Inputs = [
    {"number_raw": "CN 107,076,464", "country": "CN", "kind": "utility", "confidence": 1.0, "normalized_number": "CN107076464"},
    {"number_raw": "US 10,277,158", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US10277158"},
    {"number_raw": "US 9,473,066", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US9473066"},
    {"number_raw": "JP 6,622,213", "country": "JP", "kind": "utility", "confidence": 1.0, "normalized_number": "JP6622213"},
    {"number_raw": "US 9,252,310", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US9252310"},
    {"number_raw": "US 9,810,452", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US9810452"},
    {"number_raw": "US 10,024,580", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US10024580"},
    {"number_raw": "JP 6,668,248", "country": "JP", "kind": "utility", "confidence": 1.0, "normalized_number": "JP6668248"},
    {"number_raw": "US D823,786", "country": "US", "kind": "design", "confidence": 1.0, "normalized_number": "USD823786"},
    {"number_raw": "US 10,845,093", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US10845093"},
    {"number_raw": "US 10,601,362", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US10601362"},
    {"number_raw": "US D846,162", "country": "US", "kind": "design", "confidence": 1.0, "normalized_number": "USD846162"},
    {"number_raw": "US D856,548 U", "country": "US", "kind": "design", "confidence": 0.6, "normalized_number": "USD856548"},
    {"number_raw": "US 10,998,847", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US10998847"},
    {"number_raw": "US 11,143,436", "country": "US", "kind": "utility", "confidence": 1.0, "normalized_number": "US11143436"},
    {"number_raw": "US 7,343,362", "normalized_number": "US7343362", "confidence": 0.95, "source": "audit"},
    {"number_raw": "8,128,044", "normalized_number": "US8128044", "confidence": 0.95, "source": "audit"},
]

Expected = [
    "CN107076464A",
    "US10277158B2",
    "US9473066B2", 
    "JP6622213B2"
]

@pytest.mark.parametrize("patent, expected", list(zip(Inputs[:4], Expected)))
def test_normalize_pat_returns_expected(patent, expected):
    result = normalize_pat(patent)
    print(f"Normalized '{patent['number_raw']}' -> '{result}', expected '{expected}'")
    assert result == expected





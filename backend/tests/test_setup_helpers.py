"""Unit tests for the Voice Studio setup/launch pure helpers."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools import envdetect  # noqa: E402

_SAMPLE_SMI = """
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 552.22       Driver Version: 552.22       CUDA Version: 12.4      |
|-------------------------------+----------------------+----------------------+
"""


def test_parse_cuda_version_found():
    assert envdetect.parse_nvidia_smi_cuda_version(_SAMPLE_SMI) == "12.4"


def test_parse_cuda_version_missing():
    assert envdetect.parse_nvidia_smi_cuda_version("no cuda here") is None


def test_cuda_version_to_tag():
    assert envdetect.cuda_version_to_tag("12.4") == "cu124"
    assert envdetect.cuda_version_to_tag("12.6") == "cu124"
    assert envdetect.cuda_version_to_tag("12.1") == "cu121"
    assert envdetect.cuda_version_to_tag("12.0") == "cu121"
    assert envdetect.cuda_version_to_tag("11.8") == "cu118"
    assert envdetect.cuda_version_to_tag("10.2") is None
    assert envdetect.cuda_version_to_tag(None) is None


def test_torch_index_url():
    assert envdetect.torch_index_url("cu124") == "https://download.pytorch.org/whl/cu124"
    assert envdetect.torch_index_url("cu118") == "https://download.pytorch.org/whl/cu118"
    assert envdetect.torch_index_url(None) is None
    assert envdetect.torch_index_url("cpu") is None
    assert envdetect.torch_index_url("mps") is None


def test_detect_cuda_tag_with_injected_runner():
    assert envdetect.detect_cuda_tag(runner=lambda: _SAMPLE_SMI) == "cu124"
    assert envdetect.detect_cuda_tag(runner=lambda: None) is None

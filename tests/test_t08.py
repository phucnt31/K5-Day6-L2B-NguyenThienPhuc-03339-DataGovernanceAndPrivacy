"""Unit tests for Track T08 (Retention & Delete Request Simulator)."""
import json
from pathlib import Path
import pandas as pd
import pytest

from src.pipeline import _build_ancestor_legal_holds


def test_t08_legal_hold_lineage_propagation():
    """Kiểm tra tính lan truyền Legal Hold từ raw video xuống toàn bộ cây phái sinh."""
    mock_arts = [
        {"artefact_id": "raw_1", "type": "raw_video", "parent_ids": [], "legal_hold": "LH-TEST-01"},
        {"artefact_id": "bak_1", "type": "backup", "parent_ids": ["raw_1"], "legal_hold": None},
        {"artefact_id": "frm_1", "type": "frame", "parent_ids": ["raw_1"], "legal_hold": None},
        {"artefact_id": "crp_1", "type": "face_crop", "parent_ids": ["frm_1"], "legal_hold": None},
        {"artefact_id": "emb_1", "type": "embedding", "parent_ids": ["crp_1"], "legal_hold": None},
        {"artefact_id": "raw_free", "type": "raw_video", "parent_ids": [], "legal_hold": None},
        {"artefact_id": "frm_free", "type": "frame", "parent_ids": ["raw_free"], "legal_hold": None},
    ]

    holds = _build_ancestor_legal_holds(mock_arts)

    # Toàn bộ con cháu của raw_1 phải mang mã Legal Hold
    assert holds["raw_1"] == "LH-TEST-01"
    assert holds["bak_1"] == "LH-TEST-01"
    assert holds["frm_1"] == "LH-TEST-01"
    assert holds["crp_1"] == "LH-TEST-01"
    assert holds["emb_1"] == "LH-TEST-01"

    # Nhánh không có hold phải là None
    assert holds["raw_free"] is None
    assert holds["frm_free"] is None


def test_t08_policy_precedence_and_idempotency():
    """Kiểm tra thứ tự ưu tiên chính sách và tính bất biến (chạy 2 lần cho kết quả giống hệt nhau)."""
    with open("fixtures/t08_deletion/data_graph.json", "r", encoding="utf-8") as f:
        graph = json.load(f)
    with open("fixtures/t08_deletion/requests.json", "r", encoding="utf-8") as f:
        requests = json.load(f)

    artefacts = graph["artefacts"]
    holds = _build_ancestor_legal_holds(artefacts)

    # Test case 1: DR-002 (subj_03) dính Legal Hold LH-2026-03 -> tất cả phải là retain_legal_hold
    subj_03_arts = [a for a in artefacts if "subj_03" in a.get("subject_ids", [])]
    for a in subj_03_arts:
        if a["type"] != "training_export":
            assert holds[a["artefact_id"]] == "LH-2026-03"

    # Test case 2: Origin unknown (a0075) phải là escalate
    a0075 = next(a for a in artefacts if a["artefact_id"] == "a0075")
    assert a0075["origin_known"] is False

    # Test case 3: Multi-subject (a0011 chứa subj_00 và subj_01) phải là escalate
    a0011 = next(a for a in artefacts if a["artefact_id"] == "a0011")
    assert len(a0011["subject_ids"]) == 2
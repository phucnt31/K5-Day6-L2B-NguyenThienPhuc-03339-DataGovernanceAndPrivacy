"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set
import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"Provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    requests_file = ctx.input_dir / "requests.json"
    graph_file = ctx.input_dir / "data_graph.json"
    if not requests_file.exists():
        raise FileNotFoundError(f"Missing requests.json in {ctx.input_dir}")
    if not graph_file.exists():
        raise FileNotFoundError(f"Missing data_graph.json in {ctx.input_dir}")
    with open(requests_file, "r", encoding="utf-8") as f:
        requests_data = json.load(f)
    with open(graph_file, "r", encoding="utf-8") as f:
        graph_data = json.load(f)
    return {
        "manifest": pd.read_csv(manifest) if manifest.exists() else None,
        "requests": requests_data,
        "artefacts": graph_data.get("artefacts", []),
    }


# ---------------------------------------------------------------- 02 process
def _build_ancestor_legal_holds(artefacts: List[Dict[str, Any]]) -> Dict[str, str | None]:
    """Truy vết ngược phả hệ (lineage) từ con lên cha để lan truyền Legal Hold.
    
    Trong data_graph.json, chỉ có raw_video mang nhãn legal_hold; các node phái sinh
    (backup, frame, crop, embedding) có legal_hold = null. Hàm này đảm bảo mọi artefact
    con cháu đều kế thừa đúng mã Legal Hold từ tổ tiên của nó.
    """
    by_id = {a["artefact_id"]: a for a in artefacts}
    memo: Dict[str, str | None] = {}
    def get_hold(art_id: str, visited: Set[str]) -> str | None:
        if art_id in memo:
            return memo[art_id]
        if art_id in visited or art_id not in by_id:
            return None
        visited.add(art_id)
        art = by_id[art_id]
        # 1. Nếu bản thân node có legal hold
        if art.get("legal_hold"):
            memo[art_id] = art["legal_hold"]
            return art["legal_hold"]
        # 2. Ngược dòng kiểm tra tất cả parent_ids
        for pid in art.get("parent_ids", []):
            parent_hold = get_hold(pid, visited.copy())
            if parent_hold:
                memo[art_id] = parent_hold
                return parent_hold
        memo[art_id] = None
        return None
    for a in artefacts:
        aid = a["artefact_id"]
        if aid not in memo:
            get_hold(aid, set())
    return memo
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    """Áp dụng thứ tự ưu tiên 4 bậc: Legal Hold > Permission/Origin > Multi-Subject > Delete."""
    requests = data["requests"]
    artefacts = data["artefacts"]
    # 1. Xây dựng bản đồ kế thừa Legal Hold trên toàn bộ đồ thị
    ancestor_holds = _build_ancestor_legal_holds(artefacts)
    rows = []
    for req in requests:
        req_id = req["request_id"]
        subj_id = req["subject_id"]
        # Tìm toàn bộ artefact có liên quan tới subject_id này
        related_arts = [a for a in artefacts if subj_id in a.get("subject_ids", [])]
        for art in related_arts:
            art_id = art["artefact_id"]
            art_type = art.get("type", "unknown")
            subjs = art.get("subject_ids", [])
            acl = art.get("acl", [])
            origin_known = art.get("origin_known", True)
            hold_code = ancestor_holds.get(art_id)
            # THỨ TỰ ƯU TIÊN CHÍNH SÁCH (POLICY PRECEDENCE):
            # Bậc 1: Nghĩa vụ pháp lý (Legal Hold) -> Giữ lại nguyên trạng
            if hold_code is not None:
                action = "retain_legal_hold"
                score = 0.95
                reason = f"Legal hold active ({hold_code}) on lineage"
            # Bậc 2: Nguồn gốc không rõ ràng -> Chuyển duyệt
            elif not origin_known:
                action = "escalate"
                score = 0.90
                reason = "Unknown data origin (origin_known=False)"
            # Bậc 3: Thiếu quyền hạn (ACL) -> Chuyển duyệt
            elif "data-platform" not in acl:
                action = "escalate"
                score = 0.85
                reason = f"Insufficient platform permissions: ACL={acl}"
            # Bậc 4: Đa chủ thể (Multi-subject) -> Chuyển duyệt làm mờ/tách dữ liệu
            elif len(subjs) > 1:
                action = "escalate"
                score = 0.80
                reason = f"Multi-subject artefact ({len(subjs)} subjects: {subjs})"
            # Bậc 5: Đầy đủ điều kiện -> Xóa an toàn
            else:
                action = "delete"
                score = 0.10
                reason = f"Standard compliant deletion for {subj_id}"
            rows.append({
                "request_id": req_id,
                "artefact_id": art_id,
                "action": action,
                "score": score,
                "reason": reason,
                "type": art_type,
            })
            # Ghi vết kiểm toán (bắt buộc cho metric Audit trace completeness)
            ctx.audit.log(
                actor="deletion_poc",
                action=action,
                item_id=art_id,
                before="stored",
                after="deleted" if action == "delete" else "retained",
                reason=reason,
                request_id=req_id,
                extra={"type": art_type, "hold": hold_code}
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Xếp hạng top-B các ca ngoại lệ cần con người thẩm định."""
    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored,
        id_col="artefact_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        action_col="action",
        slice_col="type",
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Nạp quyết định override của reviewer (nếu có file reviewed)."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        scored = apply_overrides(scored, reviewed, id_col="artefact_id", value_col="action", audit=ctx.audit)
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    """Đưa ra quyết định cấp hệ thống GO / HOLD."""
    # Kiểm tra số lượng hành động
    n_delete = int((final.action == "delete").sum())
    n_hold = int((final.action == "retain_legal_hold").sum())
    n_escalate = int((final.action == "escalate").sum())
    spec = get_track(ctx.track)
    evidence_files = [str(ctx.out(spec.pred_file)), str(ctx.out("audit_log.jsonl"))]
    # Nếu có ca escalate chưa có người duyệt thủ công -> Cảnh báo HOLD
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if n_escalate > 0 and not reviewed_path.exists():
        return Decision(
            status="HOLD",
            reason_code="EXCEPTIONS_PENDING_REVIEW",
            reason=f"Found {n_escalate} exceptions requiring human DPO review before final purge",
            owner=ctx.config.get("owner", "Nguyễn Thiên Phúc"),
            scope=ctx.track,
            evidence=evidence_files,
            metrics={"delete": n_delete, "legal_hold": n_hold, "escalate": n_escalate}
        )
    return Decision(
        status="GO",
        reason_code="ALL_POLICIES_VERIFIED",
        reason="Full lineage traversed; legal holds and multi-subject constraints strictly enforced",
        owner=ctx.config.get("owner", "Nguyễn Thiên Phúc"),
        scope=ctx.track,
        evidence=evidence_files,
        metrics={"delete": n_delete, "legal_hold": n_hold, "escalate": n_escalate}
    )
def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    # Xuất file actions.csv đúng contract bắt buộc
    out_csv = ctx.out(spec.pred_file)
    final[spec.pred_columns].to_csv(out_csv, index=False)
    # Ghi nhận quyết định hệ thống
    decision = decide(ctx, final)
    write_decision(decision, ctx.out("decision.json"), ctx.out("decision_log.csv"))
    print(f"[poc_pipeline] Đã xử lý {len(final)} actions ({decision.status}: {decision.reason_code}) -> {out_csv}")

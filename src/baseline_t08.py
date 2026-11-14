"""Naive Baseline for T08 (Retention & Delete Request Simulator).

Tái sử dụng cấu trúc và các module hạ tầng từ src/examples/random_baseline.py:
- RunContext (context môi trường, seed, rng, config, output paths)
- make_review_queue & write_review_queue (human-in-the-loop review queue)
- Decision & write_decision (cơ chế chốt quyết định GO/HOLD/REWORK)
- get_track (thông tin contract, cột bắt buộc, file output của track)
- ctx.audit.log (ghi nhật ký kiểm toán cho từng hành động)

Đặc thù thuật toán Baseline theo mô tả trong docs/tracks/T08.md:
- Xóa một bản raw theo filename/subject_id.
- Không tìm các artefact phái sinh (lineage: frame, crop, embedding, annotation, export, backup).
- Không kiểm tra ràng buộc Legal Hold.
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.review import make_review_queue, write_review_queue
from .metrics.tracks import get_track


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)

    # 1. Load: Đọc requests.json và data_graph.json
    requests_path = ctx.input_dir / "requests.json"
    graph_path = ctx.input_dir / "data_graph.json"

    with open(requests_path, "r", encoding="utf-8") as f:
        requests = json.load(f)

    with open(graph_path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    artefacts = graph.get("artefacts", [])

    # 2. Process: Thuật toán ngây thơ (Naive Baseline)
    # Tái sử dụng ý tưởng gán score ngẫu nhiên từ random_baseline để ưu tiên review queue
    rows = []
    for req in requests:
        req_id = req["request_id"]
        subj_id = req["subject_id"]

        # Chỉ tìm 1 file raw_video khớp với filename hoặc subject_id
        for art in artefacts:
            is_raw = art.get("type") == "raw_video"
            matches_subject = subj_id in art.get("subject_ids", []) or subj_id in art.get("filename", "")

            if is_raw and matches_subject:
                art_id = art["artefact_id"]
                action = "delete"  # ngây thơ: cứ thấy raw là xoá, không kiểm tra legal hold
                score = round(float(ctx.rng.random()), 4)
                reason = f"naive baseline raw match: {art.get('filename', art_id)}"

                rows.append({
                    "request_id": req_id,
                    "artefact_id": art_id,
                    "action": action,
                    "score": score,
                    "reason": reason,
                })

                # Ghi vết kiểm toán append-only vào out/baseline/audit_log.jsonl
                ctx.audit.log(
                    actor="baseline_naive",
                    action=action,
                    item_id=art_id,
                    before="stored",
                    after="deleted",
                    reason=reason,
                    request_id=req_id,
                )
                break  # Đúng quy tắc baseline: chỉ xoá 1 bản raw đầu tiên tìm thấy

    df = pd.DataFrame(rows)
    ctx.stats["n_items"] = len(df)

    # 3. Rank: Tái sử dụng make_review_queue và write_review_queue từ random_baseline.py
    budget = int(ctx.param("budget", 20))
    if not df.empty:
        q = make_review_queue(
            df,
            id_col="artefact_id",
            score_col="score",
            budget=budget,
            reason_col="reason",
            action_col="action",
        )
        write_review_queue(q, ctx.out("review_queue.csv"))

    # 4. Xuất file actions.csv theo đúng schema contract của T08
    out_path = ctx.out(spec.pred_file)
    df[spec.pred_columns].to_csv(out_path, index=False)

    # 5. Decide: Tái sử dụng Decision & write_decision từ random_baseline.py
    write_decision(
        Decision(
            status="HOLD",
            reason_code="BASELINE_ONLY",
            reason="Naive baseline: only deletes single raw video per filename without lineage tracing or legal hold check",
            owner=ctx.config.get("owner", "baseline"),
            scope=ctx.track,
            evidence=[str(out_path)],
        ),
        ctx.out("decision.json"),
        ctx.out("decision_log.csv"),
    )

    print(f"[baseline_t08] Đã xử lý {len(df)} yêu cầu xóa ngây thơ -> {out_path}")

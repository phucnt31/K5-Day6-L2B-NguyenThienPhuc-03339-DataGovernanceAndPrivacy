# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
| --- | --- |
| Group ID | G61 |
| Challenge | T08 · Retention & Delete Request Simulator |
| Thành viên + vai trò | Nguyễn Thiên Phúc |
| Git URL | https://github.com/phucnt31/K5-Day6-L2B-NguyenThienPhuc-03339-DataGovernanceAndPrivacy |
| Tag `demo-180m` (commit) |  |
| Tag `final-24h` (commit) | final-24h |
| Deadline (giờ VN) | 2026-11-15 |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Người dùng yêu cầu xoá dữ liệu cá nhân (chủ thể dữ liệu) và doanh nghiệp. Nếu không xoá sạch, doanh nghiệp bị phạt tới 4% doanh thu toàn cầu theo GDPR Điều 17 hoặc vi phạm Luật 91/2025. Nếu xoá nhầm chứng cứ đang bị toà án/cơ quan điều tra giữ (Legal Hold), doanh nghiệp chịu trách nhiệm hình sự về hành vi tiêu hủy chứng cứ.

- Điểm nghẽn cụ thể: Dữ liệu phái sinh (derived artefacts: vector embeddings, cropped faces, data frames, snapshot backup) nằm rải rác trên nhiều kho lưu trữ khác nhau nhưng không được liên kết phả hệ (lineage).

- Đầu vào → đầu ra: 
+ Đầu vào: 10 yêu cầu xóa (requests.json) từ 10 chủ thể dữ liệu + Đồ thị phả hệ 212 artefacts (data_graph.json).
+ Đầu ra: File hành động chuẩn hóa out/poc/actions.csv (158 dòng quyết định phân loại), nhật ký kiểm toán bất biến out/poc/audit_log.jsonl, và hàng đợi duyệt ngoại lệ out/poc/review_queue.csv.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): 
+ GO: Deletion Completeness = 1.0, False-delete = 0, Audit trace completeness = 1.0, toàn bộ ca escalate đã có DPO thẩm định.
+ HOLD: Xuất hiện bất kỳ ca ngoại lệ (multi-subject, unknown origin) chưa được người duyệt.
+ REWORK: Xoá nhầm dữ liệu Legal Hold (False-delete > 0).
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): ____

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
| --- | --- | --- | --- | --- |
| dev | 10 requests / 212 artefacts | `fixtures/t08_deletion/` | CC0-1.0 | Có (Synthetic offline) |
| eval / heldout | Instructor overlay | `fixtures/t08_deletion/gt/` | CC0-1.0 | Có |

- Schema & class mapping:
+ 7 loại artefact: raw_video (15), backup (15), frame (45), face_crop (45), embedding (45), annotation (45), training_export (2).
+ 3 hành động (action): delete (xóa an toàn), retain_legal_hold (giữ lại theo nghĩa vụ pháp lý), escalate (chuyển chuyên viên DPO duyệt vì đa chủ thể hoặc thiếu quyền/nguồn gốc).
- Seed: 42 · Cách chia split (theo scene/group/segment?): Đồ thị dạng Directed Acyclic Graph (DAG) liên kết phân cấp từ nút gốc raw_video lan tỏa ra các phái sinh. Tập 10 yêu cầu xóa bao phủ toàn diện 10 kịch bản thực tế (có ca sạch, ca dính Legal Hold, ca thiếu quyền, ca đa chủ thể).
- `manifest.csv` verified (sha256): có — lệnh: `python -m tools.verify_manifests`
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: ____

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: 
1. GDPR Article 17 (Right to Erasure) & Exceptions (Art. 17(3)(b) Legal obligation) — Cơ sở pháp lý quốc tế cho việc bắt buộc giữ lại dữ liệu khi có Legal Hold bất chấp yêu cầu xóa của người dùng.
2. California DELETE Act (SB 362) & DROP Platform (2025) — Tham chiếu mô hình kiến trúc điều phối xóa dữ liệu tập trung qua hàng đợi thẩm định và lưu vết kiểm toán bất biến.
3. OpenLineage / Data Provenance Standards — Cơ sở thuật toán duyệt ngược đồ thị DAG để truy vết phả hệ dữ liệu phân tán.

- Sơ đồ data flow (input → process → rank/QC → review → decision → report): requests.json + data_graph.json 
→ 01 Load (Kiểm tra hash manifest) → 02 Process (Xây dựng đồ thị lineage DAG + Lan truyền thuộc tính Legal Hold từ trên xuống + Đánh giá thứ tự ưu tiên 4 bậc) → 03 Rank (Trích xuất top-20 ca ngoại lệ rủi ro vào review_queue.csv) → 04 Review (Đọc quyết định override từ DPO, ghi audit_log.jsonl) → 05 Decide (Chốt Risk Gate GO/HOLD) → 06 Output (actions.csv, decision.json, run_info.json).

- Thành phần offline (model/weights + checksum + license nếu có): Thuần Python 3.15 + Pandas, chạy hoàn toàn offline không cần tải model/weights bên ngoài, ngăn chặn hoàn toàn nguy cơ rò rỉ mạng (--offline).

- Trade-offs đã cân nhắc: 
1. Trade-off 1 (Lan truyền Legal Hold): Nếu chỉ đánh dấu nút gốc raw_video mà không lan truyền xuống con, hệ thống sẽ xóa nhầm file backup/embedding của vụ án. Nhóm chọn giải pháp lan truyền toàn diện từ cha xuống toàn bộ con cháu (Top-down Constraint Propagation).
2. Trade-off 2 (Xử lý Multi-subject): Xóa ngay lập tức sẽ làm mất dữ liệu của chủ thể thứ hai; giữ nguyên sẽ vi phạm quyền của chủ thể thứ nhất. Nhóm chọn giải pháp escalate để con người thực hiện cắt tỉa/làm mờ có kiểm soát.

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): Viết trong src/baseline_t08.py. Mô phỏng cách làm cẩu thả thường gặp: chỉ tìm 1 file raw_video có tên chứa subject_id rồi gán delete, hoàn toàn không kiểm tra Legal Hold và bỏ qua toàn bộ 148 artefact phái sinh (frame, embedding, backup...).
- PoC (mô tả, version/config, commit): Viết trong src/pipeline.py. Xây dựng đồ thị lineage hoàn chỉnh, lan truyền ràng buộc Legal Hold từ gốc xuống lá, phân tầng quyết định 4 bậc (Legal Hold > Permission/Origin > Multi-subject > Delete) và tích hợp hàng đợi thẩm định Human-in-the-loop.
- Cùng budget / cùng heldout / cùng seed: xác nhận Xác nhận cùng chạy trên seed 42, cùng budget review B=20, cùng tập dữ liệu offline 212 artefacts và 10 delete requests.

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Deletion Completeness** (must-delete artefacts deleted / must-delete artefacts) | all | 0.0784 | 1.0000 | 0.9216 | +1175.0% | higher | 158 |
| False-delete count (count (target 0): exceptions deleted + deletes outside request scope) | all | 2.0000 | 0.0000 | -2.0000 | -100.0% | lower | None |
| Exception handling accuracy (legal-hold/escalate rows handled as expected / such rows) | all | 0.0000 | 1.0000 | 1.0000 | baseline=0 | higher | None |
| Audit trace completeness (actions with an audit entry / actions) | all | 1.0000 | 1.0000 | 0.0000 | +0.0% | higher | None |
| Runtime / 100 items (s) | all | 0.1830 | 0.0568 | | | lower | |

## 05 · Evaluation protocol

- Công thức primary metric: 
  $$\text{Deletion Completeness} = \frac{\text{Số artefact phải xóa đã xóa thực tế}}{\text{Tổng số artefact phải xóa theo ground truth}}$$
  - Đơn vị đánh giá: Hành động xóa theo cặp `(request_id, artefact_id)`.
  - Tử số (Numerator): Số lượng cặp có nhãn `action == "delete"` khớp với `expected_action == "delete"` (PoC đạt 102/102; Baseline chỉ đạt 8/102).
  - Mẫu số (Denominator): Tổng số lượng artefact hợp lệ cần xóa (102 artefacts).
- Chỉ số lỗi xấu (mục tiêu = 0): `False-delete count = (số ngoại lệ bị bấm xóa nhầm) + (số ca xóa ngoài phạm vi)`. Baseline bị 2 lỗi (xóa nhầm 2 file có Legal Hold); PoC đạt chuẩn 0 lỗi.
- Threshold / budget B / K và lúc chốt: Chốt ngân sách duyệt ngoại lệ B = 20 đưa vào `review_queue.csv`. Thứ tự ưu tiên chính sách 4 bậc (`Legal Hold > Permission/Origin > Multi-Subject > Delete`) được chốt cứng trong code trước khi đánh giá.
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: Vì tập test gồm 10 requests với 158 hành động cụ thể, nhóm đánh giá chính xác theo từng lát cắt ngoại lệ (edge case) thay vì chỉ nhìn vào trung bình cộng.
- Lệnh evaluate chính xác:
  ```powershell
  .\.venv\Scripts\python.exe -m src.evaluate --track t08 --gt out/gt_internal.csv --pred out/poc/actions.csv --run-name poc --out reports/metrics_poc.json
  ```

## 06 · Result slices

| Slice (Hành động kỳ vọng) | N | Baseline Accuracy | PoC Accuracy | Ghi chú |
|---|---|---|---|---|
| `delete` (Xoá hợp lệ) | 102 | 7.8% (8/102) | 100.0% (102/102) | Baseline bỏ sót 94 file derived/backup |
| `retain_legal_hold` (Giữ do luật) | 40 | 0.0% (0/40) | 100.0% (40/40) | Nằm ở 2 cây phả hệ của subj_03 và subj_07 |
| `escalate` (Chờ người duyệt) | 16 | 0.0% (0/16) | 100.0% (16/16) | Gồm unknown origin, vendor ACL, multi-subject |

- **Failure case 1 (Tiêu hủy chứng cứ pháp lý):**
  - Metadata: Request `DR-002` (`subj_03`), artefact gốc `a0043` (`raw_video`) mang cờ `legal_hold: "LH-2026-03"`.
  - Root cause: Baseline chỉ đọc tên file `drive_subj_03_003.mp4` thấy khớp với chủ thể là gán ngay `delete`. Hậu quả là doanh nghiệp tiêu hủy chứng cứ đang có lệnh giữ của tòa án. PoC đã khắc phục bằng cách truy vết đồ thị lineage và lan truyền trạng thái `retain_legal_hold` xuống toàn bộ 14 file con phái sinh (`a0044` đến `a0056`).
- **Failure case 2 (Rò rỉ định danh Vector DB & vi phạm đa chủ thể):**
  - Metadata: Request `DR-004` (`subj_05`), bao gồm 3 embedding `a0075, a0079, a0083` có `origin_known: False` và frame `a0067` có `subject_ids: ["subj_04", "subj_05"]`.
  - Root cause: Baseline chỉ xóa file raw video, bỏ quên các vector embedding khuôn mặt trong database. Ngoài ra với frame `a0067`, nếu xóa trắng sẽ làm mất luôn ảnh của `subj_04`. PoC đã phát hiện cả hai trường hợp bất thường và chuyển sang `escalate` để DPO xem xét.
- Latency / compute: Chạy trên CPU máy cá nhân (Windows 11, Intel Core), runtime của PoC cho 158 hành động là 0.0897 giây (tương đương ~0.0568 giây cho mỗi 100 items).

## 07 · Human & decision

- Review queue: File `out/poc/review_queue.csv`, ngân sách B = 20, ưu tiên các ca có rủi ro cao nhất (`score >= 0.8` gồm toàn bộ các ca `escalate` và `retain_legal_hold`).
- Cách override + audit log:
  - Thẩm định viên (DPO) mở file review queue, điền tên vào cột `reviewer`, chọn quyết định (`approve` / `edit` / `reject`) và lưu thành `out/poc/review_queue_reviewed.csv`.
  - Pipeline tự động áp dụng giá trị mới qua hàm `apply_overrides` và ghi lại từng hành động (kèm timestamp, actor, lý do) vào file nhật ký kiểm toán bất biến `out/poc/audit_log.jsonl`.
- Decision policy + `reason_code` + owner:
  - Chốt `HOLD` với mã `EXCEPTIONS_PENDING_REVIEW` khi phát hiện các ca ngoại lệ cần DPO xem xét trước khi thực hiện xóa vĩnh viễn.
  - Chốt `GO` với mã `ALL_POLICIES_VERIFIED` khi toàn bộ 158 hành động đã được thẩm định an toàn.
  - Người ký duyệt: `Nguyễn Thiên Phúc`.
- Khi nào HOLD/REWORK thay vì tự động release: Hệ thống lập tức chặn lệnh xóa (`HOLD`) khi phát hiện dữ liệu liên quan tới tranh chấp pháp lý hoặc ảnh chụp chung nhiều người chưa được làm mờ (redaction).

## 08 · Reproduce & tests

```powershell
# 1. Kiểm tra tính toàn vẹn dữ liệu gốc
.\.venv\Scripts\python.exe -m tools.verify_manifests

# 2. Chạy bộ unit tests
.\.venv\Scripts\python.exe -m pytest -q tests/test_t08.py

# 3. Chạy pipeline PoC một lệnh duy nhất
.\.venv\Scripts\python.exe -m src.main --track t08 --pipeline src.pipeline --output out/poc --run-name poc --offline --seed 42
```

- Output của `pytest -q`: `.. [100%]` (2 passed trong 0.08 giây, 0 failed).
- Máy / CPU / OS / Python: Windows 11 · Python 3.15.2 · Intel64 Family 6 · Git SHA: `b0ce8bf`.

## 09 · Limitations & ethics

- **Rủi ro pháp lý & PII:** Dù các vector embedding trong cơ sở dữ liệu đã bị xóa, nhưng nếu trước đó các mô hình AI đã được huấn luyện trên các vector này thì vẫn tồn tại nguy cơ "ghi nhớ thông tin" (Model Memorization). Doanh nghiệp cần xây dựng thêm quy trình Machine Unlearning hoặc retrain mô hình định kỳ.
- **Rủi ro khi scale 10×:** Hiện tại đồ thị DAG được duyệt trên bộ nhớ RAM (in-memory). Khi quy mô tăng lên hàng triệu nodes và hàng nghìn yêu cầu mỗi ngày, việc duyệt đệ quy sẽ tiêu tốn tài nguyên; cần chuyển sang cơ sở dữ liệu đồ thị chuyên dụng (Neo4j hoặc Amazon Neptune).
- **Tuyên bố đạo đức & Pháp lý:** Nhóm không khẳng định phần mềm này tự động giúp doanh nghiệp "đạt chuẩn GDPR 100%". Hệ thống chỉ đóng vai trò chốt chặn kỹ thuật; mọi quyết định giữ lại dữ liệu hay hủy bỏ chứng cứ bắt buộc phải có văn bản phê duyệt của DPO và cơ quan pháp chế.
- **Kế hoạch cải tiến:** Tích hợp module tự động nhận diện và làm mờ khuôn mặt (Face Redaction) cho các ca multi-subject, giúp tự động chuyển từ `escalate` sang `delete` an toàn mà không cần chuyên viên phải can thiệp thủ công.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Member 1 | | Integration / CLI | | |
| Member 2 | | Data + GT | | |
| Member 3 | | Core algorithm | | |
| Member 4 | | Metric + tests | | |
| Member 5 | | Review queue + report | | |
| Member 6 (nếu có) | | Research / ablation / debate | | |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| | | |

---

**Bảng 3 · Checklist chốt khi nộp**

- [X] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [X] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [X] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [X] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [X] Mỗi thành viên có ≥1 commit thực chất và được nêu minh bạch trong bảng trên.

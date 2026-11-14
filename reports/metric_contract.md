# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
| --- | --- |
| Track | T08 · Retention & Delete Request Simulator |
| Primary metric | `Deletion Completeness` (tên chuẩn evaluator: `Deletion Completeness`) |
| Tăng tốt hay giảm tốt? | higher (mục tiêu: 1.0 = 100%) |
| Đơn vị đánh giá | Hành động xóa theo cặp `(request_id, artefact_id)` |
| Công thức | `Số artefact phải xóa đã xóa / Tổng số artefact phải xóa` (numerator: done, denominator: len(must)) |
| Cách ghép prediction ↔ GT | Ghép chính xác theo cặp khóa `(request_id, artefact_id)` |
| Candidate pool cố định | 10 requests trong `requests.json` ghép nối trên 212 artefacts của `data_graph.json` |
| Review budget B | B = 20 (chọn lọc top-20 ca ngoại lệ rủi ro cao nhất: Legal Hold, Escalate) |
| Seed | 42 |
| Threshold policy | Bậc ưu tiên chính sách cố định: Legal Hold > Unknown Origin / ACL > Multi-Subject > Delete |
| Eval split | Offline fixture synthetic (212 artefacts, 10 delete requests) |
| Chỉ số lỗi xấu | `False-delete count` (xoá nhầm dữ liệu exception hoặc xoá ngoài phạm vi request — mục tiêu = 0) |
| Slices sẽ báo cáo | Phân nhóm theo `expected_action`: `delete`, `retain_legal_hold`, `escalate` |
| Báo độ bất định khi N nhỏ | Tần suất chính xác và kiểm toán completeness trên tập 10 yêu cầu xóa |
| Ngày giờ chốt + người chốt | 2026-11-14 17:30 · Nguyễn Thiên Phúc |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.

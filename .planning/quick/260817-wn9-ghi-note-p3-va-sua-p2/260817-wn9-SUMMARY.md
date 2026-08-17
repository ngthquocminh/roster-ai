---
quick_id: 260817-wn9
description: Ghi note re-frame P3 và sửa P2 (Gate A không chạy lại được)
date: 2026-08-17
status: complete
commits:
  - cabedbf docs(260817-wn9) re-frame P3 as a consumption-site category error
  - 8139866 fix(gate-a) exempt the readiness report's own output from the dirty-tree check
---

# Quick Task 260817-wn9 — Summary

Hai prep task còn lại trước Epic 3 (retro §6.2). P1 (CI) và P4/A1
(`docs/DOMAIN-MODEL.md`) đã xong từ trước.

## Task 1 — Re-frame P3 (commit `cabedbf`)

Khung "evidence files have no expiry" sai, và đã bị chép sang ba nơi. Đã đính chính
tại chỗ, giữ nguyên quan sát gốc (annotation cộng thêm, không xoá lịch sử):

| File | Thay đổi |
|---|---|
| `deferred-work.md:103` | 4 bullet annotation: monotone là đúng thiết kế; defect ở consumption site; scope 4/20 và rủi ro không đồng đều; hướng xử lý là 1.9 → live CI test |
| `sprint-status.yaml` | Viết lại action item P3 + comment giải thích tại sao khung cũ sai |
| `epic-1-2-retro-2026-08-16.md` §6.2 | Gạch ngang dòng P3 + annotation |
| `epic-1-2-retro-2026-08-16.md` §6.3 | P1 đánh dấu CLEARED; P3 gỡ khỏi critical path |
| `gate_a_readiness._evidence_result()` | Docstring cảnh báo ngay tại nơi người ta đáp xuống khi debug |

Nội dung đính chính: evidence là **bản ghi lịch sử** ("tại commit X, phép đo Y cho kết
quả Z") — đúng vĩnh viễn, tái lập bằng checkout X. Monotone của `audit_evidence_file()`
là **đúng theo thiết kế**; Story 1.11 đã sửa đúng cái defect gộp "sinh ra có trung thực
không" với "giờ còn hợp lệ không", và đòi expiry là yêu cầu tái tạo nó. Defect thật là
**lỗi phạm trù ở nơi tiêu thụ**: `_evidence_result()` trả phép đo quá khứ làm phán quyết
hiện tại. Scope **4/20 check**; 16 check kia ăn JUnit XML tươi.

Rủi ro trong 4 check đó không đồng đều — điều bản ghi cũ không phân biệt:
- **1.4 / 1.5 thấp.** Ngưỡng 2s được assert ngay trong test
  (`test_postgres_integration.py:593`), marker `@pytest.mark.postgres`, CI chạy mỗi push.
  Evidence chỉ ghi số đo trên máy tham chiếu; đo lại đã scripted.
- **1.9 mới là gap thật.** Tĩnh hoàn toàn, không có đường đo lại tự động, guard vòng
  tròn, và gác invariant mutation-denial mà Story 3.1 sẽ ghi vào.

Hướng: biến 1.9 thành live CI test rồi bỏ `evidence_path`; **không** dựng `subject_paths`
cho cả 20 check. P3 rời khỏi critical path — chạy song song Epic 3.

## Task 2 — P2: Gate A chạy lại được (commit `8139866`)

`main()` ghi `evidence/gate-a-readiness.json` → cây bẩn → lần chạy thứ hai chết bằng
`DirtyTreeError` trước khi làm gì. Nguyên tắc sửa (đã chốt với user): bẩn vì *source chưa
commit* → vẫn từ chối; bẩn vì *chính output sắp ghi đè* → vô hại.

- `working_tree_status(..., ignore_paths=...)`; `resolve_code_binding()` và
  `resolve_bindings()` truyền xuống; `main()` đưa `--output` + `.tmp` staging.
- Không cần guard "chỉ output được bẩn" riêng — bộ lọc tự cho điều đó.
- Miễn trừ *được sử dụng thật* ghi ra `binding_scope`; `working_tree_dirty` giữ `false`.
- Không `git stash`; giữ nguyên `--code-from`; không đụng `audit_evidence_file()`.

### Hai phát hiện trong lúc làm

1. **`git status --porcelain` gộp thư mục untracked thành một entry `evidence/`**, nên
   exemption theo path chính xác không khớp và checkout mới vẫn bị từ chối. Sửa bằng
   `--untracked-files=all` — cũng giữ cho exemption không vô tình xoá các file anh em
   trong cùng thư mục untracked. **Test bắt được, không phải do đọc code.**
2. `test_evaluation_harness.py:956` monkeypatch `resolve_code_binding` bằng lambda phải
   học thêm keyword mới.

### Red-then-green (chuẩn A2)

Mở rộng bộ lọc thành bỏ qua *mọi* path →
`test_exempting_the_output_file_still_refuses_an_uncommitted_source_change` đỏ với
`DID NOT RAISE DirtyTreeError`. Lần chạy đỏ đầu tiên hỏng vì `MigrationGraphError` ở
downstream nên đã thêm `migrations_dir`/`contract_dir` để red chỉ đúng thứ bị hỏng.

### Kiểm chứng trên repo thật (không chỉ tmp_path)

```
RUN 1: ok  commit=813986656  dirty=False  scope=yes
RUN 2: ok  commit=813986656  dirty=False  scope=yes
```
Và sửa `backend/settings.py` chưa commit → `REFUSED as required; offender listed:
['backend/settings.py']`.

**Backend suite: 866 passed, 2 skipped.**

## Chưa làm / còn mở

- **P3 phần thực thi** (1.9 → live CI test) — cố ý chưa làm; task này chỉ ghi note.
  Cần xong trước khi Story 3.1 **merge**, không phải trước khi tạo.
- **CI xanh trên `main`** chưa xác minh được — `gh` không có trên máy này.
- Nhánh `chore/gate-a-p2-p3`, chưa merge.

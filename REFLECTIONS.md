# W6 Side Challenge Reflections

## 1. AI assistance: What fraction of code came from AI tools (Claude / Cursor / Copilot) unmodified? Which parts did you actively modify, why?
Khoảng 80-90% mã nguồn cốt lõi (sử dụng boto3, xử lý paginator, gom nhóm dữ liệu bằng defaultdict) được hỗ trợ tạo bởi AI. AI giúp hoàn thành cực kỳ nhanh chóng các đoạn code tương tác với AWS SDK thay vì phải mò đọc tài liệu API của boto3. Tuy nhiên, mình đã phải chủ động rà soát và điều chỉnh lại một số phần, điển hình như logic an toàn (safety contract) ở lệnh `terminate` và `clean`. AI có xu hướng viết code thẳng đuột để xóa, nhưng mình phải tinh chỉnh lại để luôn có bước `confirm` hoặc chế độ `dry-run` mặc định, cũng như việc in ra log rõ ràng thay vì quăng lỗi traceback Python khiến người dùng hoang mang.

## 2. `clean --apply` blast radius: If you accidentally ran clean --tag Environment=dev --apply in an account shared with another team, what would you have wanted in place to limit damage?
Nếu vô tình chạy lệnh `clean --tag Environment=dev --apply` trong một tài khoản AWS dùng chung với các team khác, hậu quả có thể rất nghiêm trọng (xóa nhầm cụm server Dev của team bạn đang code). Để giới hạn rủi ro (blast radius) này, hệ thống cần có các lớp phòng vệ:
1. **Bắt buộc nhập xác nhận cụ thể**: Không chỉ là `--apply`, mà CLI nên bắt người dùng gõ tên môi trường hoặc số lượng tài nguyên sẽ xóa (vd: gõ "15 resources" để đồng ý).
2. **Quyền IAM chặt chẽ (ABAC - Attribute-Based Access Control)**: User/Role dùng để chạy lệnh CLI chỉ nên có quyền `ec2:TerminateInstances` đối với các tài nguyên có gắn thẻ Tag cụ thể thuộc sở hữu của chính team mình (vd: `Condition: {"StringEquals": {"aws:ResourceTag/Team": "Group8"}}`).
3. **Bảo vệ Termination (Termination Protection)**: Trên AWS, các EC2 quan trọng cần được bật `Termination Protection`. Dù CLI có gọi lệnh xóa, AWS cũng sẽ từ chối thao tác này cho đến khi tính năng bảo vệ được tắt.

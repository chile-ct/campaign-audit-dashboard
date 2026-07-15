# Handoff — Digital Campaign Audit Dashboard (v3)

Repo: `chile-ct/campaign-audit-dashboard` · Live: https://chile-ct.github.io/campaign-audit-dashboard/

Bản handoff cũ (`handoff_notes_v2.md`, gửi rời qua chat) đã **lỗi thời** — phần "chưa làm proxy/cron" trong đó đã làm xong. File này thay thế, và từ giờ nằm luôn trong repo nên không cần gửi rời nữa.

## Cách bắt đầu (cho collaborator mới, vd: Kiệt)

1. Đảm bảo đã được add làm collaborator trên GitHub (đã xong).
2. Trong Claude (Desktop/Code) của bạn, mở terminal và clone repo:
   ```
   gh repo clone chile-ct/campaign-audit-dashboard
   cd campaign-audit-dashboard
   ```
   (Nếu `gh` chưa login: `gh auth login` trước, chọn tài khoản GitHub có quyền vào repo này.)
3. Nói với Claude: *"Đọc HANDOFF.md và index.html trong repo này, tôi muốn sửa/thêm ..."* — không cần paste gì thêm, mọi thứ đã nằm trong repo.

## Kiến trúc hiện tại (khác hẳn v2)

- **`index.html`** — dashboard, UI/logic y như trước. Điểm khác: không còn phụ thuộc `window.cowork` (Builder OS) để lấy data live nữa. Mỗi lần load/refresh trang, nó `fetch('data/live-snapshot.json')` để lấy bản mới nhất.
- **`data/live-snapshot.json`** — snapshot 30-ngày gần nhất (funnel + campaign detail + spend). Auto-generated, **không sửa tay file này**.
- **`scripts/update_snapshot.py`** — script Python chạy 3 query BigQuery (funnel/campaign/spend, y hệt SQL cũ trong index.html), build lại `live-snapshot.json`, giữ nguyên metric "Save" từ bản cũ (không re-query vì tốn ~28GB).
- **`.github/workflows/update-dashboard.yml`** — GitHub Actions, tự chạy script trên **10:00 sáng mỗi ngày (giờ VN)**, tự commit + push nếu data đổi. Chạy bằng Python + BigQuery client trực tiếp — **không qua AI, không tốn token**, chỉ tốn BQ job cost (~4GB/ngày).
- Secret `GOOGLE_CREDENTIALS` (Settings → Secrets → Actions) đã được cấu hình sẵn — **không cần đụng vào**, trừ khi workflow báo lỗi auth.

## Muốn sửa/thêm gì thì sửa ở đâu

| Muốn làm | Sửa ở |
|---|---|
| Đổi UI, thêm chart, sửa cách tính CPL, sửa filter... | `index.html` (đọc mục "Cấu trúc file quan trọng" bên dưới) |
| Đổi khung thời gian, thêm field mới vào snapshot 30 ngày | `scripts/update_snapshot.py` **và** phần fetch/merge trong `index.html` (hàm `loadStaticSnapshot()`) phải khớp nhau |
| Đổi giờ chạy cron | `.github/workflows/update-dashboard.yml`, dòng `cron:` (giờ UTC, VN = UTC+7) |
| Thêm data mới không phải rolling-30-ngày (vd: theo tháng, YTD) | Vẫn là snapshot tĩnh nhúng trong `index.html` lúc build — muốn tự động hoá thêm thì viết thêm query trong `update_snapshot.py` và field mới trong JSON |

## Cấu trúc file quan trọng trong `index.html`

- `renderTable()` — bảng Campaign Detail
- `openDrawer()` — popup chi tiết root-cause
- `renderSupplyDemandCheck()` — panel health marketplace
- `getActiveCampaignRows(v)` / `getSpendInfo(campaign)` — nguồn data theo `selectedMonth`
- `loadStaticSnapshot()` — fetch `data/live-snapshot.json`, merge vào `SUMMARY`/`CAMPAIGNS`/`SPEND_LAST30`, gọi lại khi bấm nút "Refresh Data"
- Test qua Node/DOM giả trước khi push (tránh lỗi runtime kiểu "trắng trang").

## Việc còn dang dở (kế thừa từ v2, vẫn đúng)

- CPL/Landing/Audience mới cover subset campaign — phần còn lại thiếu data ở nguồn.
- Chưa tra được Meta campaign thật cho nhóm job theo vai trò.
- `SUPPLY_DEMAND_METRICS` vẫn là snapshot tĩnh 1 ngày, chưa tự động hoá — chỉ phần 30-ngày (funnel/campaign/spend) đã live.

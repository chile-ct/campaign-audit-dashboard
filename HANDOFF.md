# Handoff — Digital Campaign Audit Dashboard (v4)

Repo: `chile-ct/campaign-audit-dashboard` · Live: https://chile-ct.github.io/campaign-audit-dashboard/

Bản cũ (v3) đã lỗi thời ở phần cấu trúc UI/logic (rất nhiều đã đổi). File này thay thế hoàn toàn.

## Cách bắt đầu (cho collaborator mới, vd: Kiệt)

1. Đảm bảo đã được add làm collaborator trên GitHub.
2. Clone repo:
   ```
   gh repo clone chile-ct/campaign-audit-dashboard
   cd campaign-audit-dashboard
   ```
3. Nói với Claude: *"Đọc HANDOFF.md trong repo này, tôi muốn sửa/thêm ..."* — không cần đọc lại toàn bộ `index.html` từ đầu, file này tóm tắt đủ để bắt đầu.
4. Workflow sửa code (bắt buộc theo, đã dùng suốt): sửa `index.html` → `node --check` (extract script block, verify syntax) → chạy local `python3 -m http.server 8743` + test qua Browser pane (dùng JS assertions qua DOM, KHÔNG dựa vào screenshot vì tool screenshot hay bị glitch/hiển thị sai dù DOM đúng) → `git pull --rebase origin main` (tránh conflict với GitHub Actions auto-commit data hàng ngày) → `git add/commit/push`.

## Kiến trúc dữ liệu — không đổi từ v3

- **`index.html`** — toàn bộ dashboard: UI + logic + data nhúng tĩnh (build-time cho phần theo-tháng) + fetch live cho rolling-30-ngày.
- **`data/live-snapshot.json`** — snapshot 30-ngày gần nhất, auto-generated bởi GitHub Actions mỗi ngày 10:00 sáng giờ VN (`scripts/update_snapshot.py`). **Không sửa tay.**
- **Zero-token pipeline**: `.github/workflows/update-dashboard.yml` chạy Python script trực tiếp query BigQuery — không qua AI, không tốn Claude token, chỉ tốn BQ job cost (~4GB/ngày). Secret `GOOGLE_CREDENTIALS` đã cấu hình sẵn.
- **4 vertical**: `pty` (Nhà Tốt), `veh` (Chợ Tốt Xe), `gds` (Chợ Tốt Goods), `jobs` (Việc Làm Tốt) — filter Paid Search + Display only, từ `chotot_data.traffic_visit_detail` UNNEST(category) join `dim.d_category` để lấy vertical.
- **Touch-based attribution**: 1 session/campaign có thể được gán cho nhiều vertical nếu user chạm nhiều category trong 1 session — đây là methodology có chủ đích, không phải bug (đã note rõ trong code/UI).

## Cấu trúc quan trọng trong `index.html` (theo thứ tự trong file)

| Function | Vai trò |
|---|---|
| `GOALS_MONTHLY`, `GOALS`, `monthlyGoal()`, `resolvedGoal()` | Goal CPL/CR theo tháng (FC2 2026) và theo năm, dùng cho color-coding và gap sentences |
| `crClass(cr, v)` / `cplClass(cpl, v)` | Goal-relative red/yellow/green — dùng để tô màu bảng VÀ để xác định "campaign đang đỏ" trong `computeRecentAnomaly` |
| `renderCards(v)` / `computeCards(v)` | 6 card tổng quan đầu trang (Total DAU, DAU w/Save, w/Adview, w/Lead, Total Lead, Avg CPL) |
| `computeAvgCPL(v)` | CPL trung bình, chỉ tính trên campaign có DAU≥100 và có spend data |
| `renderMonthlyTrend(v)` / `renderMonthlyCPLTrend(v)` | 2 chart xu hướng theo tháng (bar actual vs target), kèm `gapSentence(...)` diễn giải khoảng cách so goal |
| `computeNetworkSplit(v)` / `renderChannelSplit(v)` | **Mới:** 2 chart Facebook vs Google (trước đây là Display vs Paid Search — đã đổi theo yêu cầu). Aggregate từ campaign-level rows qua `campaignNetwork()`. Đặt bên trong panel Campaign Detail, dưới `<h2>` và trên thanh search/filter. |
| `renderSupplyDemandCheck(v)` | Panel Cross-check Marketplace Supply-Demand — 4 metric threshold-gated (Ad/Buyer Coverage ≥0.70, Demand Balance ≥0.50, Supply Balance ≥1.0) + 2 metric chẩn đoán không-threshold (Conversion issue %, Demand issue %). Data này vẫn là snapshot tĩnh 1 ngày trong `SUPPLY_DEMAND_METRICS`, **chưa tự động hoá** (khác với phần 30-ngày đã live). Ý nghĩa 2 metric chẩn đoán được note ngay dưới badge khỏe/yếu bằng bullet list ngắn gọn — action đúng khi cao là Category/Sales/Product cải thiện chất lượng tin/matching, KHÔNG phải giảm traffic marketing (giữ nguyên câu Việt này khi sửa, đã tinh chỉnh ngắn gọn qua vài vòng feedback).
| `getActiveCampaignRows(v)` | Nguồn data campaign-level theo `selectedMonth` (last30 / ytd / theo tháng cụ thể). Đã filter: (1) loại `EXCLUDED_CAMPAIGNS`/`EXCLUDED_NAME_PATTERN` (chứa "install"), (2) loại campaign có `campaignVerticalShare < 0.5` (đa số traffic thuộc vertical khác — tránh CPL bị thổi phồng vì spend không chia theo vertical). |
| `campaignNetwork(name, channel)` | Heuristic phân loại Google/Facebook/Khác dựa tên campaign: `_gg_/pmax/dsa/demandgen/_google_` → Google; `_fb_/b2s.surround` → Facebook; tên chứa "search" → Google; **Display + tên chứa "clicklink"** → Facebook (mới thêm); còn lại → Khác. |
| `campaignVerticalShare(campaign, v)` | % DAU của campaign thuộc vertical `v` so với tổng DAU (mọi vertical) — dùng để loại minority-vertical campaigns khỏi bảng, và cảnh báo ⚠️ CPL bị thổi phồng khi share < 0.3 trong drawer. |
| `renderTable(v)` | Bảng Campaign Detail — cột: Campaign, Channel, DAU, DAU w/Lead, Total Lead, CR→Lead, CPL. CSS đã tighten (padding 6px, không giới hạn max-width tên campaign) để tên full hiện trên 1 dòng, hạn chế wrap. |
| `computeRecentAnomaly(name, v, currentCr)` | **Quan trọng — sinh root-cause/fix cho từng campaign trong drawer.** Dựa vào swing MoM của CR/CPL (ngưỡng ±15%) map vào decision-tree của skill `paid-ads` (đã đánh giá và loại 3 skill khác không phù hợp: `out-app-campaign-eval` chỉ dành app-install, `fb-ads` là skill vận hành không phải chẩn đoán, `marketing-demand-acquisition` là framework B2B SaaS phương Tây không áp dụng cho marketplace VN). Có catch-all đảm bảo **MỌI campaign đang đỏ (CR dưới goal) đều có root-cause/fix**, kể cả khi: (a) chưa đủ data trend theo tháng, (b) swing không rơi vào bad/bad hay bad/ok rõ ràng, (c) **cả CR và CPL đều đang cải thiện (crGood && cplGood) nhưng vẫn còn đỏ** — case này bị thiếu ở 2 vòng fix đầu, tới vòng fix thứ 3 mới bắt được qua test trực tiếp toàn bộ campaign đỏ ở cả 4 vertical (xem "Cách test" bên dưới). Mỗi note luôn có disclaimer cuối: suy luận dựa trên decision-tree skill `paid-ads`, chưa xác nhận qua campaign ID thật trên Ads Manager. |
| `openDrawer(campaign, v)` | Popup chi tiết: funnel, root-cause (`computeRecentAnomaly`), landing page (vertical-scoped qua `LANDING_PAGES[name][v]`), CPL + cảnh báo cross-vertical. |
| `render()` | Thứ tự render hiện tại: `monthNote + renderCards + renderMonthlyTrend + renderMonthlyCPLTrend + renderSupplyDemandCheck + renderTable` (renderTable tự chèn `renderChannelSplit` bên trong nó). |

## Cách test khi sửa `computeRecentAnomaly` hoặc bất kỳ logic root-cause nào

Đừng chỉ test 1-2 campaign mẫu — logic có nhiều branch, cần quét **toàn bộ** campaign đang đỏ ở cả 4 vertical để chắc chắn không sót case. Snippet đã dùng (chạy qua Browser pane `javascript_tool`, sau khi mở dashboard qua local `http.server`):

```js
(function(){
  const VERTS=['pty','veh','gds','jobs'];
  const failing=[];
  let totalRed=0;
  VERTS.forEach(v=>{
    getFilteredSortedRows(v).forEach(r=>{
      if (crClass(r.cr, v) === 'cr-bad'){
        totalRed++;
        const notes = computeRecentAnomaly(r.campaign, v, r.cr);
        const hasRootCause = notes && notes.some(n => /🔍|🛠️/.test(n));
        if (!hasRootCause) failing.push({v, campaign:r.campaign, cr:r.cr, notes});
      }
    });
  });
  return JSON.stringify({totalRed, failingCount:failing.length, failing});
})();
```
`failingCount` phải luôn = 0 trước khi push.

## Việc còn dang dở / để ý khi làm tiếp

- `SUPPLY_DEMAND_METRICS` vẫn là snapshot tĩnh 1 ngày, chưa tự động hoá qua GitHub Actions — chỉ phần 30-ngày (funnel/campaign/spend) đã live.
- `campaignNetwork()` là heuristic theo tên, không phải mapping thật từ Ads Manager — sẽ có sai số với campaign đặt tên không theo convention. Mỗi lần user báo case sai (vd: "search" → Google, "clicklink"+Display → Facebook) thì thêm rule mới vào đúng function này, luôn test lại toàn bộ danh sách campaign trước khi push để tránh regression.
- CPL/Landing/Audience mới cover subset campaign có spend data — phần còn lại thiếu nguồn.
- Chưa tra được Meta campaign thật cho nhóm job theo vai trò.
- Root-cause trong `computeRecentAnomaly` là suy luận theo pattern (paid-ads decision tree), KHÔNG phải chẩn đoán đã xác nhận — luôn giữ disclaimer line, không bỏ.
- Khi user yêu cầu thay đổi UI/copy, ưu tiên chỉnh ngắn gọn — đã có nhiều vòng feedback yêu cầu bớt chữ, bớt câu thừa (vd: bỏ "(TB năm)", "Ref:", bỏ câu note trùng lặp trong Supply-Demand panel).

## Muốn sửa/thêm gì thì sửa ở đâu

| Muốn làm | Sửa ở |
|---|---|
| Đổi UI, thêm chart, sửa cách tính CPL, sửa filter, sửa network classification... | `index.html` (bảng function ở trên) |
| Đổi khung thời gian, thêm field mới vào snapshot 30 ngày | `scripts/update_snapshot.py` **và** `loadStaticSnapshot()` trong `index.html` phải khớp nhau |
| Đổi giờ chạy cron | `.github/workflows/update-dashboard.yml`, dòng `cron:` (giờ UTC, VN = UTC+7) |
| Thêm data mới không phải rolling-30-ngày (vd: theo tháng, YTD) | Vẫn là snapshot tĩnh nhúng trong `index.html` lúc build — muốn tự động hoá thêm thì viết thêm query trong `update_snapshot.py` và field mới trong JSON |

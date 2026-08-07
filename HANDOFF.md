# Handoff — Digital Campaign Audit Dashboard (v5)

Repo: `chile-ct/campaign-audit-dashboard` · Live: https://chile-ct.github.io/campaign-audit-dashboard/

Bản cũ (v4) vẫn đúng phần lớn nhưng thiếu 3 phần mới nhất: theo-ngày tích luỹ vĩnh viễn (`daily-snapshot.json`), goal H2 thống nhất theo deck (`H2_GOALS`), và bảng Segment Demand PTY (`segment-demand.json`). File này đã gộp đủ, đọc bản này là đủ, không cần lục lại v3/v4.

## Cách bắt đầu (cho collaborator mới, vd: Kiệt)

1. Đảm bảo đã được add làm collaborator trên GitHub.
2. Clone repo:
   ```
   gh repo clone chile-ct/campaign-audit-dashboard
   cd campaign-audit-dashboard
   ```
3. Nói với Claude: *"Đọc HANDOFF.md trong repo này, tôi muốn sửa/thêm ..."* — không cần đọc lại toàn bộ `index.html` từ đầu, file này tóm tắt đủ để bắt đầu.
4. Workflow sửa code (bắt buộc theo, đã dùng suốt): sửa `index.html` → `node --check` (extract script block, verify syntax) → chạy local `python3 -m http.server 8743` + test qua Browser pane (dùng JS assertions qua DOM, KHÔNG dựa vào screenshot vì tool screenshot hay bị glitch/hiển thị sai dù DOM đúng) → `git pull --rebase origin main` (tránh conflict với GitHub Actions auto-commit data hàng ngày) → `git add/commit/push`.

## Kiến trúc dữ liệu

- **`index.html`** — toàn bộ dashboard: UI + logic + data nhúng tĩnh (chỉ còn là fallback lúc build) + fetch live cho cả rolling-30-ngày VÀ phần theo-tháng.
- **`data/live-snapshot.json`** — snapshot 30-ngày gần nhất, auto-generated bởi GitHub Actions mỗi ngày 10:00 sáng giờ VN (`scripts/update_snapshot.py`). **Không sửa tay.**
- **`data/monthly-snapshot.json`** — snapshot theo-tháng (`monthly_summary`, `monthly_campaigns`, `spend_by_month`), cũng auto-generated bởi cùng script/cùng lịch chạy mỗi ngày. **Chỉ tháng hiện tại (current calendar month) được re-query mỗi lần chạy** — các tháng đã qua giữ nguyên vì data không đổi (tự động chỉ thêm key tháng mới khi sang tháng, không xoá tháng cũ). `current_month` / `current_month_through` trong file này cho biết tháng nào đang là MTD và dữ liệu đã kéo tới ngày nào — frontend dùng 2 field này để tự sinh label "(MTD, đến X/Y)" thay vì hardcode. **Không sửa tay.**
- **`data/daily-snapshot.json`** — lịch sử theo-ngày (`daily_summary`, `spend_by_day`), dùng cho toggle "Theo ngày" ở 2 chart trend. Khác 2 file trên — **tích luỹ vĩnh viễn, không phải rolling window**: mỗi lần chạy chỉ query những ngày CHƯA có trong file (từ ngày sau `last_day` cũ tới hôm nay), nên sau lần backfill đầu tiên (từ `DAILY_HISTORY_START` = 2026-01-01, ~11-12GB one-time) chi phí mỗi ngày chỉ còn ~1 ngày data (rẻ). `history_start`/`last_day` cho biết phạm vi dữ liệu thật đang có. **Không sửa tay.**
  - ⚠️ **Bug đã fix, đừng lặp lại:** `last_day` PHẢI lấy từ ngày lớn nhất thực sự CÓ data trong `daily_summary`, không phải `query_end` (=hôm nay) — vì bảng nguồn `traffic_visit_detail` trễ ~1 ngày, hôm nay thường chưa có data. Nếu ghi `last_day=hôm nay` dù 0 dòng, ngày mai script sẽ bắt đầu query từ hôm nay+1, **bỏ sót vĩnh viễn ngày hôm nay** dù nguồn cuối cùng cũng có data. Đã tự confirm bug này qua 1 lần chạy thật fail (xem commit "fix: don't fail the whole pipeline...").
  - ⚠️ **Bug đã fix, đừng lặp lại:** khi 1-ngày-range trả về 0 dòng (bình thường do source lag), KHÔNG được `raise SystemExit` — làm vậy script exit code 1 khiến step "Commit and push if changed" (không có `if: always()` lúc đó) bị SKIP hoàn toàn, mất luôn data live-snapshot/monthly-snapshot đã query thành công trước đó trong CÙNG lần chạy. Giờ: 1-ngày 0 dòng → log rồi skip êm; multi-ngày 0 dòng → vẫn raise (dấu hiệu gap thật). Step commit cũng đã thêm `if: always()` làm lớp bảo vệ thứ 2.
- **`data/segment-demand.json`** — bảng demand-supply theo segment, **chỉ có PTY** (chưa có nguồn tương đương cho veh/gds/jobs). Đọc từ `ct_nha.transform__pty_serviceable_effectiveness_daily` (bảng Dataform riêng của mkt-director, cùng nguồn với Looker report nội bộ — KHÔNG tự build từ traffic_visit_detail) rồi cross-reference với 1 query riêng tính % lead mỗi segment đến từ digital campaign (paid Search/Display) của MKT Growth. Cập nhật hàng tuần — script chỉ re-query khi có `week_ending` mới xuất hiện ở bảng nguồn (check `MAX(week_ending)`), nên hầu hết lần chạy cron hàng ngày là no-op ở phần này. **Không sửa tay.**
- **Zero-token pipeline**: `.github/workflows/update-dashboard.yml` chạy Python script trực tiếp query BigQuery — không qua AI, không tốn Claude token, chỉ tốn BQ job cost (~4GB/ngày cho phần 30-ngày + ~1-1.5GB/ngày cho phần tháng hiện tại, tăng dần theo số ngày đã qua trong tháng rồi reset về nhỏ khi sang tháng mới + ~vài trăm MB/ngày cho phần theo-ngày sau lần backfill đầu + ~4.2GB mỗi khi có tuần mới cho phần segment demand PTY). Secret `GOOGLE_CREDENTIALS` đã cấu hình sẵn.
- **4 vertical**: `pty` (Nhà Tốt), `veh` (Chợ Tốt Xe), `gds` (Chợ Tốt Goods), `jobs` (Việc Làm Tốt) — filter Paid Search + Display only, từ `chotot_data.traffic_visit_detail` UNNEST(category) join `dim.d_category` để lấy vertical.
- **Touch-based attribution**: 1 session/campaign có thể được gán cho nhiều vertical nếu user chạm nhiều category trong 1 session — đây là methodology có chủ đích, không phải bug (đã note rõ trong code/UI).

## Cấu trúc quan trọng trong `index.html` (theo thứ tự trong file)

| Function | Vai trò |
|---|---|
| `GOALS_MONTHLY`, `H2_GOALS`, `GOALS`, `isH2()`, `monthlyGoal()`, `resolvedGoal()` | Goal CPL/CR/CP DAU/DwL/MAU/MwL. **H1 (Jan-Jun)**: mỗi tháng 1 target riêng trong `GOALS_MONTHLY` (chỉ có cr/cpl — cp_dau/dwl/mau/mwl cho H1 fallback về `GOALS` annual). **H2 (Jul-Dec)**: TẤT CẢ 6 tháng dùng CHUNG 1 số duy nhất trong `H2_GOALS` (theo yêu cầu thống nhất, không còn khác nhau mỗi tháng) — `monthlyGoal()` check `isH2(ym)` để route. `GOALS` (annual/FY) chỉ dùng làm fallback cho YTD blend + cp_dau/dwl/mau/mwl của H1. **Toàn bộ số trong `GOALS`/`H2_GOALS`/`GOALS_MONTHLY` lấy từ deck "Chợ Tốt — App Growth Direction 2026"** (artifact Claude, section 04 "App growth" → driver 1 "Digital campaigns" → bảng `d1_vert`/`d1_data` trong deck's embedded JS) — KHÔNG phải số tự tính từ dashboard's own BigQuery data. Khi deck update số mới, phải tay đối chiếu lại và sửa 3 const này (xem "Cách đối chiếu goal với deck" bên dưới). |
| `crClass(cr, v)` / `cplClass(cpl, v)` | Goal-relative red/yellow/green — dùng để tô màu bảng VÀ để xác định "campaign đang đỏ" trong `computeRecentAnomaly` |
| `renderCards(v)` / `computeCards(v)` | 6 card tổng quan đầu trang (Total DAU, DAU w/Save, w/Adview, w/Lead, Total Lead, Avg CPL) |
| `computeAvgCPL(v)` | CPL trung bình, chỉ tính trên campaign có DAU≥100 và có spend data |
| `renderMonthlyTrend(v)` / `renderMonthlyCPLTrend(v)` | 2 chart xu hướng CR/CPL, có chip "Theo tháng / Theo ngày" (`trendChip()`, state `trendViewMode`). Theo ngày dùng `computeDailyCR`/`computeDailyCPL` + `daysForSelectedMonth()` (lọc theo top filter, dữ liệu lấy từ `DAILY_SUMMARY`/`SPEND_BY_DAY` — full history từ `data/daily-snapshot.json`, không phải rolling window). Hover bar hiện tooltip qua CSS `.daybar-wrap:hover .daybar-tip` (không dùng `title=` vì có độ trễ hover). Kèm `gapSentence(...)` diễn giải khoảng cách so goal (luôn dựa trên 30-ngày, không đổi theo chip). |
| `computeNetworkSplit(v)` / `renderChannelSplit(v)` | **Mới:** 2 chart Facebook vs Google (trước đây là Display vs Paid Search — đã đổi theo yêu cầu). Aggregate từ campaign-level rows qua `campaignNetwork()`. Đặt bên trong panel Campaign Detail, dưới `<h2>` và trên thanh search/filter. |
| `renderSupplyDemandCheck(v)` | Panel Cross-check Marketplace Supply-Demand — 4 metric threshold-gated (Ad/Buyer Coverage ≥0.70, Demand Balance ≥0.50, Supply Balance ≥1.0) + 2 metric chẩn đoán không-threshold (Conversion issue %, Demand issue %). Data này vẫn là snapshot tĩnh 1 ngày trong `SUPPLY_DEMAND_METRICS`, **chưa tự động hoá** (khác với phần 30-ngày đã live). Ý nghĩa 2 metric chẩn đoán được note ngay dưới badge khỏe/yếu bằng bullet list ngắn gọn — action đúng khi cao là Category/Sales/Product cải thiện chất lượng tin/matching, KHÔNG phải giảm traffic marketing (giữ nguyên câu Việt này khi sửa, đã tinh chỉnh ngắn gọn qua vài vòng feedback).
| `getActiveCampaignRows(v)` | Nguồn data campaign-level theo `selectedMonth` (last30 / ytd / theo tháng cụ thể). Đã filter: (1) loại `EXCLUDED_CAMPAIGNS`/`EXCLUDED_NAME_PATTERN` (chứa "install"), (2) loại campaign có `campaignVerticalShare < 0.5` (đa số traffic thuộc vertical khác — tránh CPL bị thổi phồng vì spend không chia theo vertical). |
| `campaignNetwork(name, channel)` | Heuristic phân loại Google/Facebook/Khác dựa tên campaign: `_gg_/pmax/dsa/demandgen/_google_` → Google; `_fb_/b2s.surround` → Facebook; tên chứa "search" → Google; **Display + tên chứa "clicklink"** → Facebook (mới thêm); còn lại → Khác. |
| `campaignVerticalShare(campaign, v)` | % DAU của campaign thuộc vertical `v` so với tổng DAU (mọi vertical) — dùng để loại minority-vertical campaigns khỏi bảng, và cảnh báo ⚠️ CPL bị thổi phồng khi share < 0.3 trong drawer. |
| `renderTable(v)` | Bảng Campaign Detail — cột: Campaign, Channel, DAU, DAU w/Lead, Total Lead, CR→Lead, CPL. CSS đã tighten (padding 6px, không giới hạn max-width tên campaign) để tên full hiện trên 1 dòng, hạn chế wrap. |
| `computeRecentAnomaly(name, v, currentCr)` | **Quan trọng — sinh root-cause/fix cho từng campaign trong drawer.** Dựa vào swing MoM của CR/CPL (ngưỡng ±15%) map vào decision-tree của skill `paid-ads` (đã đánh giá và loại 3 skill khác không phù hợp: `out-app-campaign-eval` chỉ dành app-install, `fb-ads` là skill vận hành không phải chẩn đoán, `marketing-demand-acquisition` là framework B2B SaaS phương Tây không áp dụng cho marketplace VN). Có catch-all đảm bảo **MỌI campaign đang đỏ (CR dưới goal) đều có root-cause/fix**, kể cả khi: (a) chưa đủ data trend theo tháng, (b) swing không rơi vào bad/bad hay bad/ok rõ ràng, (c) **cả CR và CPL đều đang cải thiện (crGood && cplGood) nhưng vẫn còn đỏ** — case này bị thiếu ở 2 vòng fix đầu, tới vòng fix thứ 3 mới bắt được qua test trực tiếp toàn bộ campaign đỏ ở cả 4 vertical (xem "Cách test" bên dưới). Mỗi note luôn có disclaimer cuối: suy luận dựa trên decision-tree skill `paid-ads`, chưa xác nhận qua campaign ID thật trên Ads Manager. |
| `openDrawer(campaign, v)` | Popup chi tiết: funnel, root-cause (`computeRecentAnomaly`), landing page (vertical-scoped qua `LANDING_PAGES[name][v]`), CPL + cảnh báo cross-vertical. |
| `renderSegmentDemand(v)` | **Mới:** bảng Segment Demand-Supply, đặt giữa Supply-Demand panel và Campaign Detail. Đọc `SEGMENT_DEMAND[v]` (chỉ có key `pty` hiện tại — verticals khác function trả về chuỗi rỗng, không render gì). Cột `% Digital` (màu xanh ≥30%, vàng 15-30%, đỏ <15%) là phần mới nhất, tính riêng ở `scripts/update_snapshot.py`, KHÔNG tính trong browser. |
| `render()` | Thứ tự render hiện tại: `monthNote + renderCards + renderMonthlyTrend + renderMonthlyCPLTrend + renderSupplyDemandCheck + renderSegmentDemand + renderTable` (renderTable tự chèn `renderChannelSplit` bên trong nó). |

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

## Cách đối chiếu goal (GOALS/H2_GOALS/GOALS_MONTHLY) với deck

Deck "Chợ Tốt — App Growth Direction 2026" (artifact Claude, link trong lịch sử chat — search "App Growth Direction 2026" nếu cần tìm lại) mới là nguồn số target thật, không phải BigQuery. Muốn đối chiếu:

1. Đọc artifact, tìm biến JS `d1_data` (data theo tháng, mảng 12 phần tử mỗi field: `daus`, `dauwlead`, `leads`, `budget`, `cplead`, `cpdwl`...) và `d1_vert` (bảng tổng hợp H1/H2/FY, field `cost.cplead/cpdau/cpdwl/cpmau/cpmwl` và `conv.pctdwl`) trong section 04 "App growth" → driver 1 "Digital campaigns".
2. `GOALS_MONTHLY[v].cpl["2026-XX"]` phải khớp CHÍNH XÁC `d1_data[v].cplead[thángXX-1]` (index 0 = tháng 1). Tương tự `cr` khớp `dauwlead[i]/daus[i]`.
3. `H2_GOALS[v]` = cột "H2 (FC2)" trong `d1_vert[v].cost` (index 1 trong mảng 3 phần tử `[H1, H2, FY]`). `cr` thì tự tính `sum(dauwlead tháng 7-12) / sum(daus tháng 7-12)` từ `d1_data` — chính xác hơn % làm tròn 1 chữ số hiển thị trong deck.
4. `GOALS[v]` (annual/FY) = cột FY (index 2) trong `d1_vert[v].cost`, cùng cách tính `cr` như trên nhưng sum cả 12 tháng.
5. Sau khi sửa số, luôn `node --check` + test trong browser (in `monthlyGoal('pty','2026-08')` ra console, so với kỳ vọng) trước khi push.

## Việc còn dang dở / để ý khi làm tiếp

- `SUPPLY_DEMAND_METRICS` vẫn là snapshot tĩnh 1 ngày, chưa tự động hoá qua GitHub Actions — chỉ phần 30-ngày, theo-tháng, theo-ngày, và segment demand PTY (funnel/campaign/spend) đã live.
- `data/segment-demand.json` chỉ có PTY — veh/gds/jobs chưa có bảng `transform__..._effectiveness_daily` tương đương từ mkt-director. Khi có, thêm cùng logic vào `update_snapshot.py` (đổi tên bảng + category range + tier logic cho vertical đó) và `SEGMENT_DEMAND[v]` sẽ tự động render vì `renderSegmentDemand()` đã generic theo `v`.
- Phần theo-tháng chỉ re-query tháng hiện tại mỗi lần chạy (rẻ, ~1-1.5GB) — nếu cần backfill lại một tháng đã qua vì phát hiện lỗi data, phải tự chạy tay 1 lần (sửa `DATE_TRUNC(CURRENT_DATE(), MONTH)` thành tháng cụ thể trong query, chạy 1 lần, rồi trả lại code gốc — đừng để logic backfill này chạy default mỗi ngày vì sẽ tốn lại full-year cost).
- `campaignNetwork()` là heuristic theo tên, không phải mapping thật từ Ads Manager — sẽ có sai số với campaign đặt tên không theo convention. Mỗi lần user báo case sai (vd: "search" → Google, "clicklink"+Display → Facebook) thì thêm rule mới vào đúng function này, luôn test lại toàn bộ danh sách campaign trước khi push để tránh regression.
- CPL/Landing/Audience mới cover subset campaign có spend data — phần còn lại thiếu nguồn.
- Chưa tra được Meta campaign thật cho nhóm job theo vai trò.
- Root-cause trong `computeRecentAnomaly` là suy luận theo pattern (paid-ads decision tree), KHÔNG phải chẩn đoán đã xác nhận — luôn giữ disclaimer line, không bỏ.
- Khi user yêu cầu thay đổi UI/copy, ưu tiên chỉnh ngắn gọn — đã có nhiều vòng feedback yêu cầu bớt chữ, bớt câu thừa (vd: bỏ "(TB năm)", "Ref:", bỏ câu note trùng lặp trong Supply-Demand panel).

## Muốn sửa/thêm gì thì sửa ở đâu

| Muốn làm | Sửa ở |
|---|---|
| Đổi UI, thêm chart, sửa cách tính CPL, sửa filter, sửa network classification... | `index.html` (bảng function ở trên) |
| Đổi khung thời gian, thêm field mới vào snapshot 30 ngày hoặc theo-tháng | `scripts/update_snapshot.py` **và** `loadStaticSnapshot()` trong `index.html` phải khớp nhau |
| Đổi giờ chạy cron | `.github/workflows/update-dashboard.yml`, dòng `cron:` (giờ UTC, VN = UTC+7) |
| Thêm data mới không nằm trong rolling-30-ngày hay theo-tháng (vd: quarterly, custom range) | Viết thêm query trong `update_snapshot.py`, field mới trong JSON, và merge logic tương ứng trong `loadStaticSnapshot()` |
| Đổi target CPL/CR/CP DAU/DwL/MAU/MwL | `GOALS_MONTHLY`/`H2_GOALS`/`GOALS` trong `index.html` — LUÔN lấy số từ deck "App Growth Direction 2026", xem "Cách đối chiếu goal với deck" ở trên, không tự chế số |
| Thêm segment demand cho vertical khác ngoài PTY | Phần "PTY SEGMENT DEMAND" trong `update_snapshot.py` — cần bảng `transform__..._effectiveness_daily` tương đương từ team đó trước, rồi lặp lại logic (đổi category range + tier CASE cho đúng vertical) |

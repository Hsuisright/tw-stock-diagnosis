# V1.5 變更紀錄

## NEXT PHASE：V1.5 Data Independence

逐步將目前 FinMind-derived EPS production dataset 遷移至授權明確的官方或自有資料管線。本輪只記錄此技術債，未變更 EPS。

## 籌碼壓力（Positioning Pressure）MVP

- 新增融資、融券與（資料合格時的）借券市場部位觀察。
- 新增空方壓力、空方回補、多方擁擠、多方去槓桿、雙向擁擠與壓力釋放等固定規則狀態。
- 每個狀態都顯示可追溯的價格、量能與餘額變化證據；不代表因果證明。
- 不納入 TRS，不建立投資總分，也不產生買賣建議。
- 公開精簡資料由 GitHub Actions 每日更新；本機與 Streamlit Cloud 讀取相同版本化資料。
- 借券目前未納入第一版狀態：FinMind 公開回應已驗證為交易資料，尚無可比較的每日餘額欄位。

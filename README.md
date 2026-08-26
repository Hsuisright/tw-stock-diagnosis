# 台股個股診斷公開版

這是無持倉、無帳戶、無成本資料的 Streamlit 個股診斷網站。使用者輸入台股代號後，系統會下載公開歷史價格與 P/E，計算估值溫度、正常 P/E 參考價格、市場隱含成長壓力或獲利緩衝，以及布林通道位階。

## 本機執行

```powershell
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run quick_app.py --server.port 8502
```

## 雲端部署

將本資料夾單獨建立為 Git repository，部署入口指定為 `quick_app.py`。若使用 FinMind Token，請在部署平台的祕密環境變數中設定 `FINMIND_TOKEN`，不要寫入程式或上傳到 Git。

網站執行期間只會在 `data/quick_analysis.db` 建立公開市場資料快取；此資料庫不含個人持倉資料，且已由 `.gitignore` 排除。

## 注意事項

- 資料來源為公開市場資料；公開營運前仍須確認來源的使用條款、額度及轉載規定。
- 免費雲端環境的本機快取可能在重新啟動後消失，這不影響個人資料，僅會重新抓取市場資料。
- 本工具為歷史比較與市場期待診斷，不構成投資建議。

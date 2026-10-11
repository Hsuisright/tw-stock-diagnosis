# V1.6 PDF 字型

原始 Noto Sans TC variable TTF 與 OFL.txt 來自 Google Fonts 官方倉庫。來源 URL、原檔與衍生檔 SHA256 見 provenance.json；保留 Adobe 原始版權及完整 SIL Open Font License 1.1。

`V16ReportTC-Regular.ttf` 是 fontTools 固定 wght=400 的衍生版本。主要字型名稱改為 V16 Report TC，不使用授權保留名稱 Source。衍生字型繼續依 OFL 1.1 散布；不得單獨販售字型。OFL 允許隨軟體提供與嵌入 PDF，報告文件本身不受字型 OFL 授權限制。

部署須一併保留 Regular.ttf、OFL.txt、provenance.json；執行時不下載字型、不依賴 Windows 系統字型。字型 OS/2 fsType=0，PDF 測試驗證 FontFile2 嵌入。字型缺失或雜湊失敗即停止產生 PDF，不默默代換。

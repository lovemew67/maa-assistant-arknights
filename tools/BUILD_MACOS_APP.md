# 在 Apple Silicon (M4 / M 系列) Mac 上編譯與運行 MAA ZZH.app

本文檔介紹如何在 Apple Silicon (M1/M2/M3/M4) Mac 上從原始碼構建自訂命名的原生應用程式 `MAA ZZH.app` 並直接執行使用。

---

## 一、環境需求與安裝

編譯原生 `MAA ZZH.app` 需要完整版 Xcode 與基礎建構工具。

### 1. 安裝 Xcode
1. 開啟 Mac **App Store**，搜尋並安裝 **Xcode**。
2. 安裝完成後，開啟終端機執行以下指令，將開發者工具路徑切換至 Xcode.app：
   ```bash
   sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
   ```
3. 接受 Xcode 授權條款：
   ```bash
   sudo xcodebuild -license accept
   ```

### 2. 透過 Homebrew 安裝工具
在終端機中執行：
```bash
brew install cmake ninja
```

---

## 二、一鍵編譯與安裝

倉庫已提供專門構建 `MAA ZZH.app` 的自動化腳本 [tools/build_macos_app.sh](file:///Users/zzh/Golang/gopath/src/github.com/MaaAssistantArknights/MaaAssistantArknights/tools/build_macos_app.sh)。

### 1. 編譯並直接安裝至 ｢應用程式｣ 目錄（推薦）
```bash
./tools/build_macos_app.sh --install
```
腳本完成後會自動將應用程式以 `MAA ZZH.app` 命名安裝至 `/Applications/` 並清除 macOS 隔離屬性，您可以直接從 Launchpad（啟動台）或 Spotlight 搜尋 ｢MAA ZZH｣ 點擊開啟使用。

### 2. 僅編譯至本地 dist 目錄
```bash
./tools/build_macos_app.sh
```
編譯產物將生成於 `./dist/MAA ZZH.app`，您可以直接雙擊執行：
```bash
open ./dist/"MAA ZZH.app"
```

### 3. 清理舊快取並重新編譯
```bash
./tools/build_macos_app.sh --clean --install
```

---

## 三、常見問題排查 (Q&A)

### 1. 提示 ｢xcodebuild requires Xcode, but active developer directory is CommandLineTools...｣
- **原因**：目前系統指向的是輕量版的 CommandLineTools，缺少 Xcode 完整工具鏈。
- **解決方法**：安裝 Xcode.app 後執行：
  ```bash
  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
  ```

### 2. 提示 ｢無法開啟 "MAA ZZH.app"，因為無法驗證開發者｣
- **原因**：本機編譯使用的是 Ad-Hoc 自簽名。
- **解決方法**：
  在終端機中執行清除隔離屬性指令：
  ```bash
  xattr -cr /Applications/"MAA ZZH.app"
  ```
  或至 macOS ｢系統設定｣ -> ｢隱私權與安全性｣ 點擊 ｢仍要打開｣。

### 3. 提示 ｢Ld ... Objects-normal/x86_64/Binary/MAA normal x86_64｣ 失敗
- **原因**：Xcode 預設嘗試編譯 Universal 二進制檔（包含 x86_64），但本地環境只構建了 arm64 的 MaaCore。
- **解決方法**：已在腳本中鎖定僅編譯目標架構（`ARCHS=arm64 ONLY_ACTIVE_ARCH=YES`）並隔離專案 DerivedData，直接重新執行腳本即可。

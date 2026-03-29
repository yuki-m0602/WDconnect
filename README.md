# WDConnect

[WDConnect.exe（最新）](https://github.com/yuki-m0602/WDConnect_1/releases/latest/download/WDConnect.exe) · [scrcpy（公式 Releases）](https://github.com/Genymobile/scrcpy/releases) · [Android SDK Platform-Tools（adb）](https://developer.android.com/studio/releases/platform-tools)

Android の **ワイヤレスデバッグ** のセットアップと接続を、デスクトップからまとめて行うためのツールです。軽量な **Logcat ビュー** の表示や、**scrcpy** による画面ミラーリング（任意）にも対応します。GUI は **Tkinter**（Python 標準ライブラリ）で実装されています。

---

## 主な機能

- **ワイヤレスデバッグ** — ペアリング・接続・デバイス管理
- **ADB** — 実行ファイルの指定、デバイス一覧の確認
- **軽量 Logcat** — ログの表示・フィルタリング
- **scrcpy**（任意）— インストールパスを指定して起動

---

## 動作環境

| 項目 | 内容 |
|------|------|
| OS | Windows を想定（起動用 `.bat` / `.ps1` 同梱） |
| Python | 3.9 以上を推奨（ソース実行・ビルド時） |
| ADB | [Android SDK Platform-Tools](https://developer.android.com/studio/releases/platform-tools) から `adb` を入手し、アプリ内でパスを指定 |
| scrcpy | 任意 — 画面ミラーを使う場合、[公式 Releases](https://github.com/Genymobile/scrcpy/releases) から入手 |

設定は作業ディレクトリに `wireless_debug_config.json` として保存されます（リポジトリには含めない運用を推奨します）。

---

## ダウンロード（Windows）

事前ビルド済みの実行ファイルは **Releases** から入手できます。

**[最新の WDConnect.exe をダウンロード](https://github.com/yuki-m0602/WDConnect_1/releases/latest/download/WDConnect.exe)**

ダウンロード後はダブルクリックで起動できます（ADB 等の準備は上記「動作環境」を参照）。

---

## ソースから実行

1. リポジトリをクローン、または ZIP を展開します。
2. 依存関係をインストールします。

   ```bash
   pip install -r requirements.txt
   ```

3. 次のいずれかで起動します。

   ```bash
   python run_light_logcat.py
   ```

   - Windows: `run_light_logcat.bat` または `run_light_logcat.ps1` でも起動できます。

---

## Windows 向け EXE のビルド

PyInstaller で単体 EXE を作成する場合の例です。

```bash
pip install -r requirements.txt
build_light_logcat.bat
```

ビルド成果物は `WDconnect_light_logcat.spec` の `name` 設定に従い、現状は `dist\WDConnect.exe` に出力されます。

---

## リポジトリ構成

| パス | 説明 |
|------|------|
| `run_light_logcat.py` | アプリのエントリポイント |
| `main_light_logcat.py` | メインウィンドウ・アプリ本体 |
| `logcat_widget_light.py` | 軽量 Logcat UI |
| `WDconnect_light_logcat.spec` | PyInstaller の設定 |
| `build_light_logcat.bat` | EXE ビルド用バッチ |
| `WDCONNECT_STANDALONE.md` | 単体プロジェクト化・移行時のメモ（開発者向け） |

---

## トラブルシューティング（よくあること）

- **ADB が見つからない** — `platform-tools` をインストールし、アプリ内で `adb` のパスを指定してください。
- **デバイスに接続できない** — USB デバッグ・ワイヤレスデバッグの有効化、同一ネットワーク、ペアリングコードの入力ミスがないか確認してください。

---

## 貢献・フィードバック

Issue や Pull Request での指摘・改善提案を歓迎します。

---

## ライセンス

[MIT License](LICENSE) — 再利用・改変・再配布が比較的容易で、GitHub 上の OSS でも採用例が多いライセンスです。

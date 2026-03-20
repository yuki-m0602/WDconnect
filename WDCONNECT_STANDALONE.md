# WDConnect（ライト版）— 単体プロジェクト継続ガイド

本ドキュメントは、現在本リポジトリで「本筋」となっている **ライト版（Wireless Debug + 軽量 Logcat）** を、**別リポジトリとして `WDConnect` 名で継続開発する**ための整理用です。コード変更は含めず、移行時の判断材料とチェックリストとして使います。

---

## 1. プロダクトの定義

| 項目 | 内容 |
|------|------|
| **役割** | Android ワイヤレスデバッグの設定・接続管理、オプションで scrcpy、軽量 logcat 表示 |
| **エントリ** | `run_light_logcat.py` → `main_light_logcat.main()` |
| **GUI** | Tkinter（標準ライブラリ） |
| **設定ファイル** | 作業ディレクトリの `wireless_debug_config.json`（読み書き） |

ウィンドウタイトル等の表記は現状 `WDconnect Light` ですが、新プロジェクト名を **WDConnect** に揃える場合は、文言・EXE 名・spec 出力名を一括で合わせると一貫します（任意）。

---

## 2. 新リポジトリに含めるファイル（必須）

以下は **相互依存が閉じており**、他の `main.py` / `gui.py` / `logcat_widget.py`（非 light）に依存しません。

| ファイル | 役割 |
|----------|------|
| `main_light_logcat.py` | メインアプリ本体（`LightWDconnectApp`） |
| `logcat_widget_light.py` | 軽量 logcat UI（`LightLogcatWidget`） |
| `run_light_logcat.py` | 起動用ラッパー（PyInstaller 時のパス解決あり） |

**推奨で同梱するスクリプト**

| ファイル | 役割 |
|----------|------|
| `run_light_logcat.bat` | Windows 向け起動 |
| `run_light_logcat.ps1` | PowerShell 向け起動 |
| `build_light_logcat.bat` | PyInstaller ビルド（下記 spec 参照） |

---

## 3. 含めない（旧版・別ライン）の目安

単体プロジェクトにするなら、次は **必須ではありません**（重複・混乱の元になるため、原則コピーしない）。

- `main.py`, `gui.py`, `logic.py`, `config.py` — 旧構成のメインライン
- `main_with_logcat.py`, `main_advanced_logcat.py`, `run_advanced_logcat.py`, `run_logcat.py` 等 — 別エディション
- `logcat_widget.py` — 非 light の logcat ウィジェット
- `wireless_debug_tool_compact.py` — 参考用の単一ファイル版
- `BUILD_LOGCAT.md`, `BUILD_ADVANCED_LOGCAT.md` — 別ビルド向けドキュメント

必要なら、ライセンスやクレジットの一文だけ新 `README` に残す程度で十分です。

---

## 4. 依存関係

### 4.1 Python

- **言語**: Python 3（既存は 3.6 以上想定の記述あり。新環境では 3.9+ 推奨）
- **標準ライブラリ**: `tkinter`, `subprocess`, `threading`, `json`, `re`, `socket` 等  
  ライト版のコアは **PyPI パッケージ必須ではない**（`requests` は `main_light_logcat` では未使用）

### 4.2 外部ツール（ユーザー環境）

- **ADB**（`platform-tools` の `adb`）— 自動検出または手動パス
- **scrcpy**（任意）— 画面ミラーリング

### 4.3 ビルド（EXE 化）

- **PyInstaller** — `build_light_logcat.bat` が `python -m PyInstaller WDconnect_light_logcat.spec` を呼び出す想定

---

## 5. PyInstaller と `.spec` について（重要）

- 本リポジトリの `.gitignore` では **`*.spec` が無視**されています。そのため **`WDconnect_light_logcat.spec` がリポジトリに無い**状態でも開発できる一方、**別リポジトリで継続するなら spec はバージョン管理に含める**ことを強く推奨します。
- 新 `WDConnect` リポジトリでは次を推奨します。
  1. 動作している `WDconnect_light_logcat.spec` を取得・コミットする  
  2. `.gitignore` から `*.spec` を外す、または `!WDconnect_light_logcat.spec` のように例外を書く  
  3. 成果物名を `WDConnect.exe` 等に変える場合は **spec の `name` / `exe` 設定と `build_*.bat` を揃える**

---

## 6. 新リポジトリ作成 — チェックリスト

1. **空の Git リポジトリ**を作成し、上記「含めるファイル」を追加する  
2. **`README.md`** をライト版向けに書き直す（起動コマンド: `python run_light_logcat.py`）  
3. **`requirements.txt`** を整理する（実行のみなら `pyinstaller` のみ、または `[dev]` と分ける）  
4. **`WDconnect_light_logcat.spec`（または改名した spec）をコミット**する  
5. **`.gitignore`** を見直す（`dist/`, `build/` は無視のまま、spec は追跡）  
6. **設定ファイル**: `wireless_debug_config.json` はユーザー環境に生成されるため、リポジトリには含めない（`.gitignore` 推奨）  
7. **ライセンス**: 元リポジトリから分離する場合はライセンスファイルを明示する  
8. （任意）クラス名・ウィンドウタイトル・EXE 名を **WDConnect** に統一  

---

## 7. 推奨ディレクトリ構成（例）

```
WDConnect/
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── WDconnect_light_logcat.spec   # 名前はプロジェクトに合わせて変更可
├── run_light_logcat.py
├── main_light_logcat.py
├── logcat_widget_light.py
├── run_light_logcat.bat
├── run_light_logcat.ps1
└── build_light_logcat.bat
```

将来的に `src/` 配下へ移す場合は、`run_light_logcat.py` のパス解決と import を合わせて調整します。

---

## 8. 元リポジトリ側の扱い（参考）

- 歴史的コード（フル版・Advanced 版）を **アーカイブ用に残す**  
- または **WDConnect を正とし、本リポジトリはメンテナンス終了**と README に明記する  

運用方針はチームの好みで問題ありません。重要なのは **どちらが canonical か** を README で一箇所に書くことです。

---

## 9. 変更が必要になりうる箇所（リネーム時）

ブランドを **WDConnect** に統一する場合、grep で確認するとよい文字列の例です。

- `main_light_logcat.py`: `root.title(...)`、`LightWDconnectApp` 等の表示名  
- `run_light_logcat.py`: モジュール docstring  
- `build_light_logcat.bat`: 出力パス `dist\WDconnect_Light_Logcat.exe`  
- PyInstaller `.spec` 内の `name` とアイコン指定  

本ドキュメントは移行の「設計メモ」です。実際のリネームやファイル追加は、別途タスクとして実施してください。

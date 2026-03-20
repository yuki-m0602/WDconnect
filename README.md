# WDConnect（ライト版バンドル）

Android ワイヤレスデバッグ＋軽量 Logcat の Tkinter アプリです。  
このフォルダはリポジトリ内にまとめた **単体移動用** です。親ディレクトリ（例: `AndroidStudioProjects`）へフォルダごと移動して、そこで `git init` する想定です。

## 起動

```bash
python run_light_logcat.py
```

Windows: `run_light_logcat.bat` または `run_light_logcat.ps1`

## ビルド（EXE）

```bash
pip install -r requirements.txt
build_light_logcat.bat
```

成果物: `dist\WDconnect_Light_Logcat.exe`

## 同梱ファイル

| ファイル | 説明 |
|----------|------|
| `main_light_logcat.py` | メインアプリ |
| `logcat_widget_light.py` | 軽量 Logcat UI |
| `run_light_logcat.py` | エントリ（PyInstaller もこれを起点） |
| `WDconnect_light_logcat.spec` | PyInstaller 設定 |
| `build_light_logcat.bat` | ビルド用バッチ |

詳細は `WDCONNECT_STANDALONE.md` を参照。

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WDconnect Light - Android Wireless Debug Tool with Light Logcat
軽量版のAndroidワイヤレスデバッグツール（ログキャット機能付き）
"""

import sys
import os

# PyInstallerでバンドルされた場合のパス設定
if getattr(sys, 'frozen', False):
    # PyInstallerでバンドルされた場合
    application_path = sys._MEIPASS
else:
    # 通常のPython実行の場合
    application_path = os.path.dirname(os.path.abspath(__file__))

# パスを追加
sys.path.insert(0, application_path)

# メインモジュールをインポート
try:
    from main_light_logcat import main
except ImportError as e:
    print(f"エラー: 必要なモジュールが見つかりません: {e}")
    print(f"現在のパス: {application_path}")
    print("main_light_logcat.pyファイルが同じディレクトリにあることを確認してください。")
    sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nアプリケーションを終了します。")
        sys.exit(0)
    except Exception as e:
        print(f"予期しないエラーが発生しました: {e}")
        sys.exit(1) 
@echo off
chcp 65001 > nul
echo WDconnect Light Logcat ビルド開始...
echo.

REM 既存のビルドファイルを削除
if exist "dist\WDconnect_Light_Logcat.exe" (
    echo 既存の実行ファイルを削除中...
    del /f /q "dist\WDconnect_Light_Logcat.exe"
)

if exist "build" (
    echo ビルドディレクトリを削除中...
    rmdir /s /q "build"
)

echo.
echo PyInstallerでビルド中...
python -m PyInstaller WDconnect_light_logcat.spec

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ビルド成功！
    echo 実行ファイル: dist\WDconnect_Light_Logcat.exe
    echo.
    echo 軽量版の特徴:
    echo - ファイルサイズ: 大幅に削減
    echo - 起動速度: 高速化
    echo - メモリ使用量: 最適化
    echo - 基本機能: ログキャット、レベルフィルター、検索
    echo.
    pause
) else (
    echo.
    echo ビルド失敗！
    echo エラーコード: %ERRORLEVEL%
    echo.
    pause
) 
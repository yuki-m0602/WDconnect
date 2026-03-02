import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import threading
import os
import sys
import re
import json
import time
from typing import Optional
from logcat_widget_light import LightLogcatWidget

class LightWDconnectApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WDconnect Light - Android Wireless Debug Tool")
        self.lock_window_size = True
        self.root.geometry("720x320")
        self.root.minsize(720, 320)
        self.root.maxsize(720, 320)
        self.root.resizable(False, False)
        
        # ADB設定
        self.adb_path = None
        self.devices = []
        self.selected_device = None
        
        # SCRCPY設定
        self.scrcpy_path = None
        self.scrcpy_process = None
        self.is_scrcpy_running = False
        
        # ワイヤレスデバッグ設定
        self.wireless_ip = None
        self.wireless_port = "5555"
        
        # ウィジェット
        self.logcat_widget = None
        
        # 設定用変数
        self.logcat_window_size = "900x700"  # Android Studio風のサイズ
        self.logcat_theme = "android_studio"
        
        # ADBコマンド実行用のロック（スレッドセーフティ）
        self.adb_lock = threading.Lock()
        
        # 接続監視用変数
        self.is_monitoring = False
        self.monitor_thread = None
        self.last_connected_device = None
        self.connection_check_interval = 5  # 5秒間隔でチェック
        
        self.setup_ui()
        self.load_settings()
        
        # 設定が読み込まれていない場合のみ自動検出
        if not self.adb_path:
            self.detect_adb()
        if not self.scrcpy_path:
            self.detect_scrcpy()
            
        # 初期設定を保存
        self.save_settings()
        
    def setup_ui(self):
        """軽量なUIを設定"""
        # メインフレーム
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        
        # タイトル
        title_label = ttk.Label(main_frame, text="WDconnect Light", font=("Arial", 13, "bold"))
        title_label.pack(pady=(0, 10))
        
        # ADB設定フレーム
        adb_frame = ttk.LabelFrame(main_frame, text="ADB設定", padding="5")
        adb_frame.pack(fill=tk.X, pady=(0, 10))
        
        # ADBパス設定
        adb_path_frame = ttk.Frame(adb_frame)
        adb_path_frame.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(adb_path_frame, text="ADBパス:").pack(side=tk.LEFT)
        self.adb_path_var = tk.StringVar()
        self.adb_path_entry = ttk.Entry(adb_path_frame, textvariable=self.adb_path_var, width=40)
        self.adb_path_entry.pack(side=tk.LEFT, padx=(5, 5), fill=tk.X, expand=True)
        
        ttk.Button(adb_path_frame, text="参照", command=self.browse_adb).pack(side=tk.LEFT)
        ttk.Button(adb_path_frame, text="検出", command=self.detect_adb).pack(side=tk.LEFT, padx=(5, 0))
        
        # デバイス選択
        device_frame = ttk.Frame(adb_frame)
        device_frame.pack(fill=tk.X, pady=(4, 0))
        
        ttk.Label(device_frame, text="デバイス:").pack(side=tk.LEFT)
        self.device_combo = ttk.Combobox(device_frame, state="readonly", width=24)
        self.device_combo.pack(side=tk.LEFT, padx=(5, 5))
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_select)
        
        ttk.Button(device_frame, text="更新", command=self.refresh_devices).pack(side=tk.LEFT)
        
        # 接続状態
        self.status_label = ttk.Label(adb_frame, text="未接続", foreground="red")
        self.status_label.pack(pady=(5, 0))
        
        # USB接続管理フレーム
        usb_frame = ttk.LabelFrame(main_frame, text="USB接続管理", padding="5")
        usb_frame.pack(fill=tk.X, pady=(0, 10))
        
        # USB接続ボタン
        usb_buttons_frame = ttk.Frame(usb_frame)
        usb_buttons_frame.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Button(usb_buttons_frame, text="USB接続確認", command=self.check_usb_connection).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(usb_buttons_frame, text="ワイヤレスデバッグ有効化＆接続", command=self.enable_wireless_debug).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(usb_buttons_frame, text="ポートスキャン", command=self.scan_port_manual).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(usb_buttons_frame, text="手動ワイヤレス接続", command=self.connect_wireless).pack(side=tk.LEFT)
        
        # ワイヤレス設定
        wireless_frame = ttk.Frame(usb_frame)
        wireless_frame.pack(fill=tk.X, pady=(4, 0))
        
        ttk.Label(wireless_frame, text="IPアドレス:").pack(side=tk.LEFT)
        self.ip_var = tk.StringVar()
        self.ip_entry = ttk.Entry(wireless_frame, textvariable=self.ip_var, width=12)
        self.ip_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Label(wireless_frame, text="ポート:").pack(side=tk.LEFT)
        self.port_var = tk.StringVar(value="5555")
        self.port_entry = ttk.Entry(wireless_frame, textvariable=self.port_var, width=6)
        self.port_entry.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(wireless_frame, text="ADB+", width=5, command=self.copy_adb_connect_command).pack(side=tk.LEFT, padx=(6, 0))
        
        # ワイヤレス状態
        self.wireless_status_label = ttk.Label(usb_frame, text="ワイヤレス未接続", foreground="red")
        self.wireless_status_label.pack(pady=(5, 0))
        
        # SCRCPY設定フレーム
        scrcpy_frame = ttk.LabelFrame(main_frame, text="SCRCPY設定", padding="5")
        scrcpy_frame.pack(fill=tk.X, pady=(0, 10))
        
        # SCRCPYパス設定
        scrcpy_path_frame = ttk.Frame(scrcpy_frame)
        scrcpy_path_frame.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(scrcpy_path_frame, text="SCRCPYパス:").pack(side=tk.LEFT)
        self.scrcpy_path_var = tk.StringVar()
        self.scrcpy_path_entry = ttk.Entry(scrcpy_path_frame, textvariable=self.scrcpy_path_var, width=40)
        self.scrcpy_path_entry.pack(side=tk.LEFT, padx=(5, 5), fill=tk.X, expand=True)
        
        ttk.Button(scrcpy_path_frame, text="参照", command=self.browse_scrcpy).pack(side=tk.LEFT)
        ttk.Button(scrcpy_path_frame, text="検出", command=self.detect_scrcpy).pack(side=tk.LEFT, padx=(5, 0))
        
        # SCRCPYコントロール
        scrcpy_control_frame = ttk.Frame(scrcpy_frame)
        scrcpy_control_frame.pack(fill=tk.X, pady=(4, 0))
        
        self.scrcpy_start_button = ttk.Button(scrcpy_control_frame, text="SCRCPY開始", command=self.start_scrcpy)
        self.scrcpy_start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.scrcpy_stop_button = ttk.Button(scrcpy_control_frame, text="SCRCPY停止", command=self.stop_scrcpy, state=tk.DISABLED)
        self.scrcpy_stop_button.pack(side=tk.LEFT)
        
        # ログキャットボタン
        logcat_frame = ttk.LabelFrame(main_frame, text="ログキャット", padding="5")
        logcat_frame.pack(fill=tk.X, pady=(0, 6))
        
        logcat_button = ttk.Button(logcat_frame, text="📱 ログキャットを開く", command=self.open_logcat_window)
        logcat_button.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(logcat_frame, text="ログキャットウィンドウを別ウィンドウで開きます").pack(side=tk.LEFT)
        
        # ログキャットウィンドウの参照
        self.logcat_window = None
        self.logcat_widget = None
        
    def run_adb_command(self, args, timeout=10, retry_on_timeout=True):
        """タイムアウト付きで安全にADBコマンドを実行
        
        Args:
            args: ADBコマンドの引数リスト
            timeout: タイムアウト秒数（デフォルト10秒）
            retry_on_timeout: タイムアウト時に再試行するか
            
        Returns:
            subprocess.CompletedProcess: 実行結果
            None: エラー発生時
        """
        if not self.adb_path:
            print("エラー: ADBパスが設定されていません")
            return None
        
        with self.adb_lock:
            try:
                cmd = [self.adb_path] + args
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    encoding='utf-8',
                    errors='replace'
                )
                return result
                
            except subprocess.TimeoutExpired:
                print(f"ADBコマンドがタイムアウトしました: {' '.join(args)}")
                
                if retry_on_timeout:
                    print("ADBサーバーをリセットして再試行します...")
                    if self.reset_adb_server():
                        # リセット後に再試行（再帰呼び出しを防ぐためretry_on_timeout=False）
                        return self.run_adb_command(args, timeout=timeout, retry_on_timeout=False)
                
                return None
                
            except Exception as e:
                print(f"ADBコマンド実行エラー: {e}")
                return None
    
    def reset_adb_server(self):
        """ADBサーバーをリセット
        
        Returns:
            bool: 成功したかどうか
        """
        try:
            print("ADBサーバーを停止中...")
            subprocess.run([self.adb_path, "kill-server"], 
                         capture_output=True, timeout=5)
            time.sleep(1)
            
            print("ADBサーバーを起動中...")
            result = subprocess.run([self.adb_path, "start-server"], 
                                  capture_output=True, timeout=10)
            
            if result.returncode == 0:
                print("ADBサーバーのリセットに成功しました")
                return True
            else:
                print(f"ADBサーバーの起動に失敗: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"ADBサーバーリセットエラー: {e}")
            return False
    
    def browse_adb(self):
        """ADBファイルを選択"""
        filename = filedialog.askopenfilename(
            title="ADBファイルを選択",
            filetypes=[("実行ファイル", "*.exe"), ("すべてのファイル", "*.*")]
        )
        if filename:
            self.adb_path_var.set(filename)
            self.adb_path = filename
            self.save_settings()  # 設定を保存
            self.refresh_devices()
            
    def detect_adb(self):
        """ADBを自動検出"""
        # 一般的なADBパスをチェック
        possible_paths = [
            "adb.exe",
            "platform-tools/adb.exe",
            "Android/Sdk/platform-tools/adb.exe",
            "AppData/Local/Android/Sdk/platform-tools/adb.exe",
            "Program Files/Android/Android Studio/Sdk/platform-tools/adb.exe",
            "Program Files (x86)/Android/Android Studio/Sdk/platform-tools/adb.exe"
        ]
        
        # 環境変数PATHからも検索
        path_dirs = os.environ.get('PATH', '').split(os.pathsep)
        
        for path_dir in path_dirs:
            adb_path = os.path.join(path_dir, "adb.exe")
            if os.path.exists(adb_path):
                self.adb_path = adb_path
                self.adb_path_var.set(adb_path)
                self.save_settings()  # 設定を保存
                self.refresh_devices()
                return
                
        # 相対パスもチェック
        for path in possible_paths:
            if os.path.exists(path):
                self.adb_path = os.path.abspath(path)
                self.adb_path_var.set(self.adb_path)
                self.save_settings()  # 設定を保存
                self.refresh_devices()
                return
                
        # 設定が読み込まれていない場合のみ警告を表示
        if not self.adb_path:
            messagebox.showwarning("警告", "ADBが見つかりませんでした。手動で選択してください。")
        
    def browse_scrcpy(self):
        """SCRCPYファイルを選択"""
        filename = filedialog.askopenfilename(
            title="SCRCPYファイルを選択",
            filetypes=[("実行ファイル", "*.exe"), ("すべてのファイル", "*.*")]
        )
        if filename:
            self.scrcpy_path_var.set(filename)
            self.scrcpy_path = filename
            self.save_settings()  # 設定を保存
            
    def detect_scrcpy(self):
        """SCRCPYを自動検出"""
        # 一般的なSCRCPYパスをチェック
        possible_paths = [
            "scrcpy.exe",
            "scrcpy/scrcpy.exe",
            "tools/scrcpy.exe",
            "AppData/Local/scrcpy/scrcpy.exe",
            "Program Files/scrcpy/scrcpy.exe",
            "Program Files (x86)/scrcpy/scrcpy.exe"
        ]
        
        # 環境変数PATHからも検索
        path_dirs = os.environ.get('PATH', '').split(os.pathsep)
        
        for path_dir in path_dirs:
            scrcpy_path = os.path.join(path_dir, "scrcpy.exe")
            if os.path.exists(scrcpy_path):
                self.scrcpy_path = scrcpy_path
                self.scrcpy_path_var.set(scrcpy_path)
                self.save_settings()  # 設定を保存
                return
                
        # 相対パスもチェック
        for path in possible_paths:
            if os.path.exists(path):
                self.scrcpy_path = os.path.abspath(path)
                self.scrcpy_path_var.set(self.scrcpy_path)
                self.save_settings()  # 設定を保存
                return
                
        # 設定が読み込まれていない場合のみ警告を表示
        if not self.scrcpy_path:
            messagebox.showwarning("警告", "SCRCPYが見つかりませんでした。手動で選択してください。")
        
    def refresh_devices(self):
        """デバイスリストを更新（安全なコマンド実行）"""
        result = self.run_adb_command(["devices"], timeout=5)
        
        if result is None:
            self.status_label.config(text="ADB応答なし", foreground="red")
            return
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]  # ヘッダーを除外
            self.devices = []
            
            for line in lines:
                if line.strip() and '\t' in line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        device_id, status = parts[0], parts[1]
                        if status == 'device':
                            self.devices.append(device_id)
                            
            # コンボボックスを更新
            self.device_combo['values'] = self.devices
            
            if self.devices:
                self.device_combo.set(self.devices[0])
                self.selected_device = self.devices[0]
                self.status_label.config(text=f"接続済み: {len(self.devices)}台", foreground="green")
                
                # ログキャットウィジェットに設定（存在する場合のみ）
                if self.logcat_widget:
                    self.logcat_widget.set_adb_path(self.adb_path)
                    self.logcat_widget.set_device_id(self.selected_device)
            else:
                self.status_label.config(text="デバイスが見つかりません", foreground="orange")
        else:
            print(f"デバイス取得エラー: {result.stderr}")
            self.status_label.config(text="エラー", foreground="red")
            
    def on_device_select(self, event=None):
        """デバイス選択時の処理"""
        self.selected_device = self.device_combo.get()
        if self.selected_device and self.logcat_widget:
            self.logcat_widget.set_device_id(self.selected_device)
            
    def start_scrcpy(self):
        """SCRCPYを開始"""
        if not self.scrcpy_path or not self.selected_device or self.is_scrcpy_running:
            return
            
        try:
            # SCRCPYを開始
            cmd = [self.scrcpy_path, "-s", self.selected_device]
            
            # Windowsでコマンドラインウィンドウを表示しないようにする
            import platform
            if platform.system() == "Windows":
                self.scrcpy_process = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.scrcpy_process = subprocess.Popen(cmd)
                
            self.is_scrcpy_running = True
            self.scrcpy_start_button.config(state=tk.DISABLED)
            self.scrcpy_stop_button.config(state=tk.NORMAL)
            
        except Exception as e:
            print(f"SCRCPYの開始に失敗しました: {e}")
            
    def stop_scrcpy(self):
        """SCRCPYを停止"""
        if not self.is_scrcpy_running:
            return
            
        try:
            if self.scrcpy_process:
                self.scrcpy_process.terminate()
                self.scrcpy_process.wait(timeout=5)
                self.scrcpy_process = None
                
            self.is_scrcpy_running = False
            self.scrcpy_start_button.config(state=tk.NORMAL)
            self.scrcpy_stop_button.config(state=tk.DISABLED)
            
        except Exception as e:
            print(f"SCRCPYの停止に失敗しました: {e}")
            
    def run(self):
        """アプリケーションを実行"""
        # アプリケーション終了時に設定を保存
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        self.root.mainloop()
        
    def on_app_close(self):
        """アプリケーション終了時の処理"""
        print("アプリケーションを終了します...")
        self.stop_connection_monitor()
        self.save_settings()
        self.root.destroy()

    def start_connection_monitor(self):
        """接続監視を開始"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_connection, daemon=True)
        self.monitor_thread.start()
        print("接続監視を開始しました")

    def stop_connection_monitor(self):
        """接続監視を停止"""
        self.is_monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)
        print("接続監視を停止しました")

    def _monitor_connection(self):
        """接続状態を監視（バックグラウンドスレッド）"""
        consecutive_failures = 0
        max_failures = 3  # 3回連続で失敗したら再接続
        
        while self.is_monitoring:
            try:
                # 選択されているデバイスがある場合のみ監視
                if self.selected_device:
                    # デバイスリストを取得
                    result = self.run_adb_command(["devices"], timeout=5, retry_on_timeout=False)
                    
                    if result and result.returncode == 0:
                        # 現在のデバイスが接続されているか確認
                        device_connected = self.selected_device in result.stdout
                        
                        if device_connected:
                            consecutive_failures = 0
                            self.last_connected_device = self.selected_device
                        else:
                            consecutive_failures += 1
                            print(f"接続監視: デバイスが見つかりません ({consecutive_failures}/{max_failures})")
                            
                            # 3回連続で失敗したら再接続
                            if consecutive_failures >= max_failures:
                                print("接続が切断されました。自動再接続を試行します...")
                                self.root.after(0, self._handle_disconnect)
                                consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        print(f"接続監視: ADB応答なし ({consecutive_failures}/{max_failures})")
                        
                        if consecutive_failures >= max_failures:
                            print("ADBサーバーに問題があります。リセットします...")
                            self.reset_adb_server()
                            consecutive_failures = 0
                
                # インターバル待機
                for _ in range(self.connection_check_interval):
                    if not self.is_monitoring:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                print(f"接続監視エラー: {e}")
                time.sleep(5)

    def _handle_disconnect(self):
        """接続切断時の処理（メインスレッドで実行）"""
        self.wireless_status_label.config(text="接続切断 - 再接続中...", foreground="orange")
        
        # 自動再接続を試行
        if self.last_connected_device and ':' in self.last_connected_device:
            # ワイヤレス接続の場合
            ip, port = self.last_connected_device.rsplit(':', 1)
            self.ip_var.set(ip)
            self.port_var.set(port)
            self.auto_reconnect()
        else:
            # USB接続の場合はデバイスリストを更新
            self.refresh_devices()

    def auto_reconnect(self, max_retries=5):
        """自動再接続（指数バックオフ）"""
        ip = self.ip_var.get().strip()
        port = self.port_var.get().strip()
        
        if not ip or not port:
            return False
        
        for i in range(max_retries):
            wait_time = min(2 ** i, 30)  # 1, 2, 4, 8, 16, 30秒
            print(f"再接続試行 {i+1}/{max_retries}: {wait_time}秒後...")
            time.sleep(wait_time)
            
            # 接続を試行
            result = self.run_adb_command(["connect", f"{ip}:{port}"], timeout=10)
            
            if result and result.returncode == 0 and "connected" in result.stdout.lower():
                print(f"再接続成功: {ip}:{port}")
                self.wireless_status_label.config(text=f"ワイヤレス接続済み: {ip}:{port}", foreground="green")
                self.refresh_devices()
                return True
            else:
                print(f"再接続失敗: {result.stdout if result else 'No response'}")
        
        print("再接続が最大試行回数に達しました")
        self.wireless_status_label.config(text="再接続失敗", foreground="red")
        return False

    def check_usb_connection(self):
        """USB接続状態を確認"""
        if not self.adb_path:
            return
            
        result = self.run_adb_command(["devices"], timeout=5)
        
        if result is None:
            print("USB接続確認: ADB応答なし")
            return
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]  # ヘッダーを除外
            usb_devices = [line for line in lines if line.strip() and 'device' in line and 'offline' not in line]
            
            if usb_devices:
                device_info = usb_devices[0].split('\t')[0]
                # IPアドレスを自動取得
                self.get_device_ip()
            else:
                print("USB接続されたデバイスが見つかりませんでした。")
        else:
            print(f"ADBコマンドが失敗しました: {result.stderr}")

    def get_device_ip(self):
        """デバイスのIPアドレスを取得（安全なコマンド実行）"""
        if not self.selected_device:
            return
        
        # 方法1: ip routeコマンド
        result = self.run_adb_command(
            ["-s", self.selected_device, "shell", "ip", "route"],
            timeout=5
        )
        
        if result and result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'wlan' in line or 'wifi' in line:
                    parts = line.split()
                    if len(parts) >= 9:
                        ip = parts[8]
                        if self.is_valid_ip(ip):
                            self.ip_var.set(ip)
                            return
        
        # 方法2: ifconfigコマンド（代替）
        result = self.run_adb_command(
            ["-s", self.selected_device, "shell", "ifconfig", "wlan0"],
            timeout=5
        )
        
        if result and result.returncode == 0:
            match = re.search(r'inet addr:(\d+\.\d+\.\d+\.\d+)', result.stdout)
            if match:
                ip = match.group(1)
                self.ip_var.set(ip)

    def scan_wireless_port(self, ip):
        """ワイヤレスデバッグポートをスキャン"""
        try:
            # nmapでポートスキャン（35000-44000の範囲）
            result = subprocess.run(
                ["nmap", ip, "-p", "35000-44000", "-sS", "-oG", "-", "--defeat-rst-ratelimit"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                # ポートを検索
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if '/open/tcp/' in line:
                        match = re.search(r'Ports: (\d+)/open/', line)
                        if match:
                            port = match.group(1)
                            return port
                            
            return None
            
        except subprocess.TimeoutExpired:
            print("ポートスキャンがタイムアウトしました")
            return None
        except FileNotFoundError:
            # nmapが見つからない場合は代替方法を試行
            print("nmapが見つかりません。代替方法でポートスキャンを実行します。")
            print("より正確なスキャンのためにnmapをインストールすることをお勧めします:")
            print("https://nmap.org/download.html")
            return self.scan_wireless_port_alternative(ip)
        except Exception as e:
            print(f"ポートスキャンエラー: {e}")
            return None

    def scan_wireless_port_alternative(self, ip):
        """nmapを使わない代替ポートスキャン"""
        try:
            import socket
            
            # 一般的なワイヤレスデバッグポートを試行
            common_ports = [5555, 35000, 36000, 37000, 38000, 39000, 40000, 41000, 42000, 43000, 44000]
            
            for port in common_ports:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((ip, port))
                    sock.close()
                    
                    if result == 0:
                        return str(port)
                        
                except:
                    continue
                    
            # 範囲スキャン（35000-44000）
            for port in range(35000, 44001, 100):  # 100ポートずつスキャン
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(0.5)
                    result = sock.connect_ex((ip, port))
                    sock.close()
                    
                    if result == 0:
                        return str(port)
                        
                except:
                    continue
                    
            return None
            
        except Exception as e:
            print(f"代替ポートスキャンエラー: {e}")
            return None

    def scan_wireless_port_fast(self, ip):
        """高速ポートスキャン（並列処理）"""
        import socket
        
        # 一般的なポートを優先的にチェック
        common_ports = [5555, 35000, 36000, 37000, 38000, 39000, 40000, 41000, 42000, 43000, 44000]
        open_port = None
        
        def check_port(port):
            nonlocal open_port
            if open_port is not None:
                return
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((ip, port))
                sock.close()
                if result == 0:
                    open_port = port
            except:
                pass
        
        # 並列スキャン（最大10スレッド）
        threads = []
        for port in common_ports:
            t = threading.Thread(target=check_port, args=(port,))
            threads.append(t)
            t.start()
        
        # すべてのスレッドが完了するか、ポートが見つかるまで待機
        for t in threads:
            t.join(timeout=0.5)
            if open_port is not None:
                break
        
        return str(open_port) if open_port else None

    def is_valid_ip(self, ip):
        """IPアドレスが有効かチェック"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not 0 <= int(part) <= 255:
                    return False
            return True
        except:
            return False

    def enable_wireless_debug(self):
        """ワイヤレスデバッグを有効化して自動接続"""
        if not self.selected_device:
            print("エラー: デバイスが選択されていません")
            return
        
        # TCP/IPポート5555でワイヤレスデバッグを有効化
        result = self.run_adb_command(
            ["-s", self.selected_device, "tcpip", "5555"],
            timeout=10
        )
        
        if result is None:
            print("ワイヤレスデバッグ有効化: ADB応答なし")
            return
        
        if result.returncode == 0:
            self.wireless_status_label.config(text="ワイヤレスデバッグ有効", foreground="green")
            
            # IPアドレスを取得
            self.get_device_ip()
            
            # デバイスがWiFiに切り替わるのを待ってから接続（5秒に延長）
            self.root.after(5000, self.auto_connect_wireless)
            
            # SCRCPYを起動（8秒後）
            self.root.after(8000, self.auto_start_scrcpy)
        else:
            print(f"ワイヤレスデバッグの有効化に失敗: {result.stderr}")

    def auto_connect_wireless(self):
        """自動ワイヤレス接続"""
        ip = self.ip_var.get().strip()
        
        if not ip:
            print("IPアドレスが取得できませんでした。")
            return
        
        # ポートスキャンを実行（タイムアウト短縮）
        port = self.scan_wireless_port_fast(ip)
        
        if not port:
            print("ワイヤレスデバッグポートが見つかりませんでした。手動でポートを指定してください。")
            return
        
        # 見つかったポートを設定
        self.port_var.set(port)
        
        # ワイヤレス接続（安全なコマンド実行）
        result = self.run_adb_command(
            ["connect", f"{ip}:{port}"],
            timeout=10
        )
        
        if result is None:
            print("ワイヤレス接続: ADB応答なし")
            return
        
        if result.returncode == 0 and "connected" in result.stdout.lower():
            self.wireless_status_label.config(text=f"ワイヤレス接続済み: {ip}:{port}", foreground="green")
            self.refresh_devices()
            print(f"ワイヤレス接続成功: {ip}:{port}")
            # 接続監視を開始
            self.start_connection_monitor()
        else:
            print(f"ワイヤレス接続失敗: {result.stdout if result else 'No response'}")
            # 診断情報を表示
            self.diagnose_connection(ip, port)

    def scan_port_manual(self):
        """手動ポートスキャン"""
        ip = self.ip_var.get().strip()
        
        if not ip or not self.is_valid_ip(ip):
            return
            
        # ポートスキャンを実行
        port = self.scan_wireless_port(ip)
        
        if port:
            self.port_var.set(port)
            print(f"ワイヤレスデバッグポートが見つかりました: {port}")
        else:
            print("ワイヤレスデバッグポートが見つかりませんでした。")

    def connect_wireless(self):
        """ワイヤレス接続を実行"""
        ip = self.ip_var.get().strip()
        port = self.port_var.get().strip()
        
        if not ip or not self.is_valid_ip(ip):
            return
        
        # ワイヤレス接続
        result = self.run_adb_command(
            ["connect", f"{ip}:{port}"],
            timeout=10
        )
        
        if result is None:
            print("ワイヤレス接続: ADB応答なし")
            self.diagnose_connection(ip, port)
            return
        
        if result.returncode == 0 and "connected" in result.stdout.lower():
            self.wireless_status_label.config(text=f"ワイヤレス接続済み: {ip}:{port}", foreground="green")
            self.refresh_devices()
            print(f"ワイヤレス接続成功: {ip}:{port}")
            # 接続監視を開始
            self.start_connection_monitor()
        else:
            print(f"ワイヤレス接続失敗: {result.stdout}")
            self.diagnose_connection(ip, port)

    def copy_adb_connect_command(self):
        """adb connect <IP>:<PORT> をクリップボードにコピー"""
        ip = self.ip_var.get().strip()
        port = (self.port_var.get().strip() or "5555")
        if not ip or not self.is_valid_ip(ip):
            return
        adb_cmd = f'"{self.adb_path}"' if self.adb_path else "adb"
        cmd = f"{adb_cmd} connect {ip}:{port}"
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
            self.root.update()
            print("adb connect コマンドをコピーしました")
        except Exception as e:
            print(f"クリップボードコピー失敗: {e}")

    def auto_start_scrcpy(self):
        """自動SCRCPY起動"""
        if not self.scrcpy_path or not self.selected_device or self.is_scrcpy_running:
            return
            
        try:
            # SCRCPYを開始
            cmd = [self.scrcpy_path, "-s", self.selected_device]
            
            # Windowsでコマンドラインウィンドウを表示しないようにする
            import platform
            if platform.system() == "Windows":
                self.scrcpy_process = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.scrcpy_process = subprocess.Popen(cmd)
                
            self.is_scrcpy_running = True
            self.scrcpy_start_button.config(state=tk.DISABLED)
            self.scrcpy_stop_button.config(state=tk.NORMAL)
            
            print("SCRCPYが自動起動されました")
            
        except Exception as e:
            print(f"SCRCPYの自動起動に失敗しました: {e}")

    def open_logcat_window(self):
        """ログキャットウィンドウを開く"""
        if self.logcat_window is None or not self.logcat_window.winfo_exists():
            # 新しいウィンドウを作成（Android Studio風）
            self.logcat_window = tk.Toplevel(self.root)
            self.logcat_window.title("Logcat - WDconnect")
            self.logcat_window.geometry(self.logcat_window_size)
            # Android Studio風のアイコン設定（可能な場合）
            try:
                self.logcat_window.iconbitmap("icon.ico")
            except:
                pass
            
            # 最前面にピン留め機能を追加
            self.logcat_window.attributes('-topmost', True)
            
            # ピン留め制御フレーム
            pin_frame = ttk.Frame(self.logcat_window)
            pin_frame.pack(fill=tk.X, padx=5, pady=2)
            
            self.pin_var = tk.BooleanVar(value=True)
            pin_check = ttk.Checkbutton(pin_frame, text="最前面にピン留め", variable=self.pin_var, 
                                      command=self.toggle_pin)
            pin_check.pack(side=tk.LEFT)
            
            # ログキャットウィジェットを作成
            self.logcat_widget = LightLogcatWidget(self.logcat_window)
            
            # ADBパスとデバイスを設定
            if self.adb_path:
                self.logcat_widget.set_adb_path(self.adb_path)
            if self.selected_device:
                self.logcat_widget.set_device_id(self.selected_device)
                
            # 保存されたテーマを適用
            if hasattr(self, 'logcat_theme') and self.logcat_theme:
                self.logcat_widget.apply_theme(self.logcat_theme)
                if hasattr(self.logcat_widget, 'theme_combo'):
                    self.logcat_widget.theme_combo.set(self.logcat_theme)
            
            # ウィンドウが閉じられたときの処理
            self.logcat_window.protocol("WM_DELETE_WINDOW", self.on_logcat_window_close)
            
            print("ログキャットウィンドウを開きました（最前面にピン留め）")
        else:
            # 既存のウィンドウを前面に
            self.logcat_window.lift()
            self.logcat_window.focus_force()

    def toggle_pin(self):
        """ピン留めの切り替え"""
        if self.logcat_window:
            self.logcat_window.attributes('-topmost', self.pin_var.get())
            if self.pin_var.get():
                print("ログキャットウィンドウを最前面にピン留めしました")
            else:
                print("ログキャットウィンドウのピン留めを解除しました")
            # 設定を保存
            self.save_settings()

    def on_logcat_window_close(self):
        """ログキャットウィンドウが閉じられたときの処理"""
        # ウィンドウサイズを保存
        if self.logcat_window:
            self.logcat_window_size = self.logcat_window.geometry()
            
        # テーマを保存
        if self.logcat_widget and hasattr(self.logcat_widget, 'current_theme'):
            self.logcat_theme = self.logcat_widget.current_theme
            
        # 設定を保存
        self.save_settings()
        
        self.logcat_widget = None
        self.logcat_window.destroy()
        self.logcat_window = None
        print("ログキャットウィンドウを閉じました")

    def load_settings(self):
        """設定を読み込み"""
        try:
            if os.path.exists('wireless_debug_config.json'):
                with open('wireless_debug_config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # ADBパスを設定
                if 'adb_path' in config and os.path.exists(config['adb_path']):
                    self.adb_path = config['adb_path']
                    self.adb_path_var.set(config['adb_path'])
                    
                # SCRCPYパスを設定
                if 'scrcpy_path' in config and os.path.exists(config['scrcpy_path']):
                    self.scrcpy_path = config['scrcpy_path']
                    self.scrcpy_path_var.set(config['scrcpy_path'])
                    
                # IPアドレスを設定
                if 'wireless_ip' in config:
                    self.ip_var.set(config['wireless_ip'])
                    
                # ポートを設定
                if 'wireless_port' in config:
                    self.port_var.set(config['wireless_port'])
                    
                # ウィンドウサイズを設定（固定モードでは適用しない）
                if 'window_size' in config and not getattr(self, 'lock_window_size', True):
                    self.root.geometry(config['window_size'])
                    
                # ログキャットウィンドウサイズを設定
                if 'logcat_window_size' in config:
                    self.logcat_window_size = config['logcat_window_size']
                    
                # ログキャットテーマを設定
                if 'logcat_theme' in config:
                    self.logcat_theme = config['logcat_theme']
                    
                print("設定を読み込みました")
                    
        except Exception as e:
            print(f"設定読み込みエラー: {e}")
            
        # 設定が不完全な場合は初期値を設定
        if not hasattr(self, 'logcat_window_size'):
            self.logcat_window_size = "800x600"
        if not hasattr(self, 'logcat_theme'):
            self.logcat_theme = "light"

    def save_settings(self):
        """設定を保存"""
        try:
            config = {}
            
            # ADBパスを保存
            if self.adb_path and os.path.exists(self.adb_path):
                config['adb_path'] = self.adb_path
                
            # SCRCPYパスを保存
            if self.scrcpy_path and os.path.exists(self.scrcpy_path):
                config['scrcpy_path'] = self.scrcpy_path
                
            # IPアドレスを保存
            if self.ip_var.get().strip():
                config['wireless_ip'] = self.ip_var.get().strip()
                
            # ポートを保存
            if self.port_var.get().strip():
                config['wireless_port'] = self.port_var.get().strip()
                
            # ウィンドウサイズを保存（固定モードでは保存しない）
            if not getattr(self, 'lock_window_size', True):
                config['window_size'] = self.root.geometry()
            
            # ログキャットウィンドウサイズを保存
            if hasattr(self, 'logcat_window_size'):
                config['logcat_window_size'] = self.logcat_window_size
            else:
                config['logcat_window_size'] = "800x600"
                
            # ログキャットテーマを保存
            if hasattr(self, 'logcat_theme'):
                config['logcat_theme'] = self.logcat_theme
            else:
                config['logcat_theme'] = "light"
                
            # 保存日時を記録
            from datetime import datetime
            config['last_saved'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            with open('wireless_debug_config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                
            print(f"設定を保存しました: {config['last_saved']}")
                
        except Exception as e:
            print(f"設定保存エラー: {e}")

def main():
    root = tk.Tk()
    app = LightWDconnectApp(root)
    app.run()

if __name__ == "__main__":
    main() 
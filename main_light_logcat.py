import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
import subprocess
import threading
import concurrent.futures
import socket as py_socket
import os
import sys
import re
import json
import time
from typing import Optional
from datetime import datetime
from logcat_widget_light import LightLogcatWidget

ADB_DEVICE_TXT = "adb_device.txt"


def _subprocess_hide_console_kwargs():
    """Windows で adb 等を叩くたびに CMD が一瞬表示されるのを防ぐ"""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class StdoutRedirector:
    """標準出力をGUIのテキストウィジェットにリダイレクト"""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.original_stdout = sys.stdout if sys.stdout else None
        
    def write(self, message):
        # GUIに出力（メイン）
        if message.strip():  # 空行でない場合のみ
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.text_widget.insert(tk.END, f"[{timestamp}] {message}")
                self.text_widget.see(tk.END)  # 自動スクロール
            except:
                pass  # ウィジェットが破棄されている場合は無視
        
        # 元のstdoutにも出力（コンソールがある場合のみ）
        try:
            if self.original_stdout and hasattr(self.original_stdout, 'write'):
                self.original_stdout.write(message)
        except:
            pass  # コンソールがない場合は無視
            
    def flush(self):
        try:
            if self.original_stdout and hasattr(self.original_stdout, 'flush'):
                self.original_stdout.flush()
        except:
            pass

class LightWDconnectApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WDconnect Light - Android Wireless Debug Tool")
        self.root.geometry("720x480")
        self.root.minsize(620, 400)
        self.root.resizable(True, True)
        
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
        self.ip_var = tk.StringVar()
        self.port_var = tk.StringVar(value="5555")
        self.pairing_port_var = tk.StringVar()
        self.pairing_code_var = tk.StringVar()
        self.simple_connect_hint_var = tk.StringVar(value="")
        self.saved_mdns_endpoint_var = tk.StringVar(value="")
        
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
        
        # 接続履歴（成功した接続を記憶）
        self.connection_history = []
        self.max_history_size = 10
        
        # 接続状況の自動更新（メインスレッドで adb devices を定期実行）
        self.status_poll_interval_ms = 3000
        self._status_poll_job = None
        self._closing = False
        
        self.setup_ui()
        self.load_settings()
        self._sync_saved_endpoint_from_file()
        
        # 設定が読み込まれていない場合のみ自動検出
        if not self.adb_path:
            self.detect_adb()
        if not self.scrcpy_path:
            self.detect_scrcpy()
            
        # 初期設定を保存
        self.save_settings()
        
        self._schedule_status_poll()
        if self.adb_path:
            self.refresh_devices(preserve_selection=True)

    def auto_connect_on_startup(self):
        """起動時に自動接続を試行（1クリック操作を実現）"""
        if not self.adb_path:
            return

        print("自動接続を開始します...")

        # USBデバイスからIPを取得
        self._try_autofill_ip_from_usb()

        # 保存された接続先を試行
        if self._try_saved_mdns_connect_with_refresh():
            print("✅ 保存された接続先で接続成功")
            return

        # mDNSや他の候補を試行
        candidates = self._wireless_connect_candidates(include_mdns=True)
        if candidates:
            for ip, port in candidates:
                print(f"接続試行: {self._format_endpoint_label(ip, port)}")
                result = self.run_adb_command(["connect", f"{ip}:{port}"], timeout=10)
                if result and result.returncode == 0 and "connected" in result.stdout.lower():
                    self._finalize_wireless_connected(ip, port)
                    print(f"✅ 自動接続成功: {ip}:{port}")
                    return

        print("自動接続: 利用可能な接続先が見つかりませんでした")
        
    def setup_ui(self):
        """軽量なUIを設定（簡単／詳細タブ）"""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        
        title_label = ttk.Label(main_frame, text="WDconnect Light", font=("Arial", 13, "bold"))
        title_label.pack(pady=(0, 8))
        
        adb_frame = ttk.LabelFrame(main_frame, text="ADB設定", padding="5")
        adb_frame.pack(fill=tk.X, pady=(0, 6))
        
        adb_path_frame = ttk.Frame(adb_frame)
        adb_path_frame.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(adb_path_frame, text="ADBパス:").pack(side=tk.LEFT)
        self.adb_path_var = tk.StringVar()
        self.adb_path_entry = ttk.Entry(adb_path_frame, textvariable=self.adb_path_var, width=40)
        self.adb_path_entry.pack(side=tk.LEFT, padx=(5, 5), fill=tk.X, expand=True)
        
        ttk.Button(adb_path_frame, text="参照", command=self.browse_adb).pack(side=tk.LEFT)
        ttk.Button(adb_path_frame, text="検出", command=self.detect_adb).pack(side=tk.LEFT, padx=(5, 0))
        
        device_frame = ttk.Frame(adb_frame)
        device_frame.pack(fill=tk.X, pady=(4, 0))
        
        ttk.Label(device_frame, text="デバイス:").pack(side=tk.LEFT)
        self.device_combo = ttk.Combobox(device_frame, state="readonly", width=24)
        self.device_combo.pack(side=tk.LEFT, padx=(5, 5))
        self.device_combo.bind("<<ComboboxSelected>>", self.on_device_select)
        
        ttk.Button(device_frame, text="更新", command=self.refresh_devices).pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(adb_frame, text="未接続", foreground="red")
        self.status_label.pack(pady=(5, 0))
        
        self.wireless_status_label = ttk.Label(main_frame, text="ワイヤレス未接続", foreground="red")
        self.wireless_status_label.pack(anchor=tk.W, pady=(0, 4))
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        
        tab_simple = ttk.Frame(notebook, padding=6)
        tab_advanced = ttk.Frame(notebook, padding=6)
        notebook.add(tab_simple, text="簡単")
        notebook.add(tab_advanced, text="詳細")
        
        self.logcat_window = None
        self.logcat_widget = None
        
        self._setup_advanced_tab(tab_advanced)
        self._setup_simple_tab(tab_simple)
        
        notebook.select(0)
        
        def _hint_on_ip_change(*_):
            try:
                if self.root.winfo_exists():
                    self._refresh_simple_connect_hint()
            except tk.TclError:
                pass
        
        self.ip_var.trace_add('write', lambda *_: self.root.after_idle(_hint_on_ip_change))
        self.port_var.trace_add('write', lambda *_: self.root.after_idle(_hint_on_ip_change))
        
        print("✅ WDconnect Light を起動しました（「簡単」タブ：2回目からは接続ボタンのみ）")
        print("💡 詳細なログは「詳細」タブを開いてください")
    
    def _setup_simple_tab(self, parent):
        """簡単UI: 接続とSCRCPYのみ"""
        hint = ttk.Label(
            parent,
            text="スマホで「ワイヤレスデバッグ」をONにして、同じWi‑Fiに接続してから「接続」ボタンを押してください。",
            justify=tk.LEFT,
            wraplength=620,
            font=("Arial", 9),
        )
        hint.pack(anchor=tk.W, pady=(0, 10))
        
        button_frame = ttk.Frame(parent)
        button_frame.pack(pady=(0, 10))
        
        ttk.Button(
            button_frame,
            text="接続",
            command=self.easy_wireless_connect,
            width=20,
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(
            button_frame,
            text="SCRCPY開始",
            command=self.start_scrcpy,
            width=15,
        ).pack(side=tk.LEFT)
        
        log_frame = ttk.LabelFrame(parent, text="ログ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        self.simple_log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.simple_log_text.pack(fill=tk.BOTH, expand=True)
        
        self.simple_log_text.tag_config("info", foreground="black")
        self.simple_log_text.tag_config("success", foreground="green")
        self.simple_log_text.tag_config("error", foreground="red")
        
        ttk.Button(
            log_frame,
            text="クリア",
            command=self.clear_simple_log,
        ).pack(pady=(5, 0))
        
        ttk.Label(
            parent,
            text="詳細設定は「詳細」タブへ",
            foreground="gray",
            font=("Arial", 8),
        ).pack(pady=(5, 0))

    def clear_simple_log(self):
        """简单タブのログをクリア"""
        self.simple_log_text.delete(1.0, tk.END)

    def log_simple(self, message, tag="info"):
        """简单タブにログを出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.simple_log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.simple_log_text.see(tk.END)
    
    def _setup_advanced_tab(self, parent):
        """従来のUSB・ワイヤレス・ログ一式"""
        usb_frame = ttk.LabelFrame(parent, text="USB接続管理", padding="5")
        usb_frame.pack(fill=tk.X, pady=(0, 10))
        
        usb_buttons_frame = ttk.Frame(usb_frame)
        usb_buttons_frame.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Button(usb_buttons_frame, text="USB接続確認", command=self.check_usb_connection).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(usb_buttons_frame, text="ワイヤレスデバッグ有効化＆接続", command=self.enable_wireless_debug).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(usb_buttons_frame, text="ポートスキャン", command=self.scan_port_manual).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(usb_buttons_frame, text="手動ワイヤレス接続", command=self.connect_wireless).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(usb_buttons_frame, text="🩺診断＆修復", command=self.diagnose_and_fix).pack(side=tk.LEFT)
        
        wireless_frame = ttk.Frame(usb_frame)
        wireless_frame.pack(fill=tk.X, pady=(4, 0))
        
        ttk.Label(wireless_frame, text="IPアドレス:").pack(side=tk.LEFT)
        self.ip_entry = ttk.Entry(wireless_frame, textvariable=self.ip_var, width=12)
        self.ip_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Label(wireless_frame, text="ポート:").pack(side=tk.LEFT)
        self.port_entry = ttk.Entry(wireless_frame, textvariable=self.port_var, width=6)
        self.port_entry.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(wireless_frame, text="ADB+", width=5, command=self.copy_adb_connect_command).pack(side=tk.LEFT, padx=(6, 0))
        
        scrcpy_frame = ttk.LabelFrame(parent, text="SCRCPY設定", padding="5")
        scrcpy_frame.pack(fill=tk.X, pady=(0, 10))
        
        scrcpy_path_frame = ttk.Frame(scrcpy_frame)
        scrcpy_path_frame.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(scrcpy_path_frame, text="SCRCPYパス:").pack(side=tk.LEFT)
        self.scrcpy_path_var = tk.StringVar()
        self.scrcpy_path_entry = ttk.Entry(scrcpy_path_frame, textvariable=self.scrcpy_path_var, width=40)
        self.scrcpy_path_entry.pack(side=tk.LEFT, padx=(5, 5), fill=tk.X, expand=True)
        
        ttk.Button(scrcpy_path_frame, text="参照", command=self.browse_scrcpy).pack(side=tk.LEFT)
        ttk.Button(scrcpy_path_frame, text="検出", command=self.detect_scrcpy).pack(side=tk.LEFT, padx=(5, 0))
        
        scrcpy_control_frame = ttk.Frame(scrcpy_frame)
        scrcpy_control_frame.pack(fill=tk.X, pady=(4, 0))
        
        self.scrcpy_start_button = ttk.Button(scrcpy_control_frame, text="SCRCPY開始", command=self.start_scrcpy)
        self.scrcpy_start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.scrcpy_stop_button = ttk.Button(scrcpy_control_frame, text="SCRCPY停止", command=self.stop_scrcpy, state=tk.DISABLED)
        self.scrcpy_stop_button.pack(side=tk.LEFT)
        
        logcat_frame = ttk.LabelFrame(parent, text="ログキャット", padding="5")
        logcat_frame.pack(fill=tk.X, pady=(0, 6))
        
        ttk.Button(logcat_frame, text="📱 ログキャットを開く", command=self.open_logcat_window).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(logcat_frame, text="ログキャットウィンドウを別ウィンドウで開きます").pack(side=tk.LEFT)
        
        log_frame = ttk.LabelFrame(parent, text="📋 ログ", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        self.log_text.tag_config("info", foreground="black")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("warning", foreground="orange")
        self.log_text.tag_config("error", foreground="red")
        
        self.stdout_redirector = StdoutRedirector(self.log_text)
        sys.stdout = self.stdout_redirector
        
        button_frame = ttk.Frame(log_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(button_frame, text="🗑️ クリア", command=self.clear_log).pack(side=tk.RIGHT)
        
    def clear_log(self):
        """ログをクリア"""
        self.log_text.delete(1.0, tk.END)
        print("🗑️ ログをクリアしました")
        
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
                    errors='replace',
                    **_subprocess_hide_console_kwargs(),
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
            subprocess.run(
                [self.adb_path, "kill-server"],
                capture_output=True,
                timeout=5,
                **_subprocess_hide_console_kwargs(),
            )
            time.sleep(1)
            
            print("ADBサーバーを起動中...")
            result = subprocess.run(
                [self.adb_path, "start-server"],
                capture_output=True,
                timeout=10,
                **_subprocess_hide_console_kwargs(),
            )
            
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
        
    def refresh_devices(self, preserve_selection=True):
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
                            
            self.device_combo['values'] = self.devices
            prev = self.selected_device
            
            if self.devices:
                if preserve_selection and prev and prev in self.devices:
                    self.device_combo.set(prev)
                    self.selected_device = prev
                else:
                    self.device_combo.set(self.devices[0])
                    self.selected_device = self.devices[0]
                self.status_label.config(text=f"接続済み: {len(self.devices)}台", foreground="green")
                
                if self.logcat_widget:
                    self.logcat_widget.set_adb_path(self.adb_path)
                    self.logcat_widget.set_device_id(self.selected_device)
            else:
                self.device_combo.set('')
                self.selected_device = None
                self.status_label.config(text="デバイスが見つかりません", foreground="orange")
            
            self._update_wireless_status_display()
        else:
            print(f"デバイス取得エラー: {result.stderr}")
            self.status_label.config(text="エラー", foreground="red")
    
    def _update_wireless_status_display(self):
        """ADB 一覧に合わせてワイヤレス行のラベルを更新"""
        if not self.adb_path:
            return
        sel = self.selected_device or ''
        wireless_ok = [d for d in self.devices if ':' in d]
        
        if sel and ':' in sel:
            if sel in self.devices:
                ip, port = sel.rsplit(':', 1)
                dn = self._lookup_history_device_name(ip, port)
                if dn:
                    self.wireless_status_label.config(
                        text=f"ワイヤレス: {dn} ({sel})", foreground="green")
                else:
                    self.wireless_status_label.config(
                        text=f"ワイヤレス接続済み: {sel}", foreground="green")
            else:
                self.wireless_status_label.config(text="ワイヤレス切断", foreground="red")
        elif wireless_ok:
            self.wireless_status_label.config(
                text=f"ワイヤレス{len(wireless_ok)}台接続中（一覧で選択）",
                foreground="orange")
        else:
            self.wireless_status_label.config(text="ワイヤレス未接続", foreground="red")
            
    def on_device_select(self, event=None):
        """デバイス選択時の処理"""
        self.selected_device = self.device_combo.get()
        if self.selected_device and self.logcat_widget:
            self.logcat_widget.set_device_id(self.selected_device)
            
    def check_scrcpy_status(self):
        """SCRCPYの実際の起動状態を確認"""
        if not self.scrcpy_process:
            return False
        return self.scrcpy_process.poll() is None

    def start_scrcpy(self):
        """SCRCPYを開始"""
        if not self.scrcpy_path:
            messagebox.showwarning("SCRCPY", "SCRCPYパスが設定されていません")
            return
        if not self.selected_device:
            messagebox.showwarning("SCRCPY", "接続中のデバイスがありません")
            return
        if self.check_scrcpy_status():
            messagebox.showinfo("SCRCPY", "すでに起動中です")
            return
            
        try:
            cmd = [self.scrcpy_path, "-s", self.selected_device]
            
            import platform
            if platform.system() == "Windows":
                self.scrcpy_process = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.scrcpy_process = subprocess.Popen(cmd)
            
            self.root.after(1000, self._update_scrcpy_button_state)
            self.log_simple(f"SCRCPY起動: {self.selected_device}", "info")
            
        except Exception as e:
            messagebox.showerror("SCRCPY", f"起動に失敗しました: {e}")
            self.log_simple(f"SCRCPY起動失敗: {e}", "error")

    def _update_scrcpy_button_state(self):
        """ボタンの状態を更新（1秒後に実際のプロセス状態を確認）"""
        if self.check_scrcpy_status():
            self.is_scrcpy_running = True
            self.log_simple("SCRCPY起動中", "success")
            if hasattr(self, 'scrcpy_start_button'):
                self.scrcpy_start_button.config(state=tk.DISABLED)
            if hasattr(self, 'scrcpy_stop_button'):
                self.scrcpy_stop_button.config(state=tk.NORMAL)
        else:
            self.is_scrcpy_running = False
            if self.scrcpy_process:
                returncode = self.scrcpy_process.returncode
                if returncode != 0:
                    self.log_simple(f"SCRCPY終了（コード: {returncode}）", "error")
            if hasattr(self, 'scrcpy_start_button'):
                self.scrcpy_start_button.config(state=tk.NORMAL)
            if hasattr(self, 'scrcpy_stop_button'):
                self.scrcpy_stop_button.config(state=tk.DISABLED)
            self.scrcpy_process = None

    def stop_scrcpy(self):
        """SCRCPYを停止"""
        if not self.check_scrcpy_status():
            self.is_scrcpy_running = False
            if hasattr(self, 'scrcpy_start_button'):
                self.scrcpy_start_button.config(state=tk.NORMAL)
            if hasattr(self, 'scrcpy_stop_button'):
                self.scrcpy_stop_button.config(state=tk.DISABLED)
            self.scrcpy_process = None
            return
            
        try:
            self.scrcpy_process.terminate()
            self.scrcpy_process.wait(timeout=5)
            self.scrcpy_process = None
            self.is_scrcpy_running = False
            if hasattr(self, 'scrcpy_start_button'):
                self.scrcpy_start_button.config(state=tk.NORMAL)
            if hasattr(self, 'scrcpy_stop_button'):
                self.scrcpy_stop_button.config(state=tk.DISABLED)
            print("SCRCPYを停止しました")
            
        except Exception as e:
            messagebox.showerror("SCRCPY", f"停止に失敗しました: {e}")
            print(f"SCRCPYの停止に失敗しました: {e}")
            
    def run(self):
        """アプリケーションを実行"""
        # アプリケーション終了時に設定を保存
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        self.root.mainloop()
        
    def on_app_close(self):
        """アプリケーション終了時の処理"""
        print("アプリケーションを終了します...")
        self._closing = True
        self._cancel_status_poll()
        self.stop_connection_monitor()
        self.save_settings()
        self.root.destroy()

    def _schedule_status_poll(self):
        if getattr(self, '_closing', False):
            return
        self._status_poll_job = self.root.after(self.status_poll_interval_ms, self._on_status_poll)

    def _cancel_status_poll(self):
        if self._status_poll_job is not None:
            try:
                self.root.after_cancel(self._status_poll_job)
            except tk.TclError:
                pass
            self._status_poll_job = None

    def _on_status_poll(self):
        self._status_poll_job = None
        if getattr(self, '_closing', False):
            return
        try:
            if self.adb_path:
                self.refresh_devices(preserve_selection=True)
        except tk.TclError:
            return
        if not getattr(self, '_closing', False):
            try:
                if self.root.winfo_exists():
                    self._schedule_status_poll()
            except tk.TclError:
                pass

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
                **_subprocess_hide_console_kwargs(),
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
            self._finalize_wireless_connected(ip, port)
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

    def easy_wireless_connect(self):
        """簡単タブ: ボタン1回。保存/mDNS追従→USB補完→全候補。"""
        self.clear_simple_log()
        self.log_simple("接続を開始します...", "info")
        
        if not self.adb_path:
            self.log_simple("ADBパスが設定されていません", "error")
            messagebox.showwarning("ADB", "ADB パスを設定するか「検出」を押してください。")
            return
        
        self.log_simple("USBデバイスからIPを取得中...", "info")
        self._try_autofill_ip_from_usb()
        
        self.log_simple("保存された接続先を試行...", "info")
        if self._try_saved_mdns_connect_with_refresh():
            self.log_simple("接続成功！", "success")
            return
        
        candidates = self._wireless_connect_candidates(include_mdns=True)
        if not candidates:
            self.log_simple("接続先が見つかりません", "error")
            messagebox.showwarning(
                "接続先がありません",
                "初回は「詳細」タブでIP・ポートを入力してください。",
            )
            return
        
        pp = self.pairing_port_var.get().strip()
        pc = self.pairing_code_var.get().strip()
        pair_ip = candidates[0][0]
        if pp or pc:
            if not pp or not pc:
                messagebox.showwarning(
                    "ペアリング",
                    "ペア用ポートとコードの両方を入力するか、どちらも空にしてください。",
                )
                return
            self.log_simple(f"ペアリング: {pair_ip}:{pp}", "info")
            pr = self.run_adb_command(["pair", f"{pair_ip}:{pp}", pc], timeout=30, retry_on_timeout=False)
            if pr is None:
                self.log_simple("ADBが応答しません", "error")
                messagebox.showerror("ペアリング", "ADB が応答しません。")
                return
            out = (pr.stdout or "") + (pr.stderr or "")
            if pr.returncode != 0:
                self.log_simple(f"ペアリング失敗: {out.strip()}", "error")
                messagebox.showerror("ペアリング失敗", (out.strip() or "不明なエラー")[:800])
                return
            self.log_simple("ペアリング完了", "success")
            self.pairing_code_var.set("")
            self.save_settings()
        
        last_err = ""
        ok = False
        used_ip, used_port = None, None
        for ip, port in candidates:
            self.log_simple(f"接続試行: {ip}:{port}", "info")
            result = self.run_adb_command(["connect", f"{ip}:{port}"], timeout=20)
            if result is None:
                self.log_simple("ADBタイムアウト - サーバー再起動...", "error")
                if self.reset_adb_server():
                    self.log_simple("ADBサーバー再起動成功、再試行...", "info")
                    result = self.run_adb_command(["connect", f"{ip}:{port}"], timeout=15)
                else:
                    last_err = "ADBサーバー再起動失敗"
                    self.log_simple(last_err, "error")
                    continue

            msg = (result.stdout or "") + (result.stderr or "")
            self.log_simple(f"応答: {msg.strip()[:200]}", "info")

            if result.returncode == 0:
                if "connected" in result.stdout.lower() or "already connected" in result.stdout.lower():
                    self.log_simple("接続成功！", "success")
                    ok = True
                    used_ip, used_port = ip, port
                    break
                elif "failed" not in result.stdout.lower() and "error" not in result.stdout.lower():
                    self.log_simple("接続成功（応答メッセージなし）", "success")
                    ok = True
                    used_ip, used_port = ip, port
                    break

            last_err = msg.strip() or "接続拒否"
            self.log_simple(f"失敗: {last_err[:100]}", "error")
        
        if ok:
            self._finalize_wireless_connected(used_ip, used_port)
        else:
            self.log_simple(f"接続失敗: {last_err[:100]}", "error")
            messagebox.showerror(
                "接続失敗",
                (last_err or "接続に失敗しました。")[:800]
                + "\n\nスマホのポートが変わっている場合は、新しい IP・ポートを下に入力してください。",
            )
            if used_ip is None and candidates:
                self.diagnose_connection(candidates[0][0], candidates[0][1])

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
            self._finalize_wireless_connected(ip, port)
        else:
            print(f"ワイヤレス接続失敗: {result.stdout}")
            self.diagnose_connection(ip, port)

    def diagnose_and_fix(self):
        """自動診断と修復（ワンクリック）"""
        print("\n" + "="*50)
        print("🔧 自動診断と修復を開始します")
        print("="*50 + "\n")
        
        issues_found = []
        fixes_applied = []
        
        # Step 1: ADBパス確認
        print("Step 1/6: ADBパスを確認中...")
        if not self.adb_path:
            print("  ⚠ ADBパスが設定されていません")
            issues_found.append("ADBパス未設定")
            print("  🔧 自動検出を試行します...")
            self.detect_adb()
            if self.adb_path:
                fixes_applied.append("ADBパス自動検出")
                print("  ✅ ADBパスを自動検出しました")
            else:
                print("  ❌ ADBの自動検出に失敗しました。手動で設定してください。")
                return False
        else:
            print("  ✅ ADBパスは設定済みです")
        
        # Step 2: ADBサーバー状態確認
        print("\nStep 2/6: ADBサーバー状態を確認中...")
        result = self.run_adb_command(["version"], timeout=5, retry_on_timeout=False)
        if result is None or result.returncode != 0:
            print("  ⚠ ADBサーバーが応答しません")
            issues_found.append("ADBサーバー停止")
            print("  🔧 ADBサーバーをリセットします...")
            if self.reset_adb_server():
                fixes_applied.append("ADBサーバーリセット")
                print("  ✅ ADBサーバーをリセットしました")
            else:
                print("  ❌ ADBサーバーのリセットに失敗しました")
                return False
        else:
            print("  ✅ ADBサーバーは正常に動作しています")
        
        # Step 3: デバイス検出
        print("\nStep 3/6: デバイスを検出中...")
        self.refresh_devices()
        if self.devices:
            print(f"  ✅ {len(self.devices)}台のデバイスが検出されました")
        else:
            print("  ⚠ デバイスが検出されません")
            issues_found.append("デバイス未検出")
        
        # Step 4: USB接続確認
        print("\nStep 4/6: USB接続を確認中...")
        result = self.run_adb_command(["devices"], timeout=5)
        if result and result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]
            usb_devices = [l for l in lines if l.strip() and not ':' in l.split('\t')[0] if '\t' in l]
            if usb_devices:
                print("  ✅ USBデバイスが接続されています")
                # IPアドレス取得
                self.get_device_ip()
            else:
                print("  ⚠ USBデバイスが見つかりません")
        
        # Step 5: 履歴からの再接続試行
        print("\nStep 5/6: 過去の接続履歴から再接続を試行中...")
        if self.try_quick_reconnect():
            fixes_applied.append("履歴から高速再接続")
            print("  ✅ 過去の接続から自動再接続しました")
            print("\n" + "="*50)
            print("🎉 すべての問題が解決されました！")
            print("="*50 + "\n")
            return True
        else:
            print("  ℹ 有効な接続履歴が見つかりません")
        
        # Step 6: ワイヤレス接続準備
        print("\nStep 6/6: ワイヤレス接続の準備...")
        ip = self.ip_var.get().strip()
        if ip and self.selected_device and not ':' in self.selected_device:
            print(f"  ℹ IPアドレスが設定されています: {ip}")
            print("  💡 「ワイヤレスデバッグ有効化＆接続」ボタンで接続できます")
        else:
            print("  ℹ ワイヤレス接続の準備ができていません")
            print("  💡 USBでデバイスを接続してから「ワイヤレスデバッグ有効化」を実行してください")
        
        # 結果サマリー
        print("\n" + "="*50)
        if issues_found:
            print(f"📋 検出された問題: {len(issues_found)}件")
            for issue in issues_found:
                print(f"   - {issue}")
        if fixes_applied:
            print(f"\n🔧 適用された修正: {len(fixes_applied)}件")
            for fix in fixes_applied:
                print(f"   - {fix}")
        
        if not issues_found or len(fixes_applied) == len(issues_found):
            print("\n🎉 すべての問題が解決されました！")
        else:
            print("\n⚠ 一部の問題が残っています。上記の手順を確認してください。")
        print("="*50 + "\n")
        
        return len(fixes_applied) > 0

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
                
                if 'pairing_port' in config:
                    self.pairing_port_var.set(str(config['pairing_port']))
                
                if 'connection_history' in config and isinstance(config['connection_history'], list):
                    self.connection_history = []
                    for item in config['connection_history']:
                        if isinstance(item, dict) and 'ip' in item and 'port' in item:
                            self.connection_history.append({
                                'ip': item['ip'],
                                'port': str(item['port']),
                                'timestamp': item.get('timestamp', 0),
                                'device_name': (item.get('device_name') or '').strip(),
                            })
                    
                # ウィンドウサイズを設定
                if 'window_size' in config:
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
        
        self._refresh_simple_connect_hint()

    def _parse_mdns_services_text(self, text):
        """adb mdns services の出力から IPv4:port を抽出"""
        if not text:
            return []
        found = []
        seen = set()

        def add_from_line(line):
            for m in re.finditer(r'\b(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})\b', line):
                ip, port = m.group(1), m.group(2)
                if not self.is_valid_ip(ip) or not port.isdigit():
                    continue
                p = int(port)
                if p < 1 or p > 65535:
                    continue
                key = f"{ip}:{port}"
                if key not in seen:
                    seen.add(key)
                    found.append((ip, port))

        lines = text.splitlines()
        interesting = [ln for ln in lines if re.search(r'(?i)adb|tls|_tcp|pair|service', ln)]
        for ln in (interesting if interesting else lines):
            add_from_line(ln)
        if not found:
            add_from_line(text)
        return found

    def _discover_via_adb_mdns(self):
        """platform-tools の mDNS で同一LANのワイヤレスADBを列挙（ペア済み端末向け）"""
        if not self.adb_path:
            return []
        chk = self.run_adb_command(["mdns", "check"], timeout=5, retry_on_timeout=False)
        if chk is None:
            return []
        if chk.returncode != 0:
            hint = (chk.stdout or chk.stderr or "").strip()
            if hint:
                print(f"mDNS check 非0（Windows は Bonjour や環境変数 ADB_MDNS_OPENSCREEN=1 が必要な場合あり）: {hint[:180]}")
        r = self.run_adb_command(["mdns", "services"], timeout=14, retry_on_timeout=False)
        if r is None or r.returncode != 0:
            return []
        blob = (r.stdout or "") + "\n" + (r.stderr or "")
        eps = self._parse_mdns_services_text(blob)
        if eps:
            print(f"mDNS で {len(eps)} 件の候補を検出: {', '.join(f'{a}:{b}' for a, b in eps[:5])}{'…' if len(eps) > 5 else ''}")
        return eps

    def _adb_mdns_services_raw(self) -> str:
        """adb mdns services の生テキスト（種別パース用）"""
        if not self.adb_path:
            return ""
        chk = self.run_adb_command(["mdns", "check"], timeout=5, retry_on_timeout=False)
        if chk is None:
            return ""
        if chk.returncode != 0:
            hint = (chk.stdout or chk.stderr or "").strip()
            if hint:
                print(f"mDNS check 非0: {hint[:160]}")
        r = self.run_adb_command(["mdns", "services"], timeout=14, retry_on_timeout=False)
        if r is None or r.returncode != 0:
            return ""
        return (r.stdout or "") + "\n" + (r.stderr or "")

    def _parse_mdns_pairing_and_connect(self, text: str):
        """_adb-tls-pairing._tcp / _adb-tls-connect._tcp に紐づく行から IPv4:port を分類"""
        pairing, connect = [], []
        seen_p, seen_c = set(), set()
        if not text:
            return pairing, connect
        for line in text.splitlines():
            ll = line.lower()
            found = re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})\b", line)
            if not found:
                continue
            is_pair = "tls-pairing" in ll or "tls_pairing" in ll or "adbtlspa" in ll
            is_conn = "tls-connect" in ll or "tls_connect" in ll or "adbtlsconn" in ll
            if is_pair and not is_conn:
                for ip, port in found:
                    if not self.is_valid_ip(ip) or not port.isdigit():
                        continue
                    p = int(port)
                    if p < 1 or p > 65535:
                        continue
                    key = (ip, port)
                    if key not in seen_p:
                        seen_p.add(key)
                        pairing.append((ip, port))
            elif is_conn:
                for ip, port in found:
                    if not self.is_valid_ip(ip) or not port.isdigit():
                        continue
                    p = int(port)
                    if p < 1 or p > 65535:
                        continue
                    key = (ip, port)
                    if key not in seen_c:
                        seen_c.add(key)
                        connect.append((ip, port))
        return pairing, connect

    def _parse_endpoint_line(self, line: str):
        """'192.168.0.5:37045' 形式"""
        if not line:
            return None, None
        line = line.strip().split()[0] if line.strip() else ""
        if ":" not in line:
            return None, None
        ip, _, port = line.rpartition(":")
        ip, port = ip.strip(), port.strip()
        if not self.is_valid_ip(ip) or not port.isdigit():
            return None, None
        return ip, port

    def _load_adb_device_txt(self):
        try:
            if not os.path.isfile(ADB_DEVICE_TXT):
                return None, None
            with open(ADB_DEVICE_TXT, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            return self._parse_endpoint_line(raw)
        except Exception as e:
            print(f"{ADB_DEVICE_TXT} 読込: {e}")
            return None, None

    def _save_adb_device_txt(self, ip, port):
        ps = str(port)
        line = f"{ip}:{ps}\n"
        try:
            with open(ADB_DEVICE_TXT, "w", encoding="utf-8") as f:
                f.write(line)
            self.saved_mdns_endpoint_var.set(f"{ip}:{ps}")
            self.ip_var.set(ip)
            self.port_var.set(ps)
            print(f"{ADB_DEVICE_TXT} に保存: {ip}:{ps}")
        except Exception as e:
            print(f"{ADB_DEVICE_TXT} 保存エラー: {e}")

    def _sync_saved_endpoint_from_file(self):
        ip, port = self._load_adb_device_txt()
        if ip and port:
            self.saved_mdns_endpoint_var.set(f"{ip}:{port}")

    def _pick_connect_endpoint(self, pairing_ip, connect_list):
        if not connect_list:
            return None
        for cip, cport in connect_list:
            if cip == pairing_ip:
                return (cip, cport)
        return connect_list[0]

    def _wait_mdns_connect_after_pair(self, pairing_ip, total_wait=12.0):
        """ペア成功後: mDNS（_adb-tls-connect）をポーリングしつつ、同じ IP に対して nmap を並列実行"""
        mdns_ep = [None]
        nmap_ep = [None]

        def mdns_poll():
            deadline = time.time() + total_wait
            while time.time() < deadline:
                blob = self._adb_mdns_services_raw()
                _, conn = self._parse_mdns_pairing_and_connect(blob)
                if conn:
                    picked = self._pick_connect_endpoint(pairing_ip, conn)
                    if picked:
                        mdns_ep[0] = picked
                        print(f"mDNS 接続用: {picked[0]}:{picked[1]}")
                        return
                time.sleep(0.45)

        def nmap_scan():
            try:
                p = self.scan_wireless_port_fast(pairing_ip)
                if not p:
                    p = self.scan_wireless_port(pairing_ip)
                if p:
                    nmap_ep[0] = (pairing_ip, str(p))
                    print(f"nmap 候補: {pairing_ip}:{p}")
            except Exception as e:
                print(f"nmap スキャン: {e}")

        t1 = threading.Thread(target=mdns_poll, daemon=True)
        t2 = threading.Thread(target=nmap_scan, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=total_wait + 1)
        t2.join(timeout=45)
        if mdns_ep[0]:
            return mdns_ep[0]
        if nmap_ep[0]:
            return nmap_ep[0]
        return None

    def mdns_pair_with_code_dialog(self):
        """_adb-tls-pairing を mDNS から取得 → コードだけ入力 → pair → connect を adb_device.txt に"""
        if not self.adb_path:
            messagebox.showwarning("ADB", "ADB パスを設定するか「検出」を押してください。")
            return
        blob = self._adb_mdns_services_raw()
        pairing, _ = self._parse_mdns_pairing_and_connect(blob)
        if not pairing:
            messagebox.showerror(
                "mDNS",
                "ペアリング用サービス（_adb-tls-pairing）が見つかりません。\n"
                "・スマホでワイヤレスデバッグ ON\n・PC と同じ Wi‑Fi\n"
                "・Windows では Bonjour や ADB_MDNS_OPENSCREEN=1 が必要なことがあります。",
            )
            return
        ip, pport = pairing[0]
        if len(pairing) > 1:
            print(f"ペア候補が複数あります。先頭を使用: {ip}:{pport} （他: {pairing[1:]}）")
        code = simpledialog.askstring(
            "ペアリング",
            "スマホのペアリングコードを入力してください",
            parent=self.root,
        )
        if not code:
            return
        code = re.sub(r"\s+", "", code.strip())
        if not code:
            return
        print(f"adb pair {ip}:{pport} …")
        pr = self.run_adb_command(["pair", f"{ip}:{pport}", code], timeout=35, retry_on_timeout=False)
        if pr is None:
            messagebox.showerror("ペアリング", "ADB が応答しません。")
            return
        out = (pr.stdout or "") + (pr.stderr or "")
        if pr.returncode != 0:
            messagebox.showerror("ペアリング失敗", (out.strip() or "不明")[:700])
            return
        print(f"ペアリング成功: {out.strip()[:200]}")
        ep = self._wait_mdns_connect_after_pair(ip)
        if not ep:
            blob2 = self._adb_mdns_services_raw()
            _, conn2 = self._parse_mdns_pairing_and_connect(blob2)
            if conn2:
                cip, cport = self._pick_connect_endpoint(ip, conn2)
                self._save_adb_device_txt(cip, cport)
                messagebox.showinfo("保存", f"接続用を保存しました: {cip}:{cport}")
            else:
                messagebox.showwarning(
                    "接続先",
                    "接続用（_adb-tls-connect）が mDNS にまだ出ていません。\n"
                    "数秒待って「接続（保存→失敗時mDNS更新）」を押すか、スマホ画面の接続用を手入力してください。",
                )
            return
        cip, cport = ep
        self._save_adb_device_txt(cip, cport)
        messagebox.showinfo("完了", f"接続用を {ADB_DEVICE_TXT} と上の欄に保存しました。\n{cip}:{cport}")

    def save_endpoint_from_box_to_file(self):
        ip, port = self._parse_endpoint_line(self.saved_mdns_endpoint_var.get())
        if not ip or not port:
            messagebox.showwarning("入力", "例: 192.168.0.5:37045 の形式で入力してください。")
            return
        self._save_adb_device_txt(ip, port)
        messagebox.showinfo("保存", f"{ADB_DEVICE_TXT} に書き込みました。")

    def _get_connect_target_from_box_or_file(self):
        ip, port = self._parse_endpoint_line(self.saved_mdns_endpoint_var.get().strip())
        if ip and port:
            return ip, port
        return self._load_adb_device_txt()

    def _try_adb_connect_ok(self, ip, port):
        result = self.run_adb_command(["connect", f"{ip}:{port}"], timeout=15)
        if result is None:
            return False
        return result.returncode == 0 and "connected" in (result.stdout or "").lower()

    def _finalize_wireless_connected(self, ip, port):
        self.ip_var.set(ip)
        self.port_var.set(str(port))
        self.refresh_devices()
        dname = self._fetch_device_display_name_after_connect(f"{ip}:{port}")
        self.save_successful_connection(ip, port, device_name=dname or None)
        self._save_adb_device_txt(ip, port)
        if dname:
            self.wireless_status_label.config(
                text=f"ワイヤレス: {dname} ({ip}:{port})",
                foreground="green",
            )
        else:
            self.wireless_status_label.config(
                text=f"ワイヤレス接続済み: {ip}:{port}",
                foreground="green",
            )
        print(f"ワイヤレス接続成功: {self._format_endpoint_label(ip, port)}")
        self.start_connection_monitor()
        self._refresh_simple_connect_hint()

    def _try_saved_mdns_connect_with_refresh(self) -> bool:
        """保存（ボックス/ファイル）→ connect。失敗したら _adb-tls-connect を mDNS で取り直して再試行"""
        ip, port = self._get_connect_target_from_box_or_file()
        if not ip or not port:
            return False
        print(f"保存済み接続先を試行: {ip}:{port}")
        if self._try_adb_connect_ok(ip, port):
            self._finalize_wireless_connected(ip, port)
            return True
        print("保存先では接続できませんでした。mDNS と nmap（保存済みIP）を並列で探索します…")
        ip_saved, _ = self._get_connect_target_from_box_or_file()
        endpoints = [None]

        def mdns_job():
            blob = self._adb_mdns_services_raw()
            _, conn = self._parse_mdns_pairing_and_connect(blob)
            endpoints[0] = conn or []

        nmap_pair = [None]

        def nmap_job():
            if ip_saved and self.is_valid_ip(ip_saved):
                p = self.scan_wireless_port_fast(ip_saved)
                if not p:
                    p = self.scan_wireless_port(ip_saved)
                if p:
                    nmap_pair[0] = (ip_saved, str(p))

        t1 = threading.Thread(target=mdns_job, daemon=True)
        t2 = threading.Thread(target=nmap_job, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=20)
        t2.join(timeout=42)
        eps = endpoints[0] or []
        for ci, cp in eps:
            print(f"接続試行: {ci}:{cp} (mDNS)")
            if self._try_adb_connect_ok(ci, cp):
                self._finalize_wireless_connected(ci, cp)
                return True
        if nmap_pair[0]:
            ci, cp = nmap_pair[0]
            print(f"接続試行: {ci}:{cp} (nmap)")
            if self._try_adb_connect_ok(ci, cp):
                self._finalize_wireless_connected(ci, cp)
                return True
        if not eps and not nmap_pair[0]:
            print("mDNS にも nmap にも接続用候補がありませんでした。")
        return False

    def mdns_connect_saved_with_refresh(self):
        if not self.adb_path:
            messagebox.showwarning("ADB", "ADB パスを設定するか「検出」を押してください。")
            return
        if self._try_saved_mdns_connect_with_refresh():
            return
        messagebox.showerror(
            "接続",
            "保存された接続先でも、mDNS の接続用でも接続できませんでした。\n"
            "ワイヤレスデバッグを一度 OFF→ON してから「ペアリング」をやり直してください。",
        )

    def _local_ipv4_subnet_prefixes(self):
        """PC が属する IPv4 /24 の先頭3オクテット（同一LANスキャン用）"""
        prefixes = []
        seen = set()

        def add_from_ip(ip):
            if not ip or not self.is_valid_ip(ip):
                return
            if ip.startswith("127."):
                return
            if ip.startswith("169.254."):
                return
            pre = ".".join(ip.split(".")[:3])
            if pre not in seen:
                seen.add(pre)
                prefixes.append(pre)

        if sys.platform == "win32":
            try:
                r = subprocess.run(
                    ["ipconfig"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    encoding="utf-8",
                    errors="replace",
                    **_subprocess_hide_console_kwargs(),
                )
                if r.stdout:
                    for m in re.finditer(
                        r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b",
                        r.stdout,
                    ):
                        add_from_ip(m.group(1))
            except Exception as e:
                print(f"ipconfig 取得: {e}")

        try:
            s = py_socket.socket(py_socket.AF_INET, py_socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            add_from_ip(s.getsockname()[0])
            s.close()
        except Exception:
            pass

        return prefixes

    def _scan_lan_open_ports(self, ports=("5555", "5556"), timeout=0.16, max_workers=96):
        """同一LANの /24 を並列にスキャンし、ADB でよく使う TCP ポートが開いているホストを列挙"""
        prefixes = self._local_ipv4_subnet_prefixes()
        if not prefixes:
            print("同一LANスキャン: ローカルサブネットを特定できませんでした")
            return []

        def check(ip_port):
            ip, port_s = ip_port
            try:
                sock = py_socket.socket(py_socket.AF_INET, py_socket.SOCK_STREAM)
                sock.settimeout(timeout)
                r = sock.connect_ex((ip, int(port_s)))
                sock.close()
                return (ip, port_s) if r == 0 else None
            except OSError:
                return None

        tasks = []
        for pre in prefixes:
            for host in range(1, 255):
                ip = f"{pre}.{host}"
                for p in ports:
                    tasks.append((ip, str(p)))

        out = []
        seen = set()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            for res in pool.map(check, tasks, chunksize=32):
                if res:
                    k = f"{res[0]}:{res[1]}"
                    if k not in seen:
                        seen.add(k)
                        out.append(res)
        if out:
            preview = ", ".join(f"{a}:{b}" for a, b in out[:10])
            more = "…" if len(out) > 10 else ""
            print(f"同一LANスキャン: {len(out)} 件 {preview}{more}")
        else:
            print(
                "同一LANスキャン: 5555/5556 に応答なし。"
                "（Android 11+ のワイヤレスTLSのランダムポートは mDNS かスマホ表示が必要）"
            )
        return out

    def _try_autofill_ip_from_usb(self):
        """USB でつながっているとき Wi‑Fi の IP を adb shell から入れる（ポートは別途 mDNS 等）"""
        ip_u = self.ip_var.get().strip()
        if ip_u and self.is_valid_ip(ip_u):
            return
        self.refresh_devices(preserve_selection=True)
        dev = self.selected_device
        if dev and ':' not in dev:
            self.get_device_ip()
            got = self.ip_var.get().strip()
            if got and self.is_valid_ip(got):
                print(f"USB 経由で端末の Wi‑Fi IP を取得: {got}")

    def _wireless_connect_candidates(self, include_mdns=False):
        """ワンボタン接続用。入力 → mDNS → 同一LANスキャン → 履歴（LAN/mDNS は接続ボタン時のみ）"""
        seen = set()
        out = []
        ip_u, port_u = self.ip_var.get().strip(), self.port_var.get().strip()

        if ip_u and self.is_valid_ip(ip_u) and port_u:
            key = f"{ip_u}:{port_u}"
            seen.add(key)
            out.append((ip_u, port_u))

        mdns_eps = self._discover_via_adb_mdns() if include_mdns else []
        lan_eps = self._scan_lan_open_ports() if include_mdns else []

        for ip, port in mdns_eps:
            key = f"{ip}:{port}"
            if key not in seen:
                seen.add(key)
                out.append((ip, port))

        for ip, port in lan_eps:
            key = f"{ip}:{port}"
            if key not in seen:
                seen.add(key)
                out.append((ip, port))

        if ip_u and self.is_valid_ip(ip_u) and not port_u:
            for port in ("5555", "5556"):
                key = f"{ip_u}:{port}"
                if key not in seen:
                    seen.add(key)
                    out.append((ip_u, port))
            for ip, port in mdns_eps:
                if ip == ip_u:
                    key = f"{ip}:{port}"
                    if key not in seen:
                        seen.add(key)
                        out.append((ip, port))

        if port_u and not (ip_u and self.is_valid_ip(ip_u)):
            for ip, port in mdns_eps:
                key = f"{ip}:{port_u}"
                if key not in seen:
                    seen.add(key)
                    out.append((ip, port_u))
            for ip, _port in lan_eps:
                key = f"{ip}:{port_u}"
                if key not in seen:
                    seen.add(key)
                    out.append((ip, port_u))

        for entry in reversed(self.connection_history):
            ip, port = entry.get('ip', '').strip(), str(entry.get('port', '')).strip()
            if not ip or not self.is_valid_ip(ip) or not port:
                continue
            key = f"{ip}:{port}"
            if key not in seen:
                seen.add(key)
                out.append((ip, port))
        return out

    def _lookup_history_device_name(self, ip, port):
        """接続履歴に保存した表示名（メーカー + モデル）"""
        ps = str(port)
        for c in reversed(self.connection_history):
            if c.get('ip') == ip and str(c.get('port')) == ps:
                return (c.get('device_name') or '').strip()
        return ''

    def _format_endpoint_label(self, ip, port):
        """ログ用: IP:ポート (端末名)"""
        name = self._lookup_history_device_name(ip, port)
        if name:
            return f"{ip}:{port} ({name})"
        return f"{ip}:{port}"

    def _fetch_device_display_name_after_connect(self, serial):
        """接続済みの serial（例 192.168.0.5:5555）から端末のわかりやすい名前を取得"""
        if not self.adb_path or not serial:
            return ''
        m = self.run_adb_command(
            ['-s', serial, 'shell', 'getprop', 'ro.product.model'],
            timeout=5,
            retry_on_timeout=False,
        )
        man = self.run_adb_command(
            ['-s', serial, 'shell', 'getprop', 'ro.product.manufacturer'],
            timeout=5,
            retry_on_timeout=False,
        )
        model = (m.stdout or '').strip() if m and m.returncode == 0 else ''
        manu = (man.stdout or '').strip() if man and man.returncode == 0 else ''
        parts = [p for p in (manu, model) if p]
        return ' '.join(parts) if parts else ''

    def _refresh_simple_connect_hint(self):
        """簡単タブの説明文を更新（mDNS は実行しない）"""
        if not hasattr(self, 'simple_connect_hint_var'):
            return
        cands = self._wireless_connect_candidates(include_mdns=False)
        ip_u, port_u = self.ip_var.get().strip(), self.port_var.get().strip()
        if ip_u and port_u:
            self.simple_connect_hint_var.set(
                f"入力中の接続先を優先します: {ip_u}:{port_u}（空にすると自動検出・保存済みへ）"
            )
        elif ip_u and self.is_valid_ip(ip_u) and not port_u:
            self.simple_connect_hint_var.set(
                f"IP は自動取得済み: {ip_u}。接続ボタンで mDNS・5555 などを試します。"
            )
        elif cands:
            last = cands[0]
            extra = f" ほか {len(cands) - 1} 件も試行" if len(cands) > 1 else ""
            dn = self._lookup_history_device_name(last[0], last[1])
            tag = f"「{dn}」 " if dn else ""
            self.simple_connect_hint_var.set(
                f"保存済み: {tag}{last[0]}:{last[1]}。接続ボタン1回{extra}（mDNS・LAN も検索）"
            )
        else:
            self.simple_connect_hint_var.set(
                "同じ LAN でデバッグON → ボタン1回（mDNS ＋ 同一LANの 5555/5556 スキャン）。"
                " TLS のランダムポートは mDNS かスマホ表示。USB 時は IP 自動取得。"
            )

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
            
            if self.pairing_port_var.get().strip():
                config['pairing_port'] = self.pairing_port_var.get().strip()
                
            # ウィンドウサイズを保存
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
                
            # 接続履歴を保存
            if hasattr(self, 'connection_history') and self.connection_history:
                config['connection_history'] = self.connection_history[-5:]  # 最新5件のみ
            
            # 保存日時を記録
            from datetime import datetime
            config['last_saved'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            with open('wireless_debug_config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                
            print(f"設定を保存しました: {config['last_saved']}")
                
        except Exception as e:
            print(f"設定保存エラー: {e}")

    def save_successful_connection(self, ip, port, device_name=None):
        """成功した接続を履歴に保存（device_name は getprop 由来の表示用）"""
        ps = str(port)
        connection_info = {
            'ip': ip,
            'port': ps,
            'timestamp': time.time(),
            'device_name': (device_name or '').strip(),
        }
        
        # 既存の同じ接続情報を削除
        self.connection_history = [
            c for c in self.connection_history
            if not (c['ip'] == ip and str(c['port']) == ps)
        ]
        
        # 新しい接続を追加
        self.connection_history.append(connection_info)
        
        # 最大サイズを超えたら古いものを削除
        if len(self.connection_history) > self.max_history_size:
            self.connection_history.pop(0)
        
        print(f"接続履歴を保存: {ip}:{port}")
        self.save_settings()
        self._refresh_simple_connect_hint()

    def get_last_successful_connection(self):
        """最後に成功した接続情報を取得"""
        if self.connection_history:
            return self.connection_history[-1]
        return None

    def try_quick_reconnect(self):
        """履歴から高速再接続を試行"""
        last_conn = self.get_last_successful_connection()
        if not last_conn:
            return False
        
        ip, port = last_conn['ip'], last_conn['port']
        
        # ポートが開いているか確認
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip, int(port)))
            sock.close()
            
            if result == 0:
                print(f"履歴から高速再接続: {ip}:{port}")
                self.ip_var.set(ip)
                self.port_var.set(port)
                self.connect_wireless()
                return True
        except:
            pass
        
        return False

def main():
    root = tk.Tk()
    app = LightWDconnectApp(root)
    app.run()

if __name__ == "__main__":
    main() 
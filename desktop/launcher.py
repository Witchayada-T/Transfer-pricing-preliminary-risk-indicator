"""Desktop controller for the local-only, frozen financial review application."""
from pathlib import Path
import argparse
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def analysis_root():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'payload'
    return Path(__file__).resolve().parents[1]


def local_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def worker_command(port):
    prefix = [sys.executable] if getattr(sys, 'frozen', False) else [sys.executable, str(Path(__file__).resolve())]
    return prefix + ['--serve', '--port', str(port)]


def healthy(port):
    # Never send a local health request through a configured HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
            return response.status == 200 and response.read().strip() == b'ok'
    except (OSError, ValueError):
        return False


def stop_worker(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def serve(port):
    base = analysis_root()
    sys.path.insert(0, str(base))
    sys.path.insert(0, str(base / 'application'))
    os.chdir(base / 'application')
    # CLI options override machine/user settings. No network interface is exposed.
    from streamlit.web import cli
    sys.argv = ['streamlit', 'run', str(base / 'application/app.py'),
                '--server.address=127.0.0.1', f'--server.port={port}',
                '--server.headless=true', '--browser.gatherUsageStats=false',
                '--server.fileWatcherType=none', '--global.developmentMode=false']
    cli.main()


def smoke_test(receipt):
    """Check the reviewer distribution without a historical company table."""
    base=analysis_root();sys.path[:0]=[str(base),str(base/'application')]
    import joblib
    from model_engine import screen_new_company
    from streamlit.testing.v1 import AppTest
    bundle=joblib.load(base/'outputs/thai_industry_models.joblib')
    assert not (base/'clean_data/Model_input_all_items.csv').exists()
    assert not (base/'clean_data/Company_coverage.csv').exists()
    app=AppTest.from_file(str(base/'application/app.py'),default_timeout=120).run()
    assert not app.exception, [str(e) for e in app.exception]
    widget=lambda kind,label:next(w for w in getattr(app,kind) if w.label==label)
    assert list(widget('radio','Workspace').options)==['Company screening']
    assert 'Load collected example' not in widget('radio','Financial input').options
    widget('checkbox','Include financial-model comparison').uncheck().run()
    widget('selectbox','Primary functional profile').set_value('Routine entity').run()
    widget('selectbox','The routine entity has recurring losses without a business explanation').set_value('Yes')
    widget('button','Evaluate company').click().run()
    assert not app.exception
    result=app.session_state['last_report']['review_result']
    assert result['concern']=='Higher concern' and result['screening_flag'] is True
    example={'nature_pool':'it_services','registration_number':'SYNTHETIC_SMOKE_TEST','fiscal_year':2025,'revenue':1000000,'net_profit':50000,'net_margin_pct':5,'operating_margin_pct':7,'gross_margin_pct':20,'return_on_assets_pct':5,'return_on_equity_pct':10,'current_ratio':1.5,'receivables_turnover':4,'inventory_turnover':3,'payables_turnover':4,'asset_turnover':1.5,'operating_expense_ratio_pct':93,'assets_to_equity':2,'liabilities_to_assets':.5,'liabilities_to_equity':1,'liabilities_to_working_capital':1}
    assert screen_new_company(example,bundle)['status']=='SCORED'
    assert screen_new_company({'nature_pool':'OTHER'},bundle)['status']=='ABSTAIN'
    Path(receipt).write_text(json.dumps({'platform':sys.platform,'frozen':bool(getattr(sys,'frozen',False)),'model_version':bundle['version'],'application_rendered':True,'independent_rule_engine':True,'no_historical_company_table':True,'no_collected_example_browser':True,'supported_inference':'SCORED','unsupported_inference':'ABSTAIN'},indent=2),encoding='utf-8')


def desktop(test_receipt=None):
    import tkinter as tk
    from tkinter import messagebox
    base = analysis_root()
    logs = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'ThaiCompanyReview/logs'
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / ('session-' + time.strftime('%Y%m%d-%H%M%S') + '.log')
    root = tk.Tk()
    root.title('Thai Company Review')
    root.geometry('540x280')
    root.resizable(False, False)
    root.configure(bg='#F3F6F9')
    tk.Label(root, text='Thai Company Review', font=('Segoe UI', 20, 'bold'), bg='#F3F6F9', fg='#183044').pack(pady=(28, 8))
    status = tk.StringVar(value='Starting your local application…')
    tk.Label(root, textvariable=status, font=('Segoe UI', 11), bg='#F3F6F9', wraplength=490).pack(pady=8)
    tk.Label(root, text='Keep this window open while reviewing companies.\nModels and financial data stay on this computer.',
             font=('Segoe UI', 10), bg='#F3F6F9', fg='#183044').pack(pady=8)
    port = local_port()
    url = f'http://127.0.0.1:{port}'
    opened = False
    events = queue.Queue()
    log = log_path.open('wb')
    child = subprocess.Popen(worker_command(port) + ['--log-file', str(log_path)], cwd=base, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    open_button = tk.Button(root, text='Open application', state='disabled', command=lambda: webbrowser.open(url),
                            font=('Segoe UI', 11), padx=20, pady=6)
    open_button.pack(pady=6)

    def wait_ready():
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and child.poll() is None:
            if healthy(port):
                events.put('ready')
                return
            time.sleep(.4)
        events.put('failed')

    def close():
        stop_worker(child)
        log.close()
        root.destroy()

    def poll():
        nonlocal opened
        try:
            event = events.get_nowait()
        except queue.Empty:
            event = None
        if event == 'ready':
            status.set('Ready — the application is running locally.')
            open_button.configure(state='normal')
            opened = True
            if test_receipt:
                root.after(100, close)
            else:
                webbrowser.open(url)
        elif event == 'failed' or (opened and child.poll() is not None):
            status.set('The application stopped. See the local log for details.')
            open_button.configure(state='disabled')
            if test_receipt:
                close()
            else:
                messagebox.showerror('Application could not run', f'Please share this diagnostic log:\n{log_path}')
            return
        root.after(400, poll)

    tk.Button(root, text='Stop and close', command=close, font=('Segoe UI', 10)).pack(pady=6)
    root.protocol('WM_DELETE_WINDOW', close)
    threading.Thread(target=wait_ready, daemon=True).start()
    root.after(400, poll)
    try:
        root.mainloop()
    finally:
        stop_worker(child)
        log.close()
    if test_receipt:
        assert opened and child.poll() is not None, f'Desktop startup failed; see {log_path}'
        Path(test_receipt).write_text(json.dumps({'platform': sys.platform,
            'frozen': bool(getattr(sys, 'frozen', False)), 'controller_window_opened': True,
            'local_server_ready': True, 'controller_closed_server': True}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    # PyInstaller's windowed bootloader has no console streams. Libraries may
    # still write startup notices; provide valid sinks before importing them.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--port', type=int, default=8501)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--controller-smoke-test', action='store_true')
    parser.add_argument('--receipt', default='desktop_smoke_receipt.json')
    parser.add_argument('--log-file')
    args = parser.parse_args()
    if args.log_file:
        sys.stdout = sys.stderr = open(args.log_file, 'a', encoding='utf-8', buffering=1)
    if args.serve:
        serve(args.port)
    elif args.smoke_test:
        try:
            smoke_test(args.receipt)
        except Exception:
            import traceback
            Path(args.receipt).write_text(json.dumps({'failed': True, 'traceback': traceback.format_exc()}, indent=2), encoding='utf-8')
            raise SystemExit(1)
    elif args.controller_smoke_test:
        desktop(args.receipt)
    else:
        desktop()

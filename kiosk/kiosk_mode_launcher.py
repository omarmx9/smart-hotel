#!/usr/bin/env python
"""Simple Python helper to start Django dev server and open browser in kiosk mode on Windows.

Usage:
    python kiosk_mode_launcher.py --host localhost --port 8000 --path /
"""
import argparse
import os
import subprocess
import sys
import time
import webbrowser


def find_browser_exe():
    # Common installation paths for Chrome/Edge on Windows
    env = os.environ
    candidates = [
        os.path.join(env.get('ProgramFiles', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(env.get('ProgramFiles(x86)', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        os.path.join(env.get('ProgramFiles', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        os.path.join(env.get('ProgramFiles(x86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def start_django_server(host, port):
    py = sys.executable or 'python'
    args = [py, 'manage.py', 'runserver', f'{host}:{port}']
    # Launch in a new console on Windows so logs are visible
    creationflags = 0
    if os.name == 'nt':
        creationflags = subprocess.CREATE_NEW_CONSOLE
    print('Starting Django dev server:', ' '.join(args))
    return subprocess.Popen(args, creationflags=creationflags)


def open_kiosk(url):
    exe = find_browser_exe()
    if exe:
        print('Opening kiosk browser:', exe, url)
        try:
            subprocess.Popen([exe, '--kiosk', url])
            return
        except Exception:
            pass
    print('Falling back to default browser for:', url)
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', default='8000')
    parser.add_argument('--path', default='/')
    args = parser.parse_args()

    url = f'http://{args.host}:{args.port}{args.path}'

    proc = start_django_server(args.host, args.port)
    # Give server a moment to start
    time.sleep(1.5)
    open_kiosk(url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print('Shutting down server...')
        proc.terminate()


if __name__ == '__main__':
    main()

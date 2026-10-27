"""Experimental Windows adapter. Never synthesizes desktop-wide input."""
import ctypes
from ctypes import wintypes
import io
import threading
import psutil
import win32api
import win32con as C
import win32gui as G
import win32process as P
import win32ui
from PIL import Image
from PIL import ImageGrab


class GuiThreadInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND),
                ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
                ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND),
                ('rcCaret', wintypes.RECT)]


class WindowsBackend:
    def __init__(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass
        self.lock = threading.RLock()
        self.allowed = {}  # hwnd -> (pid, creation time); blocks stale process IDs
        self.allow_all = False
        self.focus = None
        self.drag = None

    def identity(self, hwnd):
        _, pid = P.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        if process.name().lower() not in {'packettracer.exe', 'packettracer'}:
            raise ValueError('Fereastra nu aparține Packet Tracer')
        return pid, process.create_time()

    def discover(self):
        result = []
        def visit(hwnd, _):
            if not G.IsWindowVisible(hwnd) or not G.GetWindowText(hwnd):
                return
            try:
                self.identity(hwnd)
                result.append({'id': str(hwnd), 'title': G.GetWindowText(hwnd)})
            except (psutil.Error, ValueError, OSError):
                pass
        G.EnumWindows(visit, None)
        return result

    def grant(self, ids):
        with self.lock:
            self.release()
            self.allow_all = False
            self.allowed = {int(i): self.identity(int(i)) for i in ids}

    def grant_all(self):
        with self.lock:
            self.release()
            self.allow_all = True
            self.allowed = {int(row['id']): self.identity(int(row['id'])) for row in self.discover()}

    def validate(self, hwnd):
        if hwnd not in self.allowed or not G.IsWindow(hwnd):
            raise ValueError('Fereastra nu mai este autorizată')
        if self.identity(hwnd) != self.allowed[hwnd]:
            raise ValueError('Procesul s-a schimbat')
        if not G.IsWindowVisible(hwnd) or G.IsIconic(hwnd):
            raise ValueError('Restaurează fereastra Packet Tracer; nu o minimiza')

    def windows(self):
        with self.lock:
            if self.allow_all:
                current = {int(row['id']): self.identity(int(row['id'])) for row in self.discover()}
                self.allowed.update(current)
            result = []
            for hwnd in list(self.allowed):
                try:
                    self.validate(hwnd)
                    result.append({'id': str(hwnd), 'title': G.GetWindowText(hwnd)})
                except (ValueError, psutil.Error, OSError):
                    continue
            return result

    def capture(self, wid):
        with self.lock:
            hwnd = int(wid)
            self.validate(hwnd)
            _, _, w, h = G.GetClientRect(hwnd)
            if not 1 <= w <= 7680 or not 1 <= h <= 4320:
                raise ValueError('Dimensiuni de captură neacceptate')
            dc = G.GetDC(hwnd)
            source = memory = bitmap = previous = None
            try:
                source = win32ui.CreateDCFromHandle(dc)
                memory = source.CreateCompatibleDC()
                bitmap = win32ui.CreateBitmap()
                bitmap.CreateCompatibleBitmap(source, w, h)
                previous = memory.SelectObject(bitmap)
                memory.FillSolidRect((0, 0, w, h), 0)
                # First ask Qt to paint the client and children. Packet Tracer
                # may use GPU-backed widgets and return a uniform frame here.
                G.SendMessageTimeout(hwnd, C.WM_PRINT, memory.GetSafeHdc(),
                                     4 | 8 | 16, C.SMTO_ABORTIFHUNG, 500)
                frame = Image.frombuffer('RGB', (w, h), bitmap.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
                extrema = frame.getextrema()
                if all(hi - lo < 2 for lo, hi in extrema):
                    # PW_RENDERFULLCONTENT is supported by modern Windows and
                    # works better for Qt/OpenGL windows than WM_PRINT.
                    memory.FillSolidRect((0, 0, w, h), 0)
                    rendered = ctypes.windll.user32.PrintWindow(
                        hwnd, memory.GetSafeHdc(), 2)
                    frame = Image.frombuffer('RGB', (w, h), bitmap.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
                    extrema = frame.getextrema()
                    if not rendered or all(hi - lo < 2 for lo, hi in extrema):
                        raise ValueError('Captură uniformă/neagră: Packet Tracer refuză capturarea ferestrei')
                frame.thumbnail((1600, 1000))
                output = io.BytesIO()
                frame.save(output, 'JPEG', quality=75)
                return output.getvalue(), frame.width, frame.height
            finally:
                if memory and previous:
                    memory.SelectObject(previous)
                if bitmap:
                    G.DeleteObject(bitmap.GetHandle())
                if memory:
                    memory.DeleteDC()
                if source:
                    source.DeleteDC()
                G.ReleaseDC(hwnd, dc)

    def descendant(self, root, target):
        return bool(target and (target == root or G.IsChild(root, target))
                    and P.GetWindowThreadProcessId(target)[1] == self.allowed[root][0])

    def hit(self, root, x, y):
        screen = G.ClientToScreen(root, (x, y))
        current = root
        for _ in range(30):
            p = G.ScreenToClient(current, screen)
            child = G.ChildWindowFromPointEx(current, p, 1 | 2 | 4)
            if not child or child == current or not self.descendant(root, child):
                break
            current = child
        return current, G.ScreenToClient(current, screen)

    def keyboard_target(self, root):
        info = GuiThreadInfo()
        info.cbSize = ctypes.sizeof(info)
        tid, _ = P.GetWindowThreadProcessId(root)
        if ctypes.windll.user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            if self.descendant(root, info.hwndFocus):
                return info.hwndFocus
        return self.focus if self.descendant(root, self.focus) else root

    def release(self):
        with self.lock:
            if self.drag:
                root, target, button, pos = self.drag
                try:
                    self.validate(root)
                    if self.descendant(root, target):
                        G.PostMessage(target, C.WM_LBUTTONUP if button == 0 else C.WM_RBUTTONUP, 0, pos)
                except (ValueError, psutil.Error, OSError):
                    pass
            self.drag = None
            self.focus = None

    def input(self, data):
        with self.lock:
            if data['type'] == 'release':
                self.release()
                return
            root = int(data['window'])
            self.validate(root)
            kind = data['type']
            if kind == 'pointer':
                _, _, w, h = G.GetClientRect(root)
                x, y = round(data['x'] * (w - 1)), round(data['y'] * (h - 1))
                target, (cx, cy) = self.hit(root, x, y)
                if self.drag:
                    if self.drag[0] != root:
                        raise ValueError('Drag între ferestre neacceptat')
                    target = self.drag[1]
                    if not self.descendant(root, target):
                        self.drag = None
                        raise ValueError('Controlul tras nu mai există')
                    cx, cy = G.ScreenToClient(target, G.ClientToScreen(root, (x, y)))
                pos = (cx & 65535) | ((cy & 65535) << 16)
                action, button = data['action'], data['button']
                flags = (C.MK_LBUTTON if self.drag[2] == 0 else C.MK_RBUTTON) if self.drag else 0
                if action == 'down':
                    self.focus = target
                    self.drag = (root, target, button, pos)
                    msg = C.WM_LBUTTONDOWN if button == 0 else C.WM_RBUTTONDOWN
                    flags = C.MK_LBUTTON if button == 0 else C.MK_RBUTTON
                elif action == 'up':
                    msg = C.WM_LBUTTONUP if button == 0 else C.WM_RBUTTONUP
                    self.drag, flags = None, 0
                elif action == 'double':
                    msg = C.WM_LBUTTONDBLCLK if button == 0 else C.WM_RBUTTONDBLCLK
                    flags = C.MK_LBUTTON if button == 0 else C.MK_RBUTTON
                elif action == 'wheel':
                    sx, sy = G.ClientToScreen(root, (x, y))
                    G.PostMessage(target, C.WM_MOUSEWHEEL, (data['delta'] & 65535) << 16,
                                  (sx & 65535) | ((sy & 65535) << 16))
                    return
                else:
                    msg = C.WM_MOUSEMOVE
                    if self.drag:
                        self.drag = (*self.drag[:3], pos)
                G.PostMessage(target, msg, flags, pos)
            elif kind == 'text':
                target = self.keyboard_target(root)
                text = data['text'].replace('\r\n', '\n').replace('\n', '\r')
                encoded = text.encode('utf-16-le')
                for i in range(0, len(encoded), 2):
                    G.PostMessage(target, C.WM_CHAR, int.from_bytes(encoded[i:i + 2], 'little'), 1)
            elif kind == 'key':
                key = data['key']
                target = self.keyboard_target(root)
                mapping = {'Enter': 13, 'Backspace': 8, 'Tab': 9, 'Escape': 27,
                           'Delete': 46, 'ArrowLeft': 37, 'ArrowUp': 38,
                           'ArrowRight': 39, 'ArrowDown': 40, 'Home': 36,
                           'End': 35, 'PageUp': 33, 'PageDown': 34}
                vk = mapping[key]
                scan = win32api.MapVirtualKey(vk, 0)
                bits = 1 | (scan << 16)
                if key in {'Delete','ArrowLeft','ArrowUp','ArrowRight','ArrowDown','Home','End','PageUp','PageDown'}:
                    bits |= 1 << 24
                G.PostMessage(target, C.WM_KEYDOWN, vk, bits)
                G.PostMessage(target, C.WM_KEYUP, vk, bits | (3 << 30))


class DesktopBackend:
    """Explicit full-desktop mode; input is global and requires host consent."""
    desktop_id = '0'

    def __init__(self):
        self.allowed = False
        self.lock = threading.RLock()
        self.left_down = False
        self.right_down = False

    def discover(self):
        return [{'id': self.desktop_id, 'title': 'Desktop complet · control global'}]

    def grant(self, ids):
        if self.desktop_id not in ids:
            raise ValueError('Selectează desktopul complet')
        self.allowed = True

    def release(self):
        if self.left_down:
            win32api.mouse_event(C.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        if self.right_down:
            win32api.mouse_event(C.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        self.left_down = self.right_down = False

    def windows(self):
        return self.discover() if self.allowed else []

    def capture(self, wid):
        if not self.allowed or str(wid) != self.desktop_id:
            raise ValueError('Desktopul complet nu este autorizat')
        frame = ImageGrab.grab(all_screens=True)
        frame.thumbnail((1600, 1000))
        output = io.BytesIO()
        frame.convert('RGB').save(output, 'JPEG', quality=75)
        return output.getvalue(), frame.width, frame.height

    def input(self, data):
        with self.lock:
            if data['type'] == 'release':
                self.release()
                return
            if not self.allowed or str(data.get('window')) != self.desktop_id:
                raise ValueError('Desktopul complet nu este autorizat')
            if data['type'] == 'pointer':
                left = win32api.GetSystemMetrics(C.SM_XVIRTUALSCREEN)
                top = win32api.GetSystemMetrics(C.SM_YVIRTUALSCREEN)
                width = win32api.GetSystemMetrics(C.SM_CXVIRTUALSCREEN)
                height = win32api.GetSystemMetrics(C.SM_CYVIRTUALSCREEN)
                x = left + round(data['x'] * max(1, width - 1))
                y = top + round(data['y'] * max(1, height - 1))
                win32api.SetCursorPos((x, y))
                action, button = data['action'], data.get('button', 0)
                if action == 'down':
                    flag = C.MOUSEEVENTF_RIGHTDOWN if button == 2 else C.MOUSEEVENTF_LEFTDOWN
                    win32api.mouse_event(flag, 0, 0, 0, 0)
                    if button == 2: self.right_down = True
                    else: self.left_down = True
                elif action == 'up':
                    flag = C.MOUSEEVENTF_RIGHTUP if button == 2 else C.MOUSEEVENTF_LEFTUP
                    win32api.mouse_event(flag, 0, 0, 0, 0)
                    if button == 2: self.right_down = False
                    else: self.left_down = False
                elif action == 'double':
                    flag = C.MOUSEEVENTF_RIGHTDOWN if button == 2 else C.MOUSEEVENTF_LEFTDOWN
                    up = C.MOUSEEVENTF_RIGHTUP if button == 2 else C.MOUSEEVENTF_LEFTUP
                    win32api.mouse_event(flag, 0, 0, 0, 0)
                    win32api.mouse_event(up, 0, 0, 0, 0)
                    win32api.mouse_event(flag, 0, 0, 0, 0)
                    win32api.mouse_event(up, 0, 0, 0, 0)
                elif action == 'wheel':
                    win32api.mouse_event(C.MOUSEEVENTF_WHEEL, 0, 0, data.get('delta', 0), 0)
            elif data['type'] == 'text':
                for char in data['text']:
                    code = ord(char)
                    win32api.keybd_event(0, code, C.KEYEVENTF_UNICODE, 0)
                    win32api.keybd_event(0, code, C.KEYEVENTF_UNICODE | C.KEYEVENTF_KEYUP, 0)
            elif data['type'] == 'key':
                mapping = {'Enter': C.VK_RETURN, 'Backspace': C.VK_BACK,
                           'Tab': C.VK_TAB, 'Escape': C.VK_ESCAPE, 'Delete': C.VK_DELETE,
                           'ArrowLeft': C.VK_LEFT, 'ArrowRight': C.VK_RIGHT,
                           'ArrowUp': C.VK_UP, 'ArrowDown': C.VK_DOWN,
                           'Home': C.VK_HOME, 'End': C.VK_END,
                           'PageUp': C.VK_PRIOR, 'PageDown': C.VK_NEXT}
                vk = mapping[data['key']]
                win32api.keybd_event(vk, 0, 0, 0)
                win32api.keybd_event(vk, 0, C.KEYEVENTF_KEYUP, 0)

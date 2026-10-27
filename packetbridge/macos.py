"""Experimental macOS host adapter for Packet Tracer.

Requires Screen Recording and Accessibility permission for the Python app.
Unlike the Windows adapter, macOS input is delivered as Quartz events and
may move the local pointer while the host is being controlled.
"""
import io
import threading

from PIL import Image
import Quartz


class MacBackend:
    def __init__(self):
        self.lock = threading.RLock()
        self.allowed = {}
        self.focus = None
        self.drag = None

    def _windows(self):
        flags = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        return Quartz.CGWindowListCopyWindowInfo(flags, Quartz.kCGNullWindowID) or []

    def _is_packet_tracer(self, item):
        owner = str(item.get(Quartz.kCGWindowOwnerName, '')).lower()
        name = str(item.get(Quartz.kCGWindowName, '')).lower()
        return 'packet tracer' in owner or 'packettracer' in owner or 'packet tracer' in name or 'packettracer' in name

    def discover(self):
        result = []
        for item in self._windows():
            if not self._is_packet_tracer(item):
                continue
            wid = item.get(Quartz.kCGWindowNumber)
            bounds = item.get(Quartz.kCGWindowBounds) or {}
            if not wid or bounds.get('Width', 0) < 10 or bounds.get('Height', 0) < 10:
                continue
            title = str(item.get(Quartz.kCGWindowName) or item.get(Quartz.kCGWindowOwnerName) or 'Packet Tracer')
            result.append({'id': str(wid), 'title': title})
        return result

    def refresh_item(self, wid):
        for item in self._windows():
            if str(item.get(Quartz.kCGWindowNumber)) == str(wid) and self._is_packet_tracer(item):
                return item
        raise ValueError('Fereastra Packet Tracer nu mai este disponibilă')

    def grant(self, ids):
        with self.lock:
            self.release()
            self.allowed = {str(i) for i in ids}

    def validate(self, wid):
        if str(wid) not in self.allowed:
            raise ValueError('Fereastra nu este autorizată')
        item = self.refresh_item(wid)
        bounds = item.get(Quartz.kCGWindowBounds) or {}
        if bounds.get('Width', 0) < 10 or bounds.get('Height', 0) < 10:
            raise ValueError('Fereastra Packet Tracer este minimizată sau ascunsă')
        return item

    def windows(self):
        with self.lock:
            result = []
            for wid in list(self.allowed):
                try:
                    item = self.validate(wid)
                    result.append({'id': str(wid), 'title': str(item.get(Quartz.kCGWindowName) or 'Packet Tracer')})
                except ValueError:
                    continue
            return result

    def capture(self, wid):
        with self.lock:
            self.validate(wid)
            image = Quartz.CGWindowListCreateImage(
                Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
                int(wid), Quartz.kCGWindowImageDefault)
            if image is None:
                raise ValueError('Captura Packet Tracer a fost refuzată; verifică Screen Recording')
            provider = Quartz.CGImageGetDataProvider(image)
            data = Quartz.CGDataProviderCopyData(provider)
            width = Quartz.CGImageGetWidth(image)
            height = Quartz.CGImageGetHeight(image)
            frame = Image.frombuffer('RGBA', (width, height), bytes(data), 'raw', 'BGRA', 0, 1).convert('RGB')
            frame.thumbnail((1600, 1000))
            output = io.BytesIO()
            frame.save(output, 'JPEG', quality=75)
            return output.getvalue(), frame.width, frame.height

    def _point(self, item, data):
        bounds = item[Quartz.kCGWindowBounds]
        x = bounds['X'] + data['x'] * max(1, bounds['Width'] - 1)
        y = bounds['Y'] + data['y'] * max(1, bounds['Height'] - 1)
        return x, y

    def release(self):
        self.drag = None
        self.focus = None

    def input(self, data):
        with self.lock:
            if data['type'] == 'release':
                self.release()
                return
            wid = str(data['window'])
            item = self.validate(wid)
            kind = data['type']
            if kind == 'pointer':
                x, y = self._point(item, data)
                button = Quartz.kCGMouseButtonRight if data.get('button') == 2 else Quartz.kCGMouseButtonLeft
                action = data.get('action')
                if action == 'down':
                    event_type = Quartz.kCGEventRightMouseDown if button == Quartz.kCGMouseButtonRight else Quartz.kCGEventLeftMouseDown
                    self.drag = button
                elif action == 'up':
                    event_type = Quartz.kCGEventRightMouseUp if button == Quartz.kCGMouseButtonRight else Quartz.kCGEventLeftMouseUp
                    self.drag = None
                elif action == 'double':
                    event_type = Quartz.kCGEventLeftMouseDown if button == Quartz.kCGMouseButtonLeft else Quartz.kCGEventRightMouseDown
                elif action == 'wheel':
                    event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitPixel, 1, int(data.get('delta', 0)))
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                    return
                else:
                    event_type = Quartz.kCGEventMouseMoved
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateMouseEvent(None, event_type, (x, y), button))
            elif kind == 'text':
                text = data.get('text', '')
                event = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                Quartz.CGEventKeyboardSetUnicodeString(event, len(text), text)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateKeyboardEvent(None, 0, False))
            elif kind == 'key':
                keycodes = {'Enter': 36, 'Backspace': 51, 'Tab': 48, 'Escape': 53, 'Delete': 117,
                            'ArrowLeft': 123, 'ArrowRight': 124, 'ArrowUp': 126, 'ArrowDown': 125,
                            'Home': 115, 'End': 119, 'PageUp': 116, 'PageDown': 121}
                if data['key'] not in keycodes:
                    raise ValueError('Tasta nu este suportată pe macOS')
                code = keycodes[data['key']]
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateKeyboardEvent(None, code, True))
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateKeyboardEvent(None, code, False))

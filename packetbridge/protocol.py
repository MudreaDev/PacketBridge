"""Wire validation shared by the relay and host. No arbitrary native messages."""
import json
import math
from urllib.parse import urlsplit

MAX_FRAME = 3 * 1024 * 1024
KEYS = {'Enter', 'Backspace', 'Tab', 'Escape', 'Delete', 'ArrowLeft',
        'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'}


def decode(raw):
    if not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError('Mesaj prea mare sau format invalid')
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('type'), str):
        raise ValueError('Mesaj invalid')
    return data


def control(data):
    kind = data.get('type')
    if kind in {'ack', 'release'}:
        return {'type': kind}
    wid = data.get('window')
    if not isinstance(wid, str) or not wid.isdecimal() or len(wid) > 20:
        raise ValueError('Fereastră invalidă')
    out = {'type': kind, 'window': wid}
    if kind == 'select':
        return out
    if kind == 'pointer':
        if data.get('action') not in {'down', 'up', 'move', 'double', 'wheel'}:
            raise ValueError('Acțiune invalidă')
        for k in ('x', 'y'):
            v = data.get(k)
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError('Coordonate invalide')
            out[k] = v
        button = data.get('button', 0)
        if type(button) is not int or button not in (0, 2):
            raise ValueError('Buton invalid')
        delta = data.get('delta', 0)
        if type(delta) is not int or not -120 <= delta <= 120:
            raise ValueError('Scroll invalid')
        out.update(action=data['action'], button=button, delta=delta)
    elif kind in {'text', 'clipboard'}:
        value = data.get('text')
        if not isinstance(value, str) or not 1 <= len(value) <= 2048:
            raise ValueError('Text clipboard invalid')
        if any(ord(c) < 32 and c not in '\r\n\t' for c in value):
            raise ValueError('Caractere de control nepermise')
        out['text'] = value
    elif kind == 'key':
        if data.get('key') not in KEYS:
            raise ValueError('Tastă neacceptată')
        out['key'] = data['key']
    else:
        raise ValueError('Comandă neacceptată')
    return out


def relay_url(value):
    p = urlsplit(value.strip())
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('Introdu adresa HTTPS a serverului')
    if p.path not in ('', '/') or p.query or p.fragment:
        raise ValueError('Folosește adresa de bază, fără cale sau parametri')
    if p.scheme != 'https' and p.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('În afara calculatorului local este obligatoriu HTTPS')
    return value.strip().rstrip('/')

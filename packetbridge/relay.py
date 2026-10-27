"""Single-process ephemeral relay; TLS is terminated by the deployment proxy."""
import argparse
import asyncio
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict, deque
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from .protocol import decode, control, MAX_FRAME


@dataclass
class Room:
    host: object
    expires: float
    client: object = None
    approved: bool = False
    request: str = ''
    pending_until: float = 0


class Relay:
    def __init__(self, ttl=600, approval_timeout=60):
        self.rooms = {}
        self.ttl = ttl
        self.approval_timeout = approval_timeout
        self.attempts = defaultdict(deque)

    async def send(self, ws, data):
        await asyncio.wait_for(ws.send(json.dumps(data)), 5)

    def limited(self, ip):
        now = time.monotonic()
        # Opportunistic cleanup keeps the map bounded by recent connections.
        for key in list(self.attempts):
            if not self.attempts[key] or self.attempts[key][-1] < now - 60:
                del self.attempts[key]
        q = self.attempts[ip]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= 20 or len(self.attempts) > 4096:
            return True
        q.append(now)
        return False

    async def handler(self, ws):
        room = None
        host = False
        code = None
        try:
            ip = ws.remote_address[0] if ws.remote_address else 'local'
            if self.limited(ip):
                await ws.close(1008, 'Prea multe încercări; așteaptă un minut')
                return
            hello = decode(await asyncio.wait_for(ws.recv(), 10))
            if hello['type'] == 'host':
                if len(self.rooms) >= 100:
                    raise ValueError('Server ocupat')
                while True:
                    code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(10))
                    if code not in self.rooms:
                        break
                room = Room(ws, time.monotonic() + self.ttl)
                self.rooms[code] = room
                host = True
                await self.send(ws, {'type': 'code', 'code': code, 'ttl': self.ttl})
            elif hello['type'] == 'join':
                code = str(hello.get('code', '')).replace('-', '').replace(' ', '').upper()
                room = self.rooms.get(code)
                if not room or room.expires < time.monotonic() or room.client:
                    room = None
                    raise ValueError('Cod invalid, expirat sau ocupat')
                room.client = ws
                room.request = secrets.token_hex(16)
                room.pending_until = time.monotonic() + self.approval_timeout
                await self.send(ws, {'type': 'waiting'})
                await self.send(room.host, {'type': 'request', 'request': room.request})
            else:
                raise ValueError('Rol invalid')
            count, start = 0, time.monotonic()
            while True:
                now = time.monotonic()
                if not room.approved and now >= room.expires:
                    raise ValueError('Cod expirat; gazda trebuie să pornească o sesiune nouă')
                if not room.approved and room.client and now >= room.pending_until:
                    raise ValueError('Confirmarea gazdei a expirat')
                try:
                    raw = await asyncio.wait_for(ws.recv(), 1)
                except asyncio.TimeoutError:
                    continue
                count += 1
                if now - start >= 1:
                    count, start = 1, now
                if count > (40 if host else 160):
                    raise ValueError('Prea multe mesaje')
                if isinstance(raw, bytes):
                    if not host or not room.approved or not room.client or len(raw) > MAX_FRAME:
                        raise ValueError('Cadru neautorizat')
                    await asyncio.wait_for(room.client.send(raw), 5)
                    continue
                data = decode(raw)
                kind = data['type']
                if host and kind == 'approve':
                    if not room.client or room.approved or data.get('request') != room.request:
                        raise ValueError('Cerere expirată')
                    room.approved = True
                    await self.send(room.client, {'type': 'connected'})
                    await self.send(ws, {'type': 'connected'})
                elif host and kind == 'deny':
                    if data.get('request') != room.request:
                        raise ValueError('Cerere expirată')
                    break  # A rejected invitation is invalidated, not reused.
                elif host and kind in {'windows', 'frame', 'error'} and room.approved:
                    await self.send(room.client, data)
                elif not host and kind == 'release' and not room.approved:
                    # Browsers send release when the page loses focus while
                    # the host is deciding whether to accept the invitation.
                    # It is harmless before approval and must not abort the room.
                    continue
                elif not host and room.approved:
                    await self.send(room.host, control(data))
                else:
                    raise ValueError('Sesiunea nu este aprobată')
        except (ValueError, TimeoutError) as exc:
            print(f'PacketBridge session error: {exc}', flush=True)
            try:
                await self.send(ws, {'type': 'error', 'message': str(exc)})
            except (ConnectionClosed, TimeoutError):
                pass
        except ConnectionClosed:
            pass
        except Exception as exc:
            print(f'PacketBridge unexpected session error: {type(exc).__name__}: {exc}', flush=True)
            try:
                await self.send(ws, {'type': 'error', 'message': 'Eroare internă a relay-ului'})
            except Exception:
                pass
        finally:
            if room:
                if self.rooms.get(code) is room:
                    del self.rooms[code]
                peers = [room.host, room.client]
                await asyncio.gather(*(p.close(1000, 'Sesiune închisă') for p in peers if p), return_exceptions=True)

    def http(self, connection, request):
        if request.path == '/ws':
            return None
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if request.path == '/healthz':
            return connection.respond(200, 'ok\n')
        item = files.get(request.path)
        if not item:
            return connection.respond(404, 'Not found')
        response = connection.respond(200, (Path(__file__).parent / 'web' / item[0]).read_text(encoding='utf-8'))
        response.headers['Content-Type'] = item[1]
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response


async def run(bind, port, origin):
    relay = Relay()
    async with serve(relay.handler, bind, port, process_request=relay.http,
                     origins=[origin, None], max_size=MAX_FRAME, max_queue=4,
                     compression=None, ping_interval=15, ping_timeout=20):
        print(f'PacketBridge relay: {bind}:{port}; browser origin: {origin}', flush=True)
        await asyncio.Future()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--origin', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    asyncio.run(run(args.bind, args.port, args.origin))


if __name__ == '__main__':
    main()

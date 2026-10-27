import asyncio
import json
import queue
import threading
from websockets.asyncio.client import connect
from .protocol import decode, control, relay_url, MAX_FRAME


class Agent:
    def __init__(self, url, backend, events):
        self.url = relay_url(url)
        self.backend, self.events = backend, events
        self.commands = queue.Queue(maxsize=16)
        self.stop = threading.Event()
        self.active = False
        self.window = None
        self.credit = asyncio.Event()

    def emit(self, **data):
        self.events.put(data)

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            asyncio.run(self.session())
        except Exception as exc:
            self.emit(type='error', message=str(exc))
        finally:
            self.backend.release()
            self.emit(type='closed')

    async def session(self):
        url = self.url.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/ws'
        async with connect(url, max_size=MAX_FRAME, compression=None, open_timeout=10,
                           ping_interval=15, ping_timeout=20) as ws:
            await ws.send(json.dumps({'type': 'host'}))
            async def receive():
                async for raw in ws:
                    data = decode(raw)
                    kind = data['type']
                    if kind in {'code', 'request', 'error'}:
                        self.emit(**data)
                    elif kind == 'connected':
                        self.active = True
                        self.credit.set()
                        self.emit(type='connected')
                    elif self.active:
                        data = control(data)
                        if kind == 'ack':
                            self.credit.set()
                        elif kind == 'select':
                            valid = {w['id'] for w in self.backend.windows()}
                            if data['window'] in valid:
                                self.backend.release()
                                self.window = data['window']
                        else:
                            try:
                                await asyncio.to_thread(self.backend.input, data)
                            except Exception as exc:
                                await ws.send(json.dumps({'type': 'error', 'message': str(exc)}))
            async def frames():
                last_windows = None
                last_error = None
                while not self.stop.is_set():
                    await asyncio.sleep(0.08)
                    if not self.active:
                        continue
                    windows = await asyncio.to_thread(self.backend.windows)
                    if windows != last_windows:
                        await ws.send(json.dumps({'type': 'windows', 'windows': windows}))
                        last_windows = windows
                    ids = {w['id'] for w in windows}
                    if self.window not in ids:
                        self.window = windows[0]['id'] if windows else None
                    if not self.window:
                        continue
                    try:
                        await asyncio.wait_for(self.credit.wait(), 1)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        wid = self.window
                        jpeg, width, height = await asyncio.to_thread(self.backend.capture, wid)
                        if self.stop.is_set():
                            return
                        if len(jpeg) > MAX_FRAME:
                            raise ValueError('Cadrul este prea mare')
                        self.credit.clear()
                        await ws.send(json.dumps({'type': 'frame', 'window': wid, 'width': width, 'height': height}))
                        await ws.send(jpeg)
                        last_error = None
                    except Exception as exc:
                        error = str(exc)
                        if error != last_error:
                            await ws.send(json.dumps({'type': 'error', 'message': error}))
                            self.emit(type='error', message=error)
                            last_error = error
            async def commands():
                while not self.stop.is_set():
                    try:
                        data = self.commands.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.05)
                        continue
                    await ws.send(json.dumps(data))
                await ws.close()
            tasks = [asyncio.create_task(f()) for f in (receive, frames, commands)]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()

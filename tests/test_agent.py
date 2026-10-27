import asyncio
import json
import queue
import unittest
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect
from packetbridge.agent import Agent
from packetbridge.relay import Relay


class FakeBackend:
    def __init__(self):
        self.inputs=[]
        self.captures=0
    def windows(self):
        return [{'id':'123','title':'Test fixture'}]
    def capture(self, wid):
        assert wid == '123'
        self.captures+=1
        return b'fixture-frame', 800, 600
    def input(self,data):
        if data.get('window','123') != '123':
            raise ValueError('Fereastră neaprobată')
        self.inputs.append(data)
    def release(self):
        pass


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_session_and_frame_backpressure(self):
        relay=Relay()
        server=await serve(relay.handler,'127.0.0.1',0)
        port=server.sockets[0].getsockname()[1]
        backend=FakeBackend()
        events=queue.Queue()
        agent=Agent(f'http://127.0.0.1:{port}',backend,events)
        task=asyncio.create_task(agent.session())
        async def event():
            for _ in range(100):
                try:
                    return events.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(.02)
            self.fail('No host event')
        try:
            code=(await event())['code']
            async with connect(f'ws://127.0.0.1:{port}/ws') as client:
                await client.send(json.dumps({'type':'join','code':code}))
                self.assertEqual(json.loads(await client.recv())['type'],'waiting')
                request=(await event())['request']
                self.assertEqual(backend.captures,0)
                agent.commands.put({'type':'approve','request':request})
                self.assertEqual(json.loads(await client.recv())['type'],'connected')
                self.assertEqual((await event())['type'],'connected')
                self.assertEqual(json.loads(await client.recv())['type'],'windows')
                self.assertEqual(json.loads(await client.recv())['type'],'frame')
                self.assertEqual(await client.recv(),b'fixture-frame')
                await asyncio.sleep(.4)
                self.assertEqual(backend.captures,1)
                await client.send(json.dumps({'type':'ack'}))
                self.assertEqual(json.loads(await client.recv())['type'],'frame')
                self.assertEqual(await client.recv(),b'fixture-frame')
                await client.send(json.dumps({'type':'text','window':'123','text':'show ip route'}))
                await asyncio.sleep(.05)
                self.assertEqual(backend.inputs[-1]['text'],'show ip route')
                await client.send(json.dumps({'type':'key','window':'999','key':'Enter'}))
                self.assertEqual(json.loads(await client.recv())['type'],'error')
                agent.stop.set()
                await asyncio.wait_for(task,2)
                self.assertEqual(relay.rooms,{})
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
            server.close()
            await server.wait_closed()

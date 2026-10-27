import asyncio
import json
import unittest
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus
from packetbridge.relay import Relay


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.relay = Relay()
        self.server = await serve(self.relay.handler, '127.0.0.1', 0,
                                  process_request=self.relay.http, origins=[None,'http://localhost'])
        self.port = self.server.sockets[0].getsockname()[1]
        self.url = f'ws://127.0.0.1:{self.port}/ws'
        self.clients=[]

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        self.server.close()
        await self.server.wait_closed()

    async def socket(self):
        ws=await connect(self.url)
        self.clients.append(ws)
        return ws

    async def send(self, ws, **data):
        await ws.send(json.dumps(data))

    async def recv(self, ws):
        return json.loads(await asyncio.wait_for(ws.recv(),2))

    async def host(self):
        h=await self.socket()
        await self.send(h,type='host')
        code=(await self.recv(h))['code']
        return h,code

    async def pair(self):
        h,code=await self.host()
        c=await self.socket()
        await self.send(c,type='join',code=code)
        self.assertEqual((await self.recv(c))['type'],'waiting')
        request=(await self.recv(h))['request']
        return h,c,code,request

    async def approved(self):
        h,c,code,request=await self.pair()
        await self.send(h,type='approve',request=request)
        self.assertEqual((await self.recv(c))['type'],'connected')
        self.assertEqual((await self.recv(h))['type'],'connected')
        return h,c,code

    async def test_approval_then_frame_and_input(self):
        h,c,_=await self.approved()
        await h.send(b'jpeg-test')
        self.assertEqual(await c.recv(),b'jpeg-test')
        await self.send(c,type='pointer',window='123',action='down',x=.2,y=.8)
        data=await self.recv(h)
        self.assertEqual(data['type'],'pointer')
        self.assertEqual(data['window'],'123')

    async def test_input_before_approval_denied(self):
        h,c,code,_=await self.pair()
        await self.send(c,type='key',window='1',key='Enter')
        self.assertEqual((await self.recv(c))['type'],'error')
        with self.assertRaises(ConnectionClosed):
            await h.recv()
        self.assertNotIn(code,self.relay.rooms)

    async def test_frame_before_approval_denied(self):
        h,c,_,_=await self.pair()
        await h.send(b'forbidden')
        self.assertEqual((await self.recv(h))['type'],'error')
        with self.assertRaises(ConnectionClosed):
            await c.recv()

    async def test_bad_code(self):
        c=await self.socket()
        await self.send(c,type='join',code='INVALID')
        self.assertEqual((await self.recv(c))['type'],'error')

    async def test_single_participant(self):
        h,c,code=await self.approved()
        other=await self.socket()
        await self.send(other,type='join',code=code)
        self.assertEqual((await self.recv(other))['type'],'error')
        await self.send(c,type='ack')
        self.assertEqual((await self.recv(h))['type'],'ack')

    async def test_expired_code(self):
        _,code=await self.host()
        self.relay.rooms[code].expires=0
        c=await self.socket()
        await self.send(c,type='join',code=code)
        self.assertEqual((await self.recv(c))['type'],'error')

    async def test_disconnect_revokes_code(self):
        h,c,code=await self.approved()
        await c.close()
        with self.assertRaises(ConnectionClosed):
            await h.recv()
        self.assertNotIn(code,self.relay.rooms)
        other=await self.socket()
        await self.send(other,type='join',code=code)
        self.assertEqual((await self.recv(other))['type'],'error')

    async def test_wrong_approval_id_closes(self):
        h,c,_,_=await self.pair()
        await self.send(h,type='approve',request='wrong')
        self.assertEqual((await self.recv(h))['type'],'error')
        with self.assertRaises(ConnectionClosed):
            await c.recv()

    async def test_rejection_closes_both(self):
        h,c,code,request=await self.pair()
        await self.send(h,type='deny',request=request)
        with self.assertRaises(ConnectionClosed):
            await c.recv()
        self.assertNotIn(code,self.relay.rooms)

    async def test_rate_limit(self):
        for _ in range(20):
            self.assertFalse(self.relay.limited('test-ip'))
        self.assertTrue(self.relay.limited('test-ip'))

    async def test_http_client_served(self):
        reader,writer=await asyncio.open_connection('127.0.0.1',self.port)
        writer.write(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
        await writer.drain()
        response=await reader.read()
        writer.close()
        await writer.wait_closed()
        self.assertIn(b'200 OK',response)
        self.assertIn(b'Content-Security-Policy',response)
        self.assertIn(b'PacketBridge',response)

    async def test_cross_origin_denied(self):
        with self.assertRaises(InvalidStatus) as caught:
            async with connect(self.url,origin='https://untrusted.example'):
                pass
        self.assertEqual(caught.exception.response.status_code, 403)

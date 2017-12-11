import asyncio
from time import sleep, time
from random import randint

import pydash as _

from mqttclient import MqttClient

def generate_id():
    timestamp = str(time()).replace(".","")
    randnum = randint(1,1000)
    return f'microdrop-py-{timestamp}-{randnum}'


class MyMqttClient(MqttClient):
    def __init__(self):
        self._name = generate_id()
        super().__init__()
    def listen(self):
        self.trigger('client-ready', 'null')
    @property
    def name(self):
        return self._name

class Microdrop:
    def __init__(self):
        self.mqttclient = MyMqttClient()
        self.loop = asyncio.get_event_loop()
    
    def execute(self, protocol, *args, **kwargs):
        self.loop.run_until_complete(protocol(self, *args, **kwargs))
    
    def safe(self, method):
        return lambda *m, **kw: self.loop.call_soon_threadsafe(method, *m, **kw)
    
    def reset_client(self):
        """ Create new client """
        future = asyncio.Future()
        self.mqttclient.client.disconnect()
        del self.mqttclient
        self.mqttclient = MyMqttClient()
        
        def client_ready(*args):
            self.connected = True
            future.set_result('client is ready')
            
        if self.mqttclient.connected:
            client_ready(self)
        else:
            self.mqttclient.on('client-ready', self.safe(client_ready))

        return future
        
    async def get_state(self, sender, prop):
        """ Get state of microdrop property """
        await self.reset_client()
        future = asyncio.Future()
        def state_msg(payload):
            future.set_result(payload)
        
        self.mqttclient.on_state_msg(sender, prop, self.safe(state_msg))
        return await future
    
    async def get_subscriptions(self, receiver):
        payload = await self.trigger_plugin(receiver, 'get-subscriptions', {})
        return payload['response']
    
    async def put_plugin(self, receiver, prop, val):
        if not isinstance(val, dict):
            msg = {}
            _.set_(msg, prop, val)
            val = msg
        await self.reset_client()
        await self.call_action(receiver, prop, val, 'put')
    
    async def trigger_plugin(self, receiver, action, val={}):
        await self.reset_client()
        result = await self.call_action(receiver, action, val, 'trigger')
        return result
 
    async def call_action(self, receiver, action, val, msg_type='trigger'):
        topic = f'microdrop/{msg_type}/{receiver}/{action}'
        sub = f'microdrop/{receiver}/notify/{self.mqttclient.name}/action'
        _.set_(val, "__head__.plugin_name", self.mqttclient.name)
        future = asyncio.Future()
        def notify_msg(payload):
            print("received notification")
            _.pull(self.mqttclient.subscriptions, sub)
            self.mqttclient.client.unsubscribe(sub)
            # XXX: no method to remove routes for wheezy.routing 
            # ignoring for now, but might causes issues in the future
            future.set_result(payload)
        self.mqttclient.on_notify_msg(receiver, action, self.safe(notify_msg))
        self.mqttclient.send_message(topic, val)
        return await future               
from json     import loads, dumps
from math     import ceil
from os.path  import abspath, basename, getsize
from colors   import log, bcolors
import aiohttp
import asyncio
import random

aiohttpSession = None


async def initLib():
    global aiohttpSession

    connector = aiohttp.TCPConnector(limit=4)
    jar       = aiohttp.DummyCookieJar()

    aiohttpSession = aiohttp.ClientSession(
        connector=connector,
        cookie_jar=jar
    )


async def destroyLib():
    global aiohttpSession
    if aiohttpSession is not None: await aiohttpSession.close()


class FileBlackHole:
    # https://fileblackhole.000webhostapp.com/API.php
    apiUrl             = 'https://fileblackhole.yukiteru.xyz/API.php'
    chunkSize          = 1000000
    sessionID          = None
    triesPerConnection = 3

    def __init__(self, chunkSize=1000000, tpc=6):
        self.triesPerConnection = tpc
        self.chunkSize          = chunkSize

    async def close(self):
        await self.sendRequest({
            'method': 'killsession'
        })

    async def sendRequest(self, data):
        tries = self.triesPerConnection
        headers = {}
        x = None

        if self.sessionID is not None: headers['Cookie'] = f"PHPSESSID={self.sessionID}"

        while True:
            try:
                async with aiohttpSession.post(self.apiUrl, headers=headers, data=data) as response:
                    if response.status == 200:
                        x = loads(await response.text())
                        if x['exitCode'] != 0:
                            log(f"[!] Request failed on server side with code {x['exitCode']}. (HEADERS: {dumps(headers)}; DATA: {dumps(data)}; RESPONSE: {dumps(x)})", [bcolors.FAIL])
                            raise Exception("Request failed")
                        return x
            except:
                pass

            await asyncio.sleep(random.randint(1, 10))

            if tries == 1:
                return x

            tries -= 1

    async def createSession(self):
        result = await self.sendRequest({
            'method': 'createSession'
        })

        if   isinstance(result, int): return result
        elif result['exitCode'] != 0: return None

        self.sessionID = result['result']['sid']

    async def uploadFileChunk(self, filename, data, chunks, chunk):
        result = await self.sendRequest({
            "method": "uploadFileChunk",
            "name"  : str(filename),
            "chunks": str(chunks),
            "chunk" : str(chunk),
            "file"  :     data
        })

        if isinstance(result, int):
            log(f"[!] Upload chunk for {filename} failed with status code {result}. (SID: {self.sessionID})", [bcolors.FAIL])
            return None
        if result is None:
            log(f"[!] Upload chunk for {filename} failed. Couldn't connect with server. (SID: {self.sessionID})", [bcolors.FAIL])
            return None
        elif result['exitCode'] != 0:
            log(f"[!] Upload chunk for {filename} failed. (SID: {self.sessionID}; CODE: {result['exitCode']}; RESPONSE: {result['result']})", [bcolors.FAIL])
            return None

        return result

    async def declareUpload(self, filename, size):
        result = await self.sendRequest({
            "method"  :  "startUpload",
            "size"    : str(size),
            "filename": str(filename)
        })

        if isinstance(result, int):
            log(f"[!] Declare upload for {filename} failed with status code {result}. (SID: {self.sessionID})", [bcolors.FAIL])
            return 1
        elif result is None:
            log(f"[!] Declare upload for {filename} failed with unknown status code. (SID: {self.sessionID})", [bcolors.FAIL])
            return 3
        elif result['exitCode'] != 0:
            log(f"[!] Declare upload for {filename} exited with code {result['exitCode']}. (SID: {self.sessionID})", [bcolors.FAIL])
            return 2

        return 0

    async def uploadFile(self, path):
        if path is None: return None
        
        path   = abspath (path)
        name   = basename(path)
        size   = getsize (path)
        chunks = ceil(size/self.chunkSize)

        # declare upload and check if it failed
        response = await self.declareUpload(name, size)
        
        if response != 0: return None
        
        # start proper upload

        fileReader = open(path, 'rb')
        chunk = 0

        while True:
            data = fileReader.read(self.chunkSize)

            if not data: break
            
            response = await self.uploadFileChunk(name, data, chunks, chunk)

            chunk += 1

        return response

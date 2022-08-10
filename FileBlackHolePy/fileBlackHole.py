from json     import loads, dumps
from math     import ceil
from os.path  import abspath, basename, getsize
from random   import randint

import aiohttp
import asyncio


class FileBlackHole:
    # https://fileblackhole.000webhostapp.com/API.php
    apiUrl             = 'https://fileblackhole.yukiteru.xyz/API.php'
    chunkSize          = 1000000
    headers            = None
    sessionID          = None
    aiohttpSession     = None
    triesPerConnection = 3

    def __init__(self, chunkSize=1000000, tpc=6):
        self.triesPerConnection = tpc
        self.chunkSize          = chunkSize

    async def init(self):
        connector = aiohttp.TCPConnector(limit=4)
        jar       = aiohttp.DummyCookieJar()

        self.aiohttpSession = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=jar
        )

    async def close(self):
        await self.sendRequest({
            'method': 'killsession'
        })
        await self.aiohttpSession.close()

    async def sendRequest(self, data: dict, tries: int = 6) -> dict | None:
        if self.headers is None: return None

        try:
            async with self.aiohttpSession.post(self.apiUrl, headers=self.headers, data=data) as response:
                if response.status != 200: raise Exception(f"Server returned status code {response.status}")

                x = loads(await response.text())
                if x['exitCode'] == 0: return x

                raise Exception(
                    f"Request failed on server side with code {x['exitCode']}. ("
                    f"HEADERS: {dumps(self.headers)}; "
                    f"DATA: {dumps(data)}; "
                    f"RESPONSE: {dumps(x)})"
                )
        except (Exception,) as e:
            print(e)
            if tries == 0: return None
            await asyncio.sleep(randint(1, 10))
            return await self.sendRequest(data, tries-1)

    async def createSession(self) -> int | None:
        result = await self.sendRequest({
            'method': 'createSession'
        })

        if   isinstance(result, int): return result
        elif result['exitCode'] != 0: return None

        self.sessionID = result['result']['sid']
        self.headers = {'Cookie': f"PHPSESSID={self.sessionID}"}

    async def uploadFileChunk(self, filename: str, data, chunks: int, chunk : int) -> dict | None:
        result = await self.sendRequest({
            "method": "uploadFileChunk",
            "name"  : filename,
            "chunks": chunks,
            "chunk" : chunk,
            "file"  : data
        })

        if isinstance(result, int):
            print(f"[!] Upload chunk for {filename} failed with status code {result}. (SID: {self.sessionID})")
            return None
        if result is None:
            print(f"[!] Upload chunk for {filename} failed. Couldn't connect with server. (SID: {self.sessionID})")
            return None
        elif result['exitCode'] != 0:
            print(f"[!] Upload chunk for {filename} failed. ("
                  f"SID: {self.sessionID}; "
                  f"CODE: {result['exitCode']}; "
                  f"RESPONSE: {result['result']}"
                  f")")
            return None

        return result

    async def declareUpload(self, filename: str, size: int) -> int:
        result = await self.sendRequest({
            "method"  : "startUpload",
            "size"    : size,
            "filename": filename
        })

        if isinstance(result, int):
            print(f"[!] Declare upload for {filename} failed with status code {result}. (SID: {self.sessionID})")
            return 1
        elif result is None:
            print(f"[!] Declare upload for {filename} failed with unknown status code. (SID: {self.sessionID})")
            return 3
        elif result['exitCode'] != 0:
            print(f"[!] Declare upload for {filename} exited with code {result['exitCode']}. (SID: {self.sessionID})")
            return 2

        return 0

    async def uploadFile(self, path: str) -> dict | None:
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

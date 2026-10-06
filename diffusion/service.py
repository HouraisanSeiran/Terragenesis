"""Serialized model access, bounded HTTP protocol; raw meters remain in persistent cache."""
import json,struct,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from .backend import TerrainDiffusionBackend
from .store import TerrainTileStore

class TerrainService:
    def __init__(self,config):
        self.config=config;self.backend=TerrainDiffusionBackend(config);self.store=TerrainTileStore(self.backend.identity)
        self.lock=threading.Lock()
    def tile(self,seed,tx,tz):
        import numpy as np
        with self.lock:
            cached=self.store.read(seed,tx,tz)
            if cached is not None:return cached
            # Shared +1 border provides continuous interpolation across negative and positive tile coordinates.
            size=self.config.tile_pixels+1
            elev,climate,meta=self.backend.generate(seed,tx*self.config.tile_pixels,tz*self.config.tile_pixels,size)
            if elev.shape!=(size,size) or climate.shape!=(4,size,size):raise RuntimeError('Unexpected model output shape')
            if not np.isfinite(elev).all() or not np.isfinite(climate).all():raise RuntimeError('Non-finite model output')
            return self.store.write(seed,tx,tz,elev,climate,meta)
    def payload(self,seed,tx,tz):
        import numpy as np
        elev,climate,meta=self.tile(seed,tx,tz)
        # Interleaved native samples: meters, annual temperature, annual precipitation.
        values=np.stack([elev,climate[0],climate[2]],axis=-1).astype('<f4')
        header=struct.pack('<4siiiif',b'RMD2',65,self.config.blocks_per_pixel,self.config.sea_level,0,self.config.meters_per_height_block)
        return header+values.tobytes()

def serve(service,port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                request=urlparse(self.path)
                if request.path=='/health':
                    payload=json.dumps({'status':'ready','backend':'terrain-diffusion','identity':service.backend.identity,
                                        'profile':service.config.conditioning_mode}).encode();kind='application/json'
                elif request.path=='/tile':
                    query=parse_qs(request.query,strict_parsing=True)
                    seed=int(query['seed'][0]);tx=int(query['x'][0]);tz=int(query['z'][0])
                    if not -(1<<63)<=seed<(1<<63) or max(abs(tx),abs(tz))>1000000:raise ValueError('Coordinates out of range')
                    payload=service.payload(seed,tx,tz);kind='application/octet-stream'
                else:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(payload)))
                self.send_header('X-Terrain-Identity',service.backend.identity)
                self.send_header('X-Terrain-Profile',service.config.conditioning_mode)
                self.send_header('X-Blocks-Per-Pixel',str(service.config.blocks_per_pixel))
                self.end_headers();self.wfile.write(payload)
            except Exception as exc:
                print('Inference request failed:',repr(exc),flush=True)
                self.send_error(503,str(exc))
    service.backend.load()
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'True diffusion service ready: http://127.0.0.1:{port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close();service.backend.close()

package com.remotemountains.diffusion;

import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;

/** Loopback-only model service. No procedural fallback; seed is attached to every request. */
public final class DiffusionClient {
    private final long seed;
    private final String profile;
    private final URI endpoint;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build();
    private String identity;
    private int spacing=2;
    private final Map<Long,DiffusionTile> cache=new LinkedHashMap<>(32,.75f,true){
        protected boolean removeEldestEntry(Map.Entry<Long,DiffusionTile> entry){return size()>64;}
    };
    public DiffusionClient(long seed,String expectedIdentity){
        this(seed,expectedIdentity,"geographic_v1");
    }
    public DiffusionClient(long seed,String expectedIdentity,String profile){
        this.seed=seed;this.identity=expectedIdentity;
        this.profile=profile;
        endpoint=URI.create(System.getProperty("remotemountains.diffusionUrl","http://127.0.0.1:19802"));
        if(!"http".equals(endpoint.getScheme())||!"127.0.0.1".equals(endpoint.getHost())||endpoint.getUserInfo()!=null)
            throw new IllegalArgumentException("Diffusion endpoint must use loopback HTTP");
        DiffusionServiceManager.ensureAvailable(expectedIdentity,profile);
        HttpResponse<byte[]> response=request("/health");validateIdentity(response);
        // Scale is fixed by the RMD2 service configuration and checked on every tile.
        String blocks=response.headers().firstValue("X-Blocks-Per-Pixel").orElseThrow(()->new IllegalStateException("Diffusion service missing grid scale"));
        spacing=Integer.parseInt(blocks);if(spacing<1||spacing>16)throw new IllegalStateException("Invalid model scale");
    }
    public synchronized String identity(){return identity;}
    private HttpResponse<byte[]> request(String path){
        try{
            HttpResponse<byte[]> r=http.send(HttpRequest.newBuilder(endpoint.resolve(path)).timeout(Duration.ofMinutes(5)).GET().build(),HttpResponse.BodyHandlers.ofByteArray());
            if(r.statusCode()!=200)throw new IllegalStateException("Diffusion service returned HTTP "+r.statusCode()+". Check runtime service log; terrain was not substituted.");
            return r;
        }catch(InterruptedException e){Thread.currentThread().interrupt();throw new IllegalStateException("Diffusion request interrupted",e);}
        catch(java.io.IOException e){throw new IllegalStateException("Terrain service unavailable. Check the terrain-service.log in Terragenesis and retry the installation.",e);}
    }
    private void validateIdentity(HttpResponse<?> response){
        String actualProfile=response.headers().firstValue("X-Terrain-Profile").orElse("geographic_v1");
        if(!profile.equals(actualProfile))throw new IllegalStateException("Terrain service model profile changed during generation");
        String current=response.headers().firstValue("X-Terrain-Identity").orElseThrow(()->new IllegalStateException("Missing model identity"));
        if(!current.matches("[0-9a-f]{64}"))throw new IllegalStateException("Invalid model identity");
        if(identity!=null&&!identity.isEmpty()&&!identity.equals(current))throw new IllegalStateException("World model identity differs from running service. Restore the original model/settings; refusing terrain seams.");
        identity=current;
    }
    public record Result(double height,double water,double temperature,double precipitation) {}
    public synchronized Result sample(double x,double z){
        Result raw=sampleRaw(x,z);
        double height=raw.height();
        // Legacy worlds retain their original bounded height remapping.
        height=height>=72?72+225*Math.tanh((height-72)/225):72+125*Math.tanh((height-72)/125);
        return new Result(height,raw.water(),raw.temperature(),raw.precipitation());
    }
    public synchronized Result sampleRaw(double x,double z){
        int span=64*spacing,tx=(int)Math.floor(x/span),tz=(int)Math.floor(z/span);
        long key=((long)tx<<32)^(tz&0xffffffffL);
        DiffusionTile tile=cache.get(key);
        if(tile==null){
            var response=request("/tile?seed="+seed+"&x="+tx+"&z="+tz);validateIdentity(response);
            tile=DiffusionTile.decode(response.body());if(tile.blocksPerPixel()!=spacing)throw new IllegalStateException("Grid scale changed");cache.put(key,tile);
        }
        var s=tile.sample((x-tx*(double)span)/spacing,(z-tz*(double)span)/spacing);
        double height=tile.seaLevel()+s.meters()/tile.verticalScale();
        return new Result(height,s.meters()<0?tile.seaLevel():Double.NaN,s.temperature(),s.precipitation());
    }
}

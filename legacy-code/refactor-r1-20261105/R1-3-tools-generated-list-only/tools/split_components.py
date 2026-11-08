"""One-time source organization: keep geological algorithms independently editable."""
from pathlib import Path
from build_local import ROOT
p=ROOT/'src/main/java/com/remotemountains/core'
s=(p/'Landscape.java').read_text(encoding='utf-8')
start=s.index('        return switch(r.type()){')
end=s.index('    private double peak(',start)
switch=s[start:end]
parts={
'InselbergShape':switch[switch.index('            case INSELBERG -> {')+len('            case INSELBERG -> {'):switch.index('            case RIFT -> {')],
'RiftShape':switch[switch.index('            case RIFT -> {')+len('            case RIFT -> {'):switch.index('            case KARST -> {')],
'KarstShape':switch[switch.index('            case KARST -> {')+len('            case KARST -> {'):switch.index('            case PILLARS -> {')],
'PillarShape':switch[switch.index('            case PILLARS -> {')+len('            case PILLARS -> {'):switch.index('        };')]
}
common='''        double dx=x-r.x(),dz=z-r.z(),cs=Math.cos(r.angle()),sn=Math.sin(r.angle());
        double u=dx*cs+dz*sn,v=-dx*sn+dz*cs;
        double ox=Noise.unit(r.key()+31)*100,oz=Noise.unit(r.key()+32)*100;
        double n=shape.fbm(x/380+ox,z/380+oz,3);
        double floor=82+8*shape.fbm(x/950,z/950,3)+3*shape.at(x/150,z/150);
'''
for name,body in parts.items():
    body=body.rstrip();body=body[:body.rfind('}')].replace('yield ','return ')
    body=body.replace('peak(', 'primitives.peak(').replace('cluster(', 'primitives.cluster(').replace('sq(', 'ShapePrimitives.sq(')
    code=f'''package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class {name} implements LandformShape {{
    private final Noise shape;
    private final ShapePrimitives primitives;
    public {name}(long seed){{shape=new Noise(seed);primitives=new ShapePrimitives(seed);}}
    public double height(Regions.Region r,double x,double z){{
{common}{body}
    }}
}}
'''
    (p/(name+'.java')).write_text(code,encoding='utf-8')
(p/'LandformShape.java').write_text('package com.remotemountains.core;\npublic interface LandformShape { double height(Regions.Region region,double x,double z); }\n',encoding='utf-8')
prim=s[end:s.index('    public boolean cave(')].replace('private double peak','public double peak').replace('private double cluster','public double cluster')
(p/'ShapePrimitives.java').write_text('''package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class ShapePrimitives {
    private final long seed; private final Noise shape;
    public ShapePrimitives(long seed){this.seed=seed;shape=new Noise(seed);}
'''+prim+'    public static double sq(double a){return a*a;}\n}\n',encoding='utf-8')
climate=s[s.index('    public Climate climate('):s.index('    public Base base(')]
climate=climate.replace('public Climate climate(', 'public Landscape.Climate sample(').replace('return new Climate(', 'return new Landscape.Climate(')
(p/'ClimateModel.java').write_text('''package com.remotemountains.core;
import static com.remotemountains.core.Noise.*;
public final class ClimateModel {
    private final Noise climate,shape;
    public ClimateModel(long seed){climate=new Noise(seed^459713);shape=new Noise(seed);}
'''+climate+'}\n',encoding='utf-8')
cave=s[s.index('    public boolean cave('):s.index('    private static double sq(')]
cave=cave.replace('public boolean cave(', 'public boolean contains(').replace('Base base','Landscape.Base base')
(p/'CaveModel.java').write_text('''package com.remotemountains.core;
public final class CaveModel {
    private final Noise caves;
    public CaveModel(long seed){caves=new Noise(seed^99273);}
'''+cave+'}\n',encoding='utf-8')
base=s[s.index('    public Base base('):s.index('    public double shape(')]
base=base.replace('shape(r,x,z)','shapes[r.type().ordinal()].height(r,x,z)').replace('Climate c=climate(x,z,h);','Climate c=climate.sample(x,z,h);')
header=s[:s.index('    private final Noise shape,climate,caves;')]
(p/'Landscape.java').write_text(header+'''    private final Noise shape;
    private final ClimateModel climate;
    private final LandformShape[] shapes;
    public final CaveModel caves;
    public Landscape(long seed){
        this.seed=seed;regions=new Regions(seed);shape=new Noise(seed);
        climate=new ClimateModel(seed);caves=new CaveModel(seed);
        shapes=new LandformShape[]{new InselbergShape(seed),new RiftShape(seed),new KarstShape(seed),new PillarShape(seed)};
    }
'''+base+'}\n',encoding='utf-8')
t=p/'Terrain.java';v=t.read_text(encoding='utf-8').replace('landscape.cave(', 'landscape.caves.contains(')
v=v.replace('double protect=base.landmark()*.80;', 'double protect=0;')
v=v.replace('// Keep the core of every landmark intact; trunk rivers may bend around it in later versions.', '// River levels remain coherent through landform boundaries.')
t.write_text(v,encoding='utf-8')
# Minecraft block composition is separate from chunk lifecycle orchestration.
g=p.parent/'world/RemoteGenerator.java';v=g.read_text(encoding='utf-8')
a=v.index('    private BlockState block(');b=v.index('    public int getBaseHeight(',a)
method=v[a:b].replace('private BlockState block(', 'public BlockState sample(')
(g.parent/'SurfacePalette.java').write_text('''package com.remotemountains.world;
import com.remotemountains.core.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
/** Maps density, rock type and current climate to vanilla blocks. */
public final class SurfacePalette {
'''+method+'}\n',encoding='utf-8')
v=v[:a]+v[b:];v=v.replace('    private volatile Terrain terrain;', '    private volatile Terrain terrain;\n    private final SurfacePalette surface=new SurfacePalette();')
v=v.replace('block(t,','surface.sample(t,');g.write_text(v,encoding='utf-8')
print('Separated climate, caves, four landform algorithms, shape primitives and block palette')

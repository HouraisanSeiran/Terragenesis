"""Create original mod data, adapting vanilla biome schema for the exact target version."""
from pathlib import Path
import copy, json, zipfile
from build_local import ROOT, REFERENCE

res=ROOT/'src/main/resources'
def write(path,data):
    p=res/path;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

write(Path('fabric.mod.json'),{
    'schemaVersion':1,'id':'remotemountains','version':'${version}',
    'name':'Terragenesis（山川形意）','description':'四种地貌区域、独立气候与跨区域水系。',
    'environment':'*','entrypoints':{'main':['com.remotemountains.RemoteMountains'],
                                  'client':['com.remotemountains.client.TerrainInstallClient']},
    'mixins':[{'config':'remotemountains.client.mixins.json','environment':'client'}],
    'depends':{'fabricloader':'>=0.19.5','minecraft':'26.3','java':'>=25','fabric-api':'*'}
})
types=['inselberg','rift','karst','pillars'];climates=['snowy','arid','temperate','humid']
palette=[]
with zipfile.ZipFile(REFERENCE/'.gradle-user/caches/fabric-loom/26.3/minecraft-common.jar') as game:
    dimension=json.loads(game.read('data/minecraft/dimension_type/overworld.json'))
    dimension.update(min_y=-64,height=1088,logical_height=1088)
    dimension['attributes']['minecraft:visual/cloud_height']=423.0
    write(Path('data/remotemountains/dimension_type/overworld_1024.json'),dimension)
    for terrain in types:
        for climate,source in zip(climates,['snowy_plains','desert','plains','forest']):
            biome=json.loads(game.read('data/minecraft/worldgen/biome/'+source+'.json'))
            name=terrain+'_'+climate;palette.append('remotemountains:'+name)
            # Original climate variants reuse vanilla vegetation, ore, and mob placements.
            write(Path('data/remotemountains/worldgen/biome/'+name+'.json'),biome)
    preset=json.loads(game.read('data/minecraft/worldgen/world_preset/normal.json'))
    preset['dimensions']['minecraft:overworld']['type']='remotemountains:overworld_1024'
    preset['dimensions']['minecraft:overworld']['generator']={'type':'remotemountains:landforms','biomes':palette,'terrain_source':'demo_landforms_perlin_v2','vdm_recipe':'diffusion-vdm-demo-cliffs-v3'}
    preset['dimensions']['minecraft:overworld']['generator']['terrain_scale']='relief_3x_sea62_1024_v1'
    demo_preset=copy.deepcopy(preset)
    preset['dimensions']['minecraft:overworld']['generator']['terrain_source']='live_diffusion_global'
    preset['dimensions']['minecraft:overworld']['generator']['vdm_recipe']='diffusion-vdm-regional-cliffs-v3'
    write(Path('data/remotemountains/worldgen/world_preset/global_landforms.json'),preset)
    region_preset=copy.deepcopy(preset)
    region_generator=region_preset['dimensions']['minecraft:overworld']['generator']
    region_generator.update(terrain_source='region_diffusion_v1',vdm_recipe='regional-xyz-vdm-v1',
                            region_chunks=24,region_processing='none_v1')
    write(Path('data/remotemountains/worldgen/world_preset/region_landforms.json'),region_preset)
    raw_preset=copy.deepcopy(region_preset)
    raw_generator=raw_preset['dimensions']['minecraft:overworld']['generator']
    raw_generator.update(terrain_source='metric_processed_readonly_v1',vdm_recipe='metric-processed-surface-v1',
                         terrain_scale='metric_1m_sea62_1024_v1')
    write(Path('data/remotemountains/worldgen/world_preset/landforms.json'),raw_preset)
    preset['dimensions']['minecraft:overworld']['generator']['terrain_source']='watershed_heightmap_v2'
    preset['dimensions']['minecraft:overworld']['generator']['vdm_recipe']='watershed-vdm-heightmap-v2'
    write(Path('data/remotemountains/worldgen/world_preset/watershed.json'),preset)
    for name,recipe in [('canyon','watershed-vdm-canyon-v2'),('canyon_single','watershed-vdm-canyon-single-v2')]:
        preset['dimensions']['minecraft:overworld']['generator']['vdm_recipe']=recipe
        write(Path('data/remotemountains/worldgen/world_preset/'+name+'.json'),preset)
write(Path('data/minecraft/tags/worldgen/world_preset/normal.json'),{'replace':False,'values':['remotemountains:landforms']})
for language in ['zh_cn','en_us']:
    names={'generator.remotemountains.landforms':'山川形意 · 区域派生地貌' if language=='zh_cn' else 'Terragenesis Regional Landforms',
           'generator.remotemountains.global_landforms':'山川形意 · 全域地貌世界' if language=='zh_cn' else 'Terragenesis (Global)',
           'generator.remotemountains.region_landforms':'山川形意 · 区域塑形（实验）' if language=='zh_cn' else 'Terragenesis Region Shaping (Experimental)',
           'generator.remotemountains.watershed':'山川形意 · 山海流域（独立演示）' if language=='zh_cn' else 'Terragenesis (Mountain to Ocean)'}
    cn_types=['平原孤山','裂谷','桂林喀斯特','张家界石柱群'];cn_climates=['寒冷','干旱','温带','湿润']
    names['generator.remotemountains.canyon']='山川形意 · 峡谷岩壁（混合角度）' if language=='zh_cn' else 'Terragenesis (Mixed Canyon Cliffs)'
    names['generator.remotemountains.canyon_single']='山川形意 · 峡谷岩壁（统一类型）' if language=='zh_cn' else 'Terragenesis (Single Canyon Cliff Type)'
    settings={
        'remotemountains.settings.title':('地貌世界设置','Terragenesis World Settings'),
        'remotemountains.settings.mode':('地形模式','Terrain mode'),
        'remotemountains.settings.region_chunks':('区域边长（区块）','Region size (chunks)'),
        'remotemountains.settings.region_help':('3 至 96，且为 3 的倍数','3 to 96, in multiples of 3'),
        'remotemountains.settings.invalid':('请输入 3 至 96 之间的 3 的倍数','Enter a multiple of 3 from 3 to 96'),
        'remotemountains.mode.processed':('区域派生地貌','Regional derived landforms'),
        'remotemountains.mode.raw':('扩散基础地形（参数调整）','Tuned diffusion base terrain'),
        'remotemountains.mode.region':('区域塑形（实验）','Region shaping (experimental)'),
        'remotemountains.mode.global':('实时全域','Live global terrain'),
        'remotemountains.mode.demo':('有限演示','Finite demo'),
        'remotemountains.mode.watershed':('山海流域','Mountain-to-ocean watershed'),
        'remotemountains.mode.canyon':('峡谷混合岩壁','Mixed canyon cliffs'),
        'remotemountains.mode.canyon_single':('峡谷统一岩壁','Uniform canyon cliffs')}
    names.update({key:value[0 if language=='zh_cn' else 1] for key,value in settings.items()})
    names['remotemountains.service.starting']='Terrain Diffusion model is starting' if language=='en_us' else '地形扩散模型正在启动'
    names['remotemountains.service.failed']='Terrain Diffusion model failed to start' if language=='en_us' else '地形扩散模型启动失败'
    names.update({
        'remotemountains.install.title':'Terrain setup' if language=='en_us' else '地形服务准备',
        'remotemountains.install.preparing':'Preparing terrain service' if language=='en_us' else '正在准备地形服务',
        'remotemountains.install.downloading':'Downloading runtime files' if language=='en_us' else '正在下载运行环境',
        'remotemountains.install.installing':'Installing dependencies' if language=='en_us' else '正在安装依赖',
        'remotemountains.install.starting':'Starting terrain service' if language=='en_us' else '正在启动地形服务',
        'remotemountains.install.ready':'Terrain service is ready' if language=='en_us' else '地形服务已就绪',
        'remotemountains.install.failed':'Terrain setup failed' if language=='en_us' else '地形服务准备失败',
        'remotemountains.install.retry':'Retry' if language=='en_us' else '重试',
        'remotemountains.install.later':'Later' if language=='en_us' else '稍后',
        'remotemountains.install.open':'Terrain setup' if language=='en_us' else '地形服务安装状态'
    })
    for i,t in enumerate(types):
        for j,c in enumerate(climates):names['biome.remotemountains.'+t+'_'+c]=(cn_climates[j]+cn_types[i]) if language=='zh_cn' else c.title()+' '+t.title()
    write(Path('assets/remotemountains/lang/'+language+'.json'),names)
print('Created 16 biome variants and world preset')


"""Extract only required WorldClim rasters into this workspace; preserve upstream source units."""
from pathlib import Path
import zipfile,shutil
ROOT=Path(__file__).resolve().parents[1]
def main():
    output=ROOT/'data/global';output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ROOT/'runtime/worldclim.zip') as archive:
        for index in (1,4,12,15):
            name=f'wc2.1_10m_bio_{index}.tif'
            match=next(n for n in archive.namelist() if Path(n).name==name)
            with archive.open(match) as source,(output/name).open('wb') as target:shutil.copyfileobj(source,target)
    print('Required WorldClim rasters ready',flush=True)
if __name__=='__main__':main()

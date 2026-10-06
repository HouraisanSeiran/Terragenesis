package com.remotemountains.prepared;

import com.remotemountains.core.BaseTerrainSource;
import com.remotemountains.core.Terrain;
import java.io.IOException;
import java.nio.file.Path;

/** Runtime base source backed entirely by the checked finite height/water artifact. */
public final class PreparedTerrainSource implements BaseTerrainSource {
    private final PreparedArtifact artifact;
    public PreparedTerrainSource(PreparedArtifact artifact){this.artifact=artifact;}
    public PreparedTerrainSource(Path directory,long seed,String expectedIdentity)throws IOException{
        this(PreparedArtifact.read(directory,seed,expectedIdentity));
    }
    public PreparedArtifact artifact(){return artifact;}
    @Override public String identity(){return artifact.identity();}
    @Override public Terrain.Column sample(double x,double z){return artifact.sample(x,z);}
}

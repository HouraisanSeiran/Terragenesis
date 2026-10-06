package com.remotemountains.core;

public enum Landform {
    INSELBERG("平原孤山",0x9CAC64), RIFT("裂谷",0xC28B64),
    KARST("桂林喀斯特",0x5DABA0), PILLARS("张家界石柱群",0x9A88BC);
    public final String title;
    public final int color;
    Landform(String title,int color){this.title=title;this.color=color;}
}

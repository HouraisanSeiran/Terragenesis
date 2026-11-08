# Terragenesis移植说明

固定上游提交：`57e79cc331d17e2a45c897bea9c4c022d1fc5551`。本目录的C#源码、README、LICENSE和THIRD_PARTY_NOTICES保持取得时原始字节；`manifest.json`记录上游URL、Git blob和SHA-256。本文件是本项目补充。

NumPy实现位于 `terrain_pipeline/advanced_terrain_filter.py`，移植C#的PhacelleNoise和ErosionFilter；不移植Unity封装、立方球投影、原始FBM及高度偏移。输入为米制坐标、基础高程、坡度和局部峰谷淡出目标；波长与幅度分别标定水平/竖向尺度。滤波器内部艺术方向不等于最终几何的精确导数。

有意改动：

- 默认`hash_mode=stable`使用uint64晶格哈希。原始浮点Hash2在大坐标处失去小数位，造成空间偏移塌缩；保留`hash_mode=upstream`供公式对照。哈希替换改变具体地形，算法身份为`advanced-terrain-filter-v2-stable-hash`。
- 两种模式均用固定用途字符串`advanced-terrain-filter-v1:{world_seed}:phacelle`做SHA-256。stable取前8字节小端uint64；upstream取前4字节小端并模1,000,000。元数据记录实际值及模式。
- float64广播计算、有限输入范围及内存预算属于本项目接口约束；非零幅度至少0.001m。平滑函数用显式分支避免未选分支溢出。

单octave测试使用独立标量公式检查upstream模式；其它测试检查分块、顺序、接缝、远坐标哈希多样性及种子分离。没有直接编译运行Unity或逐值核验Shadertoy GLSL，因此不宣称与二者位级一致。外观滤波不提供水量、泥沙或冰川守恒模型。

Rune Skovbo Johansen的代码采用MPL-2.0；C#转换及辅助代码的完整归属见本目录原始许可文件。NumPy移植文件保留MPL声明。

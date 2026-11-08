# 火山岛Voronoi形态修正

日期：2026-11-08。[完整记录](../../.scratch/volcanic-islands-refinement-20261108/review.md) · [主产品与图片绑定](image_binding.json) · [关闭/开启对照绑定](comparison_binding.json) · [图片复制核对](delivery_receipt.json)。

![同址旧版、Voronoi关闭与开启的实际岛岸对照](old_off_on_full_coast.png)

三行依次是旧v4、v5关闭Voronoi、v5开启Voronoi；四列依次是幼年、成熟、塌陷和侵蚀静态情景。使用相同位置、坐标范围、种子和高程着色。最后一行的海岸与坡面变化来自保存高程，未仅改变颜色。第四列旧版放射切槽已在v5中移除。

![开启Voronoi的实际上锥几何](volcano_stages_geometry_az225.png)

灰色图没有材质纹理，垂直夸张1倍，四阶段采用同一正交相机和物理高宽比例。图为上锥近景，半幅约4.99km，完整岛岸另见首图或[四阶段全岸](volcano_stages_full_coast.png)。另有[反向几何](volcano_stages_geometry_az45.png)、[双向剖面](volcano_stages_sections_focus.png)与[旧/OFF/ON近景](old_off_on_focus.png)。

来源为实际保存的程序化板块基底与`ocean-islands-volcanic-edifices-v5`；`world_seed=20260903`。基础板块身份`78e2a5fc5ba6e3f6c0cd53d29d99f508d9fb03bfe6c7078c33c61d413459d0bb`，ON实际产品身份`7505d94d91a5fa7c58fe1f48a6ee97fae7657b03d6d4e64ca5b979c88b856d17`，OFF身份`4cd4535aef68322cafbf65e2d634d1466208dcd0896aabc512c723856682c775`。完整路径、原文件与代码SHA见绑定JSON。

局部直接采样99.93m，剖面24.99m；世界概览2km。四阶段是同一固定要素的显式静态对照，非四座自然默认世界岛、非时间模拟。高程与阴影配色不代表卫星观测、植被或岩浆材质；Voronoi是熔岩堆积的几何近似，没有运行岩浆、喷发、水文或真实侵蚀。未使用生成式图片。

本轮图像及来源核对通过；形态自然度保留为用户判断。15张图均有保存样本，不用测试数量替代形态验收。

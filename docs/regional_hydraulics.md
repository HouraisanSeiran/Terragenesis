# 有限计算区域地表水

当前生产身份为`regional-surface-local-inertial-D4-implicit-new-q-drag-v2`，不是旧台阶截头扩散波或Picard模型。完整256²、30m、58.9824km²，H2=H0。模型来源、固定预算、A输入、输出及限制见[阶段接口](regional_hydraulics_delivery.md)。旧显式/Picard失败及v1旧Q摩阻探针保留，不追溯宣称通过v2。

## 面律

使用真实水面梯度；共享面湿深为`max(eta_left,eta_right)-max(bed_left,bed_right)`的非负部分。单位宽流量的更新为：

```text
rhs = q_old - g*h*dt*(eta_right-eta_left)/dx
a = g*dt*n²/h^(7/3)
q_new = 2*rhs/(1+sqrt(1+4*a*abs(rhs)))
```

解析根满足`q_new+a*abs(q_new)*q_new=rhs`，首步也包含摩阻。n=.035 s/m^(1/3)，不截速度/Froude。重力CFL=.45；正性保护保守缩放donor所有出流，不clip负水。削减交换量不是丢水量，次数/比例/最小系数独立报告。

局部惯性忽略平流动量，不是完整浅水方程。高Froude诊断不能隐去；数值守恒与步长趋近不是陡坡自然水力认证。平底格体积V=900h，离散水柱共享水平边位置但各格独立顶高，连续插值背景不得称同体积。

## 读取范围

全部强迫区间积分面转移与首末状态用于逐格连续性冷校验；每24区间首个子步保存动量证据，仅认证抽样离散式，不重认证全部轨迹动量。最终面Q是状态。冷读不得准备地形、重建路由、重新绑定强迫或推进动力学。

案例磁盘2GiB目前为结束后检查，不是运行时预防性限制。solver运行源码冻结；archive/mesh为独立新文件，不改变已运行身份。

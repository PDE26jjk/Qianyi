# Qianyi
牵衣。一个布料模拟的Blender插件


本项目是Qianyi的Blender端代码，还需要配合[Qianyi_DP](https://github.com/PDE26jjk/Qianyi_DP)数据处理才能使用。

## 开发进度及演示

请关注bilibili账号 [@PDE26jjk](https://space.bilibili.com/8300902)

## 待办


- 网格生成
  - [x] 优化三角剖分
  - [ ] 四边形
- 物理仿真
  - [x] 显式积分
  - [ ] PCG (未完成)
  - [ ] Chebyshev (未完成)
  - 碰撞
    - [ ] 空间hash（待优化）
    - [ ] bvh
    - [ ] sdf或水平集
  - 布料各项异性
    - [ ] 板片方向
    - [ ] 算法实现（有限元、弹簧质点）
- 板片编辑器
  - [x] 选择框
  - [x] 创建实例/对称
  - 版片的移动、缩放、旋转
    - [x] 移动
    - [x] 缩放
    - [x] 旋转
  - [ ] 复制粘贴
  - 边的操作
    - [x] 添加点分割边
    - [ ] 添加样条线点改变边的形状
  - [x] 缝线
    - [x] 分区算法
    - [ ] UI（未完成）
  - [ ] 内部线

- [x] 鼠标、VR交互
- [x] 动画录制、缓存
- [ ] 动画缓存导出

## 引用和参考

代码结构，操作部分参考了[CAD_Sketcher](https://github.com/hlorus/CAD_Sketcher)

翻译参考了 [MMD_Tools](https://github.com/MMD-Blender/blender_mmd_tools)


## 其他

“牵衣” 出自同名填词古风歌曲，也源自 “稚子牵衣” 这一古诗文中的常用意象。

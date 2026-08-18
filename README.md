# Iron Reign

Iron Reign 是一款使用 Unreal Engine 5.8 开发、面向 PC 和 macOS 的单机武侠/武将类 RPG。

第一阶段目标是完成一个小型垂直切片，包含一个城镇、一个野外区域、一个势力、一个门派、一个可招募角色、一个数据驱动事件、一次战术战斗，以及存档/读档功能。

## 开始使用

1. 安装 Unreal Engine 5.8，并为目标平台安装 C++ 开发工具链。
2. 使用 Unreal Editor 打开 `IronReign.uproject`。如果编辑器提示生成项目文件，请允许生成。
3. 在编辑器中创建 `/Game/Maps/L_Main` 地图，或者临时修改 `Config/DefaultEngine.ini` 中的默认地图配置。
4. 启用项目使用的 Enhanced Input、Gameplay Tags、Gameplay Ability System 和 Gameplay Tasks 插件。

如果使用源码构建，请通过 `IronReign.uproject` 的右键菜单生成项目文件，然后为目标平台构建 `IronReignEditor`。Windows 和 macOS 共用当前 Target 文件；平台专用的打包配置会在第一个可玩版本完成后补充。

仓库初始状态不会包含 Unreal 自动生成的 `Binaries`、`Intermediate`、`DerivedDataCache` 和 `Saved` 目录。

## 项目目标

- 平台：PC 和 macOS
- 游戏类型：单机、系统驱动的 RPG
- 初期战斗方向：小规模战术战斗

## 项目结构

```text
Source/IronReign/
  Characters/                  角色和后续成长系统使用的数据资产
  IronReignGameMode.*           默认运行时游戏模式
  IronReignWorldStateSubsystem.*
                               世界时间和模拟系统的入口
```

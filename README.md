# Iron Reign · 铁血王座

Iron Reign 是一款使用 Unreal Engine 5.8 开发、面向 PC 和 macOS 的单机 2D 历史策略 RPG，玩法与画面风格致敬光荣（Koei）的《三国志 IX》和《太阁立志传 IV》：在一张手绘风格的九州地图上按月下达指令，看着军团沿道路行军，在六角格战场上亲自指挥战斗，并让武将以一骑讨（单挑）决胜负。

全部画面由 Slate 在运行时绘制，美术、音乐、剧本和多语言文本都是 `Content/Data` 下可再生成的普通文件（PNG / WAV / JSON / TTF），因此项目不依赖任何 `.uasset` 或 `.umap`，克隆后即可编译运行。

## 游戏内容

- **剧本「破碎的天命」（公元 212 年）**：六大势力（铁旗军、西狼骑、青庭、东海盟、南莲、黑山寨）与若干中立城池，22 座城市、34 条道路，约 80 名原创武将，3 个武林门派，十余种武学绝技和二十个左右的数据驱动事件。
- **战略层（三国志 IX 式）**：每月为空闲武将分配内政（开垦、商业、城防、巡察、征兵、训练）、人事（搜索、登用、移动、褒赏）、外交（同盟、停战、赠礼）与门派修行；组建最多 5 名武将的军团出征，月内 30 天实时推进，在道路上遭遇即野战，抵达敌城即攻城。
- **人物成长（太阁立志传式）**：五维能力（武力、统率、智力、政治、魅力）随工作与战斗积累经验成长；忠诚、相性、野心；酒馆传闻与在野武将；门派好感、修行与绝技；俘虏的登用、释放与处斩；君主继承与势力灭亡。
- **战术战斗**：六角格地图（野战地形随城市与道路地形生成，攻城战含城墙、城门与本阵），步兵/骑兵/弓兵相克、地形防御、士气与溃散、火计/混乱/鼓舞等计略，可随时委任 AI 自动指挥。
- **一骑讨**：攻、守、虚三招相克的回合制单挑，配合门派绝技。
- **AI**：电脑势力会发展内政、登用人才、调兵增援、评估兵力后进攻，并向玩家提出同盟或停战；可设置难度。
- **存档**：8 个存档位（0 号为每月自动存档），存档与语言无关。
- **多语言**：English、简体中文、繁體中文、日本語、한국어，可在标题画面或设置中即时切换。

## 开始使用（macOS / Windows）

1. 安装 Unreal Engine 5.8 以及对应平台的 C++ 工具链（macOS 需 Xcode）。
2. 右键 `IronReign.uproject` 生成项目文件（macOS 可用 `GenerateProjectFiles.sh -project=<路径>/IronReign.uproject -game`），然后构建 `IronReignEditor`；或直接双击 `IronReign.uproject` 让编辑器提示编译模块。
3. 在编辑器中点击 Play（或使用 Standalone Game）。默认地图为引擎自带的 `/Engine/Maps/Entry`，游戏模式 `AIronReignGameMode` 会创建全部界面，无需额外地图。
4. 打包时 `Content/Data` 会作为非资源文件一并打包（见 `Config/DefaultGame.ini` 的 `DirectoriesToAlwaysStageAsUFS`）。

## 操作

| 场景 | 操作 |
|---|---|
| 战略地图 | 左键选城；拖动平移；滚轮缩放；右侧指令面板下达命令；空格键结束回合 / 暂停 |
| 执行阶段 | 顶栏可调节推进速度；发生我方战斗时选择「亲自指挥」或「委任」 |
| 战术战斗 | 点选我方部队 → 点蓝色格子移动 → 选择攻击/计略/单挑/待机；右键或 Esc 取消；「结束回合」交给敌军行动 |
| 一骑讨 | 攻胜虚、虚胜守、守胜攻；绝技每场限用一次 |

## 项目结构

```text
Source/IronReign/
  Sim/          与引擎无关的规则引擎（C++20 标准库），可在 Tests/ 中脱离 UE 单独测试
    IronState     数据模型、剧本/存档 JSON 读写
    IronGame*     战略规则、月度流程、AI、事件、外交
    IronBattle*   六角格战术战斗与战斗 AI
    IronDuel      一骑讨
    IronLocale    多语言字符串表
  UI/           Slate 界面：会话、资源加载、风格、标题/新游戏/存读档/设置、战略地图、战斗与单挑界面、音频
  IronReignGameMode / IronReignPlayerController / IronReignWorldStateSubsystem
  Tests/        UE 自动化测试（IronReign.*）
Content/Data/
  Scenarios/    剧本 JSON
  Art/          生成的美术（地图、城池、六角地块、部队、立绘、UI、事件插画）
  Audio/        生成的音乐与音效（WAV）
  Fonts/        OFL 字体（拉丁字体 + 按语言裁剪的 Noto Serif CJK）
  Localization/ 各语言字符串表
Tools/
  ArtGen/       美术生成脚本（Python + numpy/Pillow）
  AudioGen/     音乐与音效合成脚本
  Localization/ 文本提取、完整性检查、CJK 字体裁剪
  validate_scenario.py
Tests/          规则引擎单元测试与无头 AI 战役（CMake）
docs/DESIGN.md  设计文档与制作规范（数据格式、美术规范、界面规范）
```

## 数据、美术与本地化工作流

- **剧本**：编辑 `Content/Data/Scenarios/*.json`（格式见 `docs/DESIGN.md` 第 7 节），然后运行 `python3 Tools/validate_scenario.py`。
- **美术 / 音频**：`python3 Tools/ArtGen/<脚本>.py`、`python3 Tools/AudioGen/make_audio.py` 可重新生成全部资源（需要 `pip install numpy scipy pillow`）。
- **文本**：代码中所有可见文本都写成 `Loc("key", "English")` / `LocF(...)`。修改文本或剧本后：
  1. `python3 Tools/Localization/extract_strings.py` 更新英文源表；
  2. 在 `Content/Data/Localization/<语言>/` 中补全翻译；
  3. `python3 Tools/Localization/check_localization.py` 检查缺失键与占位符；
  4. `python3 Tools/Localization/build_fonts.py` 按实际用字重新裁剪 CJK 字体（需要 `pip install fonttools brotli`）。

## 测试

```bash
cmake -S Tests -B build -G Ninja && cmake --build build && ctest --test-dir build --output-on-failure
```

包含 JSON、存档往返、内政/军事/外交规则、战斗与单挑平衡、以及让 AI 操控所有势力进行二十年的无头战役测试。CMake 工程还会把 `Sim/` 全部源文件合并为一个翻译单元编译，以模拟 UE 的 Unity Build。

## 持续集成

`.github/workflows/ci.yml` 包含三个作业：

1. **Rules engine**：在 Ubuntu 上分别用 gcc 和 clang 编译并运行规则引擎测试。
2. **Data**：校验剧本与各语言字符串表。
3. **Unreal Engine 5.8**：在 Epic 官方容器镜像 `ghcr.io/epicgames/unreal-engine:dev-slim-5.8` 中编译 `IronReignEditor`、运行 `IronReign.*` 自动化测试；推送到 `main` 或手动触发（勾选 package）时还会烘焙并打包 Linux 版本作为构建产物。

Epic 的镜像是私有的，需要：

- 将 GitHub 账号与 Epic Games 账号关联（参见 Epic 的 “Unreal Engine on GitHub” 说明）；
- 在仓库 Secrets 中设置 `GHCR_USERNAME`（该 GitHub 用户名）与 `GHCR_TOKEN`（具有 `read:packages` 权限的个人访问令牌）。

可选的仓库变量：`UE_IMAGE`（覆盖镜像标签）与 `UE_RUNNER`（引擎镜像较大，可改用更大磁盘的 runner 或自托管 runner）。未配置凭据时该作业会给出警告并跳过。

## 许可

字体遵循 SIL Open Font License（见 `Content/Data/Fonts/OFL-*.txt`）。其余美术与音频均由仓库内脚本生成。

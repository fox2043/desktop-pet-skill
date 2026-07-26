# 电脑桌面宠物（Desktop Pet Skill）

把 1–4 张猫或狗照片制作成一个 Windows 透明背景桌面宠物。它会在桌面上慢慢发呆、躺卧、睡觉、散步，并对鼠标、右键菜单、喂食、工作状态和深夜作出不同反应。

## 隐私与离线原则

- 运行时不调用任何 AI API，也不上传照片或遥测数据。
- 照片仅在本机提取主体并生成动作资源。
- 此仓库不包含用户宠物照片、生成的 EXE、安装包或测试产物。

## 安装技能

将本仓库的 `desktop-pet` 文件夹复制到 Codex 的 skills 目录，例如：

```powershell
Copy-Item -Recurse .\desktop-pet "$env:USERPROFILE\.codex\skills\desktop-pet"
```

随后在 Codex 中说：

> 使用 $desktop-pet，根据我上传的宠物照片制作完全离线的 Windows 桌面宠物。

## 使用方式

准备 1–4 张清晰的宠物照片，选择 `cat` 或 `dog`。技能会生成：

- `宠物名桌面宠物.exe`：可直接运行的透明桌面宠物；
- `宠物名桌面宠物-便携版.zip`：分享给他人的便携包；
- 可选安装程序：在本机安装 Inno Setup 后构建。

运行环境与命令、动作清单、故障排查见 [requirements.md](desktop-pet/references/requirements.md)。技能说明见 [SKILL.md](desktop-pet/SKILL.md)。

## 动作与交互

每只宠物默认生成 13 类动作、65 张透明 PNG 帧。猫和狗采用不同的姿态模板；静止状态会保留较长时间，避免高频切换。包含：休息、睡觉、等待、招呼、跳跃、卖萌、工作陪伴、审阅、左右散步、喂食、玩耍和开心回应。

## 依赖与许可

生成端需要 Windows、Python、PyInstaller、Pillow、OpenCV、NumPy 与 PyYAML；成品运行不需要 Python，也不访问网络。抠图模型的上游许可说明在 [MODEL_LICENSE.txt](desktop-pet/assets/project-template/assets/models/MODEL_LICENSE.txt)。本仓库其余代码采用 [MIT License](LICENSE)。

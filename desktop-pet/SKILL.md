---
name: desktop-pet
description: Create a fully offline Windows desktop pet from 1–4 user-provided cat or dog photos. Use when a user asks to turn their pet photos into a transparent-background desktop companion, personalized pet EXE, portable ZIP, or installer with species-specific sleeping, greeting, playing, walking, working, feeding, mouse-interaction, and bedtime behaviors. The runtime must not call any API or upload photos.
---

# 电脑桌面宠物

从用户提供的 1–4 张猫或狗照片，本地生成带透明动作包的 Windows 桌面宠物。

## 工作流

1. 确认运行环境为 Windows，并收集：
   - 宠物名字。
   - 宠物类型，只能是 `cat` 或 `dog`。
   - 1–4 张本地照片路径。
   - 是否需要独立 EXE、便携 ZIP，以及可选安装程序。
2. 检查照片：
   - 至少一张主体清楚、身体较完整。
   - 优先组合正面、侧面、坐姿和趴姿。
   - 不把照片上传到任何服务，不调用图像 API。
3. 如依赖缺失，执行：

   ```powershell
   python -m pip install -r "<skill-dir>\assets\project-template\requirements.txt"
   ```

4. 运行生成器；每张照片重复一个 `--photo`：

   ```powershell
   python "<skill-dir>\scripts\create_desktop_pet.py" `
     --name "雪球" `
     --species cat `
     --photo "C:\photos\cat-front.jpg" `
     --photo "C:\photos\cat-side.jpg" `
     --output "C:\output\snowball-desktop-pet"
   ```

5. 用户明确需要安装程序时，加 `--installer`。如果没有找到 Inno Setup，
   安装 Inno Setup 6/7，或用 `--iscc "...\ISCC.exe"` 指定编译器。
6. 对生成结果运行：

   ```powershell
   python "<skill-dir>\scripts\validate_output.py" `
     --result "C:\output\snowball-desktop-pet\result.json"
   ```

7. 只在验证通过后交付 `deliverables/` 中的 EXE、便携 ZIP和可选安装程序。

## 行为要求

- 猫以睡觉、趴着、发呆为主，互动动作慢而克制；保留踩奶和慢速桌面散步。
- 狗使用歪头、抬爪迎接、玩耍弓步、守候和更主动的跟随行为。
- 常规姿态至少停留 7 秒；睡觉和躺卧停留更久。
- 右键打招呼、跳跃、卖萌、开心玩耍、喂食和陪工作必须切换到对应动作。
- 动作直接衔接，不使用叠化，避免双影。
- 23:00 后触发睡觉提醒。
- 窗口必须透明、无背景；退出只通过托盘或右键菜单，不弹确认框。

## 输出与隐私

- 生成器把动作包预装进 EXE；首次运行复制到当前 Windows 用户的本地数据目录。
- 每只宠物使用独立的数据目录、设置项和启动项，避免多个桌宠互相覆盖。
- 运行时代码不得包含 OpenAI、HTTP 客户端或其他远程生成依赖。
- 不要把用户照片、测试输出、构建缓存或本地密钥提交到 Git 仓库。

需要照片选择、依赖、输出结构或故障排查细节时，读取
[requirements.md](references/requirements.md)。

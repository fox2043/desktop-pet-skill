# 电脑桌面宠物：运行与输入要求

## 环境

- Windows 10/11 x64。
- Python 3.11 或 3.12。
- 构建依赖在 `assets/project-template/requirements.txt`。
- 安装程序是可选产物，需要 Inno Setup 6 或 7。

## 照片建议

- 支持 JPG、JPEG、PNG、WebP、BMP。
- 使用 1–4 张同一只宠物的照片。
- 避免宠物被家具、玩具或人手大面积遮挡。
- 最佳组合：正面坐姿、侧面全身、趴姿或睡姿、脸部清晰近照。
- 程序使用本地 Mask R-CNN 提取宠物轮廓；复杂背景可能降低边缘质量。

## 默认动作包

每只宠物生成 13 类动作，每类 5 帧，共 65 张透明 PNG：

- `idle`
- `sleeping`
- `waiting`
- `waving`
- `jumping`
- `failed`
- `working`
- `review`
- `walking-right`
- `walking-left`
- `feeding`
- `playing`
- `happy`

## 输出目录

```text
<output>/
├── result.json
├── project/
│   ├── assets/bootstrap/
│   ├── src/
│   └── dist/
└── deliverables/
    ├── <宠物名>桌面宠物.exe
    ├── <宠物名>桌面宠物-便携版.zip
    └── <宠物名>桌面宠物安装程序-v2.0.0.exe  # 可选
```

## 常见问题

- 未识别到猫或狗：换用身体更完整、光线更好、遮挡更少的照片。
- 边缘带背景：换用背景简单的照片，尤其避免与毛色相近的地毯。
- 动作形象差异大：增加同一宠物的正面和侧面照片。
- 找不到 PyInstaller：安装项目 `requirements.txt`。
- 找不到 Inno Setup：省略 `--installer` 仍可交付独立 EXE和便携 ZIP。
- Windows SmartScreen 提示：未购买代码签名证书时属于预期现象；只从可信来源分发。

# 好柒实用工具资产库 (HAOAH's Blender Asset Library)

Blender 5.2+ 远程资产库，可在 Blender 的资产浏览器中直接浏览与下载。

## 在 Blender 中添加

`编辑 > 偏好设置 > 文件路径 > 资产库 > + > 添加远程资产库`

URL: `https://haoah0091.github.io/blender-assets/`

## 更新

本地库改动后，运行发布脚本或手动执行：

```
blender -b -c asset_listing generate <仓库根目录>
```

然后修正 `_asset-library-meta.json` 里的 hash 并提交推送。

## 目录结构

- `自研节点/` —— 自己开发的几何节点工具
- `外部节点/` —— 第三方节点
- `待优化/` —— 待改进的资产
- `过时/` —— 已淘汰的资产

> ⚠️ 注意：`_asset-library-meta.json` 中的 hash 必须与 `_v1/asset-index.json` 的实际
> 内容字节严格一致（UTF-8 无 BOM）。切勿用 PowerShell 的 `Set-Content -Encoding UTF8`
> 重写该文件——它会写入 BOM，导致 hash 校验失败、Blender 报 "file is too old"。

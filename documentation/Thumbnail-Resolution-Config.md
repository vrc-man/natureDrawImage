# 管理后台缩略图分辨率修改说明

本文档说明 `/admin` 管理后台中 **画风、角色、工作流缩略图** 的生成分辨率、压缩质量在哪里修改，以及修改后如何重新构建前端。

当前缩略图规格：

- 输出尺寸：`512 × 512`
- 输出格式：`WebP`
- 压缩质量：`90%`
- 生效范围：画风缩略图、角色缩略图、工作流缩略图，包含单图上传和批量上传

---

## 1. 前端修改位置

文件：

```text
frontend/src/components/admin/useAdminApi.ts
```

核心位置：

```ts
const THUMBNAIL_SIZE = 512
const THUMBNAIL_QUALITY = 0.9
```

含义：

| 常量 | 说明 |
|------|------|
| `THUMBNAIL_SIZE` | 前端 canvas 输出的缩略图尺寸，目前是 `512`，即生成 `512×512` |
| `THUMBNAIL_QUALITY` | 前端 WebP 压缩质量，目前是 `0.9`，即约 `90%` |

如果以后要改成其他尺寸，例如 `768×768`：

```ts
const THUMBNAIL_SIZE = 768
```

如果以后要改成 95% 质量：

```ts
const THUMBNAIL_QUALITY = 0.95
```

### 前端覆盖范围

这个 `resizeImage()` 是管理后台缩略图上传的共享方法，会影响：

- 画风管理：`StyleSection.vue`
- 角色管理：`CharacterSection.vue`
- 工作流元数据：`WfMetaSection.vue`
- 单张缩略图上传
- 批量缩略图上传

所以正常情况下，只需要改 `useAdminApi.ts` 里的常量，不需要分别改三个 Vue 组件的上传逻辑。

---

## 2. 后端修改位置

文件：

```text
web/app.py
```

核心位置：

```py
THUMBNAIL_SIZE = 512
```

以及后端兜底保存质量：

```py
img.save(buf, format="WEBP", quality=90, optimize=True)
```

含义：

| 配置 | 说明 |
|------|------|
| `THUMBNAIL_SIZE` | 后端最终校验/转换的缩略图尺寸，目前是 `512×512` |
| `quality=90` | 后端兜底转换 WebP 时的压缩质量，目前是 `90%` |

如果以后前端尺寸改了，后端这里也要同步改，否则会出现两种问题：

- 只改前端，不改后端：后端可能又把图片压回旧尺寸；
- 只改后端，不改前端：前端可能先生成低分辨率图，再被后端放大，画质会变差。

### 后端覆盖范围

后端 `_verify_and_resize_thumb()` 会被 `_save_upload()` 调用，覆盖以下接口：

```text
POST /api/admin/style_thumbnail
POST /api/admin/character_thumbnail
POST /api/admin/wf_thumbnail
POST /api/admin/style_thumbnail_batch
POST /api/admin/character_thumbnail_batch
POST /api/admin/wf_thumbnail_batch
```

也就是说，画风、角色、工作流的单图上传和批量上传都会走后端兜底校验。

---

## 3. 三个管理后台组件的位置

这些文件是上传入口和提示文案所在位置，一般不用改尺寸逻辑：

```text
frontend/src/components/admin/StyleSection.vue
frontend/src/components/admin/CharacterSection.vue
frontend/src/components/admin/WfMetaSection.vue
```

当前这些组件只负责：

- 打开文件选择框；
- 调用 `resizeImage()` 压缩图片；
- 上传到对应后端接口；
- 显示上传结果和说明文案。

如果只是改缩略图实际生成尺寸，优先改：

```text
frontend/src/components/admin/useAdminApi.ts
web/app.py
```

如果要改后台页面上的文字提示，例如“上传后会自动生成 512×512 WebP 缩略图”，再改上面三个组件。

---

## 4. 前端构建命令

进入前端目录：

```bash
cd /i/网站/shengtu/natureDrawImage-main-sqlit/frontend
```

执行构建：

```bash
npm run build
```

项目的构建脚本来自：

```text
frontend/package.json
```

当前脚本是：

```json
"build": "vue-tsc -b && vite build"
```

构建后产物会输出到：

```text
web/static/dist
```

因为 `frontend/vite.config.ts` 中配置了构建输出目录指向后端静态目录。

---

## 5. 后端语法检查命令

修改 `web/app.py` 后，可以执行：

```bash
python -m py_compile 'I:/网站/shengtu/natureDrawImage-main-sqlit/web/app.py'
```

无输出通常表示语法检查通过。

---

## 6. 上传后如何确认尺寸

上传缩略图后，找到实际保存的 `.webp` 文件，然后执行：

```bash
python -c "from PIL import Image; img=Image.open(r'实际缩略图路径.webp'); print(img.size, img.format)"
```

期望输出：

```text
(512, 512) WEBP
```

需要分别抽查：

- `web/style_thumbnails/`：画风缩略图；
- `web/character_thumbnails/`：角色缩略图；
- `web/thumbnails/`：工作流缩略图。

---

## 7. 修改尺寸时的推荐流程

如果以后要把缩略图从 `512×512` 改成其他尺寸，建议按这个顺序操作：

1. 修改前端：

```text
frontend/src/components/admin/useAdminApi.ts
```

修改：

```ts
const THUMBNAIL_SIZE = 新尺寸
const THUMBNAIL_QUALITY = 新质量
```

2. 修改后端：

```text
web/app.py
```

修改：

```py
THUMBNAIL_SIZE = 新尺寸
img.save(buf, format="WEBP", quality=新质量整数, optimize=True)
```

3. 如有需要，修改三个管理后台组件里的提示文案：

```text
frontend/src/components/admin/StyleSection.vue
frontend/src/components/admin/CharacterSection.vue
frontend/src/components/admin/WfMetaSection.vue
```

4. 重新构建前端：

```bash
cd /i/网站/shengtu/natureDrawImage-main-sqlit/frontend
npm run build
```

5. 检查后端语法：

```bash
python -m py_compile 'I:/网站/shengtu/natureDrawImage-main-sqlit/web/app.py'
```

6. 打开 `/admin`，分别测试画风、角色、工作流缩略图上传。

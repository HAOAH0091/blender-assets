"""远程资产库发布工具（修复中文资产缩略图撞名问题）

背景：Blender 自带的 `asset_listing generate` 在导出缩略图时，
用 `_name_to_filename()` 清洗资产名——它做了
`unicodedata.normalize('NFKD', name).encode('ascii','ignore')`，
**非 ASCII 字符（中文）会被整体丢弃**，导致：

    二极化分布调整   -> Nodetree/.webp    （空名）
    随机值_二极化调整 -> Nodetree/.webp    （空名，撞车被覆盖！）

于是索引里两个资产声明了不同 hash，却指向同一个文件，必然有一个校验失败。

本脚本在 generate 之后接管缩略图：
  1. 用 Blender 后台打开每个 .blend，把每个资产的预览图导出成唯一文件名
     （`<资产名清洗>__<md5(名字)[:8]>.webp`，保证不撞车）
  2. 重写 assets-*.json 里对应资产的 thumbnail.url / hash
  3. 重算分页 hash 与 meta hash
  4. 从磁盘读回做最终校验

用法：
    python publish.py <仓库目录>
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.parse

BLENDER = r"G:\steam\steamapps\common\Blender\blender.exe"

_EXPORT_SCRIPT = r'''
import bpy, os, json, hashlib, unicodedata, re

OUT = os.environ["RA_OUT"]
REF = json.load(open(os.environ["RA_REF"], encoding="utf-8"))
want = set(REF["want"])   # 需要导出的资产 key: "<id_type>|<name>"

def safe_name(v):
    v = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode("ascii")
    v = re.sub(r"[^\w\s_-]", "", v.lower())
    v = re.sub(r"[-\s]+", "-", v).strip("-_")
    return v or "asset"

result = {}
for coll_name in ("node_groups", "materials", "objects", "images", "worlds", "collections"):
    coll = getattr(bpy.data, coll_name, None)
    if coll is None:
        continue
    for db in coll:
        if not db.asset_data:
            continue
        key = db.id_type + "|" + db.name
        if key not in want:
            continue
        p = db.preview
        if not p or p.image_size[0] <= 0 or p.image_size[1] <= 0:
            continue
        w, h = p.image_size
        px = list(p.image_pixels_float)
        rows = [px[i*w*4:(i+1)*w*4] for i in range(h)][::-1]   # OpenGL 行序翻转
        flat = [c for r in rows for c in r]
        suffix = hashlib.md5(key.encode("utf-8")).hexdigest()[:8]
        fname = f"{safe_name(db.name)}__{suffix}.webp"
        img = bpy.data.images.new("_ra_tmp", width=w, height=h, alpha=True)
        img.pixels = flat
        img.file_format = "WEBP"
        img.save(filepath=os.path.join(OUT, fname), quality=80)
        bpy.data.images.remove(img)
        data = open(os.path.join(OUT, fname), "rb").read()
        result[key] = {
            "file": fname,
            "hash": "SHA256:" + hashlib.sha256(data).hexdigest(),
        }

json.dump(result, open(os.environ["RA_RESULT"], "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("EXPORTED", len(result))
'''


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "SHA256:" + h.hexdigest()


def read_json(path: str):
    return json.loads(open(path, encoding="utf-8-sig").read())


def write_json(path: str, obj):
    # 无 BOM、LF —— 与 Blender 的裸字节 hash 口径一致
    open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, ensure_ascii=False, indent=2))


def main(repo: str) -> int:
    repo = os.path.abspath(repo)
    idx_path = os.path.join(repo, "_v1", "asset-index.json")
    idx = read_json(idx_path)
    report = {"regenerated": [], "failed": []}

    # --- 收集：哪些资产的缩略图需要重新导出 ---
    # 只处理「同一个 .blend 内多个资产解析到同一个缩略图 URL」的冲突组
    for page in idx.get("pages", []):
        page_path = os.path.join(repo, *page["url"].replace("/", os.sep).split(os.sep))
        page_data = read_json(page_path)

        # 按 blend 文件分组，找出 URL 冲突
        by_file: dict[str, list] = {}
        for a in page_data.get("assets", []):
            th = a.get("thumbnail")
            if not th:
                continue
            f = a.get("files", [""])[0]
            by_file.setdefault(f, []).append(a)

        for blend_rel, alist in by_file.items():
            # 触发条件（任一）：
            #   1) 同一 blend 内多个资产指向同一个缩略图 URL（真撞名）
            #   2) 缩略图文件名被清洗成空（中文名被 ascii 化丢弃，如 "/.webp"）
            urls: dict[str, int] = {}
            for a in alist:
                u = a["thumbnail"]["url"]
                urls[u] = urls.get(u, 0) + 1
            has_dup = any(n > 1 for n in urls.values())
            has_empty = any(
                urllib.parse.unquote(u).endswith("/.webp") or
                os.path.basename(urllib.parse.unquote(u)) == ".webp"
                for u in urls)
            if not (has_dup or has_empty):
                continue

            blend_path = os.path.join(repo, *blend_rel.split("/"))
            if not os.path.exists(blend_path):
                report["failed"].append(f"missing blend: {blend_rel}")
                continue

            # 让 Blender 导出这一批资产
            want = [a["id_type"] + "|" + a["name"] for a in alist]
            outdir = os.path.join(repo, os.path.dirname(blend_rel),
                                  os.path.splitext(os.path.basename(blend_rel))[0] + "_thumbnails")
            os.makedirs(outdir, exist_ok=True)
            with tempfile.TemporaryDirectory() as td:
                ref = os.path.join(td, "ref.json")
                res = os.path.join(td, "res.json")
                scr = os.path.join(td, "export.py")
                json.dump({"want": want}, open(ref, "w", encoding="utf-8"), ensure_ascii=False)
                open(scr, "w", encoding="utf-8").write(_EXPORT_SCRIPT)
                env = dict(os.environ, RA_OUT=outdir, RA_REF=ref, RA_RESULT=res)
                p = subprocess.run([BLENDER, "--background", "--factory-startup",
                                    blend_path, "--python", scr],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", env=env, timeout=900)
                if not os.path.exists(res):
                    report["failed"].append(f"export failed: {blend_rel}: {(p.stdout or '')[-200:]}")
                    continue
                exported = json.load(open(res, encoding="utf-8"))

            # 回写：给每个资产指向自己的唯一缩略图
            prefix = os.path.dirname(blend_rel)
            for a in alist:
                key = a["id_type"] + "|" + a["name"]
                info = exported.get(key)
                if not info:
                    report["failed"].append(f"no preview: {blend_rel} :: {a['name']}")
                    continue
                rel = "/".join([p for p in (prefix, os.path.basename(outdir), info["file"]) if p])
                a["thumbnail"] = {"url": urllib.parse.quote(rel), "hash": info["hash"]}
                report["regenerated"].append({"asset": a["name"], "file": rel})

        write_json(page_path, page_data)

    # --- 重算分页 hash ---
    for page in idx.get("pages", []):
        page_path = os.path.join(repo, *page["url"].replace("/", os.sep).split(os.sep))
        page["hash"] = sha256_file(page_path)
    write_json(idx_path, idx)

    # --- 重写 meta ---
    meta_path = os.path.join(repo, "_asset-library-meta.json")
    meta = read_json(meta_path) if os.path.exists(meta_path) else {}
    meta["name"] = "好柒实用工具资产库"
    meta.setdefault("contact", {"name": "HAOAH", "url": "https://github.com/HAOAH0091",
                                "email": "toukou0091@gmail.com"})
    meta["api_versions"] = {"v1": {"url": "_v1/asset-index.json",
                                   "hash": sha256_file(idx_path)}}
    write_json(meta_path, meta)

    # --- 最终校验 ---
    vmeta = read_json(meta_path)
    ok_meta = vmeta["api_versions"]["v1"]["hash"] == sha256_file(idx_path)
    vidx = read_json(idx_path)
    ok_pages = True
    thumbs_total = thumbs_bad = 0
    for page in vidx.get("pages", []):
        pp = os.path.join(repo, *page["url"].replace("/", os.sep).split(os.sep))
        if sha256_file(pp) != page["hash"]:
            ok_pages = False
        pd = read_json(pp)
        for a in pd.get("assets", []):
            th = a.get("thumbnail")
            if not th:
                continue
            thumbs_total += 1
            fp = os.path.join(repo, *urllib.parse.unquote(th["url"]).replace("/", os.sep).split(os.sep))
            if not os.path.exists(fp) or sha256_file(fp) != th["hash"]:
                thumbs_bad += 1

    print(json.dumps({
        "report": report,
        "verify": {"meta_hash_ok": ok_meta, "pages_hash_ok": ok_pages,
                   "thumbs_checked": thumbs_total, "thumbs_bad": thumbs_bad,
                   "assets": vidx.get("asset_count")},
    }, ensure_ascii=False, indent=1))
    return 0 if (ok_meta and ok_pages and thumbs_bad == 0) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))

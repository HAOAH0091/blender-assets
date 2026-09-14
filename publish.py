"""远程资产库发布 —— 后处理 + 校验
用法: python _ra_publish.py <仓库目录>
1) 校验 _v1/asset-index.json 的 hash 与 meta 一致（裸字节口径，同 Blender hashing.py）
2) 校验每个分页 hash
3) 校验每个缩略图 hash；不一致的按实际文件修正（生成器对中文名资产会撞名覆盖）
4) 重写 meta 的页码 hash，最后统一回写，并再次从磁盘读回验证
"""
import os, sys, json, hashlib, urllib.parse

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "SHA256:" + h.hexdigest()

def read_json(p):
    return json.loads(open(p, encoding="utf-8-sig").read())

def write_json(p, obj):
    # 关键：无 BOM、LF、UTF-8
    open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(obj, ensure_ascii=False, indent=2))

def rel_to_path(repo, url):
    return os.path.join(repo, *urllib.parse.unquote(url).replace("/", os.sep).split(os.sep))

def main(repo):
    repo = os.path.abspath(repo)
    report = {"thumb_fixed": [], "thumb_missing": [], "errors": []}

    idx_path = os.path.join(repo, "_v1", "asset-index.json")
    idx = read_json(idx_path)

    # --- 1. 修正缩略图 hash（先于分页）---
    for page in idx.get("pages", []):
        page_path = os.path.join(repo, *page["url"].replace("/", os.sep).split(os.sep))
        page_data = read_json(page_path)
        changed = False
        for a in page_data.get("assets", []):
            th = a.get("thumbnail")
            if not th:
                continue
            fp = rel_to_path(repo, th["url"])
            if not os.path.exists(fp):
                report["thumb_missing"].append({"asset": a["name"], "url": th["url"]})
                continue
            actual = sha256_file(fp)
            if actual != th["hash"]:
                report["thumb_fixed"].append({
                    "asset": a["name"], "url": th["url"],
                    "declared": th["hash"][:20], "actual": actual[:20]})
                th["hash"] = actual
                changed = True
        if changed:
            write_json(page_path, page_data)

    # --- 2. 回写分页 hash 到索引 ---
    for page in idx.get("pages", []):
        page_path = os.path.join(repo, *page["url"].replace("/", os.sep).split(os.sep))
        page["hash"] = sha256_file(page_path)
    write_json(idx_path, idx)

    # --- 3. 回写 meta ---
    meta_path = os.path.join(repo, "_asset-library-meta.json")
    meta = read_json(meta_path) if os.path.exists(meta_path) else {}
    meta.setdefault("contact", {"name": "HAOAH", "url": "https://github.com/HAOAH0091",
                                "email": "toukou0091@gmail.com"})
    meta["name"] = "好柒实用工具资产库"
    meta["api_versions"] = {"v1": {"url": "_v1/asset-index.json", "hash": sha256_file(idx_path)}}
    write_json(meta_path, meta)

    # --- 4. 从磁盘读回最终验证（模拟 Blender 校验）---
    vmeta = read_json(meta_path)
    h_declared = vmeta["api_versions"]["v1"]["hash"]
    h_actual = sha256_file(idx_path)
    vidx = read_json(idx_path)
    page_ok = all(sha256_file(os.path.join(repo, *p["url"].replace("/", os.sep).split(os.sep))) == p["hash"]
                  for p in vidx.get("pages", []))
    # 缩略图全量复查
    thumb_bad = 0; thumb_total = 0
    for page in vidx.get("pages", []):
        pd = read_json(os.path.join(repo, *page["url"].replace("/", os.sep).split(os.sep)))
        for a in pd.get("assets", []):
            th = a.get("thumbnail")
            if not th: continue
            fp = rel_to_path(repo, th["url"])
            if os.path.exists(fp):
                thumb_total += 1
                if sha256_file(fp) != th["hash"]:
                    thumb_bad += 1

    verify = {
        "meta_hash_ok": h_declared == h_actual,
        "pages_hash_ok": page_ok,
        "thumbs_checked": thumb_total,
        "thumbs_bad": thumb_bad,
        "asset_count": vidx.get("asset_count"),
        "file_count": vidx.get("file_count"),
        "catalogs": [c.get("simple_name") for c in vidx.get("catalogs", [])],
    }
    print(json.dumps({"report": report, "verify": verify}, ensure_ascii=False, indent=1))
    return 0 if (verify["meta_hash_ok"] and verify["pages_hash_ok"] and thumb_bad == 0) else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))

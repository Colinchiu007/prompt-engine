"""解析 NBP README，提取结构化 prompt 数据并导入 RAG 知识库"""
import logging
import re
import json
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_nbp_readme(readme_path: str) -> list[dict]:
    """从 NBP README 提取所有 prompt 条目"""
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按 "### No.X:" 分割各 prompt 条目（No. 后面可能有个空格）
    # 匹配模式: ### No. 1: Wide quote card...
    entries = re.split(r'(?=^### No\.\s*\d+:)', content, flags=re.MULTILINE)

    results = []
    entry_id = 0

    for section in entries:
        # 提取标题（去掉 ### No.X: 前缀）
        title_match = re.match(r'### No\.\s*\d+:\s*(.+)', section.strip())
        if not title_match:
            continue

        title = title_match.group(1).strip()

        # 提取 prompt 代码块内容
        prompt_match = re.search(r'```(?:\n)?\s*(.*?)\s*```', section, re.DOTALL)
        if not prompt_match:
            continue

        prompt_text = prompt_match.group(1).strip()
        if len(prompt_text) < 20:  # 跳过太短的
            continue

        # 提取 description（#### 📖 Description 之后）
        desc_match = re.search(r'#### 📖 Description\s*\n(.*?)(?=####|$)', section, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""

        # 提取标签/分类
        tags = []
        for tag_match in re.finditer(r'!\[([^\]]+)\]\([^)]+\)', section[:500]):  # 只在前面找标签
            tag = tag_match.group(1)
            if tag not in ('English', 'Featured', '🚀-Raycast_Friendly'):
                tags.append(tag)

        # 映射 platform（基于标签/内容判断）
        platform = "generic"
        if "Midjourney" in section or "mj" in section.lower():
            platform = "midjourney"
        elif "Stable Diffusion" in section or "sd" in section.lower():
            platform = "stable_diffusion"

        # 映射 style
        style = "realistic"
        section_lower = section.lower()
        if any(s in section_lower for s in ['anime', 'manga', 'cartoon']):
            style = "anime"
        elif any(s in section_lower for s in ['oil paint', 'painting']):
            style = "oil_painting"
        elif any(s in section_lower for s in ['watercolor']):
            style = "watercolor"
        elif any(s in section_lower for s in ['cyberpunk', 'sci-fi']):
            style = "cyberpunk"
        elif any(s in section_lower for s in ['pixel', 'retro']):
            style = "retro"

        entry_id += 1
        results.append({
            "id": f"nbp_{entry_id:05d}",
            "title": title,
            "description": description[:500],  # 截断
            "prompt_text": prompt_text,
            "language": "en",
            "categories": tags[:5],
            "platform": platform,
            "style": style,
            "quality_score": 9,  # Featured 都算高质量
        })

    return results


def import_to_project(parsed_entries: list[dict], project_dir: str):
    """导入到项目 prompts.json"""
    db_path = Path(project_dir) / "prompt_engine" / "prompts_db" / "prompts.json"
    
    # 读取现有数据
    existing = []
    if db_path.exists() and db_path.stat().st_size > 0:
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            logger.warning("Failed to load existing prompts.json, starting fresh")
            existing = []

    # 追加新数据
    existing.extend(parsed_entries)
    
    # 保存
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    
    return existing


def rebuild_index(project_dir: str):
    """重建 TF-IDF 索引"""
    from prompt_engine.knowledge.vector_store import PromptVectorStore
    from prompt_engine.knowledge.loader import PromptEntry
    
    db_path = Path(project_dir) / "prompt_engine" / "prompts_db"
    store = PromptVectorStore(str(db_path))
    
    # 从 prompts.json 加载
    json_path = db_path / "prompts.json"
    if not json_path.exists():
        print("No prompts.json found")
        return
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entries = [
        PromptEntry(
            id=e["id"],
            title=e["title"],
            description=e["description"],
            prompt_text=e["prompt_text"],
            language=e.get("language", "en"),
            categories=e.get("categories", []),
            platform=e.get("platform", "generic"),
            style=e.get("style", ""),
            quality_score=e.get("quality_score", 5),
        )
        for e in data
    ]
    
    store.add_prompts(entries)
    print(f"✅ Index rebuilt: {store.count} entries")


if __name__ == "__main__":
    import sys
    readme = sys.argv[1] if len(sys.argv) > 1 else "/tmp/nbp_raw.md"
    project_dir = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\邱领\projects\prompt-engine"
    
    print(f"📂 Parsing {readme}...")
    entries = parse_nbp_readme(readme)
    print(f"📝 Extracted {len(entries)} entries")
    
    print(f"💾 Importing to {project_dir}...")
    all_entries = import_to_project(entries, project_dir)
    print(f"📚 Total entries: {len(all_entries)}")
    
    print(f"🔍 Rebuilding index...")
    rebuild_index(project_dir)

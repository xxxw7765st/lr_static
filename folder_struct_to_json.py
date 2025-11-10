import json
import os
import subprocess
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

HASH_PATTERN = re.compile(r"\._\.M[0-9a-z]+\._\.")

def get_git_root(path: str) -> Optional[str]:
    """获取Git仓库根目录，非Git仓库返回None"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=os.path.abspath(path),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, Exception):
        return None


def get_git_last_modified_utc(
    file_path: str, git_root: Optional[str]
) -> Optional[datetime]:
    """获取文件的Git最新提交时间（转为UTC时区），未跟踪/非Git返回None"""
    if not git_root or not os.path.isfile(file_path):
        return None
    try:
        rel_path = os.path.relpath(os.path.abspath(file_path), git_root)
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ai", "--", rel_path],
            cwd=git_root,
            capture_output=True,
            text=True,
            check=True,
        )
        time_str = result.stdout.strip()
        if not time_str:
            return None

        git_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S %z")
        return git_dt.astimezone(timezone.utc)
    except (subprocess.CalledProcessError, Exception):
        return None


def calculate_folder_total_size(folder_path: str) -> int:
    """计算文件夹内所有文件的大小总和（字节），跳过符号链接"""
    total = 0
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            if not os.path.islink(file_path):
                try:
                    total += os.path.getsize(file_path)
                except Exception:
                    continue
    return total


def get_folder_latest_mtime_utc(folder_path: str, git_root: Optional[str]) -> datetime:
    """获取文件夹最新更新时间（内部文件Git/系统时间的最大值，统一转为UTC）"""
    max_mtime = None
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.islink(file_path):
                continue

            git_mtime_utc = get_git_last_modified_utc(file_path, git_root)
            if git_mtime_utc:
                current_dt = git_mtime_utc
            else:
                # 修复：直接使用导入的 timezone 类
                current_dt = datetime.fromtimestamp(
                    os.path.getmtime(file_path),
                    tz=timezone.utc,  # 不再用 datetime.timezone
                )

            if not max_mtime or current_dt > max_mtime:
                max_mtime = current_dt

    if not max_mtime:
        # 修复：直接使用导入的 timezone 类
        max_mtime = datetime.fromtimestamp(
            os.path.getmtime(folder_path),
            tz=timezone.utc,  # 不再用 datetime.timezone
        )
    return max_mtime


def traverse_folder(
    target: str, parent_rel_path: str, git_root: Optional[str]
) -> List[Dict]:
    """递归遍历文件夹，生成文件/文件夹结构数据（时间统一为ISO UTC）"""
    structure = []
    target_abs = os.path.abspath(target)

    for entry in os.listdir(target_abs):
        entry_abs = os.path.join(target_abs, entry)
        entry_rel = os.path.join(parent_rel_path, entry) if parent_rel_path else entry

        # 处理文件
        if os.path.isfile(entry_abs) and not os.path.islink(entry_abs):
            size = os.path.getsize(entry_abs) if os.path.exists(entry_abs) else 0
            git_mtime_utc = get_git_last_modified_utc(entry_abs, git_root)
            if git_mtime_utc:
                last_modified = git_mtime_utc.isoformat()
            else:
                # 修复：直接使用导入的 timezone 类
                last_modified = datetime.fromtimestamp(
                    os.path.getmtime(entry_abs), tz=timezone.utc
                ).isoformat()

            structure.append(
                {
                    "type": "file",
                    "name": HASH_PATTERN.sub(".", entry),
                    "relative_path": entry_rel,
                    "size_bytes": size,
                    "last_modified_at": last_modified,
                }
            )

        # 处理文件夹（递归）
        elif os.path.isdir(entry_abs) and not os.path.islink(entry_abs):
            total_size = calculate_folder_total_size(entry_abs)
            latest_mtime_utc = get_folder_latest_mtime_utc(
                entry_abs, git_root
            ).isoformat()
            children = traverse_folder(entry_abs, entry_rel, git_root)

            structure.append(
                {
                    "type": "folder",
                    "name": entry,
                    "relative_path": entry_rel,
                    "total_size_bytes": total_size,
                    "last_modified_at": latest_mtime_utc,
                    "children": children,
                }
            )

    return structure


def main():
    if len(sys.argv) not in [2, 3]:
        print(
            "用法：python folder_struct_utc_json_fixed.py <目标文件夹路径> [输出JSON路径]"
        )
        print(
            "示例：python folder_struct_utc_json_fixed.py ./my_project ./struct_utc.json"
        )
        sys.exit(1)

    target_folder = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) == 3 else "folder_structure_utc.json"

    if not os.path.isdir(target_folder):
        print(f"错误：目标路径 '{target_folder}' 不是有效文件夹", file=sys.stderr)
        sys.exit(1)

    git_root = get_git_root(target_folder)
    print(
        f"Git仓库状态：{'已检测到（时间自动转为UTC）' if git_root else '未检测到（使用文件系统UTC时间）'}"
    )

    print(f"正在遍历文件夹：{os.path.abspath(target_folder)}")
    struct_data = traverse_folder(target_folder, "", git_root)
    for item in struct_data:
        if item.get("relative_path") == output_path:
            item["last_modified_at"] = datetime.now(timezone.utc).isoformat()
            break

    result = {
        "target_folder": target_folder,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "files": struct_data,
    }

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"成功生成UTC时间格式的JSON：{os.path.abspath(output_path)}")
    except Exception as e:
        print(f"写入文件失败：{str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

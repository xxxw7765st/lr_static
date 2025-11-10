import hashlib
import os
import re

BASE36_CHARS = "0123456789abcdefghijklmnopqrstuvwxyz"
HASH_PATTERN = re.compile(r"\._\.M[0-9a-z]+\._\.")


def calc_md5(file_path, chunk=4096):
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk_data := f.read(chunk):
            md5.update(chunk_data)
    num = int.from_bytes(md5.digest(), byteorder="big")
    result = []
    while num > 0:
        num, rem = divmod(num, 36)
        result.append(BASE36_CHARS[rem])
    return "".join(reversed(result))


def process_files(folder, hash_len=16):
    """递归重命名：高效处理批量文件"""
    for root, _, files in os.walk(folder):
        for file in files:
            if file.startswith(".") or HASH_PATTERN.search(file):
                # 隐藏/已hash
                continue

            file_path = os.path.join(root, file)
            name, ext = os.path.splitext(file)
            new_name = (
                f"{name}._.{calc_md5(file_path).zfill(hash_len)[:hash_len]}._.{ext.strip('.')}"
            )
            new_path = os.path.join(root, new_name)

            try:
                os.rename(file_path, new_path)
                print(f"✅ {file} → {new_name}")
            except Exception as e:
                print(f"❌ {file} 失败：{str(e)}")


# 执行
if __name__ == "__main__":
    TARGET_FOLDER = r"./static/asset/"
    HASH_LENGTH = 16
    process_files(TARGET_FOLDER, HASH_LENGTH)

#!/usr/bin/env python3
"""
X-AnyLabeling 数据集管理工具

功能：
1. 从导出目录导入/移动文件到 images/[精灵]/labels/[精灵]
2. 自动维护 classes.txt（所有类别名称）
3. 自动维护 dataset.yaml（训练/验证路径）
4. 支持查看状态、添加/删除精灵、生成配置
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set
import yaml


class SpriteDatasetManager:
    """精灵数据集管理器"""

    def __init__(self, data_root: str = None):
        if data_root is None:
            # 默认使用脚本所在目录的父目录（即项目根目录）
            self.data_root = Path(__file__).parent.parent
        else:
            self.data_root = Path(data_root)
        self.images_dir = self.data_root / "data" / "images"
        self.labels_dir = self.data_root / "data" / "labels"
        self.classes_file = self.data_root / "data" / "classes.txt"
        self.dataset_file = self.data_root / "data" / "dataset.yaml"
        self.export_dir = self.data_root / "data" / "X-AnyLabeling"

        # 确保基础目录存在
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.labels_dir.mkdir(parents=True, exist_ok=True)

    # ========== 读取操作 ==========

    def get_all_sprites(self) -> List[str]:
        """获取所有精灵类型文件夹名"""
        sprites = []

        if self.images_dir.exists():
            for item in self.images_dir.iterdir():
                if item.is_dir():
                    sprites.append(item.name)

        return sorted(sprites)

    def get_sprite_files(self, sprite_name: str) -> Dict[str, int]:
        """获取指定精灵的文件统计"""
        img_dir = self.images_dir / sprite_name
        label_dir = self.labels_dir / sprite_name

        img_count = sum(1 for _ in img_dir.glob("*") if _.suffix.lower() in ['.jpg', '.jpeg', '.png'])
        label_count = sum(1 for _ in label_dir.glob("*.txt"))

        return {
            "name": sprite_name,
            "images": img_count,
            "labels": label_count,
            "complete": img_count == label_count and img_count > 0
        }

    def parse_sprite_name(self, filename: str) -> str:
        """智能解析精灵名称

        支持多种命名模式：
        - 奇丽家族-奇丽叶00000.jpg -> 奇丽家族-奇丽叶
        - pet_001.jpg -> pet
        - sprite-abc-123.jpg -> sprite-abc
        - 任意名称+数字.jpg -> 去掉尾部数字
        """
        # 去掉扩展名
        name = Path(filename).stem

        # 模式1：处理中文命名（如：奇丽家族-奇丽叶00000）
        chinese_match = re.match(r'^([^\d]+)', name)
        if chinese_match:
            sprite_name = chinese_match.group(1)
            # 去掉末尾可能的连接符
            sprite_name = sprite_name.rstrip('-_')
            if sprite_name:
                return sprite_name

        # 模式2：处理下划线分隔（如：pet_001）
        if '_' in name:
            return name.split('_')[0]

        # 模式3：处理连字符分隔（如：sprite-abc-123）
        if '-' in name:
            parts = name.split('-')
            # 如果最后一部分全是数字，去掉它
            if parts[-1].isdigit():
                parts = parts[:-1]
            return '-'.join(parts)

        # 默认：返回原始名称
        return name

    def extract_class_ids_from_label(self, label_file: Path) -> Set[int]:
        """从标注文件中提取所有的 class_id"""
        if not label_file.exists():
            return set()

        class_ids = set()
        with open(label_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) >= 1:
                        try:
                            class_id = int(parts[0])
                            class_ids.add(class_id)
                        except ValueError:
                            pass

        return class_ids

    def scan_export_dir(self, export_dir: str) -> Dict[str, List[tuple]]:
        """扫描导出目录，找出未处理的 img+txt 对"""

        source = Path(export_dir)

        if not source.exists():
            return {"error": f"导出目录不存在：{source}"}

        image_extensions = ['.jpg', '.jpeg', '.png']
        unpaired_images = {}

        for ext in image_extensions:
            for img_file in source.glob(f"*{ext}"):
                txt_file = img_file.with_suffix('.txt')

                # 智能解析精灵名称
                sprite_name = self.parse_sprite_name(img_file.name)

                # 提取 class_id 信息
                class_ids = self.extract_class_ids_from_label(txt_file)

                key = sprite_name
                if key not in unpaired_images:
                    unpaired_images[key] = []

                if txt_file.exists():
                    unpaired_images[key].append((img_file, txt_file, class_ids))
                else:
                    print(f"[警告] {img_file.name} 没有对应 .txt 文件")

        return unpaired_images

    def read_classes(self) -> List[str]:
        """读取 classes.txt"""
        if not self.classes_file.exists():
            return []

        with open(self.classes_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]

    def read_dataset_config(self) -> dict:
        """读取 dataset.yaml 配置"""
        if not self.dataset_file.exists():
            return None

        with open(self.dataset_file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    # ========== 写入操作 ==========

    def move_files_to_dataset(self, sprite_name: str, files: list):
        """移动文件到数据集目录"""

        img_target = self.images_dir / sprite_name
        label_target = self.labels_dir / sprite_name

        img_target.mkdir(parents=True, exist_ok=True)
        label_target.mkdir(parents=True, exist_ok=True)

        for file_entry in files:
            # 支持新旧两种格式
            if len(file_entry) == 3:
                img_file, txt_file, _ = file_entry
            else:
                img_file, txt_file = file_entry

            # 移动图片
            shutil.move(str(img_file), img_target / img_file.name)
            # 移动标注
            shutil.move(str(txt_file), label_target / txt_file.name)

    def update_classes(self, sprite_name: str, class_name: str):
        """更新 classes.txt"""

        current_classes = self.read_classes()

        if class_name not in current_classes:
            current_classes.append(class_name)

        with open(self.classes_file, 'w', encoding='utf-8') as f:
            for cls in current_classes:
                f.write(f"{cls}\n")

    def update_classes_from_labels(self, files: list):
        """根据标注文件更新 classes.txt

        如果发现新的 class_id，会提示用户输入对应的类名
        """
        current_classes = self.read_classes()
        max_id = len(current_classes)

        # 收集所有出现的 class_id
        all_class_ids = set()
        for file_entry in files:
            if len(file_entry) >= 3:
                all_class_ids.update(file_entry[2])

        # 检查是否有新的 class_id
        new_ids = [cid for cid in all_class_ids if cid >= max_id]

        if new_ids:
            print(f"\n检测到新的 class_id: {new_ids}")
            print("请为每个新 class_id 输入对应的类名:")

            # 扩展 classes 列表
            classes_to_add = [''] * (max(new_ids) + 1 - len(current_classes))
            current_classes.extend(classes_to_add)

            for cid in sorted(new_ids):
                # 如果已有类名，显示出来
                if cid < len(current_classes) and current_classes[cid]:
                    print(f"  class_id {cid}: {current_classes[cid]} (已存在)")
                    continue

                class_name = input(f"  class_id {cid}: ").strip()
                if class_name:
                    current_classes[cid] = class_name

            # 写入文件
            with open(self.classes_file, 'w', encoding='utf-8') as f:
                for cls in current_classes:
                    if cls:  # 只写入非空类名
                        f.write(f"{cls}\n")

    def generate_dataset_yaml(self):
        """生成 dataset.yaml 配置文件"""

        sprites = self.get_all_sprites()

        # 读取 classes.txt
        classes = self.read_classes()

        with open(self.dataset_file, 'w', encoding='utf-8') as f:
            # 写入注释
            f.write("# YOLOv8 数据集配置\n")
            f.write("# train/val 按真实文件夹结构\n")
            f.write("# names 按 classes.txt 顺序，class_id 即索引\n\n")
            f.write(f"path: .\n\n")
            f.write("train:\n")
            for sprite in sprites:
                f.write(f"  - images/{sprite}\n")
            f.write("\nval:\n")
            for sprite in sprites:
                f.write(f"  - images/{sprite}\n")
            f.write(f"\nnc: {len(classes)}\n\n")
            f.write("names:\n")
            for i, name in enumerate(classes):
                f.write(f"  {i}: {name}\n")

    # ========== 交互操作 ==========

    def import_from_export(self, export_dir: str, overwrite: bool = False):
        """从导出目录导入数据"""

        unpaired = self.scan_export_dir(export_dir)

        if "error" in unpaired:
            print(unpaired["error"])
            return

        if not unpaired:
            print("没有找到任何 img+txt 文件对")
            return

        print("\n检测到以下精灵的数据:")
        for sprite_name, files in unpaired.items():
            # 显示 class_id 信息
            all_ids = set()
            for file_entry in files:
                if len(file_entry) >= 3:
                    all_ids.update(file_entry[2])

            class_info = f" (class_id: {sorted(all_ids)})" if all_ids else ""
            print(f"  - {sprite_name}: {len(files)} 个 img+txt 对{class_info}")

        print("\n请输入精灵名称以导入数据（或输入 'all' 全部导入）:")
        choice = input("> ").strip()

        if choice == 'all':
            target_sprites = list(unpaired.keys())
        else:
            target_sprites = [choice]

        for sprite_name in target_sprites:
            if sprite_name not in unpaired:
                print(f"[错误] 未找到精灵: {sprite_name}")
                continue

            files = unpaired[sprite_name]
            total = len(files)

            # 预览文件和 class_id 信息
            print(f"\n准备导入 '{sprite_name}' ({total} 个文件对)")
            for file_entry in files[:3]:  # 预览前 3 个
                if len(file_entry) >= 3:
                    img_f, txt_f, ids = file_entry
                    id_str = f" [class_id: {sorted(ids)}]" if ids else ""
                else:
                    img_f, txt_f = file_entry
                    id_str = ""
                print(f"  {img_f.name}{id_str}")
            if total > 3:
                print(f"  ... 还有 {total - 3} 个")

            # 检查 classes.txt 中是否有标注文件里用到的 class_id
            classes = self.read_classes()
            all_ids = set()
            for file_entry in files:
                if len(file_entry) >= 3:
                    all_ids.update(file_entry[2])

            # 检查是否需要补充 classes.txt
            max_needed_id = max(all_ids) if all_ids else 0
            if max_needed_id >= len(classes):
                print(f"\n[警告] 标注文件使用了 class_id {max_needed_id}，但 classes.txt 只有 {len(classes)} 个类别")
                print("请先通过 [4] 添加新精灵 或 [7] 同步配置 来补充 classes.txt")
                print(f"跳过导入 '{sprite_name}'")
                continue

            confirm = input(f"\n将导入到 'images/{sprite_name}/' 文件夹，是否继续？(y/n): ").strip().lower()

            if confirm == 'y':
                # 移动文件到同名文件夹
                self.move_files_to_dataset(sprite_name, files)
                # 更新 dataset.yaml
                self.generate_dataset_yaml()
                print(f"[完成] 已导入 {sprite_name}")

    def add_new_sprite(self, sprite_name: str, class_name: str = None):
        """添加新精灵条目（仅创建目录）"""

        if class_name is None:
            class_name = sprite_name

        # 创建目录
        (self.images_dir / sprite_name).mkdir(parents=True, exist_ok=True)
        (self.labels_dir / sprite_name).mkdir(parents=True, exist_ok=True)

        # 更新 classes.txt
        self.update_classes(sprite_name, class_name)

        # 重新生成 dataset.yaml
        self.generate_dataset_yaml()

        print(f"[完成] 已添加精灵: {sprite_name} (类别: {class_name})")

    def remove_sprite(self, sprite_folder: str):
        """删除精灵及其数据"""

        img_dir = self.images_dir / sprite_folder
        label_dir = self.labels_dir / sprite_folder

        if not img_dir.exists():
            print(f"[错误] 文件夹不存在: {sprite_folder}")
            return

        print(f"\n将删除精灵 '{sprite_folder}' 的所有数据:")
        img_count = sum(1 for _ in img_dir.iterdir())
        label_count = sum(1 for _ in label_dir.iterdir())
        print(f"  图片: {img_count}")
        print(f"  标注: {label_count}")

        confirm = input("确认删除？(y/n): ").strip().lower()

        if confirm != 'y':
            print("取消")
            return

        # 递归删除目录
        shutil.rmtree(img_dir)
        shutil.rmtree(label_dir)

        # 重新生成 dataset.yaml（不需要手动删除 classes.txt，因为 classes 是按 class_id 索引的）
        self.generate_dataset_yaml()

        print(f"[完成] 已删除精灵: {sprite_folder}")

    def sync_classes_and_dataset(self):
        """同步 classes.txt 和 dataset.yaml，确保一致性"""

        # 读取当前配置
        classes = self.read_classes()
        sprites = self.get_all_sprites()

        print("\n=== 同步配置 ===")
        print(f"当前 classes.txt 中的类别: {classes}")
        print(f"当前文件夹: {sprites}")

        # 检查是否需要更新
        need_update = False

        # 如果有新文件夹但没有对应的类名，询问用户
        for sprite in sprites:
            if sprite not in classes:
                print(f"\n发现新文件夹 '{sprite}' 但不在 classes.txt 中")
                class_name = input(f"请输入对应的类名（回车使用文件夹名）: ").strip()
                if not class_name:
                    class_name = sprite

                classes.append(class_name)
                need_update = True

        # 重新生成配置文件
        if need_update:
            with open(self.classes_file, 'w', encoding='utf-8') as f:
                for cls in classes:
                    f.write(f"{cls}\n")
            print("\n[完成] 已更新 classes.txt")

        self.generate_dataset_yaml()
        print("[完成] 已同步 dataset.yaml")


def show_status(manager: SpriteDatasetManager):
    """显示数据集状态"""

    sprites = manager.get_all_sprites()

    print("\n" + "=" * 60)
    print("  数据集状态")
    print("=" * 60)

    if not sprites:
        print("\n当前还没有任何精灵数据 (没有图片文件夹)")
        return

    for sprite in sprites:
        stats = manager.get_sprite_files(sprite)
        status = "[完成]" if stats["complete"] else "[不完整]"
        print(f"\n{status} {stats['name']}")
        print(f"    图片: {stats['images']}")
        print(f"    标注: {stats['labels']}")

    # 显示 classes.txt
    classes = manager.read_classes()
    print(f"\n--- classes.txt ({len(classes)} 个类别) ---")
    for i, cls in enumerate(classes):
        print(f"  {i}: {cls}")

    # 显示 dataset.yaml 摘要
    config = manager.read_dataset_config()
    if config:
        print(f"\n--- dataset.yaml ---")
        print(f"  训练路径: {len(config.get('train', []))} 个")
        print(f"  类别数(nc): {config.get('nc', 0)}")


def main_menu():
    """主菜单"""

    manager = SpriteDatasetManager()

    while True:
        print("\n" + "=" * 50)
        print("  X-AnyLabeling 数据集管理工具")
        print("=" * 50)
        print("\n[1] 查看所有精灵状态")
        print("[2] 从 X-AnyLabeling 导出目录导入")
        print("[3] 智能导入（自动检测并导入所有数据）")
        print("[4] 添加新精灵（仅创建目录和配置）")
        print("[5] 删除精灵")
        print("[6] 重新生成 dataset.yaml")
        print("[7] 同步 classes.txt 和 dataset.yaml")
        print("[8] 显示当前配置")
        print("[0] 退出")

        choice = input("\n请选择操作：").strip()

        if choice == "1":
            show_status(manager)

        elif choice == "2":
            export_dir = input(f"导出目录 (默认: {manager.export_dir}): ").strip()
            if not export_dir:
                export_dir = str(manager.export_dir)
            manager.import_from_export(export_dir)

        elif choice == "3":
            # 智能导入：自动检测并导入所有数据
            print("\n开始智能导入...")
            export_dir = str(manager.export_dir)
            unpaired = manager.scan_export_dir(export_dir)

            if "error" in unpaired:
                print(unpaired["error"])
            elif not unpaired:
                print("没有找到需要导入的数据")
            else:
                print(f"发现 {len(unpaired)} 种精灵的数据，将自动导入...")
                manager.import_from_export(export_dir)
                print("\n智能导入完成!")

        elif choice == "4":
            sprite_name = input("精灵文件夹名: ").strip()
            class_name = input("类别名称 (回车同文件夹名): ").strip() or sprite_name
            manager.add_new_sprite(sprite_name, class_name)

        elif choice == "5":
            sprites = manager.get_all_sprites()
            if not sprites:
                print("没有可删除的精灵")
                continue

            print("\n可选精灵:")
            for i, s in enumerate(sprites):
                print(f"  [{i+1}] {s}")

            idx = input("选择要删除的精灵编号: ").strip()
            try:
                idx = int(idx) - 1
                if 0 <= idx < len(sprites):
                    manager.remove_sprite(sprites[idx])
                else:
                    print("无效编号")
            except:
                print("无效输入")

        elif choice == "6":
            manager.generate_dataset_yaml()
            print("[完成] 已重新生成 dataset.yaml")

        elif choice == "7":
            manager.sync_classes_and_dataset()

        elif choice == "8":
            config = manager.read_dataset_config()
            classes = manager.read_classes()

            print("\n--- 配置文件路径 ---")
            print(f"classes.txt: {manager.classes_file}")
            print(f"dataset.yaml: {manager.dataset_file}")
            print(f"images目录: {manager.images_dir}")
            print(f"labels目录: {manager.labels_dir}")
            print(f"导出目录: {manager.export_dir}")

            print("\n--- classes.txt ---")
            if classes:
                for i, cls in enumerate(classes):
                    print(f"{i}: {cls}")
            else:
                print("(空)")

            print("\n--- dataset.yaml ---")
            if config:
                with open(manager.dataset_file, 'r', encoding='utf-8') as f:
                    print(f.read())
            else:
                print("未配置")

        elif choice == "0":
            print("退出")
            break

        else:
            print("无效选择")


if __name__ == "__main__":
    main_menu()

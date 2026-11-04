"""
CodeSearchNet 数据下载与预处理脚本

功能：
1. 从 HuggingFace Hub 下载 CodeSearchNet 数据集
2. 提取 (code, docstring) 配对数据
3. 清洗过滤（去重、长度过滤、质量过滤）
4. 生成训练/验证/测试集 JSONL 文件

数据来源:
    CodeSearchNet (Husain et al., 2019)
    https://github.com/github/CodeSearchNet
    HuggingFace: https://huggingface.co/datasets/code_search_net

用法：
    python prepare_data.py --config ../configs/train_config.yaml
    python prepare_data.py --languages python java --output_dir ../data
"""
import os
import json
import hashlib
import argparse
import re
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# CodeSearchNet 语言到文件扩展名的映射
LANG_EXTENSIONS = {
    "python": ".py",
    "java": ".java",
    "go": ".go",
    "php": ".php",
    "ruby": ".rb",
    "javascript": ".js",
}


def load_config(config_path: str) -> dict:
    """加载训练配置"""
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        logger.warning("PyYAML未安装，使用默认配置")
        return {}


def clean_docstring(docstring: str) -> str:
    """
    清洗文档字符串
    - 去除首尾引号
    - 去除多余空白
    - 去除特殊字符
    """
    if not docstring:
        return ""

    # 去除Python docstring的引号
    docstring = re.sub(r'^("""|\'\'\'|"""|\'\'\')', '', docstring.strip())
    docstring = re.sub(r'("""|\'\'\'|"""|\'\'\')$', '', docstring.strip())

    # 去除Java/C++ 块注释标记
    docstring = re.sub(r'^/\*\*?\s*', '', docstring)
    docstring = re.sub(r'\s*\*/$', '', docstring)
    docstring = re.sub(r'^\s*\*\s?', '', docstring, flags=re.MULTILINE)

    # 合并连续空白
    docstring = re.sub(r'\s+', ' ', docstring).strip()

    # 去除 @param/@return 等标记（保留内容）
    docstring = re.sub(r'@(?:param|return|throws?|see|since|version)\s*', '', docstring)

    return docstring


def clean_code(code: str, language: str) -> str:
    """
    清洗代码
    - 去除注释（避免代码中的注释干扰训练）
    - 标准化空白
    """
    if language == "python":
        # 去除单行注释
        code = re.sub(r'#[^\n]*', '', code)
        # 去除多行字符串（docstring）
        code = re.sub(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', '', code)
    elif language in ("java", "go", "php", "javascript"):
        # 去除单行注释
        code = re.sub(r'//[^\n]*', '', code)
        # 去除多行注释
        code = re.sub(r'/\*[\s\S]*?\*/', '', code)
    elif language == "ruby":
        code = re.sub(r'#[^\n]*', '', code)
        code = re.sub(r'=begin[\s\S]*?=end', '', code)

    # 标准化空白：多个空行合并为一个
    code = re.sub(r'\n{3,}', '\n\n', code)
    # 去除行尾空白
    code = '\n'.join(line.rstrip() for line in code.split('\n'))

    return code.strip()


def extract_functions_with_docstrings(
    code: str, language: str
) -> List[Tuple[str, str]]:
    """
    从源代码中提取函数及其文档字符串
    返回: [(函数代码, 文档字符串), ...]
    """
    pairs = []

    if language == "python":
        pairs.extend(_extract_python_functions(code))
    elif language == "java":
        pairs.extend(_extract_java_functions(code))
    else:
        # 通用回退：将整个文件作为一个样本
        if len(code) > 50:
            pairs.append((code, ""))

    return pairs


def _extract_python_functions(code: str) -> List[Tuple[str, str]]:
    """提取Python函数及其docstring"""
    pairs = []
    try:
        import ast
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                docstring = ast.get_docstring(node)
                if docstring:
                    # 获取函数源码
                    start = node.lineno - 1
                    end = getattr(node, 'end_lineno', node.lineno)
                    func_lines = code.split('\n')[start:end]
                    func_code = '\n'.join(func_lines)
                    pairs.append((func_code, docstring))
    except (SyntaxError, Exception):
        pass
    return pairs


def _extract_java_functions(code: str) -> List[Tuple[str, str]]:
    """提取Java方法及其Javadoc（正则方式）"""
    pairs = []

    # 匹配 Javadoc + 方法签名
    pattern = re.compile(
        r'/\*\*([\s\S]*?)\*/\s*'
        r'(?:(?:public|private|protected|static|final|native|synchronized|abstract|transient)+\s+)*'
        r'(?:[\w<>\[\]]+)\s+(\w+)\s*\([^)]*\)',
        re.MULTILINE
    )

    for match in pattern.finditer(code):
        docstring = clean_docstring(match.group(1))
        if docstring and len(docstring) > 10:
            # 提取方法体（简化处理）
            method_start = match.end()
            brace_count = 0
            method_end = method_start
            for i in range(method_start, min(method_start + 2000, len(code))):
                if code[i] == '{':
                    brace_count += 1
                elif code[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        method_end = i + 1
                        break
            method_code = code[match.start():method_end] if method_end > method_start else match.group(0)
            pairs.append((method_code, docstring))

    return pairs


def download_codesearchnet(
    languages: List[str],
    output_dir: str,
    use_hf_dataset: bool = True,
) -> str:
    """
    下载 CodeSearchNet 数据集

    方式1（推荐）：通过 HuggingFace datasets 库下载
    方式2：通过 GitHub release 下载原始 tar.gz
    """
    os.makedirs(output_dir, exist_ok=True)

    if use_hf_dataset:
        logger.info("通过 HuggingFace datasets 下载 CodeSearchNet...")
        try:
            from datasets import load_dataset

            for lang in languages:
                logger.info(f"下载 {lang} 数据...")
                try:
                    ds = load_dataset("code_search_net", lang, trust_remote_code=True)
                    save_path = os.path.join(output_dir, f"{lang}_dataset")
                    ds.save_to_disk(save_path)
                    logger.info(f"  {lang}: 训练集 {len(ds.get('train', []))} 条, "
                                f"验证集 {len(ds.get('validation', []))} 条, "
                                f"测试集 {len(ds.get('test', []))} 条")
                except Exception as e:
                    logger.warning(f"  {lang} 下载失败: {e}")
                    continue

            return output_dir

        except ImportError:
            logger.error("需要安装 datasets 库: pip install datasets")
            raise

    else:
        logger.info("通过 GitHub 下载 CodeSearchNet 原始数据...")
        import urllib.request
        import tarfile

        base_url = "https://s3.amazonaws.com/code-search-net/Archive"
        for lang in languages:
            url = f"{base_url}/{lang}.tar.gz"
            tar_path = os.path.join(output_dir, f"{lang}.tar.gz")
            if not os.path.exists(tar_path):
                logger.info(f"下载 {url} ...")
                urllib.request.urlretrieve(url, tar_path)
                logger.info(f"解压 {tar_path} ...")
                with tarfile.open(tar_path, "r:gz") as tar:
                    tar.extractall(output_dir)
            else:
                logger.info(f"  {tar_path} 已存在，跳过")

        return output_dir


def process_split(
    data_path: str,
    languages: List[str],
    max_samples_per_lang: int,
    min_docstring_len: int,
    max_docstring_len: int,
    max_code_tokens: int,
    use_hf_dataset: bool = True,
) -> List[Dict[str, str]]:
    """
    处理数据集的一个split（train/valid/test）
    生成 (code, docstring) 配对列表
    """
    all_pairs = []
    seen_hashes = set()  # 去重

    if use_hf_dataset:
        from datasets import load_from_disk

        for lang in languages:
            lang_path = os.path.join(data_path, f"{lang}_dataset")
            if not os.path.exists(lang_path):
                logger.warning(f"  {lang} 数据不存在: {lang_path}")
                continue

            logger.info(f"处理 {lang} 数据...")
            ds = load_from_disk(lang_path)

            # 合并所有split
            count = 0
            for split_name in ds:
                for item in ds[split_name]:
                    if count >= max_samples_per_lang:
                        break

                    code = item.get("code", "")
                    docstring = item.get("docstring", "")

                    # 清洗
                    docstring = clean_docstring(docstring)
                    code = clean_code(code, lang)

                    # 过滤
                    if len(docstring) < min_docstring_len:
                        continue
                    if len(docstring) > max_docstring_len:
                        continue
                    if not code or len(code) < 20:
                        continue

                    # 去重
                    pair_hash = hashlib.md5(
                        (code[:200] + docstring[:100]).encode()
                    ).hexdigest()
                    if pair_hash in seen_hashes:
                        continue
                    seen_hashes.add(pair_hash)

                    all_pairs.append({
                        "code": code,
                        "docstring": docstring,
                        "language": lang,
                    })
                    count += 1

            logger.info(f"  {lang}: {count} 条有效配对")
    else:
        # 处理原始 jsonl.gz 文件
        import gzip
        import glob

        for lang in languages:
            jsonl_files = glob.glob(os.path.join(data_path, lang, f"*.jsonl.gz"))
            count = 0
            for fpath in jsonl_files:
                if count >= max_samples_per_lang:
                    break
                with gzip.open(fpath, 'rt', encoding='utf-8') as f:
                    for line in f:
                        if count >= max_samples_per_lang:
                            break
                        try:
                            item = json.loads(line)
                            code = item.get("code", "")
                            docstring = item.get("docstring", "")
                            docstring = clean_docstring(docstring)
                            code = clean_code(code, lang)

                            if len(docstring) < min_docstring_len:
                                continue
                            if not code:
                                continue

                            pair_hash = hashlib.md5(
                                (code[:200] + docstring[:100]).encode()
                            ).hexdigest()
                            if pair_hash in seen_hashes:
                                continue
                            seen_hashes.add(pair_hash)

                            all_pairs.append({
                                "code": code,
                                "docstring": docstring,
                                "language": lang,
                            })
                            count += 1
                        except json.JSONDecodeError:
                            continue

            logger.info(f"  {lang}: {count} 条有效配对")

    return all_pairs


def save_jsonl(pairs: List[Dict], output_path: str):
    """保存为 JSONL 格式"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    logger.info(f"已保存 {len(pairs)} 条到 {output_path}")


def create_demo_data(output_dir: str, num_train: int = 5000, num_valid: int = 500):
    """
    创建演示数据（用于在没有完整CodeSearchNet数据时测试训练流程）
    使用内置的Python标准库函数文档作为训练数据
    """
    logger.info("生成演示训练数据...")
    os.makedirs(output_dir, exist_ok=True)

    # 从Python标准库提取内置函数的文档
    demo_pairs = []

    # 内置函数文档
    builtin_docs = [
        ("def len(obj):\n    return obj.__len__()", "Return the number of items in a container."),
        ("def abs(x):\n    return x.__abs__()", "Return the absolute value of the argument."),
        ("def all(iterable):\n    for element in iterable:\n        if not element:\n            return False\n    return True", "Return True if all elements of the iterable are true."),
        ("def any(iterable):\n    for element in iterable:\n        if element:\n            return True\n    return False", "Return True if any element of the iterable is true."),
        ("def bin(number):\n    return number.__bin__()", "Return the binary representation of an integer."),
        ("def chr(i):\n    return str(i)", "Return a Unicode string of one character with the given ordinal."),
        ("def dict(**kwargs):\n    pass", "Create a new dictionary mapping keys to values."),
        ("def enumerate(iterable, start=0):\n    pass", "Return an enumerate object that yields pairs of index and value."),
        ("def filter(function, iterable):\n    pass", "Construct an iterator from elements of iterable for which function returns true."),
        ("def format(value, format_spec=''):\n    return value.__format__(format_spec)", "Format a value using the specified format specification."),
        ("def getattr(obj, name, default=None):\n    return obj.__getattribute__(name)", "Return the value of the named attribute of object."),
        ("def hasattr(obj, name):\n    try:\n        getattr(obj, name)\n        return True\n    except AttributeError:\n        return False", "Return whether the object has an attribute with the given name."),
        ("def hash(obj):\n    return obj.__hash__()", "Return the hash value of the object."),
        ("def hex(x):\n    return x.__hex__()", "Convert an integer number to a lowercase hexadecimal string."),
        ("def id(obj):\n    return obj.__id__()", "Return the identity of an object (its memory address)."),
        ("def isinstance(obj, classinfo):\n    return type(obj) in classinfo", "Return whether an object is an instance of a class or its subclass."),
        ("def map(func, *iterables):\n    pass", "Apply function to every item of iterable and return a list of results."),
        ("def max(*args, key=None):\n    pass", "Return the largest item in an iterable or the largest of two or more arguments."),
        ("def min(*args, key=None):\n    pass", "Return the smallest item in an iterable or the smallest of two or more arguments."),
        ("def open(file, mode='r'):\n    pass", "Open file and return a corresponding file object."),
        ("def print(*objects, sep=' ', end='\\n'):\n    pass", "Print objects to the text stream file, separated by sep and followed by end."),
        ("def range(start, stop=None, step=1):\n    pass", "Return an immutable sequence of numbers from start to stop."),
        ("def reversed(seq):\n    return seq[::-1]", "Return a reverse iterator."),
        ("def round(number, ndigits=None):\n    pass", "Round a number to a given precision in decimal digits."),
        ("def sorted(iterable, key=None, reverse=False):\n    pass", "Return a new sorted list from the items in iterable."),
        ("def sum(iterable, start=0):\n    pass", "Sum the items of iterable from left to right and return the total."),
        ("def zip(*iterables):\n    pass", "Iterate over several iterables in parallel, producing tuples with an item from each."),
    ]

    # 生成更多变体
    for code, doc in builtin_docs:
        demo_pairs.append({
            "code": code,
            "docstring": doc,
            "language": "python",
        })

    # 生成更多代码-注释对
    extra_pairs = [
        ("def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
         "Calculate the nth Fibonacci number using recursive approach."),
        ("def binary_search(arr, target):\n    lo, hi = 0, len(arr) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return -1",
         "Search for target in a sorted array using binary search algorithm. Returns the index of target or -1 if not found."),
        ("def quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    return quicksort(left) + middle + quicksort(right)",
         "Sort an array using the quicksort algorithm with median-of-three pivot selection."),
        ("class Stack:\n    def __init__(self):\n        self.items = []\n    def push(self, item):\n        self.items.append(item)\n    def pop(self):\n        return self.items.pop()\n    def peek(self):\n        return self.items[-1]\n    def is_empty(self):\n        return len(self.items) == 0",
         "A stack data structure implementation supporting push, pop, peek operations with LIFO ordering."),
        ("def merge_sort(arr):\n    if len(arr) <= 1:\n        return arr\n    mid = len(arr) // 2\n    left = merge_sort(arr[:mid])\n    right = merge_sort(arr[mid:])\n    return merge(left, right)",
         "Implement merge sort algorithm by recursively dividing the array and merging sorted halves."),
        ("def bfs(graph, start):\n    visited = set()\n    queue = [start]\n    result = []\n    while queue:\n        node = queue.pop(0)\n        if node not in visited:\n            visited.add(node)\n            result.append(node)\n            queue.extend(graph[node])\n    return result",
         "Perform breadth-first search traversal on a graph starting from the given node."),
        ("def dfs(graph, start, visited=None):\n    if visited is None:\n        visited = set()\n    visited.add(start)\n    for neighbor in graph[start]:\n        if neighbor not in visited:\n            dfs(graph, neighbor, visited)\n    return visited",
         "Perform depth-first search traversal on a graph starting from the given node using recursion."),
        ("def dijkstra(graph, start):\n    distances = {node: float('inf') for node in graph}\n    distances[start] = 0\n    unvisited = set(graph.keys())\n    while unvisited:\n        min_node = min(unvisited, key=lambda n: distances[n])\n        unvisited.remove(min_node)\n        for neighbor, weight in graph[min_node].items():\n            if distances[min_node] + weight < distances[neighbor]:\n                distances[neighbor] = distances[min_node] + weight\n    return distances",
         "Find shortest distances from start node to all other nodes using Dijkstra's algorithm."),
        ("def lru_cache(maxsize=128):\n    cache = {}\n    def decorator(func):\n        def wrapper(*args):\n            if args in cache:\n                return cache[args]\n            result = func(*args)\n            cache[args] = result\n            if len(cache) > maxsize:\n                oldest = next(iter(cache))\n                del cache[oldest]\n            return result\n        return wrapper\n    return decorator",
         "Implement a least-recently-used cache decorator that stores up to maxsize function results."),
        ("class LinkedList:\n    class Node:\n        def __init__(self, val):\n            self.val = val\n            self.next = None\n    def __init__(self):\n        self.head = None\n        self.size = 0\n    def append(self, val):\n        new_node = self.Node(val)\n        if not self.head:\n            self.head = new_node\n        else:\n            curr = self.head\n            while curr.next:\n                curr = curr.next\n            curr.next = new_node\n        self.size += 1",
         "A singly linked list implementation with append operation and size tracking."),
    ]

    demo_pairs.extend([
        {"code": c, "docstring": d, "language": "python"}
        for c, d in extra_pairs
    ])

    # 扩展数据（通过改写和组合）
    java_pairs = [
        ("public int factorial(int n) {\n    if (n <= 1) return 1;\n    return n * factorial(n - 1);\n}",
         "Calculate factorial of n recursively. Returns 1 for n<=1, otherwise n * factorial(n-1)."),
        ("public boolean isPrime(int n) {\n    if (n < 2) return false;\n    for (int i = 2; i * i <= n; i++) {\n        if (n % i == 0) return false;\n    }\n    return true;\n}",
         "Check if a number is prime by testing divisibility up to its square root."),
        ("public int[] bubbleSort(int[] arr) {\n    int n = arr.length;\n    for (int i = 0; i < n - 1; i++) {\n        for (int j = 0; j < n - i - 1; j++) {\n            if (arr[j] > arr[j + 1]) {\n                int temp = arr[j];\n                arr[j] = arr[j + 1];\n                arr[j + 1] = temp;\n            }\n        }\n    }\n    return arr;\n}",
         "Sort an array using bubble sort algorithm with adjacent element swapping."),
        ("public String reverse(String str) {\n    StringBuilder sb = new StringBuilder();\n    for (int i = str.length() - 1; i >= 0; i--) {\n        sb.append(str.charAt(i));\n    }\n    return sb.toString();\n}",
         "Reverse a string by iterating backwards and building a new string with StringBuilder."),
        ("public int fibonacci(int n) {\n    if (n <= 1) return n;\n    int a = 0, b = 1;\n    for (int i = 2; i <= n; i++) {\n        int temp = a + b;\n        a = b;\n        b = temp;\n    }\n    return b;\n}",
         "Calculate the nth Fibonacci number iteratively using two variables to track previous values."),
    ]

    demo_pairs.extend([
        {"code": c, "docstring": d, "language": "java"}
        for c, d in java_pairs
    ])

    # 拆分为 train/valid/test (80/10/10)
    import random
    random.shuffle(demo_pairs)
    n = len(demo_pairs)
    train_end = int(n * 0.8)
    valid_end = int(n * 0.9)

    train_pairs = demo_pairs[:train_end]
    valid_pairs = demo_pairs[train_end:valid_end]
    test_pairs = demo_pairs[valid_end:]

    # 如果数据不够，复制扩充
    while len(train_pairs) < num_train:
        train_pairs.extend(demo_pairs[:min(len(demo_pairs), num_train - len(train_pairs))])
    while len(valid_pairs) < num_valid:
        valid_pairs.extend(demo_pairs[:min(len(demo_pairs), num_valid - len(valid_pairs))])

    train_pairs = train_pairs[:num_train]
    valid_pairs = valid_pairs[:num_valid]
    test_pairs = test_pairs[:max(num_valid // 2, 100)]

    save_jsonl(train_pairs, os.path.join(output_dir, "train_pairs.jsonl"))
    save_jsonl(valid_pairs, os.path.join(output_dir, "valid_pairs.jsonl"))
    save_jsonl(test_pairs, os.path.join(output_dir, "test_pairs.jsonl"))

    logger.info(f"演示数据生成完成: train={len(train_pairs)}, valid={len(valid_pairs)}, test={len(test_pairs)}")
    return output_dir


def main():
    parser = argparse.ArgumentParser(description="CodeSearchNet 数据准备脚本")
    parser.add_argument("--config", type=str, default="../configs/train_config.yaml",
                        help="训练配置文件路径")
    parser.add_argument("--output_dir", type=str, default="../data",
                        help="输出目录")
    parser.add_argument("--languages", nargs="+", default=["python", "java"],
                        help="要处理的编程语言列表")
    parser.add_argument("--source", choices=["huggingface", "github", "demo"],
                        default="demo",
                        help="数据来源: huggingface(HuggingFace datasets), github(原始tar.gz), demo(内置演示数据)")
    parser.add_argument("--max_samples", type=int, default=100000,
                        help="每种语言最大采样数")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config) if os.path.exists(args.config) else {}
    data_config = config.get("data", {})

    languages = args.languages or data_config.get("languages", ["python", "java"])
    output_dir = args.output_dir or data_config.get("raw_data_dir", "../data")
    max_samples = args.max_samples or data_config.get("max_samples_per_lang", 100000)
    min_doc_len = data_config.get("min_docstring_len", 10)
    max_doc_len = data_config.get("max_docstring_len", 512)
    max_code_tokens = data_config.get("max_code_tokens", 384)

    logger.info(f"=== CodeSearchNet 数据准备 ===")
    logger.info(f"  语言: {languages}")
    logger.info(f"  输出目录: {output_dir}")
    logger.info(f"  数据来源: {args.source}")

    if args.source == "demo":
        # 使用内置演示数据
        create_demo_data(output_dir, num_train=max_samples, num_valid=max_samples // 10)
    else:
        # 下载 CodeSearchNet
        raw_dir = download_codesearchnet(languages, output_dir, use_hf_dataset=(args.source == "huggingface"))

        # 处理各个split
        logger.info("\n处理训练集...")
        train_pairs = process_split(
            raw_dir, languages, max_samples, min_doc_len, max_doc_len, max_code_tokens,
            use_hf_dataset=(args.source == "huggingface")
        )
        save_jsonl(train_pairs, os.path.join(output_dir, "train_pairs.jsonl"))

        logger.info("\n处理验证集...")
        valid_pairs = process_split(
            raw_dir, languages, max_samples // 10, min_doc_len, max_doc_len, max_code_tokens,
            use_hf_dataset=(args.source == "huggingface")
        )
        save_jsonl(valid_pairs, os.path.join(output_dir, "valid_pairs.jsonl"))

        logger.info("\n处理测试集...")
        test_pairs = process_split(
            raw_dir, languages, max_samples // 10, min_doc_len, max_doc_len, max_code_tokens,
            use_hf_dataset=(args.source == "huggingface")
        )
        save_jsonl(test_pairs, os.path.join(output_dir, "test_pairs.jsonl"))

    logger.info("\n=== 数据准备完成 ===")


if __name__ == "__main__":
    main()

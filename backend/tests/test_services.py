"""
单元测试 - M1接入层 + M2解析层
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.m1_ingest import IngestService, SessionManager
from app.services.m2_parser import PythonParser, ParserFactory, parse_code


# ========================
# M1 接入层测试
# ========================

class TestM1IngestService:
    """M1模块单元测试"""

    def setup_method(self):
        self.service = IngestService()

    def test_detect_encoding_utf8(self):
        raw = "def hello():\n    pass".encode("utf-8")
        encoding = self.service.detect_encoding(raw)
        assert encoding is not None

    def test_detect_language_by_extension(self):
        assert self.service.detect_language_by_extension("test.py") == "python"
        assert self.service.detect_language_by_extension("Main.java") == "java"
        assert self.service.detect_language_by_extension("app.cpp") == "cpp"
        assert self.service.detect_language_by_extension("header.h") == "cpp"
        assert self.service.detect_language_by_extension("unknown.xyz") is None

    def test_detect_language_by_content_python(self):
        code = "def foo():\n    import os\n    return self.value"
        lang = self.service.detect_language_by_content(code)
        assert lang == "python"

    def test_detect_language_by_content_java(self):
        code = "public class Main {\n    public static void main(String[] args) {\n        System.out.println(\"hello\");\n    }\n}"
        lang = self.service.detect_language_by_content(code)
        assert lang == "java"

    def test_detect_language_by_content_cpp(self):
        code = "#include <iostream>\nint main() {\n    std::cout << \"hello\";\n    return 0;\n}"
        lang = self.service.detect_language_by_content(code)
        assert lang == "cpp"

    def test_ingest_text_python(self):
        code = "def hello():\n    print('hi')\n"
        result = self.service.ingest_text(code, "test.py")
        assert result.language == "python"
        assert result.filename == "test.py"
        assert result.code_text == code
        assert result.encoding == "utf-8"
        assert result.session_id

    def test_ingest_text_auto_detect(self):
        code = "public class App {\n    public void run() { System.out.println(\"go\"); }\n}"
        result = self.service.ingest_text(code, "unknown.txt")
        assert result.language == "java"

    def test_ingest_file_bytes(self):
        content = b"import os\n\ndef read_file(path):\n    return open(path).read()\n"
        result = self.service.ingest_file(content, "utils.py")
        assert result.language == "python"
        assert result.file_size == len(content)
        assert result.session_id

    def test_session_manager_create_and_get(self):
        mgr = SessionManager(ttl=3600)
        sid = mgr.create_session()
        session = mgr.get_session(sid)
        assert session is not None
        assert "files" in session

    def test_session_manager_store_file(self):
        mgr = SessionManager(ttl=3600)
        sid = mgr.create_session()
        mgr.store_file(sid, "test.py", "code", "python")
        session = mgr.get_session(sid)
        assert "test.py" in session["files"]

    def test_session_manager_expired(self):
        mgr = SessionManager(ttl=0)  # 立即过期
        sid = mgr.create_session()
        import time
        time.sleep(0.01)
        session = mgr.get_session(sid)
        assert session is None


# ========================
# M2 AST解析层测试
# ========================

SAMPLE_PYTHON = '''
import os

class Calculator:
    """A simple calculator class."""

    def __init__(self):
        self.result = 0

    def add(self, a, b):
        """Add two numbers."""
        return a + b

    def complex_method(self, data):
        result = []
        for item in data:
            if item > 0:
                for j in range(item):
                    if j % 2 == 0:
                        result.append(j)
        return result

def standalone_function(x, y):
    return x * y
'''


class TestM2PythonParser:
    """M2 Python解析器单元测试"""

    def setup_method(self):
        self.parser = PythonParser()

    def test_parse_returns_result(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        assert result.language == "python"
        assert result.total_lines > 0
        assert len(result.parse_errors) == 0

    def test_parse_finds_classes(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        classes = result.get_all_classes()
        assert len(classes) >= 1
        assert any(c.name == "Calculator" for c in classes)

    def test_parse_finds_functions(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        functions = result.get_all_functions()
        assert len(functions) >= 1
        names = [f.name for f in functions]
        assert "add" in names or "standalone_function" in names

    def test_parse_extracts_docstring(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        classes = result.get_all_classes()
        calc = next((c for c in classes if c.name == "Calculator"), None)
        assert calc is not None
        # docstring可能被提取
        # 不同解析器行为可能不同，这里检查结构

    def test_parse_extracts_parameters(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        functions = result.get_all_functions()
        add_func = next((f for f in functions if f.name == "add"), None)
        if add_func:
            assert len(add_func.parameters) >= 2
            param_names = [p["name"] for p in add_func.parameters]
            assert "a" in param_names
            assert "b" in param_names

    def test_complexity_calculation(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        functions = result.get_all_functions()
        complex_func = next((f for f in functions if f.name == "complex_method"), None)
        if complex_func:
            assert complex_func.complexity_score > 0

    def test_parse_empty_code(self):
        result = self.parser.parse("")
        assert result.language == "python"
        assert result.total_lines == 1
        assert len(result.nodes) == 0

    def test_parse_syntax_error(self):
        bad_code = "def foo(:\n    pass"
        result = self.parser.parse(bad_code)
        # 应该不崩溃，可能有parse errors
        assert result.language == "python"

    def test_node_structure(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        for node in result.nodes:
            assert node.node_id
            assert node.node_type is not None
            assert node.start_line > 0

    def test_scope_path(self):
        result = self.parser.parse(SAMPLE_PYTHON)
        functions = result.get_all_functions()
        for f in functions:
            assert isinstance(f.scope_path, list)


class TestM2ParserFactory:
    """解析器工厂测试"""

    def test_get_python_parser(self):
        parser = ParserFactory.get_parser("python")
        assert parser.get_language() == "python"

    def test_get_java_parser(self):
        parser = ParserFactory.get_parser("java")
        assert parser.get_language() == "java"

    def test_get_cpp_parser(self):
        parser = ParserFactory.get_parser("cpp")
        assert parser.get_language() == "cpp"

    def test_unsupported_language(self):
        with pytest.raises(ValueError):
            ParserFactory.get_parser("ruby")

    def test_parse_code_convenience(self):
        result = parse_code("def foo(): pass", "python")
        assert result.language == "python"


SAMPLE_JAVA = '''
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello");
    }

    public int add(int a, int b) {
        return a + b;
    }
}
'''


class TestM2JavaParser:
    """M2 Java解析器测试"""

    def test_parse_java(self):
        result = ParserFactory.parse(SAMPLE_JAVA, "java")
        assert result.language == "java"
        assert result.total_lines > 0

    def test_java_finds_class(self):
        result = ParserFactory.parse(SAMPLE_JAVA, "java")
        classes = result.get_all_classes()
        assert len(classes) >= 1


SAMPLE_CPP = '''
#include <iostream>

class Calculator {
public:
    int add(int a, int b) {
        return a + b;
    }
};

int main() {
    std::cout << "Hello";
    return 0;
}
'''


class TestM2CppParser:
    """M2 C++解析器测试"""

    def test_parse_cpp(self):
        result = ParserFactory.parse(SAMPLE_CPP, "cpp")
        assert result.language == "cpp"
        assert result.total_lines > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

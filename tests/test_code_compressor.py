from extract.code.compressor import compress_code, MARKER


def test_python_function_body_is_stripped():
    code = "def add(a, b):\n    total = a + b\n    return total\n"
    result = compress_code(code, ".py")

    assert "def add(a, b):" in result
    assert MARKER.strip() in result
    assert "total = a + b" not in result
    assert "return total" not in result


def test_java_method_body_is_stripped_but_brace_lines_kept():
    code = (
        "class Foo {\n"
        "    int add(int a, int b) {\n"
        "        int total = a + b;\n"
        "        return total;\n"
        "    }\n"
        "}\n"
    )
    result = compress_code(code, ".java")

    assert "int add(int a, int b) {" in result
    assert "total = a + b" not in result
    # the closing brace of the method is kept, not swallowed by the marker
    assert "}" in result


def test_unsupported_extension_returns_none():
    assert compress_code("whatever content", ".xyz") is None


def test_function_with_no_body_content_is_left_alone():
    # a one-line function (body and signature on the same line has nothing to
    # elide) shouldn't produce a dangling marker
    code = "def noop(): pass\n"
    result = compress_code(code, ".py")
    assert "def noop(): pass" in result

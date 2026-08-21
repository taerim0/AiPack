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


def test_lua_function_body_is_stripped_but_end_kept():
    code = (
        "local function add(a, b)\n"
        "    local total = a + b\n"
        "    return total\n"
        "end\n"
    )
    result = compress_code(code, ".lua")

    assert "local function add(a, b)" in result
    assert MARKER.strip() in result
    assert "total = a + b" not in result
    # Lua's `end` isn't part of the body node at all (unlike a brace
    # language's `}`), so there's nothing to specially exclude -- it should
    # just survive untouched as its own line.
    assert "end" in result


def test_gdscript_function_body_is_stripped():
    code = (
        "func take_damage(amount: int) -> void:\n"
        "    var total = health - amount\n"
        "    health = total\n"
    )
    result = compress_code(code, ".gd")

    assert "func take_damage(amount: int) -> void:" in result
    assert MARKER.strip() in result
    assert "total = health - amount" not in result


def test_gdscript_constructor_body_is_stripped():
    # _init() parses as its own constructor_definition node type, distinct
    # from function_definition -- without both types in GDScript's
    # function_types, this would ship uncompressed while every sibling
    # method got body-stripped.
    code = (
        "func _init(x, y):\n"
        "    var total = x + y\n"
        "    print(total)\n"
    )
    result = compress_code(code, ".gd")

    assert "func _init(x, y):" in result
    assert MARKER.strip() in result
    assert "total = x + y" not in result


def test_unsupported_extension_returns_none():
    assert compress_code("whatever content", ".xyz") is None


def test_function_with_no_body_content_is_left_alone():
    # a one-line function (body and signature on the same line has nothing to
    # elide) shouldn't produce a dangling marker
    code = "def noop(): pass\n"
    result = compress_code(code, ".py")
    assert "def noop(): pass" in result

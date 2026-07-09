"""Language rules — определения для каждого языка.

Каждый язык определяет:
- function_types: типы узлов функций/методов (для замены тела)
- class_types: типы узлов классов
- import_types: типы узлов импортов (сохраняются)
- body_placeholder: чем заменяется тело функции
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageRules:
    """Правила скелетирования для языка."""

    function_types: tuple[str, ...]
    class_types: tuple[str, ...]
    import_types: tuple[str, ...]
    body_placeholder: str
    body_field: str = "body"


PYTHON_RULES = LanguageRules(
    function_types=("function_definition", "async_function_definition"),
    class_types=("class_definition",),
    import_types=("import_statement", "import_from_statement"),
    body_placeholder="...",
    body_field="body",
)

TYPESCRIPT_RULES = LanguageRules(
    function_types=(
        "function_declaration",
        "method_definition",
        "arrow_function",
        "function_expression",
        "generator_function_declaration",
    ),
    class_types=("class_declaration", "interface_declaration", "type_alias_declaration"),
    import_types=("import_statement",),
    body_placeholder="{}",
    body_field="body",
)

DART_RULES = LanguageRules(
    function_types=(
        "function_signature",
        "method_signature",
        "function_body",
        "constructor_signature",
    ),
    class_types=("class_definition", "mixin_declaration", "extension_declaration"),
    import_types=("import_specification",),
    body_placeholder="{}",
    body_field="body",
)

GO_RULES = LanguageRules(
    function_types=("function_declaration", "method_declaration"),
    class_types=("type_declaration",),
    import_types=("import_declaration",),
    body_placeholder="{}",
    body_field="body",
)

RUST_RULES = LanguageRules(
    function_types=("function_item",),
    class_types=("struct_item", "enum_item", "trait_item", "impl_item"),
    import_types=("use_declaration",),
    body_placeholder="{}",
    body_field="body",
)

JAVA_RULES = LanguageRules(
    function_types=("method_declaration", "constructor_declaration"),
    class_types=("class_declaration", "interface_declaration", "enum_declaration"),
    import_types=("import_declaration",),
    body_placeholder="{}",
    body_field="body",
)

CPP_RULES = LanguageRules(
    function_types=("function_definition",),
    class_types=("class_specifier", "struct_specifier", "union_specifier"),
    import_types=("preproc_include",),
    body_placeholder="{}",
    body_field="body",
)

LANGUAGE_RULES: dict[str, LanguageRules] = {
    "python": PYTHON_RULES,
    "typescript": TYPESCRIPT_RULES,
    "dart": DART_RULES,
    "go": GO_RULES,
    "rust": RUST_RULES,
    "java": JAVA_RULES,
    "cpp": CPP_RULES,
}

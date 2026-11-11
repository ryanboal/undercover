from backend.main import app

SCHEMA = app.openapi()
OPERATIONS = [
    (f"{method.upper()} {path}", operation)
    for path, methods in SCHEMA["paths"].items()
    for method, operation in methods.items()
]


def body_schema(operation):
    ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    return SCHEMA["components"]["schemas"][ref.split("/")[-1]]


def test_every_operation_has_an_operation_id_and_a_one_line_docstring():
    for name, operation in OPERATIONS:
        assert operation.get("operationId"), name
        description = operation.get("description", "")
        assert description, name
        assert "\n" not in description.strip(), name


def test_every_input_is_required():
    for name, operation in OPERATIONS:
        for parameter in operation.get("parameters", []):
            assert parameter["required"], f"{name} {parameter['name']}"
        if "requestBody" in operation:
            assert operation["requestBody"]["required"], name
            model = body_schema(operation)
            assert set(model["properties"]) == set(model["required"]), name

from dataclasses import dataclass, field
import html
import io
from typing import Any, Callable, get_args, get_origin
from flask import request
from werkzeug.datastructures.file_storage import FileStorage

import typer


def escape(s: Any):
    """Escape a string for HTML output purposes."""
    return html.escape(str(s))


@dataclass
class Params:
    name: str
    input_type: str | typer.models.ParamMeta = "text"
    validator: Callable[[str], Any] | None = None
    args: dict[str, str] = field(default_factory=dict)


def render_form(
    schema: dict[str, Params] | Callable,
    initial_data: dict[str, Any] | None = None,
):
    def _render_form(
        data: dict[str, Any] | None = None,
        check_errors=False,
    ):
        if data is None:
            data = {}
        else:
            data = data.copy()
        errors_occured = False

        ret = '<form method="post">'
        for key, params in schema.items():
            name = params.name
            input_type = params.input_type
            args = params.args.copy()
            default = None
            validator = params.validator

            annotation = None
            real_type = None

            # If the default value is a Typer parameter information, parse it
            if isinstance(input_type, typer.models.ParamMeta):
                annotation = get_origin(input_type.annotation) or input_type.annotation
                types_list = get_args(input_type.annotation)
                real_type = types_list[0] if types_list else annotation
                args["type"] = "text"
                default = getattr(input_type.default, "default", input_type.default)
                validator = validator or getattr(input_type.annotation, "parser", None) or real_type

                # Try to get the type from the annotation
                types = {
                    float: "number",
                    int: "number",
                    bool: "checkbox",
                    list: "textarea",
                }
                if real_type in types:
                    args["type"] = types.get(real_type, "")

                if issubclass(real_type, (io.TextIOWrapper, io.BufferedReader, io.BufferedWriter)):
                    args["type"] = "file"
                    if types_list:
                        args["multiple"] = ""

                # Try to parse the default value
                if isinstance(input_type.default, (typer.models.ArgumentInfo, typer.models.OptionInfo)):
                    if input_type.default.min:
                        args["min"] = str(input_type.default.min)
                        args["type"] = "number"
                    if input_type.default.max:
                        args["max"] = str(input_type.default.max)
                        args["type"] = "number"
                    if input_type.default.default is not None:
                        data.setdefault(key, input_type.default.default)
                    if input_type.default.default_factory is not None:
                        data.setdefault(key, input_type.default.default_factory())
                    if isinstance(input_type.default, typer.models.OptionInfo) and input_type.default.hide_input:
                        args["type"] = "password"
                elif input_type.default is input_type.empty:
                    default = ""
                    args["required"] = ""
            else:
                default = initial_data.get(key) if initial_data else None

            is_textarea = args["type"] == "textarea"
            data.setdefault(key, default)
            if is_textarea:
                data[key] = data[key].splitlines()

            if check_errors:
                errors = []

                if annotation is list:
                    data[key] = request.form.getlist(key) or request.files.getlist(key) or data[key]
                    if data[key] and isinstance(data[key], list):
                        if isinstance(data[key][0], FileStorage):
                            data[key] = [item.stream for item in data[key]]
                        if validator:
                            for i, item in enumerate(data[key]):
                                try:
                                    data[key][i] = validator(item)
                                except ValueError as err:
                                    errors.append(str(err))

                else:
                    data[key] = request.form.get(key) or request.files.get(key) or data[key]
                    if real_type is bool:
                        data[key] = key in request.form
                    if isinstance(data[key], FileStorage):
                        data[key] = data[key].stream
                    if validator and data[key]:
                        try:
                            data[key] = validator(data[key])
                        except ValueError as err:
                            errors.append(str(err))

                if errors:
                    errors_occured = True
                    ret += '<ul class="errors">'
                    for line in errors:
                        ret += f"<li>{escape(line)}</li>"
                    ret += "</ul>"

            ret += f'<p><label for="{key}">{escape(name)} :</label>'

            if is_textarea:
                ret += "<br>"
            else:
                ret += " "

            args["name"] = key
            args["id"] = key
            if is_textarea:
                data[key] = "\n".join(data[key])
            if data[key] and not is_textarea and args["type"] != "password":
                if isinstance(data[key], bool):
                    if data[key]:
                        args["checked"] = ""
                else:
                    args["value"] = str(data[key])
            ret += (
                ("<textarea " if is_textarea else "<input ")
                + "".join(f'{name}="{escape(value)}"' for name, value in args.items())
                + ">"
            )
            if is_textarea:
                ret += escape(data[key])
                ret += "</textarea>"
            ret += "</p>"

        ret += '<p><input type="submit" value="OK"></p>'
        ret += "</form>"
        return ret, data, errors_occured

    if callable(schema):
        from typer.utils import get_params_from_function

        params = get_params_from_function(schema)
        schema = {}
        for name, value in params.items():
            schema[name] = Params(value.name.replace("_", " ").capitalize(), value)

    if request.method == "POST":
        ret, data, errors_occured = _render_form(initial_data, True)
        if errors_occured:
            return ret

        return data

    return _render_form(initial_data)[0]
